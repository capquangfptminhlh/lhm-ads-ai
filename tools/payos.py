"""PayOS payment integration for the seller — dormant until configured.

The seller's current sales flow is a manual bank transfer to the seller's own
account, personally confirmed before a license is issued. This module prepares
PayOS (payos.vn) so it can be switched on later WITHOUT code changes: when
the seller obtains merchant credentials and sets PAYOS_CLIENT_ID,
PAYOS_API_KEY and PAYOS_CHECKSUM_KEY on the seller machine, the vendor ledger
can create payment links and a webhook can mark orders as paid.

Deliberate boundary: a verified PayOS webhook only marks an order PAID in the
seller ledger. It never signs or issues a license — signing stays on the
seller's offline machine under the seller's personal confirmation, so the
license issuer private key never lives on an Internet-facing server.

Implements the PayOS merchant API v2 conventions:
- Create payment request: POST {base}/v2/payment-requests with headers
  x-client-id / x-api-key; request signature is HMAC-SHA256 (checksum key)
  over the alphabetically sorted "key=value&..." string of
  amount, cancelUrl, description, orderCode, returnUrl.
- Webhook verification: HMAC-SHA256 (checksum key) over the data object
  flattened the same way (keys sorted; null -> empty string; objects/arrays
  as JSON with sorted keys), compared in constant time to `signature`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.request

API_BASE = 'https://api-merchant.payos.vn'
MAX_DESCRIPTION = 25  # PayOS/VietQR transfer-content limit


class PayosNotConfigured(RuntimeError):
    """Raised when merchant credentials are not set yet (integration dormant)."""


class PayosError(RuntimeError):
    """Raised when PayOS rejects a request or a webhook fails verification."""


def load_config(environ=None) -> dict:
    env = os.environ if environ is None else environ
    config = {
        'client_id': env.get('PAYOS_CLIENT_ID', '').strip(),
        'api_key': env.get('PAYOS_API_KEY', '').strip(),
        'checksum_key': env.get('PAYOS_CHECKSUM_KEY', '').strip(),
        'api_base': env.get('PAYOS_API_BASE', API_BASE).rstrip('/'),
        'return_url': env.get('PAYOS_RETURN_URL', '').strip(),
        'cancel_url': env.get('PAYOS_CANCEL_URL', '').strip(),
    }
    missing = [name for name, key in (('PAYOS_CLIENT_ID', 'client_id'),
                                      ('PAYOS_API_KEY', 'api_key'),
                                      ('PAYOS_CHECKSUM_KEY', 'checksum_key'))
               if not config[key]]
    if missing:
        raise PayosNotConfigured(
            'PayOS chưa được kích hoạt: thiếu ' + ', '.join(missing) +
            ' trong môi trường máy bên bán. Quy trình hiện tại vẫn là chuyển '
            'khoản thủ công và xác nhận tay.')
    return config


def is_configured(environ=None) -> bool:
    try:
        load_config(environ)
        return True
    except PayosNotConfigured:
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
    """Canonical "a=1&b=2" string with alphabetically sorted keys (PayOS rule)."""
    return '&'.join(f'{key}={_flatten_value(fields[key])}' for key in sorted(fields))


def sign(fields: dict, checksum_key: str) -> str:
    return hmac.new(checksum_key.encode('utf-8'),
                    data_string(fields).encode('utf-8'),
                    hashlib.sha256).hexdigest()


def new_order_code(now: float | None = None) -> int:
    """Positive millisecond-based order code, unique enough per seller ledger."""
    return int((time.time() if now is None else now) * 1000)


def create_payment_link(config: dict, *, order_code: int, amount: int,
                        description: str, transport=None) -> dict:
    if not isinstance(order_code, int) or order_code <= 0:
        raise ValueError('order_code must be a positive integer')
    if not isinstance(amount, int) or amount <= 0:
        raise ValueError('amount must be a positive integer (VND)')
    description = (description or '').strip()[:MAX_DESCRIPTION]
    if not description:
        raise ValueError('description must not be empty')
    body = {
        'orderCode': order_code,
        'amount': amount,
        'description': description,
        'returnUrl': config.get('return_url', ''),
        'cancelUrl': config.get('cancel_url', ''),
    }
    body['signature'] = sign({
        'amount': body['amount'], 'cancelUrl': body['cancelUrl'],
        'description': body['description'], 'orderCode': body['orderCode'],
        'returnUrl': body['returnUrl']}, config['checksum_key'])
    payload = _post_json(config, '/v2/payment-requests', body, transport)
    if payload.get('code') != '00' or not isinstance(payload.get('data'), dict):
        raise PayosError(f"PayOS từ chối tạo link: {payload.get('desc') or payload.get('code')}")
    data = payload['data']
    return {'checkout_url': data.get('checkoutUrl'),
            'payment_link_id': data.get('paymentLinkId'),
            'qr_code': data.get('qrCode'),
            'order_code': data.get('orderCode', order_code),
            'amount': data.get('amount', amount),
            'status': data.get('status')}


def _post_json(config: dict, path: str, body: dict, transport=None):
    url = config['api_base'] + path
    headers = {'Content-Type': 'application/json',
               'x-client-id': config['client_id'],
               'x-api-key': config['api_key']}
    if transport is not None:
        return transport('POST', url, headers, body)
    request = urllib.request.Request(
        url, data=json.dumps(body).encode('utf-8'), headers=headers, method='POST')
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode('utf-8'))


def verify_webhook(payload: dict, checksum_key: str) -> dict:
    """Return the verified `data` object or raise PayosError.

    Only a payload whose signature matches AND whose top-level code reports
    success may be treated as paid; anything else is rejected here so callers
    cannot accidentally trust return/cancel URLs instead of the webhook.
    """
    if not isinstance(payload, dict):
        raise PayosError('Webhook payload is not an object')
    data = payload.get('data')
    signature = payload.get('signature')
    if not isinstance(data, dict) or not isinstance(signature, str):
        raise PayosError('Webhook payload is missing data or signature')
    expected = sign(data, checksum_key)
    if not hmac.compare_digest(expected, signature.lower()):
        raise PayosError('Webhook signature mismatch')
    if payload.get('code') != '00' or payload.get('success') is not True:
        raise PayosError('Webhook does not report a successful payment')
    return data
