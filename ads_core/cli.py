"""Local-only administrator bootstrap. Never expose via HTTP."""
import argparse
import getpass
import sys
from .db import init_db,connection
from .security import hash_password

def _force_utf8_streams():
    # Windows consoles/pipes default to a legacy codepage (cp1252/cp437)
    # that cannot encode Vietnamese; this CLI prompts and reports in
    # Vietnamese, so pin stdout/stderr to UTF-8 when the runtime allows it.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass

def main():
    _force_utf8_streams()
    p = argparse.ArgumentParser(description='LHM Ads AI setup CLI')
    sub = p.add_subparsers(dest='command', required=True)
    u = sub.add_parser('create-admin')
    u.add_argument('--email', required=True)
    u.add_argument('--org', default='main')
    args = p.parse_args()
    init_db()
    if args.command == 'create-admin':
        password = getpass.getpass('Nhập mật khẩu admin (ít nhất 12 ký tự): ')
        confirm = getpass.getpass('Nhập lại mật khẩu: ')
        if password != confirm:
            raise SystemExit('Mật khẩu không trùng khớp')
        with connection() as db:
            db.execute('INSERT INTO users (email,password_hash,org_id,role) VALUES (?,?,?,?)',
                       (args.email.lower().strip(), hash_password(password), args.org, 'admin'))
        print('Đã tạo admin. Không tiết lộ mật khẩu.')
if __name__ == '__main__':
    main()
