"""SELLER-SIDE TOOL. Kiểm tra bản cập nhật đã ký của LHM Ads AI (chỉ kiểm tra).

Công cụ này là phía "người gọi" mà ads_core/updater.py cố ý chưa có:
updater chỉ KIỂM CHỨNG một manifest ngoại tuyến (nó không bao giờ chạm
mạng), còn file này — chạy trên máy bên bán — tải manifest đã ký từ URL
do chính bên bán cấu hình rồi đưa cho updater kiểm chứng. Nó CHỈ BÁO CÁO:
không tải bản cài đặt, không cài đặt, không thực thi bất cứ thứ gì.
download_url trong manifest được in ra để bên bán tự đối chiếu/tải tay.

Trạng thái chờ (dormant) — mặc định và là hành vi an toàn:
  Chưa cấu hình URL manifest hoặc khóa công khai thì lệnh in rõ thông báo
  "chưa được kích hoạt", thoát mã 2 và KHÔNG gọi mạng dưới bất kỳ hình
  thức nào — giống hệt mẫu dormant của tools/payos.py / tools/einvoice.py.

Cấu hình (cờ lệnh ưu tiên hơn biến môi trường):
  --url     / LHM_UPDATE_MANIFEST_URL : URL https của manifest đã ký,
              hoặc đường dẫn file cục bộ để kiểm thử ngoại tuyến.
  --pubkey  / LHM_UPDATE_PUBKEY       : khóa công khai Ed25519 của nhà
              phát hành cập nhật, dạng hex (64 ký tự, 32 byte thô), dạng
              base64 (32 byte thô — định dạng gốc của ads_core.updater),
              hoặc đường dẫn file chứa một trong hai dạng trên.
  Để không lệch cấu hình với app, LHM_UPDATE_PUBLIC_KEY (biến gốc của
  ads_core.updater, dạng base64) cũng được chấp nhận làm nguồn dự phòng
  cho khóa công khai khi LHM_UPDATE_PUBKEY chưa đặt.

Định dạng máy chủ phải trả về (một file JSON tĩnh là đủ):
  {
    "manifest": {"version": "1.2.3",
                 "download_url": "https://.../setup.exe",
                 "sha256": "<64 hex thường>",
                 "notes": "Ghi chú phát hành",
                 "issued_at": 1760000000},
    "signature": "<base64: chữ ký Ed25519 tách rời trên JSON canonical
                   của manifest — xem ads_core.updater.canonical_manifest>"
  }
  Khóa RIÊNG ký manifest không bao giờ nằm trong repo/EXE/CI: ký trên máy
  ngoại tuyến của chủ phần mềm, chỉ đăng file JSON ở trên lên máy chủ.

Mã thoát:
  0 — đã kiểm chứng: có bản mới (update_available) hoặc đã mới nhất
      (up_to_date). Hai trạng thái in khác nhau rõ rệt.
  1 — manifest không hợp lệ (invalid): tải lỗi, sai định dạng phong bì,
      chữ ký sai, trường manifest sai, hoặc khóa công khai không đọc được.
  2 — dormant: chưa cấu hình URL/khóa (không gọi mạng).

Usage:
  python tools/update_check.py --current 1.2.3
  python tools/update_check.py --current 1.2.3 --url https://example.com/update.json --pubkey <hex|base64|file>
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ads_core import updater  # noqa: E402

ENV_MANIFEST_URL = 'LHM_UPDATE_MANIFEST_URL'
ENV_PUBKEY = 'LHM_UPDATE_PUBKEY'

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_DORMANT = 2

_HEX64_RE = re.compile(r'^[0-9a-fA-F]{64}$')
_PATH_HINT_RE = re.compile(r'(\.txt|\.b64|\.pem|\.pub|\.key)$', re.IGNORECASE)


class UpdateCheckError(ValueError):
    """Lỗi phía CLI: tải manifest, phong bì, hoặc khóa công khai không đọc được."""


def _force_utf8_streams():
    # Windows consoles/pipes default to a legacy codepage (cp1252/cp437)
    # that cannot encode Vietnamese; these CLIs print Vietnamese status
    # text, so pin stdout/stderr to UTF-8 when the runtime allows it.
    import sys as _sys
    for stream in (_sys.stdout, _sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def resolve_public_key_b64(value: str) -> str:
    """Chuẩn hoá --pubkey/LHM_UPDATE_PUBKEY về base64 mà updater yêu cầu.

    Chấp nhận: hex 64 ký tự (32 byte thô), base64 32 byte thô, hoặc đường
    dẫn file chứa một trong hai dạng đó (file public key của bên bán,
    vd. file do license_issuer tạo, chứa base64). Ngoài việc chuyển mã
    hex->base64, hàm này KHÔNG chứa logic chữ ký nào — kiểm chứng vẫn do
    ads_core.updater thực hiện.
    """
    text = (value or '').strip()
    if not text:
        raise UpdateCheckError('Khóa công khai cập nhật trống.')
    candidate = Path(text)
    if candidate.is_file():
        text = candidate.read_text(encoding='utf-8').strip()
    if _HEX64_RE.match(text):
        return base64.b64encode(binascii.unhexlify(text)).decode('ascii')
    # Dạng gốc của updater: base64 của đúng 32 byte thô. Phải thử TRƯỚC
    # mọi suy luận "trông như đường dẫn": bảng chữ base64 có chứa '/'
    # nên một khóa base64 hợp lệ rất thường chứa ký tự giống đường dẫn.
    try:
        raw = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error):
        raw = None
    if raw is not None and len(raw) == 32:
        return text
    if raw is not None:
        raise UpdateCheckError(
            f'Khóa công khai cập nhật phải dài 32 byte (nhận {len(raw)} byte).')
    if '/' in text or '\\' in text or _PATH_HINT_RE.search(text):
        # Không phải hex/base64 và trông như đường dẫn nhưng file không
        # tồn tại: báo rõ thay vì để lỗi base64 khó hiểu ở tầng dưới.
        raise UpdateCheckError(
            f'Không tìm thấy file khóa công khai cập nhật: {text}')
    raise UpdateCheckError(
        'Khóa công khai cập nhật phải là hex 64 ký tự, base64 của '
        '32 byte, hoặc đường dẫn file chứa một trong hai dạng đó.')


def fetch_manifest_payload(url: str):
    """Tải phong bì manifest đã ký. Đây là lần chạm mạng DUY NHẤT của CLI.

    URL http(s) được tải bằng httpx; một đường dẫn file cục bộ được đọc
    trực tiếp (để bên bán kiểm thử manifest trước khi đăng lên máy chủ).
    Trả về đối tượng JSON đã giải mã; mọi lỗi đều thành UpdateCheckError.
    """
    if not url.startswith(('http://', 'https://')):
        path = Path(url).expanduser()
        if not path.is_file():
            raise UpdateCheckError(
                f'Không tải được manifest cập nhật: {url!r} không phải '
                'URL http(s) cũng không phải file cục bộ tồn tại.')
        try:
            return json.loads(path.read_bytes().decode('utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdateCheckError(
                f'Không đọc được manifest cập nhật từ file {path}: {exc}') from exc
    try:
        response = httpx.get(url, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise UpdateCheckError(
            f'Không tải được manifest cập nhật từ {url}: {exc}') from exc


def extract_manifest_and_signature(payload) -> tuple[bytes, str]:
    """Tách (manifest_bytes, signature_b64) khỏi phong bì JSON đã tải.

    Chỉ là tách dữ liệu: chữ ký được kiểm chứng bởi ads_core.updater,
    không phải ở đây.
    """
    if not isinstance(payload, dict):
        raise UpdateCheckError(
            'Manifest cập nhật phải là một đối tượng JSON dạng '
            '{"manifest": {...}, "signature": "<base64>"}.')
    signature = payload.get('signature') or payload.get('signature_b64')
    manifest = payload.get('manifest')
    if manifest is None or not signature:
        raise UpdateCheckError(
            'Manifest cập nhật thiếu trường "manifest" hoặc "signature" '
            'trong phong bì JSON.')
    if isinstance(manifest, dict):
        manifest_bytes = json.dumps(manifest).encode('utf-8')
    elif isinstance(manifest, str):
        manifest_bytes = manifest.encode('utf-8')
    else:
        raise UpdateCheckError('Trường "manifest" phải là đối tượng JSON.')
    if not isinstance(signature, str):
        raise UpdateCheckError('Trường "signature" phải là chuỗi base64.')
    return manifest_bytes, signature


def run_check(current_version: str, manifest_url: str, public_key_b64: str,
              *, fetcher=None) -> dict:
    """Wrapper nhỏ quanh ads_core.updater.check_for_update.

    updater cố ý không có tầng tải manifest (nó chỉ kiểm chứng ngoại
    tuyến), nên wrapper này — và chỉ wrapper này — ghép bước tải phong bì
    với bước kiểm chứng có sẵn. Mọi quyết định về chữ ký/phiên bản đều là
    của updater; wrapper không tự cài lại logic chữ ký nào.
    """
    payload = (fetcher or fetch_manifest_payload)(manifest_url)
    manifest_bytes, signature_b64 = extract_manifest_and_signature(payload)
    return updater.check_for_update(
        current_version, manifest_bytes, signature_b64,
        public_key_b64=public_key_b64)


def main(argv=None, environ=None) -> int:
    _force_utf8_streams()
    parser = argparse.ArgumentParser(
        description='LHM Ads AI: kiểm tra bản cập nhật đã ký (chỉ báo cáo, '
                    'không tải/không cài đặt)')
    parser.add_argument('--current', required=True,
                        help='Phiên bản đang dùng, dạng semver X.Y.Z (vd. 1.2.3)')
    parser.add_argument('--url',
                        help='URL manifest đã ký (mặc định: biến môi trường '
                             + ENV_MANIFEST_URL + ')')
    parser.add_argument('--pubkey',
                        help='Khóa công khai Ed25519: hex 64 ký tự, base64, '
                             'hoặc file chứa khóa (mặc định: biến môi trường '
                             + ENV_PUBKEY + ')')
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ

    manifest_url = (args.url or env.get(ENV_MANIFEST_URL) or '').strip()
    pubkey_value = (args.pubkey or env.get(ENV_PUBKEY)
                    or env.get(updater.ENV_PUBLIC_KEY) or '').strip()

    missing = []
    if not manifest_url:
        missing.append('--url / ' + ENV_MANIFEST_URL)
    if not pubkey_value:
        missing.append('--pubkey / ' + ENV_PUBKEY)
    if missing:
        # Dormant: tuyệt đối không gọi mạng khi chưa cấu hình đủ.
        print('Kiểm tra cập nhật chưa được kích hoạt: thiếu '
              + ' và '.join(missing) + '.')
        print('Phần mềm vẫn hoạt động bình thường; bản phát hành mới hiện '
              'được phân phối thủ công.')
        print('Để kích hoạt, bên bán cấu hình URL manifest đã ký và khóa '
              'công khai của nhà phát hành cập nhật (xem docs/UPDATE_CHECK.md).')
        return EXIT_DORMANT

    try:
        public_key_b64 = resolve_public_key_b64(pubkey_value)
    except UpdateCheckError as exc:
        print(f'invalid: Khóa công khai cập nhật không hợp lệ: {exc}')
        return EXIT_INVALID

    try:
        result = run_check(args.current, manifest_url, public_key_b64)
    except UpdateCheckError as exc:
        print(f'invalid: Manifest không hợp lệ: {exc}')
        return EXIT_INVALID

    status = result.get('status')
    if status == 'update_available':
        print(f"update_available: {result.get('message', '')}")
        print(f"  Phiên bản mới: {result.get('version')}")
        print(f"  Tải tại: {result.get('download_url')}")
        print(f"  SHA256 bản cài đặt: {result.get('sha256')}")
        if result.get('notes'):
            print(f"  Ghi chú: {result['notes']}")
        print('Công cụ này chỉ báo cáo — hãy tải và cài đặt thủ công từ '
              'địa chỉ trên sau khi đối chiếu SHA256.')
        return EXIT_OK
    if status == 'up_to_date':
        print(f"up_to_date: {result.get('message', '')}")
        return EXIT_OK
    if status == 'not_configured':
        # Phòng thủ: run_check luôn truyền khóa tường minh nên nhánh này
        # không nên xảy ra; nếu xảy ra vẫn giữ đúng ngữ nghĩa dormant.
        print(result.get('message') or
              'Kiểm tra cập nhật chưa được kích hoạt.')
        return EXIT_DORMANT
    print(f"invalid: Manifest không hợp lệ: {result.get('message', '')}")
    return EXIT_INVALID


if __name__ == '__main__':
    sys.exit(main())
