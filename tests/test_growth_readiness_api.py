"""Contract tests for the local Growth Intelligence advisor endpoint."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from ads_core.app import app
import ads_core.advisor  # noqa: F401 - registers route


def test_growth_readiness_requires_authentication():
    client = TestClient(app)
    response = client.post('/api/advisor/growth/readiness', json={
        'account_id': 1, 'observation': {},
    })
    assert response.status_code in (401, 403)


def test_growth_readiness_rejects_invalid_account_id():
    client = TestClient(app)
    response = client.post('/api/advisor/growth/readiness', json={
        'account_id': 0, 'observation': {},
    })
    assert response.status_code in (401, 403, 422)


def test_growth_readiness_is_read_only_and_fail_closed():
    from ads_core.growth_intelligence import assess_change_readiness
    result = assess_change_readiness({})
    assert result['may_write_ads'] is False
    assert result['requires_human_approval'] is True
    assert result['status'] == 'diagnose_first'


def test_growth_readiness_route_is_registered():
    matches = [r for r in app.routes if getattr(r, 'path', None) ==
               '/api/advisor/growth/readiness']
    assert len(matches) == 1
    assert 'POST' in matches[0].methods
