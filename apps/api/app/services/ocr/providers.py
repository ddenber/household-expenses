import io
import os
from dataclasses import dataclass
from decimal import Decimal

from ...config import get_settings


@dataclass
class OcrText:
    text: str
    confidence: float | None  # mean engine confidence 0..1, None if unknown
    fields: dict | None = None  # provider-structured extraction (schema v1); skips heuristic parsing


class OcrProvider:
    name = "base"
    real = False

    def extract_text(self, data: bytes, mime: str) -> OcrText:
        raise NotImplementedError


class TesseractProvider(OcrProvider):
    """REAL local OCR using Tesseract."""
    name = "tesseract"
    real = True

    @staticmethod
    def _prep(im):
        from PIL import Image, ImageOps
        im = ImageOps.autocontrast(ImageOps.grayscale(im))
        if max(im.size) < 1800:
            f = 1800 / max(im.size)
            im = im.resize((int(im.width * f), int(im.height * f)), Image.LANCZOS)
        return im

    def _image_text(self, im):
        import pytesseract
        im = self._prep(im)
        langs = os.environ.get("TESSERACT_LANGS", "eng+sqi")
        cfg = "--psm 6"
        d = pytesseract.image_to_data(im, lang=langs, config=cfg, output_type=pytesseract.Output.DICT)
        words = [(t, float(c)) for t, c in zip(d["text"], d["conf"]) if t.strip() and float(c) >= 0]
        text = pytesseract.image_to_string(im, lang=langs, config=cfg)
        conf = (sum(c for _, c in words) / len(words) / 100) if words else 0.0
        return text, conf

    def extract_text(self, data, mime):
        from PIL import Image, ImageOps
        if mime == "application/pdf":
            import fitz
            texts, confs = [], []
            with fitz.open(stream=data, filetype="pdf") as doc:
                for page in doc:
                    embedded = page.get_text().strip()
                    if len(embedded) > 20:
                        texts.append(embedded)
                        confs.append(0.95)
                        continue
                    pix = page.get_pixmap(dpi=200)
                    im = Image.open(io.BytesIO(pix.tobytes("png")))
                    t, c = self._image_text(im)
                    texts.append(t)
                    confs.append(c)
            return OcrText("\n".join(texts), sum(confs) / len(confs) if confs else None)
        if mime == "image/heic":
            import pillow_heif
            pillow_heif.register_heif_opener()
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        t, c = self._image_text(im)
        return OcrText(t, c)


class SimulatedProvider(OcrProvider):
    """SIMULATED: returns fixed text and never reads the image. For tests/demos only."""
    name = "simulated"
    real = False

    def extract_text(self, data, mime):
        text = os.environ.get("SIM_OCR_TEXT") or "SIMULATED MARKET SH.P.K\nData: 12/03/2026\nQumesht 2.50\nTOTAL 12.50 EUR\n"
        return OcrText(text.replace("\\n", "\n"), 0.95)


def _rows_from_boxes(items) -> str:
    """Rebuild reading-order lines from detected boxes so 'Qumesht ... 2.50' stays on one line."""
    boxes = []
    for box, text, conf in items:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        boxes.append((sum(ys) / 4, max(ys) - min(ys), min(xs), text, float(conf)))
    boxes.sort()
    rows, cur, cy, ch = [], [], None, 0
    for b in boxes:
        if cur and abs(b[0] - cy) > max(ch, b[1]) * 0.6:
            rows.append(cur)
            cur = []
        if not cur:
            cy, ch = b[0], b[1]
        cur.append(b)
    if cur:
        rows.append(cur)
    return "\n".join("  ".join(t for _, _, _, t, _ in sorted(r, key=lambda b: b[2])) for r in rows)


class RapidOcrProvider(OcrProvider):
    """REAL local OCR (PaddleOCR models via ONNX). Free, no API key, much better than Tesseract on phone photos."""
    name = "rapidocr"
    real = True
    _engine = None

    def _run(self, im):
        import numpy as np
        if RapidOcrProvider._engine is None:
            from rapidocr_onnxruntime import RapidOCR
            RapidOcrProvider._engine = RapidOCR()
        res, _ = RapidOcrProvider._engine(np.array(im))
        res = res or []
        conf = sum(float(r[2]) for r in res) / len(res) if res else 0.0
        return _rows_from_boxes(res), conf

    def extract_text(self, data, mime):
        from PIL import Image, ImageOps
        if mime == "application/pdf":
            import fitz
            texts, confs = [], []
            with fitz.open(stream=data, filetype="pdf") as doc:
                for page in doc:
                    embedded = page.get_text().strip()
                    if len(embedded) > 20:
                        texts.append(embedded)
                        confs.append(0.95)
                        continue
                    im = Image.open(io.BytesIO(page.get_pixmap(dpi=200).tobytes("png"))).convert("RGB")
                    t, c = self._run(im)
                    texts.append(t)
                    confs.append(c)
            return OcrText("\n".join(texts), sum(confs) / len(confs) if confs else None)
        if mime == "image/heic":
            import pillow_heif
            pillow_heif.register_heif_opener()
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        t, c = self._run(im)
        return OcrText(t, c)


