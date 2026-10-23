"""Embed PUBLIC release update trust settings in a Windows CI build.

Use only trusted GitHub repository variables; never embed any publisher
PRIVATE key, access token, or signing material into EXE.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

TARGET = Path(__file__).resolve().parents[1] / 'windows' / 'update_config.py'


def render(url: str, public_key: str) -> str:
    url = url.strip()
    public_key = public_key.strip()
    if not url and not public_key:
        return ("# Public online-update trust is not configured for this build.\n"
                "UPDATE_MANIFEST_URL = ''\nUPDATE_PUBLIC_KEY_B64 = ''\n")
    if not url or not public_key:
        raise ValueError('Both LHM_UPDATE_MANIFEST_URL and LHM_UPDATE_PUBLIC_KEY_B64 are required')
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.fragment or parsed.port not in (None, 443)
            or any(ch.isspace() for ch in url) or len(url)>2048):
        raise ValueError('Manifest endpoint must be valid HTTPS')
    try:
        key = base64.b64decode(public_key, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError('Update public key must be base64') from exc
    if len(key) != 32:
        raise ValueError('Update public key must contain 32 raw bytes')
    return (f"UPDATE_MANIFEST_URL = {json.dumps(url)}\n"
            f"UPDATE_PUBLIC_KEY_B64 = {json.dumps(public_key)}\n")


def main():
    result = render(os.environ.get('LHM_UPDATE_MANIFEST_URL', ''),
                    os.environ.get('LHM_UPDATE_PUBLIC_KEY_B64', ''))
    TARGET.write_text(result, encoding='utf-8')
    print('Signed online updates: '+('CONFIGURED' if 'https://' in result else 'DORMANT'))


if __name__ == '__main__':
    main()
