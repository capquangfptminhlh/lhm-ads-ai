"""Offline-consistent license revocation for LHM Ads AI.

Licenses are verified fully offline (see ads_core.licensing), so there is no
server the app can ask "is this license still good?". Revocation therefore
travels as data: the seller signs a revocation list with the SAME Ed25519
issuer key that signs licenses, and the customer receives it out of band
(e.g. attached to a renewal file, a support reply, or a future release).

A revocation list is one JSON document::

    {"version": 1, "issued_at": <unix seconds>,
     "entries": [{"license_id": "...", "reason": "...", "revoked_at": <unix>},
                 {"device_id": "...", "reason": "...", "revoked_at": <unix>}]}

Each entry carries ``license_id`` and/or ``device_id``; an entry matches a
license when either identifier equals the corresponding claim of the license
payload (payload fields are named ``license_id`` and ``device`` — see
ads_core.licensing.verify_signed_license). The signature is detached: the
raw 64-byte Ed25519 signature over the exact document bytes, distributed
next to the list as ``<list file>.sig`` containing base64 text (the same
base64 convention license files use for their signature). Producers must
write the document in the canonical form of ads_core.licensing.canonical so
the signed bytes are stable.

Honest limit: this is NOT a remote kill switch. A revocation only takes
effect on a customer machine once that machine imports/receives a list whose
``issued_at`` covers the revocation. A customer who never receives a newer
list keeps a working license until it expires; sellers must not promise
instant or guaranteed revocation.

Fail-closed rules: a list that is present but malformed, unsigned, signed by
the wrong key, or of an unsupported version raises RevocationError — it is
never silently trusted. A MISSING list file is not an error: it simply means
"no revocations known", so a valid offline install without any list keeps
working unchanged.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import licensing

SUPPORTED_VERSION = 1
ENV_VAR = 'LHM_REVOCATION_FILE'
MAX_FILE_SIZE = 256 * 1024
MAX_ENTRIES = 10000


class RevocationError(ValueError):
    """A revocation list is present but cannot be trusted."""


def empty_list() -> dict:
    """The canonical 'no revocations known' document."""
    return {'version': SUPPORTED_VERSION, 'issued_at': 0, 'entries': []}


def _validate_document(data) -> dict:
    if not isinstance(data, dict) or set(data) != {'version', 'issued_at', 'entries'}:
        raise RevocationError('Tài liệu thu hồi không đúng định dạng')
    if data['version'] != SUPPORTED_VERSION:
        raise RevocationError(
            f"Phiên bản danh sách thu hồi {data['version']!r} chưa được hỗ trợ; "
            'hãy cập nhật phần mềm')
    if not isinstance(data['issued_at'], int) or data['issued_at'] < 0:
        raise RevocationError('Thời điểm phát hành danh sách thu hồi không hợp lệ')
    entries = data['entries']
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise RevocationError('Danh sách giấy phép bị thu hồi không hợp lệ')
    for entry in entries:
        if not isinstance(entry, dict) or not set(entry) <= {'license_id', 'device_id', 'reason', 'revoked_at'}:
            raise RevocationError('Mục thu hồi không đúng định dạng')
        if not entry.get('license_id') and not entry.get('device_id'):
            raise RevocationError('Mục thu hồi phải có mã giấy phép hoặc mã máy')
        for field in ('license_id', 'device_id'):
            if field in entry and (not isinstance(entry[field], str) or not 1 <= len(entry[field]) <= 80):
                raise RevocationError('Mã trong mục thu hồi không hợp lệ')
        if not isinstance(entry.get('reason'), str) or not 1 <= len(entry['reason']) <= 300:
            raise RevocationError('Lý do thu hồi không hợp lệ')
        if not isinstance(entry.get('revoked_at'), int) or entry['revoked_at'] < 0:
            raise RevocationError('Thời điểm thu hồi không hợp lệ')
    return data


def verify_revocation_list(raw: bytes, signature: bytes, *,
                           public_key_b64: str | None = None) -> dict:
    """Verify a detached Ed25519 signature over the exact list bytes.

    ``signature`` is the raw 64-byte signature. The public key defaults to
    the same issuer key the app already trusts for licenses
    (ads_core.licensing.PUBLIC_KEY_B64, read at call time). Any problem —
    bad JSON, bad shape, unsupported version, wrong key, tampered bytes —
    raises RevocationError; nothing is returned partially trusted.
    """
    if not isinstance(raw, (bytes, bytearray)) or not 2 <= len(raw) <= MAX_FILE_SIZE:
        raise RevocationError('File danh sách thu hồi không hợp lệ')
    if not isinstance(signature, (bytes, bytearray)) or len(signature) != 64:
        raise RevocationError('Chữ ký danh sách thu hồi không hợp lệ')
    key_b64 = licensing.PUBLIC_KEY_B64 if public_key_b64 is None else public_key_b64
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(key_b64, validate=True))
        public_key.verify(bytes(signature), bytes(raw))
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise RevocationError('Chữ ký danh sách thu hồi không hợp lệ hoặc không thuộc bên phát hành') from exc
    try:
        data = json.loads(bytes(raw).decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RevocationError('File danh sách thu hồi không đọc được') from exc
    return _validate_document(data)


def is_revoked(parsed: dict, license_claims: dict) -> tuple[bool, dict | None]:
    """Return (True, entry) when a verified list revokes this license.

    ``license_claims`` is the verified license payload; its identifiers are
    the payload fields ``license_id`` and ``device``. A list entry matches
    when its ``license_id`` equals the payload's ``license_id`` or its
    ``device_id`` equals the payload's ``device``.
    """
    if not isinstance(parsed, dict) or not isinstance(license_claims, dict):
        return False, None
    license_id = license_claims.get('license_id')
    device = license_claims.get('device')
    for entry in parsed.get('entries') or []:
        if license_id and entry.get('license_id') and entry['license_id'] == license_id:
            return True, entry
        if device and entry.get('device_id') and entry['device_id'] == device:
            return True, entry
    return False, None


def signature_path(list_path: Path) -> Path:
    """Detached signature file that travels with a list file."""
    return Path(str(list_path) + '.sig')


def load_revocation_list(path: str | os.PathLike | None = None, *,
                         min_issued_at: int = 0,
                         public_key_b64: str | None = None) -> dict:
    """Load and verify the revocation list configured for this install.

    The path comes from the LHM_REVOCATION_FILE environment variable unless
    given explicitly. No configured path, or a configured path whose file
    does not exist yet, returns empty_list() — never an error, because most
    installs legitimately have no list. A list file that DOES exist must
    verify (signature file ``<path>.sig``, base64) or RevocationError is
    raised. ``min_issued_at`` optionally rejects a list older than one the
    caller has already seen, so an old list cannot silently replace a newer
    one (rollback guard for the wiring layer to persist).
    """
    configured = os.environ.get(ENV_VAR) if path is None else str(path)
    if not configured:
        return empty_list()
    list_path = Path(configured)
    if not list_path.is_file():
        return empty_list()
    sig_path = signature_path(list_path)
    if not sig_path.is_file():
        raise RevocationError('Thiếu file chữ ký của danh sách thu hồi')
    try:
        raw = list_path.read_bytes()
        signature = base64.b64decode(sig_path.read_text(encoding='ascii').strip(), validate=True)
    except (OSError, UnicodeError, ValueError) as exc:
        raise RevocationError('Không đọc được danh sách thu hồi hoặc chữ ký của nó') from exc
    parsed = verify_revocation_list(raw, signature, public_key_b64=public_key_b64)
    if parsed['issued_at'] < min_issued_at:
        raise RevocationError('Danh sách thu hồi cũ hơn danh sách đã dùng; đã từ chối để tránh bị thay bằng bản cũ')
    return parsed
