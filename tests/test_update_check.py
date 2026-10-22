"""Tests for the seller-side update-check CLI (tools/update_check.py).

Fully offline: every HTTP call is faked through the CLI's own httpx
reference, and the dormant path is guarded by an httpx double that raises
if it is touched at all. Manifests are signed in-test with a real Ed25519
keypair, exactly like tests/test_updater.py does for ads_core.updater —
the CLI must reuse updater's verification, never re-implement it.
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ads_core import updater
from tools import update_check


REPO_ROOT = Path(__file__).resolve().parents[1]


def _raw_public_bytes(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _raw_public_b64(key: Ed25519PrivateKey) -> str:
    return base64.b64encode(_raw_public_bytes(key)).decode()


def _raw_public_hex(key: Ed25519PrivateKey) -> str:
    return _raw_public_bytes(key).hex()


@pytest.fixture()
def signer():
    key = Ed25519PrivateKey.generate()
    return key, _raw_public_b64(key), _raw_public_hex(key)


def _manifest(**overrides):
    manifest = {
        'version': '1.3.0',
        'download_url': 'https://example.invalid/lhm-ads-ai-1.3.0-setup.exe',
        'sha256': 'a' * 64,
        'notes': 'Sửa lỗi và cải thiện hiệu năng.',
        'issued_at': 1760000000,
    }
    manifest.update(overrides)
    return manifest


def _envelope(key, manifest):
    signature = key.sign(updater.canonical_manifest(manifest))
    return {'manifest': manifest,
            'signature': base64.b64encode(signature).decode()}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = json.dumps(payload).encode('utf-8')

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def _fake_get(payload, seen=None):
    def get(url, **kwargs):
        if seen is not None:
            seen.append(url)
        return FakeResponse(payload)
    return get


def _exploding_get(url, **kwargs):
    raise AssertionError('mạng không được phép chạm tới trong trạng thái dormant')


def _clean_env(**extra):
    env = {k: v for k, v in os.environ.items()
           if k not in (update_check.ENV_MANIFEST_URL,
                        update_check.ENV_PUBKEY,
                        updater.ENV_PUBLIC_KEY)}
    env.update(extra)
    return env


# ---------------------------------------------------------------------------
# Dormant: exit 2, clear Vietnamese message, and absolutely no network.
# ---------------------------------------------------------------------------

def test_dormant_without_any_config_makes_no_network_call(monkeypatch, capsys):
    monkeypatch.setattr(update_check.httpx, 'get', _exploding_get)
    monkeypatch.setattr(update_check.httpx, 'Client',
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError('httpx.Client không được tạo khi dormant')))
    code = update_check.main(['--current', '1.0.0'], environ={})
    assert code == 2
    out = capsys.readouterr().out
    assert 'chưa được kích hoạt' in out
    assert update_check.ENV_MANIFEST_URL in out
    assert update_check.ENV_PUBKEY in out


def test_dormant_when_only_url_configured(monkeypatch, capsys):
    monkeypatch.setattr(update_check.httpx, 'get', _exploding_get)
    code = update_check.main(
        ['--current', '1.0.0'],
        environ={update_check.ENV_MANIFEST_URL: 'https://example.invalid/u.json'})
    assert code == 2
    assert 'khóa' in capsys.readouterr().out


def test_dormant_when_only_pubkey_configured(monkeypatch, capsys):
    monkeypatch.setattr(update_check.httpx, 'get', _exploding_get)
    code = update_check.main(
        ['--current', '1.0.0'],
        environ={update_check.ENV_PUBKEY: 'ab' * 32})
    assert code == 2
    assert update_check.ENV_MANIFEST_URL in capsys.readouterr().out


def test_dormant_via_subprocess_exit_code_2():
    out = subprocess.run(
        [sys.executable, 'tools/update_check.py', '--current', '1.0.0'],
        capture_output=True, text=True, encoding='utf-8', errors='strict',
        cwd=str(REPO_ROOT), env=_clean_env())
    assert out.returncode == 2, out.stderr
    assert 'chưa được kích hoạt' in out.stdout


# ---------------------------------------------------------------------------
# Configured paths: real Ed25519 signatures verified through the updater.
# ---------------------------------------------------------------------------

def test_update_available_with_hex_pubkey(signer, monkeypatch, capsys):
    key, _pub_b64, pub_hex = signer
    seen = []
    monkeypatch.setattr(update_check.httpx, 'get',
                        _fake_get(_envelope(key, _manifest(version='2.0.1')), seen))
    code = update_check.main(
        ['--current', '1.9.9', '--url', 'https://example.invalid/update.json',
         '--pubkey', pub_hex],
        environ={})
    assert code == 0
    out = capsys.readouterr().out
    assert 'update_available' in out
    assert '2.0.1' in out and '1.9.9' in out
    assert seen == ['https://example.invalid/update.json']


def test_up_to_date_with_base64_pubkey(signer, monkeypatch, capsys):
    key, pub_b64, _pub_hex = signer
    monkeypatch.setattr(update_check.httpx, 'get',
                        _fake_get(_envelope(key, _manifest(version='1.3.0'))))
    code = update_check.main(
        ['--current', '1.3.0', '--url', 'https://example.invalid/update.json',
         '--pubkey', pub_b64],
        environ={})
    assert code == 0
    out = capsys.readouterr().out
    assert 'up_to_date' in out
    assert 'update_available' not in out


def test_config_from_environment(signer, monkeypatch, capsys):
    key, _pub_b64, pub_hex = signer
    seen = []
    monkeypatch.setattr(update_check.httpx, 'get',
                        _fake_get(_envelope(key, _manifest(version='9.9.9')), seen))
    code = update_check.main(
        ['--current', '1.0.0'],
        environ={update_check.ENV_MANIFEST_URL: 'https://example.invalid/env.json',
                 update_check.ENV_PUBKEY: pub_hex})
    assert code == 0
    assert 'update_available' in capsys.readouterr().out
    assert seen == ['https://example.invalid/env.json']


def test_pubkey_from_file_hex_and_base64(signer, monkeypatch, tmp_path, capsys):
    key, pub_b64, pub_hex = signer
    monkeypatch.setattr(update_check.httpx, 'get',
                        _fake_get(_envelope(key, _manifest(version='1.3.0'))))
    for content in (pub_hex, pub_b64):
        path = tmp_path / 'update-public.txt'
        path.write_text(content + '\n', encoding='ascii')
        code = update_check.main(
            ['--current', '1.0.0', '--url', 'https://example.invalid/u.json',
             '--pubkey', str(path)],
            environ={})
        assert code == 0
        capsys.readouterr()  # drain


def test_invalid_signature_wrong_key(signer, monkeypatch, capsys):
    key, _pub_b64, _pub_hex = signer
    other = Ed25519PrivateKey.generate()
    monkeypatch.setattr(update_check.httpx, 'get',
                        _fake_get(_envelope(key, _manifest())))
    code = update_check.main(
        ['--current', '1.0.0', '--url', 'https://example.invalid/u.json',
         '--pubkey', _raw_public_hex(other)],
        environ={})
    assert code == 1
    out = capsys.readouterr().out
    assert 'invalid' in out
    assert 'Chữ ký' in out  # message comes from ads_core.updater itself


def test_invalid_signature_tampered_manifest(signer, monkeypatch, capsys):
    key, pub_b64, _pub_hex = signer
    envelope = _envelope(key, _manifest())
    envelope['manifest'] = dict(envelope['manifest'],
                                download_url='https://evil.invalid/payload.exe')
    monkeypatch.setattr(update_check.httpx, 'get', _fake_get(envelope))
    code = update_check.main(
        ['--current', '1.0.0', '--url', 'https://example.invalid/u.json',
         '--pubkey', pub_b64],
        environ={})
    assert code == 1
    assert 'invalid' in capsys.readouterr().out


def test_invalid_envelope_missing_signature(signer, monkeypatch, capsys):
    _key, pub_b64, _pub_hex = signer
    monkeypatch.setattr(update_check.httpx, 'get',
                        _fake_get({'manifest': _manifest()}))
    code = update_check.main(
        ['--current', '1.0.0', '--url', 'https://example.invalid/u.json',
         '--pubkey', pub_b64],
        environ={})
    assert code == 1
    assert 'invalid' in capsys.readouterr().out


def test_invalid_when_fetch_fails(signer, monkeypatch, capsys):
    _key, pub_b64, _pub_hex = signer

    def failing_get(url, **kwargs):
        raise httpx.ConnectError('connection refused', request=None)

    monkeypatch.setattr(update_check.httpx, 'get', failing_get)
    code = update_check.main(
        ['--current', '1.0.0', '--url', 'https://example.invalid/u.json',
         '--pubkey', pub_b64],
        environ={})
    assert code == 1
    assert 'invalid' in capsys.readouterr().out


def test_invalid_pubkey_format(monkeypatch, capsys):
    monkeypatch.setattr(update_check.httpx, 'get', _exploding_get)
    code = update_check.main(
        ['--current', '1.0.0', '--url', 'https://example.invalid/u.json',
         '--pubkey', 'không-phải-khóa'],
        environ={})
    assert code == 1
    assert 'invalid' in capsys.readouterr().out


def test_local_manifest_file_needs_no_network(signer, monkeypatch, tmp_path, capsys):
    key, _pub_b64, pub_hex = signer
    path = tmp_path / 'update.json'
    path.write_text(json.dumps(_envelope(key, _manifest(version='3.0.0'))),
                    encoding='utf-8')
    monkeypatch.setattr(update_check.httpx, 'get', _exploding_get)
    code = update_check.main(
        ['--current', '1.0.0', '--url', str(path), '--pubkey', pub_hex],
        environ={})
    assert code == 0
    assert 'update_available' in capsys.readouterr().out


def test_base64_pubkey_containing_slash_is_not_mistaken_for_a_path(monkeypatch, capsys):
    # Regression: the base64 alphabet contains '/', so roughly half of all
    # real public keys contain a character that looks like a path
    # separator. Such a key must be decoded as base64, never treated as
    # a (missing) file path.
    for _ in range(200):
        key = Ed25519PrivateKey.generate()
        pub_b64 = _raw_public_b64(key)
        if '/' in pub_b64:
            break
    else:  # pragma: no cover - xác suất không tìm thấy gần bằng 0
        pytest.skip('không sinh được khóa có "/" trong base64')
    assert update_check.resolve_public_key_b64(pub_b64) == pub_b64
    monkeypatch.setattr(update_check.httpx, 'get',
                        _fake_get(_envelope(key, _manifest(version='1.3.0'))))
    code = update_check.main(
        ['--current', '1.3.0', '--url', 'https://example.invalid/u.json',
         '--pubkey', pub_b64],
        environ={})
    assert code == 0
    assert 'up_to_date' in capsys.readouterr().out


def test_resolve_public_key_b64_forms(signer, tmp_path):
    _key, pub_b64, pub_hex = signer
    assert update_check.resolve_public_key_b64(pub_hex) == pub_b64
    assert update_check.resolve_public_key_b64(pub_hex.upper()) == pub_b64
    assert update_check.resolve_public_key_b64(pub_b64) == pub_b64
    path = tmp_path / 'k.txt'
    path.write_text(pub_hex, encoding='ascii')
    assert update_check.resolve_public_key_b64(str(path)) == pub_b64
    with pytest.raises(update_check.UpdateCheckError):
        update_check.resolve_public_key_b64(str(tmp_path / 'missing.txt'))
    with pytest.raises(update_check.UpdateCheckError):
        update_check.resolve_public_key_b64('abc')
