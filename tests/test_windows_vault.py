"""Local secret vault safety checks; DPAPI round-trip exercised on Windows CI."""
import base64
import json
import os
import pytest

from ads_core.windows_vault import read_or_create_settings,dpapi_encrypt,dpapi_decrypt


def test_no_silent_master_key_regeneration(tmp_path):
    path=tmp_path/'local-settings.json'
    original=read_or_create_settings(path)
    assert read_or_create_settings(path)==original
    if os.name!='nt':
        path.write_text('{"corrupt":true}',encoding='utf-8')
        with pytest.raises(RuntimeError):read_or_create_settings(path)


@pytest.mark.skipif(os.name!='nt',reason='Windows DPAPI only')
def test_windows_dpapi_encrypt_decrypt_and_old_settings_migration(tmp_path):
    secret=b'NO-EXPORT-ADS-KEYS-TO-GITHUB'
    assert dpapi_decrypt(dpapi_encrypt(secret))==secret
    path=tmp_path/'local-settings.json'
    legacy={'MASTER_KEY':base64.b64encode(b'k'*32).decode(), 'SESSION_SECRET':'s'*48}
    path.write_text(json.dumps(legacy),encoding='utf-8')
    migrated=read_or_create_settings(path)
    assert migrated==legacy
    raw=path.read_text(encoding='utf-8')
    assert 'MASTER_KEY' not in raw and legacy['MASTER_KEY'] not in raw
    assert 'windows-dpapi-v1' in raw
    assert read_or_create_settings(path)==legacy
