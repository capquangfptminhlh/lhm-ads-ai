"""Offline tests for the dormant signed update checker (ads_core/updater.py).

Generates a real Ed25519 keypair in-test and signs manifests with the
project's canonical JSON form. No network, no downloads: the module only
verifies and reports.
"""
import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ads_core import updater


def _raw_public_b64(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


@pytest.fixture()
def signer():
    key = Ed25519PrivateKey.generate()
    return key, _raw_public_b64(key)


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


def _signed(key, manifest):
    signature = key.sign(updater.canonical_manifest(manifest))
    return json.dumps(manifest).encode(), base64.b64encode(signature).decode()


def test_valid_manifest_verifies(signer):
    key, pub = signer
    raw, sig = _signed(key, _manifest())
    parsed = updater.parse_and_verify_manifest(raw, sig, pub)
    assert parsed['version'] == '1.3.0'
    assert parsed['sha256'] == 'a' * 64


def test_newer_version_reports_update_available(signer):
    key, pub = signer
    raw, sig = _signed(key, _manifest(version='2.0.1'))
    result = updater.check_for_update('1.9.9', raw, sig, public_key_b64=pub)
    assert result['status'] == 'update_available'
    assert result['version'] == '2.0.1'
    assert result['download_url'].endswith('setup.exe')


def test_equal_and_older_versions_are_up_to_date(signer):
    key, pub = signer
    for version in ('1.3.0', '1.2.9', '0.9.0'):
        raw, sig = _signed(key, _manifest(version=version))
        result = updater.check_for_update('1.3.0', raw, sig, public_key_b64=pub)
        assert result['status'] == 'up_to_date', version


def test_tampered_manifest_is_rejected(signer):
    key, pub = signer
    raw, sig = _signed(key, _manifest())
    tampered = json.loads(raw)
    tampered['download_url'] = 'https://evil.invalid/payload.exe'
    with pytest.raises(updater.UpdateManifestError):
        updater.parse_and_verify_manifest(
            json.dumps(tampered).encode(), sig, pub)
    result = updater.check_for_update(
        '1.0.0', json.dumps(tampered).encode(), sig, public_key_b64=pub)
    assert result['status'] == 'invalid'


def test_wrong_key_is_rejected(signer):
    key, _pub = signer
    other = Ed25519PrivateKey.generate()
    raw, sig = _signed(key, _manifest())
    with pytest.raises(updater.UpdateManifestError):
        updater.parse_and_verify_manifest(raw, sig, _raw_public_b64(other))


def test_malformed_fields_are_rejected(signer):
    key, pub = signer
    bad_manifests = [
        _manifest(version='1.3'),                 # not X.Y.Z
        _manifest(version='v1.3.0'),              # prefix not allowed
        _manifest(version='1.3.0-beta'),          # prerelease not strict semver
        _manifest(sha256='A' * 64),               # uppercase hex
        _manifest(sha256='ab12'),                 # too short
        _manifest(download_url='http://x.invalid/f.exe'),  # not https
        _manifest(issued_at='hôm qua'),           # not an epoch int
        _manifest(extra_field='không thuộc manifest'),
    ]
    for manifest in bad_manifests:
        raw, sig = _signed(key, manifest)
        with pytest.raises(updater.UpdateManifestError):
            updater.parse_and_verify_manifest(raw, sig, pub)


def test_missing_field_and_bad_json_and_bad_signature_encoding(signer):
    key, pub = signer
    manifest = _manifest()
    del manifest['notes']
    raw, sig = _signed(key, manifest)
    with pytest.raises(updater.UpdateManifestError):
        updater.parse_and_verify_manifest(raw, sig, pub)
    with pytest.raises(updater.UpdateManifestError):
        updater.parse_and_verify_manifest(b'{not json', sig, pub)
    raw, _sig = _signed(key, _manifest())
    with pytest.raises(updater.UpdateManifestError):
        updater.parse_and_verify_manifest(raw, '!!!not-base64!!!', pub)
    with pytest.raises(updater.UpdateManifestError):
        updater.parse_and_verify_manifest(raw, _sig, 'c2hvcnQ=')


def test_compare_versions():
    assert updater.compare_versions('1.2.3', '1.2.3') == 0
    assert updater.compare_versions('1.2.3', '1.10.0') == -1
    assert updater.compare_versions('2.0.0', '1.99.99') == 1
    assert updater.compare_versions('0.0.9', '0.0.10') == -1
    with pytest.raises(updater.UpdateManifestError):
        updater.compare_versions('1.2', '1.2.3')
    with pytest.raises(updater.UpdateManifestError):
        updater.compare_versions('1.2.3', '')


def test_not_configured_without_env(monkeypatch):
    monkeypatch.delenv(updater.ENV_PUBLIC_KEY, raising=False)
    assert updater.is_configured() is False
    result = updater.check_for_update('1.0.0', b'{}', 'AAAA')
    assert result['status'] == 'not_configured'
    assert result['configured'] is False
    assert 'LHM_UPDATE_PUBLIC_KEY' in result['message']
    with pytest.raises(updater.UpdateNotConfigured):
        updater.load_public_key_b64()


def test_env_configured_path(signer, monkeypatch):
    key, pub = signer
    monkeypatch.setenv(updater.ENV_PUBLIC_KEY, pub)
    assert updater.is_configured() is True
    raw, sig = _signed(key, _manifest(version='9.9.9'))
    result = updater.check_for_update('1.0.0', raw, sig)
    assert result['status'] == 'update_available'


def test_module_makes_no_network_calls():
    import ads_core.updater as module
    source = open(module.__file__, encoding='utf-8').read()
    for forbidden in ('urllib', 'requests', 'http.client', 'socket', 'urlopen'):
        assert forbidden not in source, forbidden