class AzureDocumentProvider(OcrProvider):
    """REAL managed document-understanding service (Azure AI Document Intelligence).

    Uses the prebuilt receipt/invoice model, which returns merchant, date, total, tax and
    currency as typed fields with per-field confidence. Sends the document to Azure (external).
    """
    name = "azure_document"
    real = True

    def __init__(self, endpoint=None, key=None, model=None, session=None):
        st = get_settings()
        self.endpoint = (endpoint or st.azure_di_endpoint).rstrip("/")
        self.key = key or st.azure_di_key
        self.model = model or st.azure_di_model
        if not self.endpoint or not self.key:
            raise RuntimeError("AZURE_DI_ENDPOINT and AZURE_DI_KEY are required for the azure_document provider")
        if self.model not in ("prebuilt-receipt", "prebuilt-invoice"):
            raise RuntimeError("AZURE_DI_MODEL must be prebuilt-receipt or prebuilt-invoice")
        import requests
        self.http = session or requests.Session()

    def _analyze(self, data: bytes) -> dict:
        import time
        url = f"{self.endpoint}/documentintelligence/documentModels/{self.model}:analyze?api-version=2024-11-30"
        headers = {"Ocp-Apim-Subscription-Key": self.key}
        r = self.http.post(url, data=data, headers={**headers, "Content-Type": "application/octet-stream"}, timeout=30)
        if r.status_code != 202:
            raise RuntimeError(f"azure analyze rejected: HTTP {r.status_code}")
        op = r.headers["Operation-Location"]
        for _ in range(40):
            g = self.http.get(op, headers=headers, timeout=30)
            g.raise_for_status()
            body = g.json()
            if body["status"] == "succeeded":
                return body["analyzeResult"]
            if body["status"] == "failed":
                raise RuntimeError("azure analysis failed")
            time.sleep(1.5)
        raise RuntimeError("azure analysis timed out")

    def extract_text(self, data, mime):
        result = self._analyze(data)
        docs = result.get("documents") or []
        fields = docs[0].get("fields", {}) if docs else {}
        return OcrText(result.get("content", ""), docs[0].get("confidence") if docs else None,
                       azure_to_extraction(fields, self.model))


def azure_to_extraction(fields: dict, model: str) -> dict:
    inv = model == "prebuilt-invoice"
    keys = ("VendorName", "InvoiceDate", "InvoiceTotal", "TotalTax") if inv else ("MerchantName", "TransactionDate", "Total", "TotalTax")

    def conf(f):
        return round(float(f.get("confidence") or 0), 3) if f else 0.0

    def money(f):
        v = (f or {}).get("valueCurrency") or {}
        amt = v.get("amount")
        if amt is None or float(amt) <= 0:
            return None, v.get("currencyCode")
        return format(Decimal(str(amt)).quantize(Decimal("0.01")), "f"), v.get("currencyCode")

    name_f, date_f, total_f, tax_f = (fields.get(k) for k in keys)
    total, cur = money(total_f)
    vat, cur2 = money(tax_f)
    cur = cur or cur2
    name = (name_f or {}).get("valueString") or (name_f or {}).get("content")
    d = (date_f or {}).get("valueDate")
    return {
        "schema_version": "v1",
        "supplier": {"value": name[:200] if name else None, "confidence": conf(name_f) if name else 0.0},
        "date": {"value": d, "confidence": conf(date_f) if d else 0.0},
        "total": {"value": total, "confidence": conf(total_f) if total else 0.0},
        "vat": {"value": vat, "confidence": conf(tax_f) if vat else 0.0},
        "currency": {"value": cur if cur and len(cur) == 3 else None, "confidence": conf(total_f) if cur else 0.0},
    }


def get_provider(name: str | None = None) -> OcrProvider | None:
    name = name or get_settings().ocr_provider
    if name in ("tesseract", "auto"):
        # Tesseract reads phone photos poorly; prefer RapidOCR whenever it is installed.
        try:
            import rapidocr_onnxruntime  # noqa: F401
            return RapidOcrProvider()
        except ImportError:
            return TesseractProvider()
    if name == "rapidocr":
        return RapidOcrProvider()
    if name == "azure_document":
        return AzureDocumentProvider()
    if name == "simulated":
        return SimulatedProvider()
    return None
