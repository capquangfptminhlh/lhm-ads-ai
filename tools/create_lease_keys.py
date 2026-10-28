"""Create the Ed25519 key pair that signs offline leases for the Windows app.

Run on the owner's own computer, once:

  python tools/create_lease_keys.py

It prints two values and stores nothing:
  1. LEASE_SIGNING_KEY  (PRIVATE) -> Cloudflare Worker secret:
       npx wrangler secret put LEASE_SIGNING_KEY
     Paste it at the prompt. Never commit it, never put it in GitHub.
  2. LHM_LEASE_PUBLIC_KEY_B64 (public) -> GitHub repository variable
     (Settings > Secrets and variables > Actions > Variables). The commercial
     EXE build pins it and then signs in only with Gmail.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main():
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print("LEASE_SIGNING_KEY (PRIVATE, Cloudflare Worker secret only):")
    print(base64.b64encode(private).decode())
    print()
    print("LHM_LEASE_PUBLIC_KEY_B64 (public, GitHub Actions variable):")
    print(base64.b64encode(public).decode())


if __name__ == "__main__":
    main()
