"""The product version has exactly one source of truth: ads_core/version.py.

These tests pin the current bootstrap release (0.3, canonical "0.3.1") and verify that
every machine-readable consumer — the FastAPI app metadata and the /healthz
status endpoint — reports the same value instead of a hardcoded copy.
"""
import base64
import re

import pytest
from fastapi.testclient import TestClient

from ads_core import version as version_module
from ads_core.version import __version__
from ads_core.app import app

SEMVER = re.compile(
    r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)'
    r'(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)'
    r'(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?'
    r'(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$')


def test_version_module_exposes_semver():
    assert isinstance(__version__, str)
    assert SEMVER.fullmatch(__version__), __version__


def test_version_is_current_release():
    # The current pilot update bootstrap is 0.3.1.
    # Bump ads_core/version.py (and only that file) when this changes.
    assert __version__ == '0.3.1'
    assert version_module.__version__ == __version__


def test_fastapi_app_metadata_uses_version_module():
    assert app.version == __version__


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'db.sqlite'))
    monkeypatch.setenv('MASTER_KEY', base64.b64encode(b'a' * 32).decode())
    monkeypatch.setenv('SESSION_SECRET', 'b' * 42)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    with TestClient(app) as c:
        yield c


def test_healthz_reports_same_version(client):
    r = client.get('/healthz')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['ok'] is True
    assert body['version'] == __version__
