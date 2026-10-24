"""Contract tests for local Growth Intelligence advisor endpoint."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from ads_core.app import app, browser_admin
import ads_core.advisor  # noqa: F401 - registers route


PATH = '/api/advisor/growth/readiness'


def test_growth_readiness_requires_authentication():
    with TestClient(app) as client:
        response = client.post(PATH, json={'account_id': 1, 'observation': {}})
    assert response.status_code in (401, 403)


def test_growth_readiness_is_read_only_and_fail_closed():
    from ads_core.growth_intelligence import assess_change_readiness
    result = assess_change_readiness({})
    assert result['may_write_ads'] is False
    assert result['requires_human_approval'] is True
    assert result['status'] == 'diagnose_first'


def test_growth_readiness_route_is_registered():
    matches = [r for r in app.routes if getattr(r, 'path', None) == PATH]
    assert len(matches) == 1
    assert 'POST' in matches[0].methods


def test_growth_readiness_scopes_account_and_never_writes_ads():
    app.dependency_overrides[browser_admin] = lambda: {'org_id': 'tenant-a', 'id': 7}
    try:
        with patch('ads_core.advisor.license_required'), \
             patch('ads_core.advisor.get_account', return_value={
                 'id': 9, 'org_id': 'tenant-a', 'platform': 'google'
             }) as get_account, \
             TestClient(app) as client:
            response = client.post(PATH, json={
                'account_id': 9, 'observation': {'tracking_verified': False}
            })
        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'diagnose_first'
        assert body['may_write_ads'] is False
        assert body['requires_human_approval'] is True
        assert body['source'] == 'operator_supplied_observation'
        get_account.assert_called_once_with(9, 'tenant-a')
    finally:
        app.dependency_overrides.pop(browser_admin, None)


def test_growth_readiness_invalid_id_fails_validation():
    app.dependency_overrides[browser_admin] = lambda: {'org_id': 'tenant-a', 'id': 7}
    try:
        with TestClient(app) as client:
            response = client.post(PATH, json={'account_id': 0, 'observation': {}})
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(browser_admin, None)
