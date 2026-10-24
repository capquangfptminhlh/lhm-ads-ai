"""Generate a Web Push VAPID P-256 keypair locally; NEVER commit the private key."""
from __future__ import annotations
import argparse
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--private-file',required=True,help='Private .pem outside any Git repository')
    args=p.parse_args()
    target=Path(args.private_file).expanduser()
    target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    key=ec.generate_private_key(ec.SECP256R1())
    private=key.private_bytes(serialization.Encoding.PEM,
       serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    fd=os.open(str(target),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as file:file.write(private)
    public=key.public_key().public_bytes(serialization.Encoding.X962,
      serialization.PublicFormat.UncompressedPoint)
    public_key=base64.urlsafe_b64encode(public).decode('ascii').rstrip('=')
    print('Private key saved at: '+str(target))
    print('LHM_VAPID_PRIVATE_KEY_FILE='+str(target))
    print('LHM_VAPID_PUBLIC_KEY='+public_key)
    print('LHM_VAPID_SUBJECT=mailto:YOUR_SUPPORT_EMAIL')
    print('Never commit/share the private key or your Ads API tokens.')

if __name__=='__main__':main()
