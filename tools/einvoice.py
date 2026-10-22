"""E-invoice integration for the seller — dormant until configured.

The seller currently sells LHM Ads AI by manual bank transfer, confirmed
personally before a license is issued (see docs/PAYOS.md). Vietnamese law
requires an e-invoice (hóa đơn điện tử) for such sales, issued through a
licensed provider such as Viettel S-Invoice, VNPT Invoice or MISA
meInvoice. This module prepares that integration so it can be switched on
later WITHOUT code changes: when the seller signs a provider contract and
sets EINVOICE_PROVIDER, EINVOICE_API_BASE, EINVOICE_API_KEY,
EINVOICE_API_SECRET, EINVOICE_TEMPLATE_CODE and EINVOICE_SERIES on the
seller machine, invoice payloads can be built and signed.

Deliberate boundaries, mirroring the PayOS integration:
- There is NO provider endpoint hard-coded anywhere in this module. The
  base URL comes only from the seller's own EINVOICE_API_BASE, and this
  module performs no network I/O at all: `issue_invoice` builds, signs
  and validates, but sends only through a transport injected by the
  caller (the vendor ledger supplies the real HTTP transport on the
  seller machine). It refuses to run while unconfigured and is only
  invoked by an explicit seller command for an already-paid order.
- Configuration missing -> EinvoiceNotConfigured with a clear Vietnamese
  message, raised before anything is built. Nothing is ever sent while
  dormant.
- An invoice may only be issued for an order whose payment the seller has
  already confirmed in the vendor ledger (manual transfer confirmed, or a
  verified PayOS order in state `paid`). This module cannot check the
  ledger itself; the caller must pass a confirmed order only — see
  docs/EINVOICE.md.

Signing convention (same canonicalization as tools/payos.py): HMAC-SHA256
over the alphabetically sorted "key=value&..." string of the flattened
payload (null -> empty string; objects/arrays as JSON with sorted keys),
compared in constant time for webhooks.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time

# Path appended to the seller-provided EINVOICE_API_BASE when a create
# request is built. Only a path — never a host — lives in the source.
CREATE_PATH = '/invoices'

# VAT rates (percent) accepted for software subscription sales in Vietnam.
VAT_RATES = (0, 5, 8, 10)
DEFAULT_VAT_RATE = 10

# Provider webhook states that mean "the invoice was actually issued".
# Anything else (pending, draft, failed, unknown) is rejected so a caller
# can never mistake an in-progress state for an issued invoice.
ISSUED_STATES = ('ISSUED', 'SIGNED', 'SUCCESS', 'COMPLETED')


class EinvoiceNotConfigured(RuntimeError):
    """Raised when provider credentials are not set yet (integration dormant)."""


class EinvoiceError(RuntimeError):
    """Raised when an order cannot become an invoice or a webhook is invalid."""


def load_config(environ=None) -> dict:
    env = os.environ if environ is None else environ
    config = {
        'provider': env.get('EINVOICE_PROVIDER', '').strip(),
        'api_base': env.get('EINVOICE_API_BASE', '').strip().rstrip('/'),
        'api_key': env.get('EINVOICE_API_KEY', '').strip(),
        'api_secret': env.get('EINVOICE_API_SECRET', '').strip(),
        'template_code': env.get('EINVOICE_TEMPLATE_CODE', '').strip(),
        'series': env.get('EINVOICE_SERIES', '').strip(),
    }
    missing = [name for name, key in (('EINVOICE_PROVIDER', 'provider'),
                                      ('EINVOICE_API_BASE', 'api_base'),
                                      ('EINVOICE_API_KEY', 'api_key'),
                                      ('EINVOICE_API_SECRET', 'api_secret'),
                                      ('EINVOICE_TEMPLATE_CODE', 'template_code'),
                                      ('EINVOICE_SERIES', 'series'))
               if not config[key]]
    if missing:
        raise EinvoiceNotConfigured(
            'Hóa đơn điện tử chưa được kích hoạt: thiếu ' + ', '.join(missing) +
            ' trong môi trường máy bên bán. Cần ký hợp đồng với nhà cung cấp '
            'hóa đơn điện tử trước; hiện tại bên bán xuất hóa đơn ngoài hệ '
            'thống này nếu khách yêu cầu.')
    return config


def is_configured(environ=None) -> bool:
    try:
        load_config(environ)
        return True
    except EinvoiceNotConfigured:
        return False


def _flatten_value(value) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False)
    return str(value)


def data_string(fields: dict) -> str:
    """Canonical "a=1&b=2" string with alphabetically sorted keys."""
    return '&'.join(f'{key}={_flatten_value(fields[key])}' for key in sorted(fields))


def sign_payload(payload: dict, secret: str) -> str:
    """HMAC-SHA256 hex over the canonical string of `payload`."""
    return hmac.new(secret.encode('utf-8'),
                    data_string(payload).encode('utf-8'),
                    hashlib.sha256).hexdigest()


def verify_webhook_signature(payload: dict, signature, secret: str) -> bool:
    """Constant-time webhook signature check; False for any malformed input."""
    if not isinstance(payload, dict) or not isinstance(signature, str) \
            or not signature.strip():
        return False
    expected = sign_payload(payload, secret)
    return hmac.compare_digest(expected, signature.strip().lower())


def _require_text(order: dict, key: str) -> str:
    value = order.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EinvoiceError(f'Thiếu trường bắt buộc cho hóa đơn: {key}')
    return value.strip()


def _check_tax_code(tax_code: str) -> str:
    """Vietnamese tax code: 10 digits, or 13 with a -NNN branch suffix."""
    code = tax_code.strip()
    digits = code.replace('-', '')
    if len(code) == 10 and code.isdigit():
        return code
    if digits.isdigit() and len(digits) == 13 and (
            len(code) == 13 or (len(code) == 14 and code[10] == '-')):
        return code
    raise EinvoiceError(
        'Mã số thuế không đúng định dạng (10 số, hoặc 13 số dạng XXXXXXXXXX-NNN): '
        + code)


def _check_amount(value, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EinvoiceError(f'{key} phải là số nguyên VND, nhận được: {value!r}')
    if value < 0:
        raise EinvoiceError(f'{key} không được âm: {value}')
    return value


def _vat_amount(subtotal: int, rate: int) -> int:
    """Round-half-up VAT on integer VND (no floats near money)."""
    quotient, remainder = divmod(subtotal * rate, 100)
    return quotient + (1 if remainder * 2 >= 100 else 0)


def build_invoice_payload(order: dict, environ=None) -> dict:
    """Validate a confirmed order and build the provider invoice payload.

    Raises EinvoiceNotConfigured while dormant (config is loaded first, so
    nothing is built), and EinvoiceError on any invalid order: missing
    buyer fields, empty/invalid items, non-integer or negative amounts, an
    unsupported VAT rate, or a caller-supplied total that does not match
    the computed subtotal + VAT (fail closed on mismatched totals).
    Amounts in the returned payload are integer VND.
    """
    config = load_config(environ)
    if not isinstance(order, dict):
        raise EinvoiceError('Đơn hàng phải là một object')

    buyer = {
        'name': _require_text(order, 'buyer_name'),
        'address': _require_text(order, 'buyer_address'),
    }
    tax_code = order.get('buyer_tax_code')
    if tax_code is not None and str(tax_code).strip():
        buyer['taxCode'] = _check_tax_code(str(tax_code))
    email = order.get('buyer_email')
    if isinstance(email, str) and email.strip():
        buyer['email'] = email.strip()

    items_in = order.get('items')
    if not isinstance(items_in, list) or not items_in:
        raise EinvoiceError('Hóa đơn cần ít nhất một dòng hàng hóa/dịch vụ (items)')
    items = []
    subtotal = 0
    for index, raw in enumerate(items_in):
        if not isinstance(raw, dict):
            raise EinvoiceError(f'items[{index}] phải là một object')
        name = raw.get('name')
        if not isinstance(name, str) or not name.strip():
            raise EinvoiceError(f'items[{index}] thiếu tên hàng hóa/dịch vụ')
        quantity = raw.get('quantity')
        if isinstance(quantity, bool) or not isinstance(quantity, int) \
                or quantity <= 0:
            raise EinvoiceError(f'items[{index}].quantity phải là số nguyên dương')
        unit_price = _check_amount(raw.get('unit_price'),
                                   f'items[{index}].unit_price')
        line_total = quantity * unit_price
        subtotal += line_total
        items.append({'name': name.strip(), 'quantity': quantity,
                      'unitPrice': unit_price, 'amount': line_total})

    vat_rate = order.get('vat_rate', DEFAULT_VAT_RATE)
    if isinstance(vat_rate, bool) or not isinstance(vat_rate, int) \
            or vat_rate not in VAT_RATES:
        raise EinvoiceError(
            f'vat_rate phải thuộc {VAT_RATES} (%), nhận được: {vat_rate!r}')
    vat_amount = _vat_amount(subtotal, vat_rate)
    total = subtotal + vat_amount
    if total <= 0:
        raise EinvoiceError('Tổng tiền hóa đơn phải lớn hơn 0')

    expected_total = order.get('total_amount')
    if expected_total is not None:
        _check_amount(expected_total, 'total_amount')
        if expected_total != total:
            raise EinvoiceError(
                f'Tổng tiền không khớp: đơn ghi {expected_total} nhưng tính '
                f'lại từ items + VAT {vat_rate}% là {total}. Dừng để tránh '
                'xuất hóa đơn sai số tiền.')

    return {
        'provider': config['provider'],
        'templateCode': config['template_code'],
        'series': config['series'],
        'orderRef': _require_text(order, 'order_ref'),
        'currency': 'VND',
        'buyer': buyer,
        'items': items,
        'vatRate': vat_rate,
        'totalBeforeVat': subtotal,
        'vatAmount': vat_amount,
        'totalAmount': total,
    }


def build_create_request(order: dict, environ=None) -> dict:
    """Build (never send) the signed create-invoice HTTP request.

    Returns method/url/headers/body so the future ledger wiring can submit
    it through whatever transport the provider contract specifies. The URL
    host comes only from the seller's EINVOICE_API_BASE.
    """
    config = load_config(environ)
    payload = build_invoice_payload(order, environ)
    body = dict(payload)
    body['signature'] = sign_payload(payload, config['api_secret'])
    return {
        'method': 'POST',
        'url': config['api_base'] + CREATE_PATH,
        'headers': {'Content-Type': 'application/json',
                    'x-api-key': config['api_key']},
        'body': body,
    }


def issue_invoice(order: dict, environ=None, transport=None) -> dict:
    """Submit a confirmed order to the configured provider and return
    {'invoice_no', 'series', 'issued_at'} (issued_at = epoch seconds).

    This module performs no network I/O itself: `transport` is the
    caller's sender with the tools/payos.py contract
    transport(method, url, headers, body) -> decoded JSON response; the
    vendor ledger injects the real HTTP transport. Raises
    EinvoiceNotConfigured while dormant — before anything is built or
    sent — and EinvoiceError when no transport is supplied, the order is
    invalid, or the provider response carries no invoice number (or
    reports a non-issued state), so a caller can never record an invoice
    that was not issued. Response field names follow the same tolerant
    conventions as parse_webhook; the exact provider response shape must
    be re-checked against the signed provider's API documentation (see
    docs/EINVOICE.md).
    """
    config = load_config(environ)
    if transport is None:
        raise EinvoiceError('Chưa nối kênh gửi tới nhà cung cấp hóa đơn: '
                            'issue_invoice cần transport do bên gọi cung cấp '
                            '(sổ bán hàng đã nối sẵn kênh này).')
    request = build_create_request(order, environ)
    try:
        payload = transport(request['method'], request['url'],
                            request['headers'], request['body'])
    except EinvoiceError:
        raise
    except Exception as exc:
        raise EinvoiceError(
            f'Gửi yêu cầu xuất hóa đơn tới nhà cung cấp thất bại: {exc}') from exc
    if not isinstance(payload, dict):
        raise EinvoiceError('Nhà cung cấp trả phản hồi không phải object; '
                            'chưa thể ghi nhận hóa đơn nào')
    data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
    status_raw = data.get('status') or data.get('state')
    if status_raw is not None and str(status_raw).strip().upper() not in ISSUED_STATES:
        raise EinvoiceError(
            f'Nhà cung cấp chưa xác nhận phát hành hóa đơn (trạng thái: {status_raw!r})')
    invoice_no = data.get('invoiceNo') or data.get('invoice_no')
    if not isinstance(invoice_no, str) or not invoice_no.strip():
        raise EinvoiceError('Nhà cung cấp không trả số hóa đơn (invoiceNo); '
                            'chưa thể ghi nhận hóa đơn nào')
    series = data.get('series')
    if not isinstance(series, str) or not series.strip():
        series = config['series']
    issued_at = data.get('issuedAt') or data.get('issued_at')
    if isinstance(issued_at, bool) or not isinstance(issued_at, int) or issued_at <= 0:
        issued_at = int(time.time())
    return {'invoice_no': invoice_no.strip(), 'series': series.strip(),
            'issued_at': issued_at}


def parse_webhook(payload: dict) -> dict:
    """Normalize a provider webhook to {invoice_no, status, order_ref}.

    Only known issued states are accepted; every other state, and any
    missing field, raises EinvoiceError so an unissued invoice can never
    be recorded as issued. Callers must verify the webhook signature with
    verify_webhook_signature BEFORE trusting this result.
    """
    if not isinstance(payload, dict):
        raise EinvoiceError('Webhook hóa đơn không phải object')
    data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
    invoice_no = data.get('invoiceNo') or data.get('invoice_no')
    status_raw = data.get('status') or data.get('state') or ''
    order_ref = data.get('orderRef') or data.get('order_ref') \
        or data.get('orderCode')
    if not isinstance(invoice_no, str) or not invoice_no.strip():
        raise EinvoiceError('Webhook hóa đơn thiếu số hóa đơn (invoiceNo)')
    if str(status_raw).strip().upper() not in ISSUED_STATES:
        raise EinvoiceError(
            f"Webhook hóa đơn không ở trạng thái đã phát hành: {status_raw!r}")
    if order_ref is None or (isinstance(order_ref, str) and not order_ref.strip()):
        raise EinvoiceError('Webhook hóa đơn thiếu mã đơn (orderRef)')
    return {'invoice_no': invoice_no.strip(), 'status': 'issued',
            'order_ref': str(order_ref)}
