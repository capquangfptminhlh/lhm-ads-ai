"""Vendor-assisted OFFLINE restore. Never run while desktop app is open.

python tools/customer_restore.py --backup customer.lhmbak --destination EMPTY_DIR

User enters backup passphrase privately. Never send passphrase to support.
The new Windows user must re-activate the device-bound license after restore.
"""
import argparse
from getpass import getpass
from pathlib import Path
from ads_core.secure_backup import restore_into_empty_directory, MAX_DATABASE_BYTES


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

def main():
    _force_utf8_streams()
    parser=argparse.ArgumentParser(description='LHM Ads AI offline customer restore')
    parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True,
                        help='Must be a NEW, EMPTY local data directory')
    args=parser.parse_args()
    password=getpass('Nhập mật khẩu sao lưu (ẩn): ')
    try:
        if args.backup.stat().st_size>MAX_DATABASE_BYTES+2048:
            parser.error('File backup lớn hơn 64 MB')
        restore_into_empty_directory(args.backup.read_bytes(),password,args.destination)
    except (OSError,ValueError,FileExistsError) as exc:
        parser.error(str(exc))
    print('Đã khôi phục. Đăng nhập lại và yêu cầu cấp bản quyền cho mã máy mới.')
    print('Bản sao lưu không chuyển session, Device ID, license hay tác nhân tự chạy.')


if __name__=='__main__':main()
