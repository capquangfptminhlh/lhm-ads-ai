"""Signed Windows update pipeline, fully offline tests with actual Ed25519."""
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ads_core import updater
from windows import online_update, update_install
from tools import configure_desktop_update


class FakeResponse:
    def __init__(self, content):
        self.content = content
        self.headers = {'content-length': str(len(content))}

    def raise_for_status(self):
        pass

    def iter_bytes(self, chunk_size=1024*1024):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _configure(monkeypatch, binary: bytes, *, tamper_signature=False, tamper_binary=False):
    key = Ed25519PrivateKey.generate()
    pub = base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    manifest = {
        'version': '0.3.2', 'download_url': 'https://updates.example.test/LHM-Ads-AI.exe',
        'sha256': hashlib.sha256(binary).hexdigest(), 'notes': 'Regression update',
        'issued_at': 1790000000,
    }
    sig = key.sign(updater.canonical_manifest(manifest))
    if tamper_signature:
        sig = b'0'*64
    envelope = {'manifest': manifest, 'signature': base64.b64encode(sig).decode()}
    responses = [
        FakeResponse(json.dumps(envelope).encode('utf-8')),
        FakeResponse(binary + (b'broken' if tamper_binary else b'')),
    ]

    class Client:
        def __init__(self, *args, **kwargs):
            assert kwargs.get('follow_redirects') is False
            assert kwargs.get('trust_env') is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            assert url == 'https://updates.example.test/update.json'
            return responses[0]

        def stream(self, method, url):
            assert method == 'GET'
            assert url == manifest['download_url']
            return responses[1]

    monkeypatch.setattr(online_update, 'UPDATE_MANIFEST_URL',
                        'https://updates.example.test/update.json')
    monkeypatch.setattr(online_update, 'UPDATE_PUBLIC_KEY_B64', pub)
    monkeypatch.setattr(online_update.httpx, 'Client', Client)
    return manifest, envelope


def test_absent_release_public_key_is_dormant_and_offline(monkeypatch):
    monkeypatch.setattr(online_update, 'UPDATE_MANIFEST_URL', '')
    monkeypatch.setattr(online_update, 'UPDATE_PUBLIC_KEY_B64', '')
    monkeypatch.setattr(online_update.httpx, 'Client',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError('network used')))
    result = online_update.check()
    assert result['status'] == 'not_configured'


def test_signed_version_check_and_verified_staging(tmp_path, monkeypatch):
    binary = b'MZ' + b'actual-byte-payload' * 8
    manifest, _ = _configure(monkeypatch, binary)
    assert online_update.check()['status'] == 'update_available'
    result = online_update.download(tmp_path)
    assert result['status'] == 'downloaded'
    staged = online_update.staged_update(tmp_path)
    assert staged is not None
    assert staged[0].read_bytes() == binary
    assert staged[1:] == (manifest['sha256'], '0.3.2')


def test_bad_signature_rejected_without_download(tmp_path, monkeypatch):
    _configure(monkeypatch, b'MZ' + b'payload', tamper_signature=True)
    assert online_update.download(tmp_path)['status'] == 'invalid'
    assert online_update.staged_update(tmp_path) is None


def test_modified_binary_rejected_with_no_ready_state(tmp_path, monkeypatch):
    _configure(monkeypatch, b'MZ' + b'payload', tamper_binary=True)
    assert online_update.download(tmp_path)['status'] == 'invalid'
    assert online_update.staged_update(tmp_path) is None
    assert not (tmp_path / 'updates' / 'ready.json').exists()


def test_insecure_download_url_rejected_even_if_signed(tmp_path, monkeypatch):
    _configure(monkeypatch, b'MZ' + b'payload')
    for url in ('http://example.test/app.exe','https://localhost/app.exe',
                'https://example.test/payload.zip','https://username@example.test/app.exe'):
        try:
            online_update._https_url(url, executable=True)
        except online_update.UpdateError:
            continue
        raise AssertionError(f'Unsafe URL accepted: {url}')


def test_embedded_publisher_config_requires_public_key_and_https():
    assert configure_desktop_update.render('', '').startswith('# Public')
    try:
        configure_desktop_update.render('https://updates.example.test/u.json','')
    except ValueError:
        pass
    else:
        raise AssertionError('Incomplete publisher config accepted')
    pub = base64.b64encode(b'K'*32).decode()
    conf = configure_desktop_update.render('https://updates.example.test/u.json',pub)
    assert 'UPDATE_MANIFEST_URL' in conf and pub in conf


def test_installer_waits_for_parent_and_maintains_rollback():
    script = update_install._powershell_script(
        Path(r'C:\LHM Ads AI\LHM-Ads-AI.exe'),
        Path(r'C:\Users\Owner\AppData\Local\LHMAdsAI\updates\0.3.1\LHM-Ads-AI.exe'),
        'a'*64, '0.3.1', 12345)
    assert 'Get-Process -Id $oldProcessId' in script
    assert 'Get-FileHash -LiteralPath $source' in script
    assert 'Rename-Item -LiteralPath $target' in script
    assert '.backup-0.3.1' in script
    assert 'Start-Process -FilePath $target' in script
    assert 'Remove-Item -LiteralPath $target' not in script


def test_commercial_build_requires_signed_update_configuration_in_ci():
    workflow = (Path(__file__).resolve().parents[1] /
                '.github' / 'workflows' / 'windows-exe.yml').read_text(encoding='utf-8')
    assert 'Require signed online updates for commercial Windows releases' in workflow
    assert "github.event_name == 'workflow_dispatch' && inputs.commercial" in workflow
    assert 'from windows.online_update import configuration' in workflow
    assert 'Commercial release blocked: signed online updates not configured' in workflow
