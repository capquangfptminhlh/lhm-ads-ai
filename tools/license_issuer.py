"""OFFLINE VENDOR TOOL. Never put this or the private key in the shipped Windows EXE.
Usage: python tools/license_issuer.py sign --private /secure/vendor-private-key.pem --device HEX32 --days 30 --out license.json
"""
import argparse
import base64
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import re
import secrets
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

PRODUCT='LHM_ADS_AI'


def main():
    ap=argparse.ArgumentParser(description='LHM Ads AI: offline license issuance (vendor only)')
    sub=ap.add_subparsers(dest='cmd',required=True)
    i=sub.add_parser('sign')
    i.add_argument('--private',required=True)
    i.add_argument('--device',required=True)
    i.add_argument('--days',type=int,default=30)
    i.add_argument('--out',required=True)
    i.add_argument('--plan',choices=('monthly','trial','annual'),default='monthly')
    i.add_argument('--renew-from',help='Giữ lại ngày còn hạn của giấy phép trước (bắt buộc chữ ký hợp lệ)')
    args=ap.parse_args()
    if not re.fullmatch(r'[a-f0-9]{32}',args.device):ap.error('Device ID phải 32 ký tự hex')
    if not 1<=args.days<=365:ap.error('Số ngày phải trong 1..365')
    if args.plan=='monthly' and args.days>31:ap.error('Gói tháng tối đa 31 ngày')
    key=serialization.load_pem_private_key(Path(args.private).read_bytes(),password=None)
    if not isinstance(key,Ed25519PrivateKey):ap.error('Chỉ hỗ trợ khóa Ed25519')
    now=int(time.time())
    base=now
    if args.renew_from:
        previous=json.loads(Path(args.renew_from).read_text(encoding='utf-8'))
        prior=previous.get('payload',{})
        if prior.get('product')!=PRODUCT or prior.get('device')!=args.device:
            ap.error('Giấy phép cũ không thuộc sản phẩm hoặc máy này')
        encoded_old=json.dumps(prior,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            key.public_key().verify(base64.b64decode(previous['signature'],validate=True),encoded_old)
        except Exception:ap.error('Chữ ký giấy phép cũ không hợp lệ')
        base=max(now,int(prior['expires_at']))
    if base+args.days*86400 > now+370*86400:
        ap.error('Không phát hành giấy phép trả trước quá 370 ngày')
    payload={'product':PRODUCT,'device':args.device,'license_id':secrets.token_hex(12),
             'issued_at':now,'expires_at':base+args.days*86400,'plan':args.plan}
    encoded=json.dumps(payload,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()
    license={'payload':payload,'signature':base64.b64encode(key.sign(encoded)).decode()}
    dest=Path(args.out)
    if dest.exists():ap.error('File đã tồn tại; chọn tên mới để tránh ghi đè license')
    with dest.open('x',encoding='utf-8') as f:json.dump(license,f,ensure_ascii=False,indent=2)
    print(f'Ký giấy phép thành công: {args.out}; hết hạn {datetime.fromtimestamp(payload["expires_at"],timezone.utc).isoformat()}')

if __name__=='__main__':main()
