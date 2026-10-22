"""Seller-PC-only issuance of real signed 30-day licenses and renewals.

Never imported by the customer app. The seller independently confirms a bank
payment before invoking issue_paid_license; this module NEVER contacts a bank,
trusts an unverified payment notification or saves a private key/passphrase.
"""
from __future__ import annotations
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools import vendor_ledger
from tools.license_issuer import PRODUCT, public_b64

MAX_KEY_BYTES = 8192


def vendor_keys_dir() -> Path:
    if os.name == 'nt':
        root = Path(os.environ.get('LOCALAPPDATA') or Path.home())
    else:
        root = Path.home() / '.local' / 'share'
    return root / 'LHMAdsAI-Vendor' / 'keys'


def vendor_license_dir() -> Path:
    return vendor_keys_dir().parent / 'issued-licenses'


def _unlock(private_path: Path, public_path: Path, passphrase: str) -> Ed25519PrivateKey:
    if not isinstance(passphrase, str) or not passphrase:
        raise ValueError('Cần mật khẩu khóa phát hành riêng của bên bán')
    if not private_path.is_file() or private_path.stat().st_size > MAX_KEY_BYTES:
        raise ValueError('Không tìm thấy private issuer key hợp lệ')
    pem = private_path.read_bytes()
    if b'-----BEGIN ENCRYPTED PRIVATE KEY-----' not in pem:
        raise ValueError('Khóa cấp license phải được mã hóa; từ chối khóa plaintext')
    try:
        key = serialization.load_pem_private_key(pem, password=passphrase.encode('utf-8'))
    except (ValueError, TypeError):
        raise ValueError('Sai mật khẩu khóa riêng hoặc khóa đã hỏng') from None
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Phải dùng khóa Ed25519')
    if not public_path.is_file() or public_b64(key) != public_path.read_text(encoding='ascii').strip():
        raise ValueError('Khóa private KHÔNG khớp public key đã dùng để build EXE')
    return key


def find_renewal_source(db, customer_ref: str, directory: Path) -> Path | None:
    row = db.execute('''
        SELECT license_id, expires_at FROM licenses WHERE customer_ref=?
        ORDER BY expires_at DESC,recorded_at DESC,license_id DESC LIMIT 1
    ''', (customer_ref,)).fetchone()
    if not row:
        return None
    candidate = directory / customer_ref / (row['license_id'] + '.json')
    if not candidate.is_file():
        raise ValueError('Không tìm thấy license cũ để gia hạn. Hãy khôi phục file license gốc.')
    return candidate


def issue_paid_license(*, customer_ref: str, receipt_ref: str,
                       passphrase: str, private_file: Path, public_file: Path,
                       db_path: Path, license_directory: Path,
                       payment_confirmed: bool, renewal_source: Path | None = None,
                       now: int | None = None) -> dict:
    """Issue only after seller checks the payment in their own bank statement.

    Atomic-ish across filesystem/ledger: on a ledger validation failure,
    remove the newly issued JSON so no unrecorded paid license is left behind.
    Never overwrite an earlier license or extend an unknown signed license.
    """
    if payment_confirmed is not True:
        raise ValueError('Phải tự đối chiếu tiền đã vào ngân hàng trước khi cấp license')
    if not vendor_ledger.REF.fullmatch(customer_ref):
        raise ValueError('Mã khách hàng không hợp lệ')
    if not vendor_ledger.REF.fullmatch(receipt_ref):
        raise ValueError('Cần mã biên nhận nội bộ đã đối chiếu (không nhập số tài khoản)')
    now = int(time.time()) if now is None else now
    if isinstance(now, bool) or not isinstance(now, int) or now <= 0:
        raise ValueError('Thời gian phát hành không hợp lệ')
    private_file, public_file = Path(private_file), Path(public_file)
    key = _unlock(private_file, public_file, passphrase)
    db = vendor_ledger.connect(db_path)
    try:
        # Serialize issuers BEFORE inspecting the latest license and receipt.
        # Without a write lock, two seller EXEs can both extend the same old
        # expiry or spend one receipt twice. SQLite waits up to busy_timeout.
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT device FROM customers WHERE customer_ref=?',
                         (customer_ref,)).fetchone()
        if not row:
            raise ValueError('Khách chưa đăng ký mã máy, cần đăng ký trước')
        device = row['device']
        exists = db.execute('SELECT COUNT(*) AS n FROM licenses WHERE customer_ref=?',
                            (customer_ref,)).fetchone()['n']
        previous_receipt = db.execute("""SELECT license_id FROM licenses
                WHERE receipt_ref=? AND payment_status='confirmed' LIMIT 1""",
                (receipt_ref,)).fetchone()
        if previous_receipt:
            raise ValueError('Mã biên nhận đã được dùng cấp license trước; từ chối thu trùng')
        if exists and renewal_source is None:
            renewal_source = find_renewal_source(db, customer_ref, Path(license_directory))
        if renewal_source is not None and not exists:
            raise ValueError('Không thể gia hạn khách chưa từng có license')
        base = now
        if renewal_source is not None:
            prior, sig_hash = vendor_ledger.verify_license(renewal_source, public_file)
            del sig_hash
            if prior['device'] != device or prior['product'] != PRODUCT:
                raise ValueError('License gia hạn sai thiết bị hoặc sai sản phẩm')
            if exists:
                newest = db.execute("""SELECT license_id FROM licenses WHERE customer_ref=?
                    ORDER BY expires_at DESC,recorded_at DESC,license_id DESC LIMIT 1""",
                    (customer_ref,)).fetchone()
                if not newest or prior['license_id'] != newest['license_id']:
                    raise ValueError('Phải gia hạn trên license MỚI NHẤT đã ghi sổ')
            base = max(now, prior['expires_at'])
        # Consistent with license_issuer.py, with a strict 30-day term.
        if base + 30 * 86400 > now + 370 * 86400:
            raise ValueError('Không cấp cộng dồn vượt 370 ngày')
        payload = {
            'product': PRODUCT,
            'device': device,
            'license_id': secrets.token_hex(12),
            'issued_at': now,
            'expires_at': base + 30 * 86400,
            'plan': 'monthly',
        }
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True,
                             separators=(',', ':')).encode()
        document = {'payload': payload, 'signature':
                    base64.b64encode(key.sign(encoded)).decode('ascii')}
        target_dir = Path(license_directory) / customer_ref
        target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = target_dir / (payload['license_id'] + '.json')
        flags = os.O_CREAT | os.O_WRONLY | os.O_EXCL
        fd = os.open(target, flags, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as dest:
                json.dump(document, dest, ensure_ascii=False, indent=2)
                dest.flush()
                os.fsync(dest.fileno())
            vendor_ledger.record(db, customer_ref, target, public_file,
                                 payment_status='confirmed', receipt_ref=receipt_ref,
                                 now=now)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return {'customer_ref': customer_ref, 'device': device,
                'license_id': payload['license_id'], 'path': str(target),
                'expires_at': payload['expires_at'],
                'expires_at_utc': datetime.fromtimestamp(
                    payload['expires_at'], timezone.utc).isoformat(),
                'days': 30, 'payment_status': 'confirmed',
                'receipt_ref': receipt_ref}
    finally:
        db.close()
