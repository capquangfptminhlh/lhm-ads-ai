"""Vendor-assisted OFFLINE restore. Never run while desktop app is open.

python tools/customer_restore.py --backup customer.lhmbak --destination EMPTY_DIR

User enters backup passphrase privately. Never send passphrase to support.
The new Windows user must re-activate the device-bound license after restore.
"""
import argparse
from getpass import getpass
from pathlib import Path
from ads_core.secure_backup import restore_into_empty_directory, MAX_DATABASE_BYTES


def main():
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
