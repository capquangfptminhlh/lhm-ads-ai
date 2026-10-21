"""OFFLINE VENDOR TOOL. Never put this or the private key in the shipped Windows EXE.
Quản lý danh sách thu hồi giấy phép (revocation list) ký bằng cùng khóa phát hành
dùng cho license. Danh sách chỉ có hiệu lực khi khách hàng nhận và nạp bản mới —
đây không phải cơ chế tắt từ xa.

Usage:
  python tools/license_revoke.py add --list revocations.json --license-id HEX --reason "Hoàn tiền" --key /secure/vendor-private-key.pem
  python tools/license_revoke.py add --list revocations.json --device-id HEX32 --reason "Lộ giấy phép" --key /secure/vendor-private-key.pem
  python tools/license_revoke.py show --list revocations.json --public vendor-public.txt
"""
import argparse
import base64
import getpass
import json
from pathlib import Path
import sys
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ads_core.license_revocation import (  # noqa: E402
    SUPPORTED_VERSION, RevocationError, empty_list, signature_path,
    verify_revocation_list)
from ads_core.licensing import canonical  # noqa: E402


def public_b64(key):
    raw = key.public_key().public_bytes(encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode('ascii')


def load_signing_key(private_path: Path) -> Ed25519PrivateKey:
    encoded_private = private_path.read_bytes()
    password = (getpass.getpass('Mật khẩu khóa phát hành: ').encode('utf-8')
                if b'ENCRYPTED PRIVATE KEY' in encoded_private else None)
    key = serialization.load_pem_private_key(encoded_private, password=password)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Chỉ hỗ trợ khóa Ed25519')
    return key


def read_existing_list(list_path: Path, key: Ed25519PrivateKey) -> dict:
    """Load the current list, trusting it only if OUR key signed it."""
    if not list_path.exists():
        return empty_list() | {'issued_at': 0}
    sig_path = signature_path(list_path)
    if not sig_path.is_file():
        raise ValueError('Danh sách đã tồn tại nhưng thiếu file chữ ký .sig; không sửa tiếp trên bản không xác thực được')
    signature = base64.b64decode(sig_path.read_text(encoding='ascii').strip(), validate=True)
    return verify_revocation_list(list_path.read_bytes(), signature,
                                  public_key_b64=public_b64(key))


def write_signed_list(list_path: Path, document: dict, key: Ed25519PrivateKey) -> None:
    raw = canonical(document)
    signature = key.sign(raw)
    list_path.parent.mkdir(parents=True, exist_ok=True)
    list_path.write_bytes(raw)
    signature_path(list_path).write_text(base64.b64encode(signature).decode('ascii') + '\n',
                                         encoding='ascii')


def cmd_add(args) -> None:
    if not args.license_id and not args.device_id:
        raise ValueError('Phải cho ít nhất một trong hai: --license-id hoặc --device-id')
    key = load_signing_key(Path(args.key))
    if args.expected_public:
        expected = Path(args.expected_public).read_text(encoding='ascii').strip()
        if expected != public_b64(key):
            raise ValueError('Khóa private không khớp public key của EXE; không ký danh sách sai khóa')
    list_path = Path(args.list)
    document = read_existing_list(list_path, key)
    for entry in document['entries']:
        if args.license_id and entry.get('license_id') == args.license_id:
            raise ValueError('Mã giấy phép này đã có trong danh sách thu hồi')
        if args.device_id and entry.get('device_id') == args.device_id:
            raise ValueError('Mã máy này đã có trong danh sách thu hồi')
    now = int(time.time())
    entry = {'reason': args.reason, 'revoked_at': now}
    if args.license_id:
        entry['license_id'] = args.license_id
    if args.device_id:
        entry['device_id'] = args.device_id
    document['entries'].append(entry)
    document['issued_at'] = now
    document['version'] = SUPPORTED_VERSION
    write_signed_list(list_path, document, key)
    target = args.license_id or args.device_id
    print(f'Đã thêm {target} vào danh sách thu hồi: {list_path} '
          f'(tổng {len(document["entries"])} mục).')
    print('Gửi CẢ HAI file cho khách hàng: danh sách và file .sig đi kèm. '
          'Thu hồi chỉ hiệu lực khi khách nạp bản mới này.')


def cmd_show(args) -> None:
    list_path = Path(args.list)
    if not list_path.is_file():
        print('Chưa có danh sách thu hồi nào.')
        return
    if args.public:
        key_b64 = Path(args.public).read_text(encoding='ascii').strip()
    else:
        from ads_core import licensing
        key_b64 = licensing.PUBLIC_KEY_B64
        print('(Đang kiểm chứng bằng public key đang nhúng trong mã nguồn hiện tại; '
              'dùng --public để chỉ định public key của bản EXE đã phát hành.)')
    sig_path = signature_path(list_path)
    if not sig_path.is_file():
        raise ValueError('Thiếu file chữ ký .sig đi kèm danh sách')
    signature = base64.b64decode(sig_path.read_text(encoding='ascii').strip(), validate=True)
    document = verify_revocation_list(list_path.read_bytes(), signature, public_key_b64=key_b64)
    print(f"Danh sách thu hồi phát hành lúc {document['issued_at']} "
          f"(phiên bản {document['version']}), {len(document['entries'])} mục:")
    for entry in document['entries']:
        target = entry.get('license_id') or entry.get('device_id')
        print(f"  - {target}: {entry['reason']} (thu hồi lúc {entry['revoked_at']})")


def main():
    ap = argparse.ArgumentParser(description='LHM Ads AI: offline license revocation (vendor only)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    add = sub.add_parser('add', help='Thêm một giấy phép/máy vào danh sách thu hồi và ký lại')
    add.add_argument('--list', required=True, help='File danh sách thu hồi (tạo mới nếu chưa có)')
    add.add_argument('--license-id', help='Mã giấy phép (trường license_id trong license.json)')
    add.add_argument('--device-id', help='Mã máy 32 ký tự hex (trường device trong license.json)')
    add.add_argument('--reason', required=True, help='Lý do thu hồi, hiển thị cho hỗ trợ')
    add.add_argument('--key', required=True, help='Private key phát hành (PEM)')
    add.add_argument('--expected-public', help='File public key dùng để build EXE; chống ký nhầm bộ khóa')
    show = sub.add_parser('show', help='In danh sách thu hồi sau khi kiểm chứng chữ ký')
    show.add_argument('--list', required=True)
    show.add_argument('--public', help='File chứa public key base64 của bên phát hành')
    args = ap.parse_args()
    try:
        if args.cmd == 'add':
            cmd_add(args)
        else:
            cmd_show(args)
    except (RevocationError, InvalidSignature, ValueError, OSError) as exc:
        ap.error(str(exc))


if __name__ == '__main__':
    main()
