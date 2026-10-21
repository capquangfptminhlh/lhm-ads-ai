"""E-invoice dormant adapter: config gate, payload validation, signatures.

Fully offline: no network, no real provider credentials. The adapter must
stay OFF (typed EinvoiceNotConfigured, clear Vietnamese message) until the
seller signs a provider contract and sets the EINVOICE_* environment, it
must fail closed on any inconsistent order, and it must contain no
hard-coded provider endpoint.
"""
from pathlib import Path

import pytest

from tools import einvoice as e

SECRET = "test-api-secret"
ENV = {"EINVOICE_PROVIDER": "generic-provider",
       "EINVOICE_API_BASE": "https://invoice.example.test/api",
       "EINVOICE_API_KEY": "key-1", "EINVOICE_API_SECRET": SECRET,
       "EINVOICE_TEMPLATE_CODE": "1/001", "EINVOICE_SERIES": "K26TAA"}

ORDER = {
    "order_ref": "KH001-20261021-001",
    "buyer_name": "Công ty TNHH Ví Dụ",
    "buyer_tax_code": "0101234567",
    "buyer_address": "Số 1 Đường Mẫu, Quận 1, TP.HCM",
    "buyer_email": "ketoan@example.test",
    "items": [
        {"name": "LHM Ads AI — gói tháng", "quantity": 1, "unit_price": 1000000},
        {"name": "Phí triển khai", "quantity": 2, "unit_price": 500000},
    ],
    "vat_rate": 10,
    "total_amount": 2200000,
}


def test_dormant_until_provider_contract_exists():
    assert e.is_configured({}) is False
    with pytest.raises(e.EinvoiceNotConfigured, match="EINVOICE_PROVIDER"):
        e.load_config({})
    # Building anything while dormant raises the same typed error.
    with pytest.raises(e.EinvoiceNotConfigured):
        e.build_invoice_payload(ORDER, environ={})
    with pytest.raises(e.EinvoiceNotConfigured):
        e.build_create_request(ORDER, environ={})


def test_partial_config_names_what_is_missing():
    partial = {"EINVOICE_PROVIDER": "x", "EINVOICE_API_BASE": "https://h.test"}
    with pytest.raises(e.EinvoiceNotConfigured) as excinfo:
        e.load_config(partial)
    message = str(excinfo.value)
    assert "EINVOICE_API_KEY" in message and "EINVOICE_SERIES" in message
    assert "EINVOICE_PROVIDER" not in message.split(": thiếu ")[1]


def test_no_provider_endpoint_is_hard_coded():
    # Provider NAMES may appear in prose (which providers fit the shape);
    # what must never appear is a URL/host or any network library — the
    # base URL comes only from the seller's EINVOICE_API_BASE.
    source = Path(e.__file__).read_text(encoding="utf-8")
    assert "import urllib" not in source and "import requests" not in source
    for host_hint in ("http://", "https://", ".vn/", "api.", "www."):
        assert host_hint not in source.lower(), host_hint


def test_valid_payload_totals_and_shape():
    payload = e.build_invoice_payload(ORDER, environ=ENV)
    assert payload["provider"] == "generic-provider"
    assert payload["templateCode"] == "1/001"
    assert payload["series"] == "K26TAA"
    assert payload["orderRef"] == "KH001-20261021-001"
    assert payload["currency"] == "VND"
    assert payload["buyer"] == {"name": "Công ty TNHH Ví Dụ",
                                "taxCode": "0101234567",
                                "address": "Số 1 Đường Mẫu, Quận 1, TP.HCM",
                                "email": "ketoan@example.test"}
    assert payload["items"][0]["amount"] == 1000000
    assert payload["items"][1]["amount"] == 1000000
    assert payload["totalBeforeVat"] == 2000000
    assert payload["vatRate"] == 10
    assert payload["vatAmount"] == 200000
    assert payload["totalAmount"] == 2200000
    for amount in (payload["totalBeforeVat"], payload["vatAmount"],
                   payload["totalAmount"]):
        assert isinstance(amount, int)


def test_vat_rounding_is_half_up_on_integers():
    order = dict(ORDER, items=[{"name": "X", "quantity": 1, "unit_price": 155}],
                 vat_rate=10, total_amount=171)  # 15.5 -> 16
    payload = e.build_invoice_payload(order, environ=ENV)
    assert payload["vatAmount"] == 16 and payload["totalAmount"] == 171


def test_individual_buyer_without_tax_code_is_allowed():
    order = dict(ORDER)
    order.pop("buyer_tax_code")
    order.pop("total_amount")
    payload = e.build_invoice_payload(order, environ=ENV)
    assert "taxCode" not in payload["buyer"]


@pytest.mark.parametrize("tax_code", ["0101234567", "0101234567001",
                                      "0101234567-001"])
def test_tax_code_formats_accepted(tax_code):
    order = dict(ORDER, buyer_tax_code=tax_code)
    payload = e.build_invoice_payload(order, environ=ENV)
    assert payload["buyer"]["taxCode"] == tax_code


