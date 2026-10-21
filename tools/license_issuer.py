"""OFFLINE VENDOR TOOL. Never put this or the private key in the shipped Windows EXE.
Usage: python tools/license_issuer.py sign --private /secure/vendor-private-key.pem --device HEX32 --days 30 --out license.json
"""
import argparse
import getpass
import os
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


def public_b64(key):
    raw=key.public_key().public_bytes(encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode('ascii')


def create_vendor_keys(private_path:Path,public_path:Path,password:str):
    """Create a unique, password-encrypted vendor signing key; never overwrite."""
    if len(password)<16:
        raise ValueError('Mật khẩu khóa phát hành phải ít nhất 16 ký tự')
    if private_path.resolve()==public_path.resolve():
        raise ValueError('Public/private paths must differ')
    if private_path.exists() or public_path.exists():
        raise FileExistsError('Không ghi đè khóa đã tồn tại; mất khóa cũ sẽ làm hỏng gia hạn')
    key=Ed25519PrivateKey.generate()
    secret=key.private_bytes(encoding=serialization.Encoding.PEM,
          format=serialization.PrivateFormat.PKCS8,
          encryption_algorithm=serialization.BestAvailableEncryption(password.encode('utf-8')))
    private_path.parent.mkdir(parents=True,exist_ok=True)
    public_path.parent.mkdir(parents=True,exist_ok=True)
    descriptor=os.open(private_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        with os.fdopen(descriptor,'wb') as output:
            output.write(secret)
            output.flush();os.fsync(output.fileno())
        with public_path.open('x',encoding='ascii') as output:
            output.write(public_b64(key)+'\n')
    except Exception:
        private_path.unlink(missing_ok=True)
        raise
    return public_b64(key)



def main():
    ap=argparse.ArgumentParser(description='LHM Ads AI: offline license issuance (vendor only)')
    sub=ap.add_subparsers(dest='cmd',required=True)
    gen=sub.add_parser('keygen',help='Tạo khóa ký bí mật có mật khẩu trên máy bên bán')
    gen.add_argument('--private',required=True)
    gen.add_argument('--public',required=True,help='File chứa public key base64 cho CI secret')
    i=sub.add_parser('sign')
    i.add_argument('--private',required=True)
    i.add_argument('--expected-public',help='File public key dùng để build EXE; chống ký nhầm bộ khóa')
    i.add_argument('--device',required=True)
    i.add_argument('--days',type=int,default=30)
    i.add_argument('--out',required=True)
    i.add_argument('--plan',choices=('monthly','trial','annual'),default='monthly')
    i.add_argument('--renew-from',help='Giữ lại ngày còn hạn của giấy phép trước (bắt buộc chữ ký hợp lệ)')
    args=ap.parse_args()
    if args.cmd=='keygen':
        password=getpass.getpass('Đặt mật khẩu bảo vệ private key (ít nhất 16 ký tự): ')
        confirm=getpass.getpass('Nhập lại mật khẩu: ')
        if password!=confirm:ap.error('Mật khẩu không khớp')
        try:
            key_b64=create_vendor_keys(Path(args.private),Path(args.public),password)
        except (ValueError,FileExistsError,OSError) as exc:
            ap.error(str(exc))
        print('Đã tạo khóa phát hành riêng. Giữ private key và mật khẩu ở hai nơi an toàn.')
        print('Chỉ chép nội dung file PUBLIC key vào GitHub Actions secret LHM_COMMERCIAL_PUBLIC_KEY_B64.')
        print('Public key fingerprint SHA256: '+__import__('hashlib').sha256(base64.b64decode(key_b64)).hexdigest()[:16])
        return
    if not re.fullmatch(r'[a-f0-9]{32}',args.device):ap.error('Device ID phải 32 ký tự hex')
    if not 1<=args.days<=365:ap.error('Số ngày phải trong 1..365')
    if args.plan=='monthly' and args.days>31:ap.error('Gói tháng tối đa 31 ngày')
    encoded_private=Path(args.private).read_bytes()
    password=(getpass.getpass('Mật khẩu khóa phát hành: ').encode('utf-8')
              if b'ENCRYPTED PRIVATE KEY' in encoded_private else None)
    key=serialization.load_pem_private_key(encoded_private,password=password)
    if not isinstance(key,Ed25519PrivateKey):ap.error('Chỉ hỗ trợ khóa Ed25519')
    if args.expected_public:
        expected=Path(args.expected_public).read_text(encoding='ascii').strip()
        if expected!=public_b64(key):
            ap.error('Khóa private không khớp public key của EXE; không phát hành license sai máy')
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
        if not isinstance(prior.get('expires_at'),int) or prior['expires_at']<prior.get('issued_at',0):
            ap.error('Ngày hết hạn trong license cũ không hợp lệ')
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
