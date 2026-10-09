# OCR pipeline

```
upload (API, returns 202) -> store original + sha256 -> enqueue job (Redis/RQ)
worker: load file -> provider.extract_text -> extractor.parse -> validate vs JSON schema v1
      -> persist ocr_results (text, extraction, confidence, provider, error) -> expense: processing -> needs_review
```
OCR **suggests**; it never approves, submits, or posts. There is no code path from `services/ocr` to `services/ledger`.

## Providers (`services/ocr/providers.py`)
| Provider | Real? | Notes |
|---|---|---|
| `rapidocr` | **Real** local OCR (PaddleOCR models on ONNX), free, no key; default | Much better than Tesseract on phone photos; boxes are regrouped into lines before parsing. |
| `tesseract` (setting `tesseract`/`auto` use RapidOCR when installed, Tesseract otherwise) | **Real** local OCR (pytesseract + Tesseract 5, `eng+sqi`) | Images; PDFs rendered with PyMuPDF (embedded text used when present). |
| `azure_document` | **Real**, managed (Azure AI Document Intelligence `prebuilt-receipt` / `prebuilt-invoice`) | Returns supplier, date, total, VAT, currency as typed fields with confidence, so no heuristic parsing. Sends the document to Azure (external, paid): needs `AZURE_DI_ENDPOINT`, `AZURE_DI_KEY`, optional `AZURE_DI_MODEL`. |
| `simulated` | **Simulated** | Deterministic fake text for tests/demos; results are stored with `provider_real=false` and the UI labels them "Simuluar". |
| `none` | – | Skips OCR; expense goes to `needs_review` for manual entry. |
Select with `OCR_PROVIDER`. A cloud provider can be added by implementing `OcrProvider.extract_text` (external cost -> needs owner approval).

## Extraction
`extractor.py` is a **heuristic, rule-based parser** (not an AI model): finds supplier (first meaningful line), date, total (keyword lines "TOTAL/SHUMA/GJITHSEJ"), VAT, currency. Each field has confidence 0..1. A total is only returned if a keyword-labelled amount parses; otherwise `null` – totals are **never invented or inferred by summing**. Output validated against `schemas/receipt_extraction.v1.json` (`schema_version` stored). Invalid output is stored as an error, not posted.

## Human confirmation
Fields below `OCR_CONFIDENCE_THRESHOLD` (0.8) set `expense.ocr_needs_confirmation`; submitting then requires explicit `confirm_low_confidence=true`. Every user change vs extraction is stored in `ocr_corrections`.

## Failure handling
Failed OCR stores `error`, sets `ocr_status=failed`, keeps the document, moves the expense to `needs_review` for manual entry; `POST /expenses/{id}/ocr/retry` re-enqueues. Jobs are idempotent (re-running replaces nothing; appends a new result row).
