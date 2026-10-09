"""Heuristic (rule-based, NOT AI) receipt field extraction. Never invents totals."""
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import jsonschema

SCHEMA = json.loads((Path(__file__).parent / "schemas" / "receipt_extraction.v1.json").read_text())
AMOUNT = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,\s]\d{3})*[.,]\d{2}|\d+[.,]\d{2})(?![\d])")
TOTAL_KW = re.compile(r"\b(total|totali|totale|shuma\s*totale|shuma|gjith[eë]sej|per\s*t[eë]\s*paguar|për\s*t[eë]\s*paguar|amount\s*due|grand\s*total)\b", re.I)
EXCLUDE_KW = re.compile(r"(sub\s*total|nentotal|nëntotal|tvsh|vat|tax|pa\s*tvsh|kusur|change|cash|pagesa|paid)", re.I)
VAT_KW = re.compile(r"\b(tvsh|vat|tax)\b", re.I)
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2})\b"), "dmy2"),
]


def parse_amount(s: str) -> Decimal | None:
    s = s.replace(" ", "")
    m = re.match(r"^(.*)[.,](\d{2})$", s)
    if not m:
        return None
    whole = re.sub(r"[.,]", "", m.group(1))
    try:
        return Decimal(f"{whole or '0'}.{m.group(2)}")
    except InvalidOperation:
        return None


def _dates(text: str) -> list[date]:
    out = []
    for rx, kind in DATE_PATTERNS:
        for m in rx.finditer(text):
            a, b, c = (int(x) for x in m.groups())
            try:
                if kind == "ymd":
                    d = date(a, b, c)
                elif kind == "dmy":
                    d = date(c, b, a)
                else:
                    d = date(2000 + c, b, a)
            except ValueError:
                continue
            if date(2000, 1, 1) <= d <= date.today():
                out.append(d)
    return out


NOISE_LINE = re.compile(r"(nipt|nuis|nui\b|fiskal|fatur|kupon|receipt|invoice|tel\b|tel[:.]|phone|www\.|https?:|@|\badres|rr\.|rruga|street|\bnr\b|\bid\b|arkatar|kasier|ora\b|data\b|artikuj|artikull|p[eë]rshkrim|sasi|[cç]mim|nj[eë]si|cmimi|item|qty|price|description|vlera|shuma)", re.I)


def _supplier_line(l: str) -> bool:
    letters = sum(ch.isalpha() for ch in l)
    digits = sum(ch.isdigit() for ch in l)
    return (letters >= 3 and letters / max(len(l), 1) > 0.5 and digits <= 3 and not _dates(l)
            and not TOTAL_KW.search(l) and not NOISE_LINE.search(l) and not AMOUNT.search(l))


def _clean_supplier(l: str) -> str:
    return re.sub(r"[^\w\s.&'\-/]", "", l).strip(" .-")[:200] or l[:200]


def extract(text: str, engine_conf: float | None = None) -> dict:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    scale = 1.0 if engine_conf is None else min(1.0, max(0.2, engine_conf / 0.8))

    supplier, sconf = None, 0.0
    for i, l in enumerate(lines[:8]):
        if _supplier_line(l):
            supplier, sconf = _clean_supplier(l), (0.6 if i < 3 else 0.45) * scale
            break

    ds = _dates(text)
    distinct = sorted(set(ds))
    d_val = distinct[0].isoformat() if len(distinct) == 1 else (ds[0].isoformat() if ds else None)
    d_conf = (0.85 if len(distinct) == 1 else 0.45) * scale if ds else 0.0

    cands: list[Decimal] = []
    for l in lines:
        if TOTAL_KW.search(l) and not EXCLUDE_KW.search(l):
            found = [parse_amount(m.group(1)) for m in AMOUNT.finditer(l)]
            found = [f for f in found if f is not None and f > 0]
            if found:
                cands.append(found[-1])
    total, tconf = None, 0.0
    if cands:
        total = cands[-1]
        tconf = (0.9 if len(set(cands)) == 1 else 0.5) * scale

    vat, vconf = None, 0.0
    for l in lines:
        if VAT_KW.search(l):
            found = [parse_amount(m.group(1)) for m in AMOUNT.finditer(l)]
            if found and found[-1] is not None and found[-1] > 0:
                vat, vconf = found[-1], 0.5 * scale
    cur, cconf = None, 0.0
    if re.search(r"€|\bEUR\b", text, re.I):
        cur, cconf = "EUR", 0.9 * scale
    elif re.search(r"\b(LEK|ALL)\b", text):
        cur, cconf = "ALL", 0.7 * scale

    result = {
        "schema_version": "v1",
        "supplier": {"value": supplier, "confidence": round(sconf, 3)},
        "date": {"value": d_val, "confidence": round(d_conf, 3)},
        "total": {"value": None if total is None else format(total, "f"), "confidence": round(tconf, 3)},
        "vat": {"value": None if vat is None else format(vat, "f"), "confidence": round(vconf, 3)},
        "currency": {"value": cur, "confidence": round(cconf, 3)},
    }
    jsonschema.validate(result, SCHEMA)
    return result


def validate(result: dict) -> None:
    jsonschema.validate(result, SCHEMA)
