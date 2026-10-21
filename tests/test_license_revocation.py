"""Offline revocation lists: signed with the issuer key, verified fail-closed."""
import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ads_core import license_revocation as revocation
from ads_core.licensing import canonical

NOW = int(time.time())
DEVICE = 'a' * 32
OTHER_DEVICE = 'b' * 32


def _keypair():
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    return key, base64.b64encode(raw).decode()


def _document(entries, *, version=1, issued_at=NOW):
    return {'version': version, 'issued_at': issued_at, 'entries': entries}


def _sign(key, document):
    raw = canonical(document)
    return raw, key.sign(raw)


def _entry(**kw):
    entry = {'reason': 'Hoàn tiền cho khách', 'revoked_at': NOW}
    entry.update(kw)
    return entry


@pytest.fixture()
def keypair():
    return _keypair()


def test_valid_list_verifies(keypair):
    key, pub = keypair
    raw, sig = _sign(key, _document([_entry(license_id='lic-123')]))
    parsed = revocation.verify_revocation_list(raw, sig, public_key_b64=pub)
    assert parsed['version'] == 1
    assert parsed['entries'][0]['license_id'] == 'lic-123'


def test_tampered_entry_fails(keypair):
    key, pub = keypair
    raw, sig = _sign(key, _document([_entry(license_id='lic-123')]))
    tampered = json.loads(raw)
    tampered['entries'][0]['license_id'] = 'lic-999'
    with pytest.raises(revocation.RevocationError):
        revocation.verify_revocation_list(canonical(tampered), sig, public_key_b64=pub)


def test_wrong_key_and_bad_signature_fail(keypair):
    key, pub = keypair
    _, other_pub = _keypair()
    raw, sig = _sign(key, _document([]))
    with pytest.raises(revocation.RevocationError):
        revocation.verify_revocation_list(raw, sig, public_key_b64=other_pub)
    with pytest.raises(revocation.RevocationError):
        revocation.verify_revocation_list(raw, b'\x00' * 64, public_key_b64=pub)
    with pytest.raises(revocation.RevocationError):
        revocation.verify_revocation_list(b'not json', sig, public_key_b64=pub)


def test_unsupported_versions_fail(keypair):
    key, pub = keypair
    for version in (0, 2, '1'):
        raw, sig = _sign(key, _document([], version=version))
        with pytest.raises(revocation.RevocationError):
            revocation.verify_revocation_list(raw, sig, public_key_b64=pub)


def test_malformed_entries_fail(keypair):
    key, pub = keypair
    bad_documents = [
        _document([{'reason': 'thiếu cả hai mã', 'revoked_at': NOW}]),
        _document([_entry(license_id='x', extra='không được phép')]),
        _document([_entry(license_id='x', reason='')]),
        _document([_entry(license_id='x', revoked_at='hôm qua')]),
        {'version': 1, 'issued_at': NOW},  # thiếu entries
    ]
    for document in bad_documents:
        raw, sig = _sign(key, document)
        with pytest.raises(revocation.RevocationError):
            revocation.verify_revocation_list(raw, sig, public_key_b64=pub)


def test_revoked_license_id_matches(keypair):
    key, pub = keypair
    raw, sig = _sign(key, _document([_entry(license_id='lic-123')]))
    parsed = revocation.verify_revocation_list(raw, sig, public_key_b64=pub)
    claims = {'license_id': 'lic-123', 'device': DEVICE, 'plan': 'monthly'}
    hit, entry = revocation.is_revoked(parsed, claims)
    assert hit and entry['license_id'] == 'lic-123'


def test_revoked_device_matches_payload_device_field(keypair):
    key, pub = keypair
    raw, sig = _sign(key, _document([_entry(device_id=DEVICE)]))
    parsed = revocation.verify_revocation_list(raw, sig, public_key_b64=pub)
    # The license payload names the machine field "device", not "device_id".
    hit, entry = revocation.is_revoked(parsed, {'license_id': 'lic-999', 'device': DEVICE})
    assert hit and entry['device_id'] == DEVICE


def test_non_revoked_license_passes(keypair):
    key, pub = keypair
    raw, sig = _sign(key, _document([_entry(license_id='lic-123'),
                                     _entry(device_id=OTHER_DEVICE)]))
    parsed = revocation.verify_revocation_list(raw, sig, public_key_b64=pub)
    hit, entry = revocation.is_revoked(parsed, {'license_id': 'lic-456', 'device': DEVICE})
    assert hit is False and entry is None
    assert revocation.is_revoked(revocation.empty_list(),
                                 {'license_id': 'lic-123', 'device': DEVICE}) == (False, None)


def test_loader_missing_file_is_empty_not_error(tmp_path, monkeypatch, keypair):
    _, pub = keypair
    missing = tmp_path / 'revocations.json'
    monkeypatch.setenv(revocation.ENV_VAR, str(missing))
    assert revocation.load_revocation_list(public_key_b64=pub) == revocation.empty_list()
    monkeypatch.delenv(revocation.ENV_VAR)
    assert revocation.load_revocation_list() == revocation.empty_list()


def test_loader_roundtrip_and_missing_signature(tmp_path, keypair):
    key, pub = keypair
    raw, sig = _sign(key, _document([_entry(license_id='lic-123')]))
    list_path = tmp_path / 'revocations.json'
    list_path.write_bytes(raw)
    with pytest.raises(revocation.RevocationError):
        revocation.load_revocation_list(list_path, public_key_b64=pub)
    revocation.signature_path(list_path).write_text(
        base64.b64encode(sig).decode() + '\n', encoding='ascii')
    parsed = revocation.load_revocation_list(list_path, public_key_b64=pub)
    assert parsed['entries'][0]['license_id'] == 'lic-123'


def test_loader_rejects_older_list_when_minimum_known(tmp_path, keypair):
    key, pub = keypair
    raw, sig = _sign(key, _document([], issued_at=NOW - 3600))
    list_path = tmp_path / 'revocations.json'
    list_path.write_bytes(raw)
    revocation.signature_path(list_path).write_text(
        base64.b64encode(sig).decode() + '\n', encoding='ascii')
    with pytest.raises(revocation.RevocationError):
        revocation.load_revocation_list(list_path, min_issued_at=NOW, public_key_b64=pub)
    assert revocation.load_revocation_list(
        list_path, min_issued_at=NOW - 7200, public_key_b64=pub)['issued_at'] == NOW - 3600


def test_default_key_is_the_license_issuer_key(monkeypatch):
    """Without an override, verification trusts licensing.PUBLIC_KEY_B64 —
    the exact key the app already verifies licenses against."""
    key, pub = _keypair()
    monkeypatch.setattr(revocation.licensing, 'PUBLIC_KEY_B64', pub)
    raw, sig = _sign(key, _document([_entry(device_id=DEVICE)]))
    parsed = revocation.verify_revocation_list(raw, sig)
    assert revocation.is_revoked(parsed, {'license_id': 'x', 'device': DEVICE})[0] is True
