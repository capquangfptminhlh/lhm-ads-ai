"""Signed, opt-in online EXE updater for the native Windows edition.

A manifest and EXE are fetched only after a publisher Ed25519 public key
and HTTPS manifest URL have been provisioned at build time. No arbitrary
download URL, update package or filename is accepted from the UI.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from ads_core import updater
from ads_core.version import __version__
from windows.update_config import UPDATE_MANIFEST_URL, UPDATE_PUBLIC_KEY_B64

MAX_EXE_BYTES = 250 * 1024 * 1024
MAX_ENVELOPE_BYTES = 32 * 1024
_LOCK = threading.Lock()


class UpdateError(RuntimeError):
    pass


def _https_url(url: str, *, executable: bool = False) -> str:
    parsed = urlsplit(url) if isinstance(url, str) else None
    if (not parsed or parsed.scheme != 'https' or not parsed.hostname
            or parsed.username or parsed.password or parsed.fragment
            or parsed.port not in (None, 443)
            or len(url) > 2048 or any(c.isspace() for c in url)
            or parsed.hostname.lower() in {'localhost', '127.0.0.1', '::1'}):
        raise UpdateError('Chỉ chấp nhận địa chỉ cập nhật HTTPS hợp lệ.')
    if executable and not parsed.path.lower().endswith('.exe'):
        raise UpdateError('Bản cập nhật phải là tệp EXE.')
    return url


def configuration():
    # The public key and publisher URL are embedded in release builds; no
    # credentials are read from a web page or an arbitrary UI argument.
    url = UPDATE_MANIFEST_URL.strip()
    key = UPDATE_PUBLIC_KEY_B64.strip()
    if not url or not key:
        return None
    _https_url(url)
    # The validator also checks key/signature sizes when verifying manifest.
    return url, key


def check(*, include_envelope: bool = False) -> dict:
    config = configuration()
    if not config:
        return {'status': 'not_configured', 'current_version': __version__,
                'message': 'Cập nhật online chưa được nhà phát hành kích hoạt.'}
    url, key = config
    try:
        with httpx.Client(timeout=12, follow_redirects=False, trust_env=False) as client:
            response = client.get(url, headers={'Accept': 'application/json'})
            response.raise_for_status()
            raw = response.content
        if not 0 < len(raw) <= MAX_ENVELOPE_BYTES:
            raise UpdateError('Manifest cập nhật vượt giới hạn kích thước.')
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {'manifest', 'signature'}:
            raise UpdateError('Thông tin phiên bản không hợp lệ.')
        manifest = payload['manifest']
        if not isinstance(manifest, dict) or not isinstance(payload['signature'], str):
            raise UpdateError('Manifest hoặc chữ ký không hợp lệ.')
        result = updater.check_for_update(
            __version__, json.dumps(manifest).encode('utf-8'),
            payload['signature'], public_key_b64=key)
        if result['status'] == 'update_available':
            _https_url(result['download_url'], executable=True)
            if include_envelope:
                result['_signed_envelope'] = payload
        return result
    except (httpx.HTTPError, ValueError, TypeError, UnicodeError,
            UpdateError, json.JSONDecodeError) as exc:
        # No secrets/URL metadata are sent to the client in exception text.
        return {'status': 'invalid', 'current_version': __version__,
                'message': 'Không xác minh được cập nhật online. Không có tệp nào được cài.'}


def _staging_directory(data_folder: Path) -> Path:
    return data_folder / 'updates'


def staged_update(data_folder: Path):
    """Return (binary path, sha256, version) only for fully staged EXE."""
    updates = _staging_directory(data_folder)
    try:
        info = json.loads((updates / 'ready.json').read_text(encoding='utf-8'))
        config = configuration()
        if not config or not isinstance(info, dict) or set(info) != {'manifest', 'signature'}:
            return None
        manifest = updater.parse_and_verify_manifest(
            json.dumps(info['manifest']).encode('utf-8'), info['signature'], config[1])
        if updater.compare_versions(manifest['version'], __version__) <= 0:
            return None
        _https_url(manifest['download_url'], executable=True)
        binary = updates / manifest['version'] / 'LHM-Ads-AI.exe'
        if not binary.is_file() or binary.stat().st_size > MAX_EXE_BYTES:
            return None
        digest = hashlib.sha256()
        with binary.open('rb') as fd:
            for chunk in iter(lambda: fd.read(1024 * 1024), b''):
                digest.update(chunk)
        if not hmac.compare_digest(digest.hexdigest(), manifest['sha256']):
            return None
        return (binary, manifest['sha256'], manifest['version'])
    except (OSError, ValueError, KeyError, TypeError, UpdateError, updater.UpdateManifestError):
        return None


def download(data_folder: Path) -> dict:
    with _LOCK:
        verified = check(include_envelope=True)
        if verified['status'] != 'update_available':
            return verified
        envelope = verified['_signed_envelope']
        url = _https_url(verified['download_url'], executable=True)
        version = verified['version']
        digest_expected = verified['sha256']
        folder = _staging_directory(data_folder) / version
        folder.mkdir(parents=True, exist_ok=True)
        partial = folder / 'LHM-Ads-AI.exe.part'
        exe = folder / 'LHM-Ads-AI.exe'
        if partial.exists():
            partial.unlink()
        try:
            digest = hashlib.sha256()
            count = 0
            with httpx.Client(timeout=httpx.Timeout(15, read=60), follow_redirects=False,
                              trust_env=False) as client:
                with client.stream('GET', url) as res:
                    res.raise_for_status()
                    if res.headers.get('content-length'):
                        if int(res.headers['content-length']) > MAX_EXE_BYTES:
                            raise UpdateError('Tệp cập nhật quá lớn.')
                    with partial.open('xb') as out:
                        for chunk in res.iter_bytes(chunk_size=1024 * 1024):
                            count += len(chunk)
                            if count > MAX_EXE_BYTES:
                                raise UpdateError('Tệp cập nhật vượt giới hạn.')
                            out.write(chunk)
                            digest.update(chunk)
            if count < 2 or partial.open('rb').read(2) != b'MZ':
                raise UpdateError('Tệp cập nhật không phải Windows EXE.')
            if not hmac.compare_digest(digest.hexdigest(), digest_expected):
                raise UpdateError('SHA-256 không khớp chữ ký manifest.')
            os.replace(partial, exe)
            marker = folder.parent / 'ready.json'
            temp = folder.parent / 'ready.json.tmp'
            # Keep the publisher's signed manifest with the staged EXE.
            # Re-verify it on install; never trust a mutable local hash alone.
            temp.write_text(json.dumps(envelope), encoding='utf-8')
            os.replace(temp, marker)
            return {'status': 'downloaded', 'version': version,
                    'message': 'Đã tải và xác minh bản cập nhật. Chọn Cài và khởi động lại.'}
        except (OSError, ValueError, httpx.HTTPError, UpdateError):
            return {'status': 'invalid',
                    'message': 'Tải hoặc xác minh EXE thất bại; không thay đổi phần mềm.'}
        finally:
            partial.unlink(missing_ok=True)
