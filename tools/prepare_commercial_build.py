"""Verify a vendor PUBLIC key before producing a commercial EXE.

Run only in the isolated Windows release runner:
  LHM_COMMERCIAL_PUBLIC_KEY_B64=<public-key> python tools/prepare_commercial_build.py --commercial

The signing PRIVATE key MUST remain offline and MUST NOT be a GitHub secret.
"""
import argparse
import base64
import os
from pathlib import Path
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT=Path(__file__).resolve().parents[1]
LICENSE=ROOT/'ads_core'/'licensing.py'
INFO=ROOT/'ads_core'/'release_info.py'

def _check_ed25519_public(value:str,name:str):
    try:
        raw=base64.b64decode(value,validate=True)
        if len(raw)!=32:
            raise ValueError('Invalid public key size')
        Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError,TypeError) as exc:
        raise ValueError(name+' must be a valid 32-byte Ed25519 public key') from exc

def prepare_commercial(public_b64:str, license_path=LICENSE, info_path=INFO, lease_public_b64:str=''):
    # Never provision from text file, command argument or source control.
    try:
        raw=base64.b64decode(public_b64,validate=True)
        if len(raw)!=32:
            raise ValueError('Invalid public key size')
        Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError,TypeError) as exc:
        raise ValueError('LHM_COMMERCIAL_PUBLIC_KEY_B64 must be a valid 32-byte Ed25519 public key') from exc
    current=license_path.read_text(encoding='utf-8')
    match=list(re.finditer(r"^PUBLIC_KEY_B64 = '[A-Za-z0-9+/=]+'$",current,re.MULTILINE))
    if len(match)!=1:
        raise RuntimeError('Cannot locate exactly one pinned license public key')
    new=current[:match[0].start()]+f"PUBLIC_KEY_B64 = '{public_b64}'"+current[match[0].end():]
    license_path.write_text(new,encoding='utf-8')
    info="EDITION = 'commercial'\n"
    if lease_public_b64:
        # Gmail mode: the EXE trusts only leases signed by the Worker's LEASE_SIGNING_KEY.
        _check_ed25519_public(lease_public_b64,'LHM_LEASE_PUBLIC_KEY_B64')
        info+=f"LEASE_PUBLIC_KEY_B64 = '{lease_public_b64}'\nCLOUD_LICENSE_MODE = 'required'\n"
    info_path.write_text(info,encoding='utf-8')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--commercial',action='store_true',required=True)
    args=ap.parse_args()
    del args
    value=os.getenv('LHM_COMMERCIAL_PUBLIC_KEY_B64','').strip()
    if not value:
        ap.error('Missing GitHub Actions secret LHM_COMMERCIAL_PUBLIC_KEY_B64; fail closed, do not ship pilot as commercial')
    lease=os.getenv('LHM_LEASE_PUBLIC_KEY_B64','').strip()
    prepare_commercial(value,lease_public_b64=lease)
    print('Commercial public key validated and pinned inside EXE. Private key was NOT loaded.')
    print('Gmail sign-in mode: '+('ON (lease public key pinned)' if lease
          else 'OFF (LHM_LEASE_PUBLIC_KEY_B64 not set, legacy offline license)'))

if __name__=='__main__':
    main()
