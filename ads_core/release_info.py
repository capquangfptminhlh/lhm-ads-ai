"""Immutable edition marker injected only during the protected Windows commercial build.

Never place vendor PRIVATE signing keys in this module or a shipped executable.
"""
EDITION = 'pilot'
# Set together by tools/prepare_commercial_build.py when LHM_LEASE_PUBLIC_KEY_B64 is given:
# the Windows build then signs in only with Gmail and accepts only server-signed leases.
LEASE_PUBLIC_KEY_B64 = ''
CLOUD_LICENSE_MODE = ''
