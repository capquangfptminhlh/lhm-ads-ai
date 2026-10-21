"""LHM Ads AI signed update checker — dormant until configured, checker only.

This module VERIFIES a signed update manifest offline. It never downloads
anything, never executes anything and never touches the network: fetching
the manifest is a future caller's job. A verified manifest only tells the
app "a newer signed release exists" — applying an update stays a separate,
explicit step, exactly like license issuance stays manual/offline.

Manifest format (JSON object, exactly these fields):
    {"version": "1.2.3", "download_url": "https://...", "sha256": "<64 hex>",
     "notes": "Ghi chú phát hành", "issued_at": 1760000000}
plus a detached Ed25519 signature (base64) over the canonical JSON of the
manifest — the same canonicalisation as ads_core.licensing.canonical:
json.dumps(..., ensure_ascii=True, sort_keys=True, separators=(',', ':')).

The publisher public key (base64 of the raw 32-byte Ed25519 public key,
same format as the license public key) comes ONLY from the environment
variable LHM_UPDATE_PUBLIC_KEY. The matching private key never ships with
the app; manifests are signed on the seller's offline machine. While the
variable is unset the checker reports 'not_configured' and does nothing
else — the same dormant pattern as tools/payos.py.
"""
from __future__ import annotations

import base64
import json
import os
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ENV_PUBLIC_KEY = 'LHM_UPDATE_PUBLIC_KEY'
MAX_MANIFEST_SIZE = 16384
_MANIFEST_FIELDS = {'version', 'download_url', 'sha256', 'notes', 'issued_at'}
_SEMVER_RE = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')
_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')

NOT_CONFIGURED_MESSAGE = (
    'Kiểm tra cập nhật chưa được kích hoạt: thiếu LHM_UPDATE_PUBLIC_KEY '
    'trong môi trường. Phần mềm vẫn hoạt động bình thường; bản phát hành '
    'mới hiện được phân phối thủ công.')


class UpdateNotConfigured(RuntimeError):
    """Raised when the update publisher key is not set yet (checker dormant)."""


class UpdateManifestError(ValueError):
    """Raised when a manifest or its signature fails validation (fail-closed)."""


