"""Vendor-only commercial release without an Authenticode certificate.

This does NOT make Windows trust the EXE. The publisher signs a domain-separated
release manifest with their offline Ed25519 license key. Customers must verify
against the publisher public key obtained independently, NOT just one inside ZIP.

The owner must approve all existing live acceptance checks before packaging.
"""
from __future__ import annotations

import argparse
import base64
from getpass import getpass
import hashlib
import hmac
import json
from pathlib import Path
import re
import sys
import zipfile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.release_gate import (ReleaseGateError, MAX_EXE, read_json,
                                verify_approval, verify_candidate)

DOMAIN=b'LHM_ADS_AI_COMMERCIAL_UNSIGNED_RELEASE_V1\n'
EXPECTED_MEMBERS={
    'LHM-Ads-AI.exe', 'LHM-Ads-AI.sha256',
    'signed-release-manifest.json', 'README-CUSTOMER.txt'
}
MAX_PACKAGE=300*1024*1024

def canonical(payload:dict)->bytes:
    return json.dumps(payload,sort_keys=True,separators=(',',':'),
                      ensure_ascii=True).encode('utf-8')

def _trusted_key(public_file:Path)->bytes:
    try:
        raw=base64.b64decode(Path(public_file).read_text(encoding='ascii').strip(),
                             validate=True)
        if len(raw)!=32: raise ValueError('Not an Ed25519 32-byte key')
        Ed25519PublicKey.from_public_bytes(raw)
        return raw
    except (ValueError,UnicodeError,TypeError) as exc:
        raise ReleaseGateError('Invalid trusted vendor public key') from exc

def _private_key(private_file:Path, password:str)->Ed25519PrivateKey:
    data=Path(private_file).read_bytes()
    if b'ENCRYPTED PRIVATE KEY' not in data or not password:
        raise ReleaseGateError('Vendor private key MUST be encrypted on disk')
    try:
        key=serialization.load_pem_private_key(data,password=password.encode('utf-8'))
    except (ValueError,TypeError):
        raise ReleaseGateError('Could not unlock encrypted vendor key') from None
    if not isinstance(key,Ed25519PrivateKey):
        raise ReleaseGateError('Expected Ed25519 vendor private key')
    return key

def create_package(*,exe:Path,checksum:Path,manifest:Path,public_file:Path,
                   lease_public_file:Path,acceptance:Path,private_file:Path,password:str,out:Path,
                   accept_unsigned:bool=False)->dict:
    if accept_unsigned is not True:
        raise ReleaseGateError('Owner must explicitly accept unsigned Windows EXE')
    candidate=verify_candidate(exe,checksum,manifest,public_file,lease_public_file)
    verify_approval(acceptance,candidate)
    key=_private_key(private_file,password)
    trusted=_trusted_key(public_file)
    derived=key.public_key().public_bytes(encoding=serialization.Encoding.Raw,
                                           format=serialization.PublicFormat.Raw)
    if not hmac.compare_digest(trusted,derived):
        raise ReleaseGateError('Private issuer key does not match EXE public key')
    out=Path(out).expanduser().resolve()
    if out.exists():
        raise FileExistsError('Will not overwrite an existing commercial release')
    if not out.parent.is_dir():
        raise ReleaseGateError('Output folder must already exist')
    if not re.fullmatch(r'LHM-Ads-AI-\d+\.\d+\.\d+-COMMERCIAL-UNSIGNED\.zip',out.name):
        raise ReleaseGateError('Use explicit COMMERCIAL-UNSIGNED filename, never SIGNED')
    expected=f"LHM-Ads-AI-{candidate['product_version']}-COMMERCIAL-UNSIGNED.zip"
    if out.name!=expected:
        raise ReleaseGateError('Output version does not match verified candidate')
    release={
        'product':'LHM Ads AI',
        'edition':'commercial-unsigned',
        'product_version':candidate['product_version'],
        'source_commit':candidate['source_commit'],
        'executable':'LHM-Ads-AI.exe',
        'sha256':candidate['sha256'],
        'license_public_key_sha256':candidate['license_public_key_sha256'],
        'lease_public_key_sha256':candidate['lease_public_key_sha256'],
        'license_mode':candidate['license_mode'],
        'builder':candidate['builder'],
        'authenticode':'UNSIGNED',
        'distribution':'OWNER_APPROVED_UNSIGNED',
        'manifest_signature_algorithm':'Ed25519 domain-separated LHM release v1',
        'publisher_warning':'Windows shows Unknown publisher / SmartScreen warnings. '
                            'No Microsoft Authenticode trust; do not bypass security warnings.',
        'license_and_live_acceptance':'Seller must keep actual evidence separately.',
    }
    signature=key.sign(DOMAIN+canonical(release))
    envelope={'manifest':release,'signature':base64.b64encode(signature).decode('ascii')}
    readme='\n'.join([
        'LHM Ads AI - COMMERCIAL, UNSIGNED WINDOWS EXE',
        'Publisher intentionally chose no Microsoft Authenticode certificate.',
        'Windows may show Unknown publisher/SmartScreen warnings.',
        'Do not disable Windows protections or bypass security warnings.',
        'Before running, verify SHA256 and Ed25519 manifest against the',
        'vendor public key obtained from an independent official source.',
        f"Product version: {release['product_version']}",
        f"Source Git commit: {release['source_commit']}",
        f"EXE SHA256: {release['sha256']}",
        f"Vendor public key SHA256: {release['license_public_key_sha256']}",
        'Never give Ads API tokens, bank credentials or backup passwords to the seller.',
        'The signed manifest DOES NOT replace an Authenticode certificate.',
        ''
    ])
    try:
        with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as archive:
            archive.write(exe,'LHM-Ads-AI.exe')
            archive.write(checksum,'LHM-Ads-AI.sha256')
            archive.writestr('signed-release-manifest.json',
                             json.dumps(envelope,sort_keys=True,indent=2,ensure_ascii=True)+'\n')
            archive.writestr('README-CUSTOMER.txt',readme)
        verify_package(out,public_file,lease_public_file)
    except Exception:
        out.unlink(missing_ok=True)
        raise
    return {'path':str(out),'version':release['product_version'],
            'authenticode':'UNSIGNED','manifest_signature':'Ed25519',
            'sha256':release['sha256']}

