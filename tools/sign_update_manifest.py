"""Offline owner-side signer for the public desktop update feed.

Private Ed25519 keys MUST remain on the owner's machine. This utility never
uploads keys or packages to GitHub and cannot publish a release automatically.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from getpass import getpass
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ads_core.updater import canonical_manifest, _validate_manifest
from windows.online_update import _https_url


def sign(executable: Path, version: str, url: str, notes: str,
         private_key_file: Path, password: str) -> dict:
    _https_url(url, executable=True)
    exe = Path(executable)
    if exe.name.lower() != 'lhm-ads-ai.exe' or not exe.is_file():
        raise ValueError('Expected compiled LHM-Ads-AI.exe')
    if not password:
        raise ValueError('An encrypted publisher signing key is required')
    key = serialization.load_pem_private_key(
        Path(private_key_file).read_bytes(), password=password.encode('utf-8'))
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Update publisher key must be Ed25519')
    with exe.open('rb') as fd:
        sha = hashlib.file_digest(fd, 'sha256').hexdigest()
    manifest = {'version': version, 'download_url': url, 'sha256': sha,
                'notes': notes, 'issued_at': int(datetime.now(timezone.utc).timestamp())}
    _validate_manifest(manifest)
    return {'manifest': manifest,
            'signature': base64.b64encode(key.sign(canonical_manifest(manifest))).decode('ascii')}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline sign a tested EXE update manifest')
    parser.add_argument('--exe', required=True, type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--download-url', required=True)
    parser.add_argument('--notes', default='Cập nhật LHM Ads AI.')
    parser.add_argument('--private', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error('Refusing to overwrite existing manifest')
    secret = getpass('Mật khẩu khóa ký cập nhật (không lưu): ')
    result = sign(args.exe, args.version, args.download_url, args.notes, args.private, secret)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n',
                        encoding='utf-8')
    print('Signed update manifest created: '+str(args.out))
    print('EXE SHA-256: '+result['manifest']['sha256'])


if __name__ == '__main__':
    main()
