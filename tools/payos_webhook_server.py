"""Seller-side PayOS webhook receiver (Python standard library only).

Run this on the seller's machine/VPS behind HTTPS (reverse proxy or tunnel)
once PayOS merchant keys exist. It does exactly one thing with a payment:
verify the webhook signature with PAYOS_CHECKSUM_KEY and mark the matching
order as PAID in the seller ledger. It never signs or issues licenses — the
seller still does that manually after seeing the paid order, the same as a
personally confirmed bank transfer.

Endpoints:
  POST /payos/webhook   PayOS webhook (signature-verified)
  GET  /payos/return    Informational page for the buyer's browser return
  GET  /payos/cancel    Informational page; never changes order state
  GET  /healthz

Usage:
  PAYOS_CHECKSUM_KEY=... python tools/payos_webhook_server.py --port 8899
"""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # Prefer the package modules so exception classes are shared.
    from tools import payos as payos_module  # noqa: E402
    from tools import vendor_ledger as ledger  # noqa: E402
except ImportError:  # Running as loose scripts outside the repo root.
    import payos as payos_module  # noqa: E402
    import vendor_ledger as ledger  # noqa: E402

INFO_PAGE = ('<!doctype html><meta charset="utf-8"><title>LHM Ads AI</title>'
             '<p>Cảm ơn bạn. Trạng thái thanh toán được xác nhận tự động qua '
             'PayOS webhook; bên bán sẽ cấp license sau khi đối soát. Trang '
             'này tự nó không xác nhận thanh toán.</p>')


def handle_webhook(db_path, raw_body: bytes, checksum_key: str):
    """Process one webhook body; returns (http_status, response_dict)."""
    try:
        payload = json.loads(raw_body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 400, {'ok': False, 'error': 'invalid JSON'}
    db = ledger.connect(db_path)
    try:
        result = ledger.apply_payos_webhook(db, payload, checksum_key)
    except payos_module.PayosError as exc:
        return 400, {'ok': False, 'error': str(exc)}
    except ValueError as exc:
        return 404, {'ok': False, 'error': str(exc)}
    finally:
        db.close()
    return 200, {'ok': True, **result}


def make_handler(db_path, checksum_key):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep stdout clean of request logs
            pass

        def _send(self, status, body, content_type='application/json'):
            raw = body if isinstance(body, bytes) else (
                body.encode('utf-8') if content_type != 'application/json'
                else json.dumps(body, ensure_ascii=False).encode('utf-8'))
            self.send_response(status)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == '/healthz':
                self._send(200, {'ok': True})
            elif self.path in ('/payos/return', '/payos/cancel'):
                self._send(200, INFO_PAGE, 'text/html')
            else:
                self._send(404, {'ok': False, 'error': 'not found'})

        def do_POST(self):
            if self.path != '/payos/webhook':
                self._send(404, {'ok': False, 'error': 'not found'})
                return
            length = int(self.headers.get('Content-Length') or 0)
            if length <= 0 or length > 65536:
                self._send(400, {'ok': False, 'error': 'invalid body size'})
                return
            status, result = handle_webhook(
                db_path, self.rfile.read(length), checksum_key)
            self._send(status, result)

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description='LHM Ads AI seller PayOS webhook receiver')
    parser.add_argument('--db', type=Path, default=ledger.default_database())
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8899)
    args = parser.parse_args(argv)
    checksum_key = os.environ.get('PAYOS_CHECKSUM_KEY', '').strip()
    if not checksum_key:
        parser.error('PAYOS_CHECKSUM_KEY chưa được đặt: webhook không thể xác minh '
                     'chữ ký, máy chủ không khởi động (tích hợp PayOS đang tắt).')
    server = ThreadingHTTPServer((args.host, args.port),
                                 make_handler(args.db, checksum_key))
    print(f'PayOS webhook listening on http://{args.host}:{args.port}/payos/webhook '
          f'(ledger: {args.db}) — put HTTPS in front before production use.')
    server.serve_forever()


if __name__ == '__main__':
    main()