def canonical_manifest(manifest: dict) -> bytes:
    """Canonical bytes that the detached signature covers (licensing format)."""
    return json.dumps(manifest, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def load_public_key_b64(environ=None) -> str:
    """Return the configured publisher public key or raise UpdateNotConfigured."""
    env = os.environ if environ is None else environ
    value = (env.get(ENV_PUBLIC_KEY) or '').strip()
    if not value:
        raise UpdateNotConfigured(NOT_CONFIGURED_MESSAGE)
    return value


def is_configured(environ=None) -> bool:
    try:
        load_public_key_b64(environ)
        return True
    except UpdateNotConfigured:
        return False


def _parse_semver(version) -> tuple[int, int, int]:
    if not isinstance(version, str):
        raise UpdateManifestError('Phiên bản phải là chuỗi dạng X.Y.Z')
    match = _SEMVER_RE.match(version)
    if not match:
        raise UpdateManifestError(
            f'Phiên bản không đúng định dạng semver X.Y.Z: {version!r}')
    return tuple(int(part) for part in match.groups())


def compare_versions(a: str, b: str) -> int:
    """Return -1 if a < b, 0 if equal, 1 if a > b. Both must be strict semver."""
    va, vb = _parse_semver(a), _parse_semver(b)
    return (va > vb) - (va < vb)


def _decode_b64(value, expected_len: int, label: str) -> bytes:
    if not isinstance(value, str):
        raise UpdateManifestError(f'{label} phải là chuỗi base64')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise UpdateManifestError(f'{label} không phải base64 hợp lệ') from exc
    if len(raw) != expected_len:
        raise UpdateManifestError(
            f'{label} phải dài {expected_len} byte (nhận {len(raw)} byte)')
    return raw


def _validate_manifest(manifest) -> dict:
    if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS:
        raise UpdateManifestError(
            'Manifest phải có đúng các trường: ' +
            ', '.join(sorted(_MANIFEST_FIELDS)))
    _parse_semver(manifest['version'])
    url = manifest['download_url']
    if (not isinstance(url, str) or not url.startswith('https://')
            or len(url) > 2048 or any(ch.isspace() for ch in url)):
        raise UpdateManifestError(
            'download_url phải là một URL https hợp lệ, tối đa 2048 ký tự')
    if not isinstance(manifest['sha256'], str) or not _SHA256_RE.match(manifest['sha256']):
        raise UpdateManifestError('sha256 phải là 64 ký tự hex thường')
    if not isinstance(manifest['notes'], str) or len(manifest['notes']) > 2000:
        raise UpdateManifestError('notes phải là chuỗi tối đa 2000 ký tự')
    issued_at = manifest['issued_at']
    if isinstance(issued_at, bool) or not isinstance(issued_at, int) or issued_at <= 0:
        raise UpdateManifestError('issued_at phải là mốc thời gian epoch dương')
    return manifest


def parse_and_verify_manifest(manifest_bytes, signature_b64, public_key_b64) -> dict:
    """Parse a manifest and verify its detached Ed25519 signature.

    Fail-closed: any malformed field, bad encoding, wrong key or invalid
    signature raises UpdateManifestError and nothing is returned.
    """
    if isinstance(manifest_bytes, str):
        manifest_bytes = manifest_bytes.encode('utf-8')
    if not isinstance(manifest_bytes, (bytes, bytearray)) \
            or not 0 < len(manifest_bytes) <= MAX_MANIFEST_SIZE:
        raise UpdateManifestError('Manifest trống hoặc vượt quá kích thước cho phép')
    try:
        manifest = json.loads(bytes(manifest_bytes).decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateManifestError('Manifest không phải JSON hợp lệ') from exc
    _validate_manifest(manifest)
    public_raw = _decode_b64(public_key_b64, 32, 'Khóa công khai cập nhật')
    signature = _decode_b64(signature_b64, 64, 'Chữ ký manifest')
    try:
        Ed25519PublicKey.from_public_bytes(public_raw).verify(
            signature, canonical_manifest(manifest))
    except InvalidSignature as exc:
        raise UpdateManifestError(
            'Chữ ký manifest không hợp lệ — từ chối thông tin cập nhật này') from exc
    return manifest


def check_for_update(current_version, manifest_bytes=None, signature_b64=None,
                     *, environ=None, public_key_b64=None) -> dict:
    """Structured, offline update check.

    Returns one of:
      {'status': 'not_configured', ...} — LHM_UPDATE_PUBLIC_KEY unset.
      {'status': 'invalid', ...}        — manifest/signature failed checks.
      {'status': 'up_to_date', ...}     — signed manifest is not newer.
      {'status': 'update_available', 'version', 'download_url', 'sha256',
       'notes', 'issued_at', ...}       — signed manifest is strictly newer.

    This only REPORTS. It never downloads or installs anything.
    """
    result = {'current_version': current_version, 'configured': True}
    try:
        _parse_semver(current_version)
    except UpdateManifestError as exc:
        return {**result, 'status': 'invalid',
                'message': f'Phiên bản hiện tại không hợp lệ: {exc}'}
    try:
        key_b64 = public_key_b64 or load_public_key_b64(environ)
    except UpdateNotConfigured:
        return {'status': 'not_configured', 'configured': False,
                'current_version': current_version,
                'message': NOT_CONFIGURED_MESSAGE}
    if manifest_bytes is None or signature_b64 is None:
        return {**result, 'status': 'invalid',
                'message': 'Chưa có manifest cập nhật để kiểm tra.'}
    try:
        manifest = parse_and_verify_manifest(manifest_bytes, signature_b64, key_b64)
    except UpdateManifestError as exc:
        return {**result, 'status': 'invalid', 'message': str(exc)}
    if compare_versions(manifest['version'], current_version) > 0:
        return {**result, 'status': 'update_available',
                'version': manifest['version'],
                'download_url': manifest['download_url'],
                'sha256': manifest['sha256'],
                'notes': manifest['notes'],
                'issued_at': manifest['issued_at'],
                'message': f"Có bản mới {manifest['version']} "
                           f"(đang dùng {current_version})."}
    return {**result, 'status': 'up_to_date',
            'version': manifest['version'],
            'message': f'Đang dùng bản mới nhất ({current_version}).'}
