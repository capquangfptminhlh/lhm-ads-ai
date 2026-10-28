"""Offline, fail-closed commercial distribution evidence gate.

This tool NEVER signs executables, acquires private keys or auto-approves live
Ads tests. The signing workstation uses it to verify exact candidate provenance,
vendor and Worker lease PUBLIC key fingerprints and a human-approved checklist before
a locally installed code-signing certificate can be used.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

HEX64=re.compile(r"^[0-9a-f]{64}$")
SHA40=re.compile(r"^[0-9a-f]{40}$")
VERSION=re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
REQUIRED_CHECKS=(
    'windows_clean_install',
    'windows_restart_and_sleep',
    'backup_restore_verified',
    'google_ads_live_read',
    'meta_ads_live_read',
    'license_activation_and_renewal',
    'terms_privacy_and_support',
    'payment_and_invoicing_ready',
)
MAX_JSON=32*1024
MAX_EXE=250*1024*1024


class ReleaseGateError(ValueError):
    pass


def read_json(path:Path) -> dict:
    path=Path(path)
    if path.stat().st_size>MAX_JSON:
        raise ReleaseGateError('Manifest or acceptance JSON too large')
    try:
        item=json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeError) as exc:
        raise ReleaseGateError('Cannot decode release metadata JSON') from exc
    if not isinstance(item,dict):
        raise ReleaseGateError('Expected JSON object')
    return item


def verify_public_file(path:Path) -> str:
    try:
        token=Path(path).read_text(encoding='ascii').strip()
        raw=base64.b64decode(token,validate=True)
        if len(raw)!=32:
            raise ReleaseGateError('Vendor public key must be Ed25519 raw 32 bytes')
        Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError,UnicodeError) as exc:
        raise ReleaseGateError('Invalid vendor PUBLIC key file') from exc
    return hashlib.sha256(raw).hexdigest()


def fingerprint_from_source(root:Path) -> str:
    root=Path(root)
    lic=(root/'ads_core'/'licensing.py').read_text(encoding='utf-8')
    edition=(root/'ads_core'/'release_info.py').read_text(encoding='utf-8')
    m=re.findall(r"^PUBLIC_KEY_B64 = '([A-Za-z0-9+/=]+)'$",lic,re.MULTILINE)
    e=re.findall(r"^EDITION = '(commercial|pilot)'$",edition,re.MULTILINE)
    if len(m)!=1 or len(e)!=1:
        raise ReleaseGateError('License public key/edition source markers missing')
    raw=base64.b64decode(m[0],validate=True)
    if len(raw)!=32:
        raise ReleaseGateError('Invalid license public key length')
    return hashlib.sha256(raw).hexdigest()


def verify_candidate(exe:Path, checksum:Path, manifest:Path, public_file:Path,
                     lease_public_file:Path) -> dict:
    info=read_json(manifest)
    expected={
        'edition':'commercial-candidate',
        'builder':'nuitka',
        'license_mode':'google-only',
        'authenticode':'UNSIGNED',
        'distribution':'NOT_APPROVED_FOR_SALE',
        'product':'LHM Ads AI',
        'executable':'LHM-Ads-AI.exe',
    }
    for field,value in expected.items():
        if info.get(field)!=value:
            raise ReleaseGateError(f'Unsafe candidate manifest: {field} mismatch')
    source=info.get('source_commit')
    if not isinstance(source,str) or not SHA40.fullmatch(source):
        raise ReleaseGateError('Missing 40-hex GitHub source commit')
    version=info.get('product_version')
    if not isinstance(version,str) or not VERSION.fullmatch(version):
        raise ReleaseGateError('Missing canonical semver in candidate manifest')
    fingerprint=info.get('license_public_key_sha256')
    if not isinstance(fingerprint,str) or not HEX64.fullmatch(fingerprint):
        raise ReleaseGateError('Missing vendor public key fingerprint')
    # Commercial builds must pin the Worker-signed Gmail lease trust anchor.
    # This is derived from the source PRE-compilation by CI, never supplied by
    # a user's renderer or payment page. No legacy-license fallback is allowed.
    lease_fingerprint=info.get('lease_public_key_sha256')
    if not isinstance(lease_fingerprint,str) or not HEX64.fullmatch(lease_fingerprint):
        raise ReleaseGateError('Missing verified Gmail lease public key fingerprint')
    # Manifest metadata is NOT proof of the trust anchor by itself.
    if lease_fingerprint!=verify_public_file(lease_public_file):
        raise ReleaseGateError('Gmail lease signing key does not match trusted Worker public key')
    if fingerprint!=verify_public_file(public_file):
        raise ReleaseGateError('Commercial EXE public key fingerprint does not match vendor key')
    if not exe.is_file() or not 0<exe.stat().st_size<=MAX_EXE or exe.name!='LHM-Ads-AI.exe':
        raise ReleaseGateError('Expected candidate EXE missing or oversized')
    with exe.open('rb') as fd:
        sha=hashlib.file_digest(fd,'sha256').hexdigest()
    if sha != info.get('sha256'):
        raise ReleaseGateError('Candidate SHA256 differs from CI manifest')
    lines=Path(checksum).read_text(encoding='ascii').strip().splitlines()
    if len(lines)!=1 or lines[0]!=f'{sha}  LHM-Ads-AI.exe':
        raise ReleaseGateError('Candidate SHA256 checksum file mismatch')
    return info


def verify_approval(path:Path, manifest:dict) -> dict:
    data=read_json(path)
    if data.get('product')!='LHM Ads AI' or data.get('source_commit')!=manifest['source_commit']:
        raise ReleaseGateError('Owner approval is not for this product/commit')
    if data.get('product_version')!=manifest['product_version']:
        raise ReleaseGateError('Owner approval does not match product version')
    if data.get('owner_approved') is not True:
        raise ReleaseGateError('Owner has not explicitly approved release')
    if not isinstance(data.get('approved_by'),str) or len(data['approved_by'].strip())<3:
        raise ReleaseGateError('Owner approval needs identifying name/reference')
    try:
        when=datetime.fromisoformat(data['approved_at_utc'].replace('Z','+00:00'))
        if when.tzinfo is None:
            raise ValueError('Timestamp without timezone')
        now=datetime.now(timezone.utc)
        if not now.year-1<=when.year<=now.year or when>now:
            raise ValueError('Invalid approval timestamp')
    except (KeyError,ValueError,TypeError,AttributeError):
        raise ReleaseGateError('Invalid approval UTC timestamp') from None
    checks=data.get('checks')
    if not isinstance(checks,dict) or set(checks)!=set(REQUIRED_CHECKS):
        raise ReleaseGateError('Missing mandatory acceptance checks')
    for name in REQUIRED_CHECKS:
        check=checks[name]
        if not isinstance(check,dict) or check.get('passed') is not True:
            raise ReleaseGateError(f'Acceptance NOT_RUN or FAIL: {name}')
        evidence=check.get('evidence_ref')
        if not isinstance(evidence,str) or not 6<=len(evidence)<=256:
            raise ReleaseGateError(f'Missing acceptance evidence reference: {name}')
        if any(x in evidence for x in ('\n','\r','\\')):
            raise ReleaseGateError(f'Invalid evidence reference: {name}')
    return data


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='Verify LHM Ads AI commercial build provenance')
    sub=parser.add_subparsers(dest='cmd',required=True)
    key=sub.add_parser('fingerprint-from-source',help='Public key hash only, safe in CI')
    key.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    inspect=sub.add_parser('inspect-candidate',help='Verify exact CI candidate WITHOUT approving distribution')
    for flag in ('exe','checksum','manifest','vendor-public','lease-public'):
        inspect.add_argument('--'+flag,required=True,type=Path)
    check=sub.add_parser('verify-candidate',help='Verify unsigned candidate, owner public key and acceptance')
    check.add_argument('--exe',type=Path,required=True)
    check.add_argument('--checksum',type=Path,required=True)
    check.add_argument('--manifest',type=Path,required=True)
    check.add_argument('--vendor-public',type=Path,required=True)
    check.add_argument('--lease-public',type=Path,required=True)
    check.add_argument('--acceptance',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.cmd=='fingerprint-from-source':
            print(fingerprint_from_source(args.root))
        elif args.cmd=='inspect-candidate':
            info=verify_candidate(args.exe,args.checksum,args.manifest,args.vendor_public,args.lease_public)
            print('PASS: unsigned Commercial Candidate verified for '+info['source_commit'])
            print('Version: '+info['product_version'])
            print('Vendor public key SHA256: '+info['license_public_key_sha256'])
            print('NOT_APPROVED_FOR_SALE: owner live acceptance/signoff still required')
        else:
            manifest=verify_candidate(args.exe,args.checksum,args.manifest,args.vendor_public,args.lease_public)
            verify_approval(args.acceptance,manifest)
            print('PASS: candidate hash, version, source commit, vendor public key and manual acceptance match')
    except (OSError,ReleaseGateError) as exc:
        parser.error(str(exc))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
