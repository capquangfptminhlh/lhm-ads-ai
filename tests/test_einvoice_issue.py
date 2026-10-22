"""vendor_ledger einvoice-issue: gates, dormant no-write, recording.

The provider adapter's issue function is always mocked here; no network,
no real provider credentials. The ledger DB lives in tmp_path.
"""
import pytest

from tools import einvoice as e
from tools import vendor_ledger as v

DEVICE = 'a' * 32
NOW = 1_800_000_000  # fixed epoch: 2027-01-15
AMOUNT = 499000      # pilot price; round-trips exactly at 10% VAT

ENV = {'EINVOICE_PROVIDER': 'fake-provider',
       'EINVOICE_API_BASE': 'https://provider.example.invalid/api',
       'EINVOICE_API_KEY': 'key-1', 'EINVOICE_API_SECRET': 'secret-1',
       'EINVOICE_TEMPLATE_CODE': '1C24TAA', 'EINVOICE_SERIES': 'C24TAA'}

BUYER = {'buyer_name': 'Nguyễn Văn A', 'buyer_address': '1 Đường Láng, Hà Nội',
         'buyer_tax_code': None, 'buyer_email': 'a@example.com'}


@pytest.fixture
def db(tmp_path):
    conn = v.connect(tmp_path / 'ledger.sqlite3')
    yield conn
    conn.close()


def make_order(db, status='paid', buyer=BUYER, code=424242):
    v.register(db, 'KH001', DEVICE, now=NOW)
    order = v.create_payos_order(db, 'KH001', AMOUNT, now=NOW, order_code=code)
    with db:
        db.execute("UPDATE payment_orders SET status=? WHERE order_code=?",
                   (status, code))
        if buyer:
            cols = ', '.join(f'{k}=?' for k in buyer)
            db.execute(f'UPDATE payment_orders SET {cols} WHERE order_code=?',
                       (*buyer.values(), code))
    return order


def row(db, code=424242):
    return db.execute('SELECT * FROM payment_orders WHERE order_code=?',
                      (code,)).fetchone()


class FakeIssuer:
    """Stands in for einvoice.issue_invoice; records every call."""

    def __init__(self):
        self.calls = []

    def __call__(self, order, environ=None):
        self.calls.append(order)
        return {'invoice_no': '0000123', 'series': 'C24TAA',
                'issued_at': NOW + 3600}


def test_paid_only_gate(db):
    make_order(db, status='pending')
    issuer = FakeIssuer()
    with pytest.raises(ValueError, match="trạng thái 'paid'"):
        v.issue_einvoice(db, 424242, environ=ENV, issue_fn=issuer)
    with db:
        db.execute("UPDATE payment_orders SET status='cancelled' "
                   'WHERE order_code=424242')
    with pytest.raises(ValueError, match="trạng thái 'paid'"):
        v.issue_einvoice(db, 424242, environ=ENV, issue_fn=issuer)
    assert issuer.calls == []
    assert row(db)['invoice_no'] is None


def test_unknown_order_rejected(db):
    with pytest.raises(ValueError, match='Không tìm thấy đơn'):
        v.issue_einvoice(db, 999999, environ=ENV, issue_fn=FakeIssuer())


def test_missing_buyer_fields_listed_and_nothing_changes(db):
    make_order(db, buyer=None)
    issuer = FakeIssuer()
    with pytest.raises(ValueError) as excinfo:
        v.issue_einvoice(db, 424242, environ=ENV, issue_fn=issuer)
    message = str(excinfo.value)
    assert 'buyer_name' in message and 'buyer_address' in message
    assert issuer.calls == []
    assert row(db)['invoice_no'] is None
    # Partially provided: only the still-missing field is listed.
    with db:
        db.execute("UPDATE payment_orders SET buyer_name='Nguyễn Văn A' "
                   'WHERE order_code=424242')
    with pytest.raises(ValueError) as excinfo:
        v.issue_einvoice(db, 424242, environ=ENV, issue_fn=issuer)
    assert 'buyer_address' in str(excinfo.value)
    assert 'buyer_name (' not in str(excinfo.value)
    assert row(db)['invoice_no'] is None


