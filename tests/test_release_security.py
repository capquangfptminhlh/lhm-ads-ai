"""Commercial release invariant checks. No client ad tokens, live providers or seller key."""
import base64
import json
from pathlib import Path
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from ads_core import licensing
from tools.license_issuer import create_vendor_keys, public_b64
from tools.prepare_commercial_build import prepare_commercial


def test_keygen_encrypts_private_key_and_matches_public(tmp_path):
    private=tmp_path/'private.pem'
    public=tmp_path/'public.b64'
    b64=create_vendor_keys(private,public,'a-very-strong-offline-vendor-password-123')
    assert b'ENCRYPTED PRIVATE KEY' in private.read_bytes()
    assert public.read_text().strip()==b64
    assert 'PRIVATE' not in public.read_text()
    with pytest.raises(FileExistsError):
        create_vendor_keys(private,public,'other-very-secure-vendor-password')
    with pytest.raises(ValueError):
        create_vendor_keys(tmp_path/'bad',tmp_path/'bad.pub','weak')


def test_build_pins_only_valid_public_key_in_isolated_copy(tmp_path):
    sk=Ed25519PrivateKey.generate()
    pub=public_b64(sk)
    lic=tmp_path/'licensing.py'
    lic.write_text("PUBLIC_KEY_B64 = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='\n",encoding='utf-8')
    info=tmp_path/'release_info.py'
    info.write_text("EDITION = 'pilot'\n",encoding='utf-8')
    lease=public_b64(Ed25519PrivateKey.generate())
    original=lic.read_text()
    with pytest.raises(ValueError):
        prepare_commercial('not-a-key',lic,info,lease_public_b64=lease)
    with pytest.raises(ValueError,match="Missing LHM_LEASE_PUBLIC_KEY_B64"):
        prepare_commercial(pub,lic,info)
    assert lic.read_text()==original, "Failed commercial setup must not mutate issuer pin"
    assert info.read_text()=="EDITION = 'pilot'\n"
    prepare_commercial(pub,lic,info,lease_public_b64=lease)
    assert f"PUBLIC_KEY_B64 = '{pub}'" in lic.read_text()
    assert info.read_text()==("EDITION = 'commercial'\n"
                              f"LEASE_PUBLIC_KEY_B64 = '{lease}'\n"
                              "CLOUD_LICENSE_MODE = 'required'\n")


def test_build_with_lease_key_turns_on_gmail_mode(tmp_path):
    sk=Ed25519PrivateKey.generate()
    lic=tmp_path/'licensing.py'
    lic.write_text("PUBLIC_KEY_B64 = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='\n",encoding='utf-8')
    info=tmp_path/'release_info.py'
    original=lic.read_text()
    with pytest.raises(ValueError):
        prepare_commercial(public_b64(sk),lic,info,lease_public_b64='not-a-key')
    assert lic.read_text()==original, "Invalid lease key must not partially mutate issuer pin"
    assert not info.exists(), "Invalid lease key must not write a commercial edition"
    lease=public_b64(Ed25519PrivateKey.generate())
    prepare_commercial(public_b64(sk),lic,info,lease_public_b64=lease)
    namespace={}
    exec(info.read_text(),namespace)
    assert namespace['EDITION']=='commercial'
    assert namespace['LEASE_PUBLIC_KEY_B64']==lease
    assert namespace['CLOUD_LICENSE_MODE']=='required'


def test_license_clock_anchor_detects_rollback_and_tampering(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'ads.db'))
    monkeypatch.setenv('MASTER_KEY',base64.b64encode(b'k'*32).decode())
    assert licensing.trusted_clock(now=1700000100)==(True,None)
    assert licensing.trusted_clock(now=1699990000)==(False,'clock_rollback')
    assert licensing.trusted_clock(now=1700000150)==(True,None)
    state=licensing.license_folder()/'clock-anchor.json'
    assert '1700000100' not in state.read_text()
    state.write_text(json.dumps({'sealed':'tampered'}))
    assert licensing.trusted_clock(now=1700000200)==(False,'clock_state_invalid')


def test_no_private_key_found_in_shipped_sources():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    assert 'Ed25519PrivateKey' not in (root/'ads_core'/'licensing.py').read_text(encoding='utf-8')
    assert 'private-key.pem' not in (root/'windows'/'launcher.py').read_text(encoding='utf-8')