@pytest.mark.parametrize("patch, match", [
    ({"buyer_name": "  "}, "buyer_name"),
    ({"buyer_address": ""}, "buyer_address"),
    ({"order_ref": ""}, "order_ref"),
    ({"buyer_tax_code": "12345"}, "Mã số thuế"),
    ({"buyer_tax_code": "01012345678"}, "Mã số thuế"),
    ({"items": []}, "items"),
    ({"items": [{"name": "X", "quantity": 0, "unit_price": 1}]}, "quantity"),
    ({"items": [{"name": "X", "quantity": 1, "unit_price": -5}]}, "không được âm"),
    ({"items": [{"name": "X", "quantity": 1, "unit_price": 99.5}]}, "số nguyên"),
    ({"items": [{"name": " ", "quantity": 1, "unit_price": 1}]}, "thiếu tên"),
    ({"vat_rate": 7}, "vat_rate"),
    ({"vat_rate": 10.0}, "vat_rate"),
])
def test_invalid_orders_fail_closed(patch, match):
    order = dict(ORDER)
    order.update(patch)
    with pytest.raises(e.EinvoiceError, match=match):
        e.build_invoice_payload(order, environ=ENV)


def test_total_mismatch_fails_closed():
    order = dict(ORDER, total_amount=2000000)  # forgets the VAT
    with pytest.raises(e.EinvoiceError, match="không khớp"):
        e.build_invoice_payload(order, environ=ENV)
    # Without a claimed total the computed one is used.
    order = dict(ORDER)
    order.pop("total_amount")
    assert e.build_invoice_payload(order, environ=ENV)["totalAmount"] == 2200000


def test_zero_total_invoice_is_rejected():
    order = dict(ORDER, items=[{"name": "Free", "quantity": 1, "unit_price": 0}],
                 total_amount=0)
    with pytest.raises(e.EinvoiceError, match="lớn hơn 0"):
        e.build_invoice_payload(order, environ=ENV)


def test_sign_and_verify_roundtrip():
    payload = e.build_invoice_payload(ORDER, environ=ENV)
    signature = e.sign_payload(payload, SECRET)
    assert e.verify_webhook_signature(payload, signature, SECRET) is True
    # Key order in the source dict must not matter (canonical sorting).
    shuffled = dict(reversed(list(payload.items())))
    assert e.sign_payload(shuffled, SECRET) == signature
    # Uppercased hex from a provider is still accepted.
    assert e.verify_webhook_signature(payload, signature.upper(), SECRET) is True


def test_verify_rejects_tampering_and_garbage():
    payload = e.build_invoice_payload(ORDER, environ=ENV)
    signature = e.sign_payload(payload, SECRET)
    tampered = dict(payload, totalAmount=1)
    assert e.verify_webhook_signature(tampered, signature, SECRET) is False
    assert e.verify_webhook_signature(payload, "0" * 64, SECRET) is False
    assert e.verify_webhook_signature(payload, signature, "other-secret") is False
    assert e.verify_webhook_signature(payload, None, SECRET) is False
    assert e.verify_webhook_signature(payload, "", SECRET) is False
    assert e.verify_webhook_signature("not-a-dict", signature, SECRET) is False


def test_build_create_request_is_signed_and_uses_env_base_only():
    request = e.build_create_request(ORDER, environ=ENV)
    assert request["method"] == "POST"
    assert request["url"] == "https://invoice.example.test/api" + e.CREATE_PATH
    assert request["headers"]["x-api-key"] == "key-1"
    body = request["body"]
    signature = body.pop("signature")
    assert signature == e.sign_payload(body, SECRET)
    assert e.verify_webhook_signature(body, signature, SECRET) is True


@pytest.mark.parametrize("status", ["ISSUED", "signed", "Success", "COMPLETED"])
def test_parse_webhook_accepts_only_issued_states(status):
    result = e.parse_webhook({"invoiceNo": "0000123", "status": status,
                              "orderRef": "KH001-20261021-001"})
    assert result == {"invoice_no": "0000123", "status": "issued",
                      "order_ref": "KH001-20261021-001"}
    nested = e.parse_webhook({"data": {"invoice_no": "9", "state": status,
                                       "orderCode": 777}})
    assert nested["invoice_no"] == "9" and nested["order_ref"] == "777"


@pytest.mark.parametrize("payload", [
    {"invoiceNo": "1", "status": "PENDING", "orderRef": "X"},
    {"invoiceNo": "1", "status": "DRAFT", "orderRef": "X"},
    {"invoiceNo": "1", "status": "FAILED", "orderRef": "X"},
    {"invoiceNo": "1", "status": "", "orderRef": "X"},
    {"status": "ISSUED", "orderRef": "X"},          # no invoice number
    {"invoiceNo": "1", "status": "ISSUED"},          # no order reference
    {"invoiceNo": " ", "status": "ISSUED", "orderRef": "X"},
    "not-a-dict",
])
def test_parse_webhook_rejects_everything_else(payload):
    with pytest.raises(e.EinvoiceError):
        e.parse_webhook(payload)
