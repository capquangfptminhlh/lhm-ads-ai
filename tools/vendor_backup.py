"""Encrypted, self-contained recovery of seller ledger + issued license JSON.

Seller workstation only; NO private Ed25519 issuer key is ever included.
A fresh install must restore the ORIGINAL encrypted issuer private key from
its independently stored offline backup before issuing future renewals.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import closing
from getpass import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import secrets
import shutil
import sqlite3
import tempfile
import time
import zipfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

# Support running the vendor-only CLI directly from a checked-out repository.
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import vendor_ledger as ledger

MAGIC = b'LHMVENDORVAULT1\x00'
SALT_BYTES = 16
NONCE_BYTES = 12
KDF_N = 1 << 15
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_LICENSES = 3000
DATABASE_FILE = 'customers.sqlite3'
PUBLIC_FILE = 'vendor-public.b64'
INDEX_FILE = 'backup-index.json'


class VendorVaultError(ValueError):
    """No caller secrets should be included in errors."""


def _key(password: str, salt: bytes) -> bytes:
    if not isinstance(password, str) or len(password) < 16:
        raise VendorVaultError('Mật khẩu sao lưu phải có ít nhất 16 ký tự')
    return Scrypt(salt=salt, length=32, n=KDF_N, r=8, p=1).derive(
        password.encode('utf-8'))


def _public_bytes(path: Path) -> bytes:
    try:
        raw = base64.b64decode(Path(path).read_text(encoding='ascii').strip(),
                               validate=True)
        if len(raw) != 32:
            raise ValueError('invalid key length')
        return raw
    except (OSError, ValueError, UnicodeError) as exc:
        raise VendorVaultError('Không tìm thấy public key Ed25519 hợp lệ') from exc


def _rows(db_path: Path) -> list[dict]:
    # Read-only, never silently create a blank database on restore.
    uri = db_path.resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        result = db.execute('PRAGMA integrity_check').fetchone()
        if result is None or result[0] != 'ok':
            raise VendorVaultError('Sổ SQLite bị hỏng')
        required = {'customers', 'licenses', 'payment_orders'}
        existing = {item[0] for item in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not required.issubset(existing):
            raise VendorVaultError('Sổ không đúng schema quản lý thuê bao LHM')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise VendorVaultError('Sổ có bản ghi mồ côi')
        count = db.execute('SELECT COUNT(*) FROM licenses').fetchone()[0]
        if count > MAX_LICENSES:
            raise VendorVaultError('Số license vượt giới hạn sao lưu bảo vệ')
        items = db.execute('''
            SELECT l.license_id, l.customer_ref, l.device, l.signature_sha256,
                   l.expires_at, c.device AS customer_device
            FROM licenses l JOIN customers c ON c.customer_ref=l.customer_ref
            ORDER BY l.customer_ref,l.license_id
        ''').fetchall()
        if len(items) != count:
            raise VendorVaultError('Sổ có license không gắn khách')
        return [dict(row) for row in items]


def _filename(row: dict) -> str:
    customer, license_id = row['customer_ref'], row['license_id']
    if not isinstance(customer, str) or not ledger.REF.fullmatch(customer):
        raise VendorVaultError('Mã khách không hợp lệ trong sổ')
    if not isinstance(license_id, str) or not ledger.LICENSE_ID.fullmatch(license_id):
        raise VendorVaultError('Mã license không hợp lệ trong sổ')
    return f'issued-licenses/{customer}/{license_id}.json'


def _check_license(path: Path, row: dict, public: Path) -> None:
    if not path.is_file() or path.stat().st_size > 4096:
        raise VendorVaultError('Thiếu hoặc sai kích thước file license đã cấp')
    try:
        payload, digest = ledger.verify_license(path, public)
    except (OSError, ValueError) as exc:
        raise VendorVaultError('File license đã cấp không xác minh được chữ ký') from exc
    if (payload['license_id'] != row['license_id'] or
            payload['device'] != row['device'] or
            payload['device'] != row['customer_device'] or
            payload['expires_at'] != row['expires_at'] or
            digest != row['signature_sha256']):
        raise VendorVaultError('File license và sổ bán không khớp')


def export_vault(db_path: Path, license_dir: Path, public_file: Path,
                 destination: Path, password: str) -> dict:
    """Snapshot live SQLite, validate every issued license, encrypt whole bundle.

    Refuse to write any output until database/license validation and crypto
    finish. The caller must choose a new path; never overwrite prior backups.
    """
    destination = Path(destination).expanduser().resolve()
    if not destination.parent.is_dir() or destination.exists():
        raise FileExistsError('Chọn file .lhmvault mới trong thư mục đã tồn tại')
    public = _public_bytes(public_file)
    salt, nonce = secrets.token_bytes(SALT_BYTES), secrets.token_bytes(NONCE_BYTES)
    key = _key(password, salt)
    db_path, license_dir = Path(db_path), Path(license_dir)
    if not db_path.is_file():
        raise VendorVaultError('Không tìm thấy SQLite sổ bán hiện tại')
    with tempfile.TemporaryDirectory(prefix='lhm-vault-') as workspace:
        snap = Path(workspace) / DATABASE_FILE
        # Acquire a consistent SQLite snapshot even while vendor app is open.
        with closing(sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro',
                                     uri=True, timeout=10)) as source:
            with closing(sqlite3.connect(snap)) as dest:
                source.backup(dest)
        rows = _rows(snap)
        blob = io.BytesIO()
        with zipfile.ZipFile(blob, 'w', zipfile.ZIP_DEFLATED,
                             compresslevel=6) as zf:
            zf.write(snap, DATABASE_FILE)
            zf.writestr(PUBLIC_FILE, base64.b64encode(public).decode('ascii'))
            index = {'format': 'lhm-vendor-backup-v1',
                     'license_count': len(rows),
                     'created_at_unix': int(time.time()),
                     'vendor_public_sha256': hashlib.sha256(public).hexdigest()}
            zf.writestr(INDEX_FILE, json.dumps(index, sort_keys=True))
            for row in rows:
                name = _filename(row)
                item = license_dir / row['customer_ref'] / (row['license_id']+'.json')
                _check_license(item, row, Path(public_file))
                zf.write(item, name)
                if blob.tell() > MAX_ARCHIVE:
                    raise VendorVaultError('Dung lượng sổ quá lớn để sao lưu')
        plaintext = blob.getvalue()
        if len(plaintext) > MAX_ARCHIVE:
            raise VendorVaultError('Dung lượng sao lưu vượt 64 MB')
        header = MAGIC + salt + nonce
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, header)
        with destination.open('xb') as fd:
            fd.write(header + ciphertext)
            fd.flush()
            os.fsync(fd.fileno())
        if os.name != 'nt':
            os.chmod(destination, 0o600)
    return {'file': str(destination), 'licenses': len(rows),
            'encrypted': True, 'contains_private_key': False,
            'contains_ads_tokens': False}


def _decrypt(raw: bytes, password: str) -> bytes:
    header_len = len(MAGIC) + SALT_BYTES + NONCE_BYTES
    if len(raw) <= header_len + 16 or not raw.startswith(MAGIC):
        raise VendorVaultError('File sao lưu LHM không hợp lệ')
    if len(raw) > MAX_ARCHIVE + 2 * 1024 * 1024:
        raise VendorVaultError('File sao lưu vượt giới hạn')
    salt = raw[len(MAGIC):len(MAGIC)+SALT_BYTES]
    nonce = raw[len(MAGIC)+SALT_BYTES:header_len]
    try:
        plain = AESGCM(_key(password, salt)).decrypt(
            nonce, raw[header_len:], raw[:header_len])
    except Exception:
        raise VendorVaultError('Sai mật khẩu hoặc file sao lưu đã bị thay đổi') from None
    if len(plain) > MAX_ARCHIVE:
        raise VendorVaultError('Dữ liệu giải mã vượt giới hạn')
    return plain


def restore_vault(vault: Path, password: str, target: Path,
                  trusted_public_file: Path) -> dict:
    """Restore to NEW directory only, never into an active seller workspace."""
    target = Path(target).expanduser().resolve()
    if target.exists() or not target.parent.is_dir():
        raise FileExistsError('Thư mục đích phải CHƯA TỒN TẠI, nằm trong thư mục cha có sẵn')
    public = _public_bytes(trusted_public_file)
    vault = Path(vault)
    if not vault.is_file() or vault.stat().st_size > MAX_ARCHIVE+2*1024*1024:
        raise VendorVaultError('File sao lưu không hợp lệ hoặc quá lớn')
    plaintext = _decrypt(vault.read_bytes(), password)
    with zipfile.ZipFile(io.BytesIO(plaintext)) as zf:
        parts = zf.infolist()
        if len(parts) > MAX_LICENSES + 3:
            raise VendorVaultError('Sao lưu chứa quá nhiều file')
        names = [part.filename for part in parts]
        if len(names) != len(set(names)) or not {DATABASE_FILE, PUBLIC_FILE, INDEX_FILE}.issubset(names):
            raise VendorVaultError('Sao lưu thiếu file chính hoặc có file trùng')
        if any(part.is_dir() or part.file_size > MAX_ARCHIVE for part in parts):
            raise VendorVaultError('Sao lưu chứa file không hợp lệ')
        if sum(part.file_size for part in parts) > MAX_ARCHIVE:
            raise VendorVaultError('Sao lưu giải nén vượt giới hạn')
        index_data = zf.read(INDEX_FILE)
        if len(index_data) > 4096:
            raise VendorVaultError('Chỉ mục sao lưu quá dài')
        try:
            info = json.loads(index_data)
        except (UnicodeError, ValueError) as exc:
            raise VendorVaultError('Chỉ mục sao lưu không hợp lệ') from exc
        if not isinstance(info, dict) or info.get('format') != 'lhm-vendor-backup-v1':
            raise VendorVaultError('Không đúng định dạng LHM vendor vault')
        if hashlib.sha256(public).hexdigest() != info.get('vendor_public_sha256'):
            raise VendorVaultError('Khóa công khai không thuộc bộ khóa của bên bán')
        try:
            packaged_public = base64.b64decode(zf.read(PUBLIC_FILE).strip(),
                                               validate=True)
        except (ValueError, TypeError) as exc:
            raise VendorVaultError('Public key trong file sao lưu không hợp lệ') from exc
        if packaged_public != public:
            raise VendorVaultError('Sao lưu sử dụng bộ khóa Ed25519 khác')
        stage = Path(tempfile.mkdtemp(prefix='.lhm-vault-restore-', dir=target.parent))
        try:
            db_out = stage / DATABASE_FILE
            db_out.write_bytes(zf.read(DATABASE_FILE))
            rows = _rows(db_out)
            expected = {DATABASE_FILE, PUBLIC_FILE, INDEX_FILE}
            for row in rows:
                expected.add(_filename(row))
            if set(names) != expected or info.get('license_count') != len(rows):
                raise VendorVaultError('Sao lưu thiếu/thừa license so với sổ')
            verified_public = stage / PUBLIC_FILE
            verified_public.write_text(base64.b64encode(public).decode(),
                                       encoding='ascii')
            for row in rows:
                member = _filename(row)
                filename = stage / member
                filename.parent.mkdir(parents=True, exist_ok=True)
                payload = zf.read(member)
                if len(payload) > 4096:
                    raise VendorVaultError('File license vượt giới hạn')
                filename.write_bytes(payload)
                _check_license(filename, row, verified_public)
            if target.exists():
                raise FileExistsError('Thư mục khôi phục đã tồn tại')
            # Rename only after all authentication/schema/signature checks pass.
            os.rename(stage, target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {'restored_to': str(target), 'licenses': len(rows),
            'requires_original_private_key': True}


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='Encrypted offline seller records recovery')
    commands=parser.add_subparsers(dest='command', required=True)
    backup=commands.add_parser('backup')
    backup.add_argument('--db',type=Path,default=ledger.default_database())
    backup.add_argument('--license-dir',type=Path,required=True)
    backup.add_argument('--public',type=Path,required=True)
    backup.add_argument('--out',type=Path,required=True)
    restore=commands.add_parser('restore')
    restore.add_argument('--vault',type=Path,required=True)
    restore.add_argument('--public',type=Path,required=True)
    restore.add_argument('--target',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        password=getpass('Mật khẩu sao lưu (ẩn, ít nhất 16 ký tự): ')
        if args.command=='backup':
            confirm=getpass('Nhập lại mật khẩu sao lưu: ')
            if password != confirm:
                raise VendorVaultError('Hai mật khẩu sao lưu không trùng')
            print(export_vault(args.db,args.license_dir,args.public,args.out,password))
        else:
            print(restore_vault(args.vault,password,args.target,args.public))
    except (OSError,VendorVaultError,sqlite3.Error,zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
