"""Read-only skill tests: every missing/sparse signal must fail closed."""
from ads_core.growth_intelligence import assess_change_readiness, hourly_cohort_candidates


def stable(**changes):
    data = dict(critical_incident='none', tracking_verified=True, website_healthy=True,
                learning_status='stable', conversion_cycle_hours=36,
                hours_since_major_change=400, evaluation_window_hours=400,
                matured_conversions=24, experiment_supported=True)
    return dict(data, **changes)


def test_ready_never_authorizes_mutations():
    result = assess_change_readiness(stable())
    assert result['status'] == 'proposal_ready'
    assert result['requires_human_approval'] is True
    assert result['may_write_ads'] is False
    assert result['skill_version']


def test_no_context_fails_closed():
    assert assess_change_readiness(None)['status'] == 'diagnose_first'
    assert assess_change_readiness([])['status'] == 'diagnose_first'
    assert assess_change_readiness(stable(tracking_verified=None))['status'] == 'diagnose_first'
    assert assess_change_readiness(stable(website_healthy=None))['status'] == 'diagnose_first'
    assert assess_change_readiness(stable(learning_status='unknown'))['status'] == 'observe_only'
    assert assess_change_readiness(stable(learning_status='learning'))['status'] == 'observe_only'


def test_urgent_issue_alerts_but_cannot_write():
    result = assess_change_readiness(stable(critical_incident='unexpected_spend'))
    assert result['status'] == 'urgent_review'
    assert not result['may_write_ads']
    assert assess_change_readiness(stable(website_healthy=False))['status'] == 'urgent_review'


def test_conversion_lag_prevents_premature_edit():
    assert assess_change_readiness(stable(conversion_cycle_hours=250, hours_since_major_change=400))['status'] == 'observe_only'
    assert assess_change_readiness(stable(evaluation_window_hours=48))['status'] == 'observe_only'
    assert assess_change_readiness(stable(hours_since_major_change=24))['status'] == 'observe_only'
    assert assess_change_readiness(stable(matured_conversions=2))['status'] == 'observe_only'


def test_missing_invalid_or_unverified_data_blocks_proposal():
    for field in ('conversion_cycle_hours', 'hours_since_major_change',
                  'evaluation_window_hours', 'matured_conversions'):
        for value in (None, float('nan'), float('inf'), -1, True):
            assert assess_change_readiness(stable(**{field: value}))['status'] != 'proposal_ready'
    assert assess_change_readiness(stable(experiment_supported=False))['status'] == 'diagnose_first'
    assert assess_change_readiness(stable(experiment_supported=None))['status'] == 'diagnose_first'


def test_hourly_cohorts_are_descriptive_only():
    history = [
        dict(weekday=5, hour=20, days_observed=5, clicks=100, conversions=10, spend=450000, matured=True),
        dict(weekday=3, hour=9, days_observed=5, clicks=100, conversions=5, spend=600000, matured=True),
    ]
    result = hourly_cohort_candidates(history)
    assert [(x['weekday'], x['hour']) for x in result] == [(5, 20), (3, 9)]
    assert result[0]['cpa'] == 45000
    assert all(x['may_adjust_schedule'] is False for x in result)


def test_hourly_sparse_unmatured_bad_data_is_excluded():
    good = dict(weekday=5, hour=20, days_observed=5, clicks=100, conversions=10, spend=450000, matured=True)
    for changes in (dict(matured=False), dict(days_observed=2), dict(clicks=10),
                    dict(conversions=4), dict(conversions=101), dict(spend=float('nan')),
                    dict(hour=24), dict(weekday=7), dict(hour=True)):
        assert hourly_cohort_candidates([dict(good, **changes)]) == []
    assert hourly_cohort_candidates(None) == []
