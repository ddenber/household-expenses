import json

import pytest

from app.services.ocr.extractor import validate
from app.services.ocr.providers import AzureDocumentProvider, azure_to_extraction

RECEIPT = {
    "MerchantName": {"valueString": "Konad Market", "confidence": 0.97},
    "TransactionDate": {"valueDate": "2026-03-05", "confidence": 0.95},
    "Total": {"valueCurrency": {"amount": 12.5, "currencyCode": "EUR"}, "confidence": 0.99},
    "TotalTax": {"valueCurrency": {"amount": 2.08, "currencyCode": "EUR"}, "confidence": 0.9},
}


class Resp:
    def __init__(self, code, body=None, headers=None):
        self.status_code, self._b, self.headers = code, body or {}, headers or {}

    def json(self):
        return self._b

    def raise_for_status(self):
        assert self.status_code < 400


class FakeHttp:
    def __init__(self, fields):
        self.fields = fields
        self.posted = None

    def post(self, url, data, headers, timeout):
        self.posted = (url, headers)
        return Resp(202, headers={"Operation-Location": "https://x/op/1"})

    def get(self, url, headers, timeout):
        return Resp(200, {"status": "succeeded", "analyzeResult": {
            "content": "KONAD", "documents": [{"confidence": 0.96, "fields": self.fields}]}})


def test_mapping_is_schema_valid_and_complete():
    r = azure_to_extraction(RECEIPT, "prebuilt-receipt")
    validate(r)
    assert (r["supplier"]["value"], r["date"]["value"], r["total"]["value"], r["vat"]["value"], r["currency"]["value"]) == (
        "Konad Market", "2026-03-05", "12.50", "2.08", "EUR")


def test_missing_fields_are_null_not_invented():
    r = azure_to_extraction({}, "prebuilt-receipt")
    validate(r)
    assert r["total"]["value"] is None and r["supplier"]["confidence"] == 0


def test_invoice_model_field_names():
    r = azure_to_extraction({"VendorName": {"valueString": "ACME", "confidence": 0.9},
                             "InvoiceTotal": {"valueCurrency": {"amount": 100, "currencyCode": "EUR"}, "confidence": 0.9}},
                            "prebuilt-invoice")
    assert r["supplier"]["value"] == "ACME" and r["total"]["value"] == "100.00"


def test_provider_flow_and_requires_credentials():
    http = FakeHttp(RECEIPT)
    p = AzureDocumentProvider("https://e.example/", "k", "prebuilt-receipt", http)
    out = p.extract_text(b"img", "image/jpeg")
    assert out.fields["total"]["value"] == "12.50" and "prebuilt-receipt:analyze" in http.posted[0]
    assert http.posted[1]["Ocp-Apim-Subscription-Key"] == "k"
    with pytest.raises(RuntimeError):
        AzureDocumentProvider("", "", "prebuilt-receipt", http)


def test_rapidocr_rows_join_label_and_amount():
    from app.services.ocr.providers import _rows_from_boxes
    box = lambda x, y: [[x, y], [x + 80, y], [x + 80, y + 20], [x, y + 20]]
    items = [(box(300, 52), "3.70 EUR", 0.9), (box(10, 50), "TOTALI", 0.9), (box(10, 10), "BIM MARKET", 0.9)]
    assert _rows_from_boxes(items).splitlines() == ["BIM MARKET", "TOTALI  3.70 EUR"]