def verify_package(package:Path,trusted_public:Path,lease_public_file:Path)->dict:
    package=Path(package)
    if not package.is_file() or not 0<package.stat().st_size<=MAX_PACKAGE:
        raise ReleaseGateError('Missing/oversized release ZIP')
    trusted=_trusted_key(trusted_public)
    with zipfile.ZipFile(package,'r') as archive:
        parts=archive.infolist()
        if len(parts)!=4 or {part.filename for part in parts}!=EXPECTED_MEMBERS:
            raise ReleaseGateError('Unexpected or duplicate package members')
        for part in parts:
            if part.is_dir() or part.file_size>MAX_EXE or part.compress_size>MAX_PACKAGE:
                raise ReleaseGateError('Malformed or oversized ZIP member')
        envelope=json.loads(archive.read('signed-release-manifest.json'))
        if not isinstance(envelope,dict) or set(envelope)!={'manifest','signature'}:
            raise ReleaseGateError('Invalid signed manifest envelope')
        data=envelope['manifest']
        if not isinstance(data,dict) or data.get('edition')!='commercial-unsigned' or data.get('authenticode')!='UNSIGNED':
            raise ReleaseGateError('Unsigned commercial edition markers are required')
        if data.get('distribution')!='OWNER_APPROVED_UNSIGNED':
            raise ReleaseGateError('Distribution approval missing')
        if data.get('builder')!='nuitka' or data.get('license_mode')!='google-only':
            raise ReleaseGateError('Commercial release must be Nuitka with verified Gmail-only licensing')
        if not isinstance(data.get('lease_public_key_sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',data['lease_public_key_sha256']):
            raise ReleaseGateError('Missing signed Gmail lease public key fingerprint')
        if data.get('license_public_key_sha256')!=hashlib.sha256(trusted).hexdigest():
            raise ReleaseGateError('Untrusted vendor key fingerprint')
        if data.get('lease_public_key_sha256')!=hashlib.sha256(_trusted_key(lease_public_file)).hexdigest():
            raise ReleaseGateError('Untrusted Worker lease public key fingerprint')
        try:
            sig=base64.b64decode(envelope['signature'],validate=True)
            Ed25519PublicKey.from_public_bytes(trusted).verify(sig,DOMAIN+canonical(data))
        except (ValueError,InvalidSignature,TypeError) as exc:
            raise ReleaseGateError('Invalid vendor Ed25519 release signature') from exc
        with archive.open('LHM-Ads-AI.exe') as fd:
            file_hash=hashlib.file_digest(fd,'sha256').hexdigest()
        if file_hash!=data.get('sha256'):
            raise ReleaseGateError('Packaged EXE SHA256 mismatch')
        if archive.read('LHM-Ads-AI.sha256').decode('ascii').strip()!=f"{file_hash}  LHM-Ads-AI.exe":
            raise ReleaseGateError('Packaged checksum mismatch')
    return data

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description='LHM commercial WITHOUT Authenticode; signed Ed25519 manifest')
    commands=parser.add_subparsers(dest='command',required=True)
    pkg=commands.add_parser('package')
    for flag in ('exe','checksum','manifest','vendor-public','lease-public','acceptance','private','out'):
        pkg.add_argument('--'+flag,required=True,type=Path)
    pkg.add_argument('--accept-unsigned-windows',action='store_true',
                     help='Explicit owner opt-out of Windows Authenticode')
    verify=commands.add_parser('verify')
    verify.add_argument('--zip',required=True,type=Path)
    verify.add_argument('--trusted-vendor-public',required=True,type=Path)
    verify.add_argument('--trusted-lease-public',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        if args.command=='verify':
            info=verify_package(args.zip,args.trusted_vendor_public,args.trusted_lease_public)
            print('PASS: publisher Ed25519 release signature and EXE SHA256 valid; Windows Authenticode UNSIGNED')
        else:
            password=getpass('Mật khẩu mở khóa riêng của bên phát hành (ẩn): ')
            info=create_package(exe=args.exe,checksum=args.checksum,
                       manifest=args.manifest,public_file=args.vendor_public,
                       lease_public_file=args.lease_public,
                       acceptance=args.acceptance,private_file=args.private,
                       password=password,out=args.out,
                       accept_unsigned=args.accept_unsigned_windows)
            print('PASS: OWNER APPROVED commercial package created; NO Windows Authenticode')
            print(info['path'])
    except (OSError,ValueError,zipfile.BadZipFile,KeyError,TypeError) as exc:
        parser.error(str(exc))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
