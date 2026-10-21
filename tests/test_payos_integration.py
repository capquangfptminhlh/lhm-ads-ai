"""PayOS dormant integration: signatures, webhook verification, ledger orders.

No network and no real merchant keys: transports are injected fakes, webhook
payloads are signed with a test checksum key. The integration must stay OFF
(clear error) until the seller configures their own merchant credentials,
and a verified webhook may only mark an order paid — never issue a license.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from tools import payos as p
from tools import vendor_ledger as v

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "payos_webhook_server", ROOT / "tools" / "payos_webhook_server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

KEY = "test-checksum-key"
ENV = {"PAYOS_CLIENT_ID": "client-1", "PAYOS_API_KEY": "api-1",
       "PAYOS_CHECKSUM_KEY": KEY,
       "PAYOS_RETURN_URL": "https://seller.example/payos/return",
       "PAYOS_CANCEL_URL": "https://seller.example/payos/cancel"}
NOW = 1_800_000_000


@pytest.fixture
def db(tmp_path):
    conn = v.connect(tmp_path / "vendor.sqlite3")
    v.register(conn, "KH001", "a" * 32, now=NOW)
    yield conn
    conn.close()


def _webhook_payload(order_code, amount, key=KEY, **overrides):
    data = {"orderCode": order_code, "amount": amount,
            "description": "LHM Ads AI KH001", "accountNumber": "0000",
            "reference": "FT123456", "transactionDateTime": "2030-01-01 00:00:00",
            "currency": "VND", "paymentLinkId": "pl-1", "code": "00",
            "desc": "success", "counterAccountBankId": "",
            "counterAccountBankName": "", "counterAccountName": "",
            "counterAccountNumber": "", "virtualAccountName": "",
            "virtualAccountNumber": ""}
    data.update(overrides)
    return {"code": "00", "desc": "success", "success": True,
            "data": data, "signature": p.sign(data, key)}


def test_dormant_until_merchant_keys_exist(db):
    assert p.is_configured({}) is False
    with pytest.raises(p.PayosNotConfigured, match="PAYOS_CLIENT_ID"):
        p.load_config({})
    with pytest.raises(p.PayosNotConfigured):
        v.create_payos_link(db, "KH001", 299000, environ={})
    # Dormant attempt must not create a half-finished order.
    assert v.payments(db) == []


def test_create_link_signs_request_and_records_order(db):
    captured = {}

    def transport(method, url, headers, body):
        captured.update(method=method, url=url, headers=headers, body=body)
        return {"code": "00", "desc": "success",
                "data": {"checkoutUrl": "https://pay.payos.vn/web/abc",
                         "paymentLinkId": "pl-1", "qrCode": "qr",
                         "orderCode": body["orderCode"], "amount": body["amount"],
                         "status": "PENDING"}}

    result = v.create_payos_link(db, "KH001", 299000, environ=ENV,
                                 transport=transport, now=NOW)
    assert result["checkout_url"] == "https://pay.payos.vn/web/abc"
    body = captured["body"]
    assert captured["headers"]["x-client-id"] == "client-1"
    assert body["signature"] == p.sign(
        {"amount": 299000, "cancelUrl": ENV["PAYOS_CANCEL_URL"],
         "description": body["description"], "orderCode": body["orderCode"],
         "returnUrl": ENV["PAYOS_RETURN_URL"]}, KEY)
    (order,) = v.payments(db)
    assert order["status"] == "pending"
    assert order["payment_link_id"] == "pl-1"


def test_webhook_marks_paid_once_and_never_issues_license(db):
    order = v.create_payos_order(db, "KH001", 299000, now=NOW, order_code=123456)
    payload = _webhook_payload(123456, 299000)
    result = v.apply_payos_webhook(db, payload, KEY, now=NOW + 60)
    assert result == {"order_code": 123456, "status": "paid",
                      "already_paid": False, "customer_ref": "KH001",
                      "amount": 299000}
    again = v.apply_payos_webhook(db, payload, KEY, now=NOW + 120)
    assert again["already_paid"] is True
    (row,) = v.payments(db)
    assert row["status"] == "paid" and row["reference"] == "FT123456"
    # Payment alone creates no license record whatsoever.
    assert db.execute("SELECT COUNT(*) c FROM licenses").fetchone()["c"] == 0
    assert order["status"] == "pending"  # original snapshot unchanged


def test_webhook_rejects_tampering_and_unknown_orders(db):
    v.create_payos_order(db, "KH001", 299000, now=NOW, order_code=777)
    bad_sig = _webhook_payload(777, 299000)
    bad_sig["signature"] = "0" * 64
    with pytest.raises(p.PayosError, match="signature"):
        v.apply_payos_webhook(db, bad_sig, KEY)
    wrong_amount = _webhook_payload(777, 1000)  # signed, but not our amount
    with pytest.raises(ValueError, match="amount"):
        v.apply_payos_webhook(db, wrong_amount, KEY)
    unknown = _webhook_payload(999999, 299000)
    with pytest.raises(ValueError, match="unknown order"):
        v.apply_payos_webhook(db, unknown, KEY)
    failed = _webhook_payload(777, 299000)
    failed["code"] = "01"
    failed["success"] = False
    with pytest.raises(p.PayosError, match="successful"):
        v.apply_payos_webhook(db, failed, KEY)
    (row,) = v.payments(db)
    assert row["status"] == "pending"


def test_webhook_server_roundtrip(tmp_path):
    db_path = tmp_path / "vendor.sqlite3"
    conn = v.connect(db_path)
    v.register(conn, "KH777", "d" * 32, now=NOW)
    v.create_payos_order(conn, "KH777", 100000, now=NOW, order_code=4242)
    conn.close()
    raw = json.dumps(_webhook_payload(4242, 100000)).encode()
    status, body = server.handle_webhook(db_path, raw, KEY)
    assert status == 200 and body["ok"] is True and body["status"] == "paid"
    status, body = server.handle_webhook(db_path, b"not-json", KEY)
    assert status == 400
    forged = _webhook_payload(4242, 100000)
    forged["data"]["amount"] = 1
    status, body = server.handle_webhook(
        db_path, json.dumps(forged).encode(), KEY)
    assert status in (400, 404) and body["ok"] is False