def test_dormant_records_nothing_and_never_calls_provider(db):
    make_order(db)  # paid, buyer complete
    issuer = FakeIssuer()
    with pytest.raises(e.EinvoiceNotConfigured, match='chưa được kích hoạt'):
        v.issue_einvoice(db, 424242, environ={}, issue_fn=issuer)
    assert issuer.calls == []
    result = row(db)
    assert result['invoice_no'] is None
    assert result['invoice_series'] is None
    assert result['invoice_issued_at'] is None


def test_success_records_invoice_fields(db):
    make_order(db)
    issuer = FakeIssuer()
    result = v.issue_einvoice(db, 424242, environ=ENV, issue_fn=issuer)
    assert result == {'order_code': 424242, 'customer_ref': 'KH001',
                      'amount': AMOUNT, 'invoice_no': '0000123',
                      'invoice_series': 'C24TAA',
                      'invoice_issued_at': NOW + 3600}
    stored = row(db)
    assert stored['invoice_no'] == '0000123'
    assert stored['invoice_series'] == 'C24TAA'
    assert stored['invoice_issued_at'] == NOW + 3600
    # The payload handed to the provider is built from the order, and the
    # ledger amount is the VAT-inclusive total the adapter must verify.
    (order,) = issuer.calls
    assert order['order_ref'] == '424242'
    assert order['buyer_name'] == BUYER['buyer_name']
    assert order['buyer_address'] == BUYER['buyer_address']
    assert order['total_amount'] == AMOUNT
    assert order['items'][0]['quantity'] == 1
    payload = e.build_invoice_payload(order, ENV)
    assert payload['totalAmount'] == AMOUNT


def test_double_issue_is_a_clear_noop_error(db):
    make_order(db)
    issuer = FakeIssuer()
    v.issue_einvoice(db, 424242, environ=ENV, issue_fn=issuer)
    with pytest.raises(ValueError, match='đã có hóa đơn số 0000123'):
        v.issue_einvoice(db, 424242, environ=ENV, issue_fn=issuer)
    assert len(issuer.calls) == 1  # provider never called a second time
    assert row(db)['invoice_no'] == '0000123'


def test_adapter_issue_invoice_with_fake_transport():
    order = {'order_ref': '424242', 'buyer_name': 'Nguyễn Văn A',
             'buyer_address': 'Hà Nội', 'total_amount': AMOUNT,
             'items': [{'name': 'LHM Ads AI KH001', 'quantity': 1,
                        'unit_price': 453636}], 'vat_rate': 10}
    seen = {}

    def transport(method, url, headers, body):
        seen.update(method=method, url=url, headers=headers, body=body)
        return {'data': {'invoiceNo': '0000456', 'status': 'ISSUED',
                         'issuedAt': NOW + 60}}

    result = e.issue_invoice(order, environ=ENV, transport=transport)
    assert result == {'invoice_no': '0000456', 'series': 'C24TAA',
                      'issued_at': NOW + 60}
    assert seen['url'] == ENV['EINVOICE_API_BASE'] + '/invoices'
    assert seen['body']['signature']  # request was signed before sending
    # A response without an invoice number can never be recorded.
    with pytest.raises(e.EinvoiceError, match='số hóa đơn'):
        e.issue_invoice(order, environ=ENV,
                        transport=lambda *a: {'data': {'status': 'ISSUED'}})
    with pytest.raises(e.EinvoiceError, match='chưa xác nhận phát hành'):
        e.issue_invoice(order, environ=ENV,
                        transport=lambda *a: {'data': {'invoiceNo': '1',
                                                       'status': 'DRAFT'}})


def test_adapter_issue_invoice_dormant_sends_nothing():
    calls = []
    with pytest.raises(e.EinvoiceNotConfigured):
        e.issue_invoice({'order_ref': '1'}, environ={},
                        transport=lambda *a: calls.append(a))
    assert calls == []


def test_cli_dormant_exits_nonzero_and_writes_nothing(db, tmp_path, capsys,
                                                      monkeypatch):
    for key in ENV:
        monkeypatch.delenv(key, raising=False)
    db_path = tmp_path / 'ledger.sqlite3'
    make_order(db)
    db.close()
    with pytest.raises(SystemExit) as excinfo:
        v.main(['--db', str(db_path), 'einvoice-issue', '--order', '424242'])
    assert excinfo.value.code != 0
    assert 'chưa được kích hoạt' in capsys.readouterr().err
    check = v.connect(db_path)
    try:
        assert check.execute('SELECT invoice_no FROM payment_orders '
                             'WHERE order_code=424242').fetchone()[0] is None
    finally:
        check.close()
