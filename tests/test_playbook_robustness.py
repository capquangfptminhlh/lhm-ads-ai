"""Robustness stress tests for ads_core.optimization_playbook.

Hostile / degenerate inputs must never crash the playbook and must never
fabricate findings: a metric that is missing, non-numeric, non-finite or
negative (physically impossible for every metric this module consumes) is
treated as absent data, and every rule depending on it stays silent.

Pure functions only: no network, no DB.
"""
import copy
import math

import pytest

from ads_core import optimization_playbook as pb

NAN = float('nan')
INF = float('inf')

# Values that must be treated as "no data" wherever a metric is expected.
BAD_VALUES = [None, NAN, INF, -INF, 'abc', '', 'NaN', 'inf', '1,000',
              True, False, [], {}, object()]


def campaign(**kw):
    base = {'id': '111', 'name': 'C', 'status': 'ENABLED', 'spend': 0.0, 'clicks': 0,
            'impressions': 0, 'ctr_percent': None, 'conversions': None,
            'conversion_value': None, 'cpa': None, 'roas': None}
    base.update(kw)
    return base


def goal_cpa(target=100.0, **kw):
    g = {'enabled': 1, 'objective': 'cpa', 'target': target, 'min_conversions': 5,
         'min_clicks': 100, 'currency': 'USD', 'meta_action_type': None}
    g.update(kw)
    return g


def codes(findings):
    return [f['code'] for f in findings]


def rich_campaign():
    """A campaign that legitimately fires several rules at once."""
    return campaign(spend=1600.0, clicks=300, impressions=9000, ctr_percent=3.3,
                    conversions=10, conversion_value=16000.0, cpa=160.0, roas=10.0)


# ---------------------------------------------------------------------------
# Empty / junk containers
# ---------------------------------------------------------------------------
def test_empty_and_none_campaign_lists():
    assert pb.evaluate_campaigns([], 'google', 'USD') == []
    assert pb.evaluate_campaigns(None, 'google', 'USD') == []
    assert pb.evaluate_account([], 'google', 'USD') == []
    assert pb.evaluate_account(None, 'google', 'USD') == []


def test_non_list_campaign_containers_do_not_raise():
    for junk in ('not-a-list', 42, 3.5, {'a': 1}):
        assert pb.evaluate_campaigns(junk, 'google', 'USD') == []
        assert pb.evaluate_account(junk, 'google', 'USD') == []


def test_junk_entries_inside_campaign_list_are_skipped():
    dead = campaign(spend=0.0, impressions=0, clicks=0)
    junk = [None, 'junk', 42, 3.5, [], {}, {'id': None}, {'name': 'no id'}]
    findings = pb.evaluate_campaigns(junk + [dead], 'google', 'USD')
    assert codes(findings) == ['dead_campaign']
    assert pb.evaluate_account(junk, 'google', 'USD') == []


def test_campaign_with_only_id_and_status_produces_nothing():
    bare = {'id': '111', 'status': 'ENABLED'}
    assert pb.evaluate_campaigns([bare], 'google', 'USD', goal_cpa()) == []
    assert pb.evaluate_campaigns([bare], 'meta', 'USD', goal_cpa()) == []


def test_missing_metrics_campaign_is_silent_except_dead():
    # spend/impressions explicitly 0 is real data (dead campaign); everything
    # else missing must not fabricate any other finding.
    c = campaign(spend=0.0, impressions=0)
    findings = pb.evaluate_campaigns([c], 'google', 'USD', goal_cpa())
    assert codes(findings) == ['dead_campaign']
    # spend/impressions missing too -> completely silent.
    c2 = {'id': '111', 'status': 'ENABLED', 'spend': None, 'impressions': None}
    assert pb.evaluate_campaigns([c2], 'google', 'USD', goal_cpa()) == []


# ---------------------------------------------------------------------------
# Bad metric values: never raise, dependent rule stays silent
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('bad', BAD_VALUES)
def test_bad_cpa_silences_cpa_rules(bad):
    c = rich_campaign()
    c['cpa'] = bad
    findings = pb.evaluate_campaigns([c], 'google', 'USD', goal_cpa(100.0))
    assert 'cpa_above_target' not in codes(findings)
    assert 'cpa_well_below_target_scale' not in codes(findings)


@pytest.mark.parametrize('bad', BAD_VALUES)
def test_bad_conversions_silences_volume_dependent_rules(bad):
    c = rich_campaign()
    c['conversions'] = bad
    findings = pb.evaluate_campaigns([c], 'google', 'USD', goal_cpa(100.0))
    for code in ('cpa_above_target', 'spend_no_conversions',
                 'low_conversion_volume_for_smart_bidding',
                 'high_ctr_no_conversions'):
        assert code not in codes(findings)


@pytest.mark.parametrize('bad', BAD_VALUES)
def test_bad_spend_and_clicks_do_not_raise(bad):
    c = campaign(clicks=80, impressions=5000, ctr_percent=1.6, conversions=0, spend=250.0)
    # spend/clicks are inputs of spend_no_conversions: corrupting either must
    # silence it. impressions/ctr are not its inputs: only "never raises".
    for key in ('spend', 'clicks'):
        mutated = dict(c)
        mutated[key] = bad
        findings = pb.evaluate_campaigns([mutated], 'google', 'USD')
        assert 'spend_no_conversions' not in codes(findings)
    for key in ('impressions', 'ctr_percent'):
        mutated = dict(c)
        mutated[key] = bad
        findings = pb.evaluate_campaigns([mutated], 'google', 'USD')
        assert isinstance(findings, list)


@pytest.mark.parametrize('bad', BAD_VALUES)
def test_bad_roas_and_value_silence_roas_rules(bad):
    c = campaign(spend=1000.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=10, conversion_value=3000.0, roas=3.0)
    goal = {'enabled': 1, 'objective': 'roas', 'target': 4.0, 'min_conversions': 5,
            'min_clicks': 100, 'currency': 'USD', 'meta_action_type': 'purchase'}
    for key in ('roas', 'conversion_value'):
        mutated = dict(c)
        mutated[key] = bad
        findings = pb.evaluate_campaigns([mutated], 'google', 'USD', goal)
        assert 'roas_below_target' not in codes(findings)
        assert 'roas_above_target_scale' not in codes(findings)


@pytest.mark.parametrize('bad', BAD_VALUES)
def test_bad_platform_targets_silence_platform_rules(bad):
    # CPA-driven campaign: corrupting bid_target_cpa silences both rules.
    c = campaign(spend=1600.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=20, cpa=500.0, bid_target_cpa=100.0)
    assert 'platform_target_missed' in codes(pb.evaluate_campaigns([c], 'google', 'USD'))
    mutated = dict(c, bid_target_cpa=bad)
    findings = pb.evaluate_campaigns([mutated], 'google', 'USD')
    assert 'platform_target_missed' not in codes(findings)
    assert 'platform_target_headroom' not in codes(findings)
    # ROAS-driven campaign: corrupting bid_target_roas silences both rules.
    c2 = campaign(spend=1600.0, clicks=300, impressions=9000, ctr_percent=3.3,
                  conversions=20, cpa=500.0, roas=0.5, bid_target_roas=4.0)
    assert 'platform_target_missed' in codes(pb.evaluate_campaigns([c2], 'google', 'USD'))
    mutated2 = dict(c2, bid_target_roas=bad)
    findings2 = pb.evaluate_campaigns([mutated2], 'google', 'USD')
    assert 'platform_target_missed' not in codes(findings2)
    assert 'platform_target_headroom' not in codes(findings2)


def test_every_metric_bad_at_once_never_raises():
    keys = ('spend', 'clicks', 'impressions', 'ctr_percent', 'conversions',
            'conversion_value', 'cpa', 'roas', 'bid_target_cpa', 'bid_target_roas',
            'bidding_strategy')
    for bad in BAD_VALUES:
        c = campaign(**{k: bad for k in keys})
        for platform in ('google', 'meta'):
            status = 'ENABLED' if platform == 'google' else 'ACTIVE'
            findings = pb.evaluate_campaigns([dict(c, status=status)], platform, 'USD',
                                             goal_cpa(100.0))
            assert findings == [], (bad, platform, findings)


def test_non_numeric_string_metrics_are_silent():
    c = campaign(clicks='eighty', impressions='lots', ctr_percent='high',
                 conversions='zero', spend='much', cpa='dear', roas='great')
    assert pb.evaluate_campaigns([c], 'google', 'USD', goal_cpa()) == []


def test_numeric_string_metrics_behave_like_numbers():
    # _num deliberately accepts numeric strings (provider payloads vary);
    # they are real data, not missing data.
    c = campaign(clicks='80', impressions='5000', ctr_percent='1.6',
                 conversions='0', spend='250')
    assert 'spend_no_conversions' in codes(pb.evaluate_campaigns([c], 'google', 'USD'))


# ---------------------------------------------------------------------------
# Negative (physically impossible) metrics must not fabricate findings
# ---------------------------------------------------------------------------
def test_negative_cpa_does_not_create_scale_opportunity():
    c = campaign(spend=700.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=10, cpa=-70.0)
    findings = pb.evaluate_campaigns([c], 'google', 'USD', goal_cpa(100.0))
    assert 'cpa_well_below_target_scale' not in codes(findings)
    assert 'cpa_above_target' not in codes(findings)


def test_negative_cpa_does_not_create_platform_headroom():
    c = campaign(spend=700.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=20, cpa=-1.0, bid_target_cpa=100.0)
    findings = pb.evaluate_campaigns([c], 'google', 'USD')
    assert 'platform_target_headroom' not in codes(findings)
    assert 'platform_target_missed' not in codes(findings)


def test_negative_roas_does_not_create_below_target_or_drift():
    goal = {'enabled': 1, 'objective': 'roas', 'target': 4.0, 'min_conversions': 5,
            'min_clicks': 100, 'currency': 'USD', 'meta_action_type': 'purchase'}
    c = campaign(spend=1000.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=10, conversion_value=3000.0, roas=-2.0)
    findings = pb.evaluate_campaigns([c], 'google', 'USD', goal)
    assert 'roas_below_target' not in codes(findings)
    baselines = pb.compute_baselines(
        [{'id': '111', 'cpa': None, 'roas': 5.0, 'period': f'W{i}'} for i in range(3)])
    findings = pb.evaluate_campaigns([c], 'google', 'USD', None, baselines)
    assert 'roas_drift_vs_baseline' not in codes(findings)


def test_negative_counts_do_not_create_findings():
    c = campaign(spend=-100.0, clicks=-50, impressions=-1000, ctr_percent=-1.0,
                 conversions=-3, conversion_value=-500.0, cpa=-10.0, roas=-1.0,
                 bid_target_cpa=100.0)
    assert pb.evaluate_campaigns([c], 'google', 'USD', goal_cpa()) == []
    assert pb.evaluate_account([c], 'google', 'USD', goal_cpa()) == []


# ---------------------------------------------------------------------------
# Extreme magnitudes: no division / rounding blowups
# ---------------------------------------------------------------------------
def test_extreme_ratio_does_not_blow_up_pct_delta():
    # CPA astronomically above a denormal-tiny target: (cpa/target) overflows
    # a float; message formatting must saturate, not raise OverflowError.
    c = campaign(spend=1e308, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=10, cpa=1e308)
    findings = pb.evaluate_campaigns([c], 'google', 'USD', goal_cpa(1e-300))
    finding = [f for f in findings if f['code'] == 'cpa_above_target']
    assert len(finding) == 1 and finding[0]['level'] == 'critical'


def test_extreme_drift_ratio_does_not_blow_up():
    baselines = {'111': {'campaign_id': '111', 'periods': 3, 'median_cpa': 1e-300,
                         'median_roas': None, 'cpa_volatility': None,
                         'roas_volatility': None}}
    c = campaign(spend=1e308, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=10, cpa=1e308)
    findings = pb.evaluate_campaigns([c], 'google', 'USD', None, baselines)
    assert 'cpa_drift_vs_baseline' in codes(findings)


def test_huge_values_do_not_raise_anywhere():
    huge = campaign(spend=1e308, clicks=10**30, impressions=10**30, ctr_percent=1e308,
                    conversions=1e308, conversion_value=1e308, cpa=1e308, roas=1e308,
                    bid_target_cpa=1.0, bidding_strategy='MANUAL_CPC')
    findings = pb.evaluate_campaigns([huge], 'google', 'USD', goal_cpa(100.0))
    assert isinstance(findings, list)
    for f in findings:
        assert isinstance(f['message'], str) and f['message']


# ---------------------------------------------------------------------------
# Hostile goals
# ---------------------------------------------------------------------------
def test_hostile_goal_objects_never_raise_and_goal_rules_stay_silent():
    c = rich_campaign()
    dead = campaign(spend=0.0, impressions=0, clicks=0)
    bad_goals = ['junk', 42, 3.5, ['x'], {'enabled': 1},
                 goal_cpa('abc'), goal_cpa(NAN), goal_cpa(INF), goal_cpa(-5.0),
                 goal_cpa(True), goal_cpa(None),
                 goal_cpa(100.0, objective='bogus')]
    for goal in bad_goals:
        findings = pb.evaluate_campaigns([c], 'google', 'USD', goal)
        assert 'cpa_above_target' not in codes(findings), goal
        # Non-goal rules are unaffected by a broken goal.
        assert 'dead_campaign' in codes(pb.evaluate_campaigns([dead], 'google', 'USD', goal))
    # A non-integer min_conversions degrades gracefully to the module default
    # floor (5) instead of breaking the goal: 10 conversions fire, 4 do not.
    degraded = goal_cpa(100.0, min_conversions='lots')
    assert 'cpa_above_target' in codes(pb.evaluate_campaigns([c], 'google', 'USD', degraded))
    thin = dict(c, conversions=4)
    assert 'cpa_above_target' not in codes(pb.evaluate_campaigns([thin], 'google', 'USD', degraded))


# ---------------------------------------------------------------------------
# Baselines: single snapshot, hostile shapes
# ---------------------------------------------------------------------------
def test_compute_baselines_single_snapshot():
    baselines = pb.compute_baselines([{'id': '111', 'cpa': 80.0, 'roas': 4.0, 'period': 'W1'}])
    b = baselines['111']
    assert b['periods'] == 1 and b['median_cpa'] == 80.0 and b['median_roas'] == 4.0
    assert b['cpa_volatility'] is None and b['roas_volatility'] is None
    # Drift can still be judged against a single-period baseline (documented
    # as reference-only in the rule guardrails) and must not crash.
    now = campaign(spend=1300.0, clicks=300, impressions=9000, ctr_percent=3.3,
                   conversions=10, cpa=130.0)
    findings = pb.evaluate_campaigns([now], 'google', 'USD', None, baselines)
    assert 'cpa_drift_vs_baseline' in codes(findings)


def test_compute_baselines_hostile_snapshots():
    assert pb.compute_baselines(None) == {}
    assert pb.compute_baselines('junk') == {}
    assert pb.compute_baselines(42) == {}
    snaps = [{'id': '111', 'cpa': 'abc'}, {'id': '111', 'cpa': None},
             {'id': '111'}, {'id': '111', 'cpa': NAN, 'roas': INF},
             {'id': '111', 'cpa': -50.0, 'roas': -2.0},
             'junk', None, {'cpa': 100.0}]
    baselines = pb.compute_baselines(snaps)
    b = baselines['111']
    # Only impossible/absent values were supplied: no median may be invented.
    assert b['median_cpa'] is None and b['median_roas'] is None


def test_hostile_baseline_objects_do_not_raise():
    now = campaign(spend=2000.0, clicks=300, impressions=9000, ctr_percent=3.3,
                   conversions=10, cpa=200.0, roas=1.0)
    for baselines in ('junk', 42, ['x'], {'111': 'junk'}, {'111': 42},
                      {'111': {'median_cpa': 'abc', 'periods': 'x'}},
                      {'111': {'median_cpa': NAN, 'median_roas': INF}}):
        findings = pb.evaluate_campaigns([now], 'google', 'USD', None, baselines)
        assert 'cpa_drift_vs_baseline' not in codes(findings), baselines
        assert 'roas_drift_vs_baseline' not in codes(findings), baselines


def test_hostile_baseline_volatility_does_not_crash_drift_message():
    # median is valid (drift fires) but volatility is garbage: formatting the
    # historical band must degrade to "no band", never raise.
    for band in ('boom', INF, NAN, [], {}, -1.0):
        baselines = {'111': {'campaign_id': '111', 'periods': 3, 'median_cpa': 100.0,
                             'median_roas': None, 'cpa_volatility': band,
                             'roas_volatility': None}}
        now = campaign(spend=2000.0, clicks=300, impressions=9000, ctr_percent=3.3,
                       conversions=10, cpa=200.0)
        findings = pb.evaluate_campaigns([now], 'google', 'USD', None, baselines)
        assert 'cpa_drift_vs_baseline' in codes(findings), band


# ---------------------------------------------------------------------------
# verify_outcome: partial / mismatched / hostile snapshots
# ---------------------------------------------------------------------------
def test_verify_outcome_partial_snapshots():
    full = campaign(conversions=10, cpa=160.0, roas=3.0, ctr_percent=0.3, impressions=100)
    partials = [{}, {'cpa': 100.0},
                {'conversions': None, 'cpa': None},
                {'conversions': 'ten', 'cpa': 'dear'},
                {'conversions': NAN, 'cpa': INF},
                {'conversions': -3, 'cpa': -50.0}]
    for code in ('cpa_above_target', 'roas_below_target', 'spend_no_conversions',
                 'low_ctr', 'dead_campaign', 'platform_target_missed',
                 'low_conversion_volume_for_smart_bidding'):
        for snap in partials:
            assert pb.verify_outcome(snap, full, code) == 'insufficient_data', (code, snap)
            assert pb.verify_outcome(full, snap, code) == 'insufficient_data', (code, snap)
    # A conversions-only snapshot IS sufficient for the volume code, whose
    # verdict depends on conversions alone: equal volume -> unchanged.
    assert pb.verify_outcome({'conversions': 10}, {'conversions': 10},
                             'low_conversion_volume_for_smart_bidding') == 'unchanged'
    assert pb.verify_outcome({'conversions': 10}, {'conversions': 12},
                             'low_conversion_volume_for_smart_bidding') == 'improved'


def test_verify_outcome_non_dict_and_unknown_code():
    full = campaign(conversions=10, cpa=160.0)
    for snap in (None, 'junk', 42, ['x']):
        assert pb.verify_outcome(snap, full, 'cpa_above_target') == 'insufficient_data'
        assert pb.verify_outcome(full, snap, 'cpa_above_target') == 'insufficient_data'
    for code in (None, '', 'no_such_code', 42):
        assert pb.verify_outcome(full, full, code) == 'insufficient_data'


def test_verify_outcome_mismatched_campaign_ids_do_not_raise():
    # verify_outcome judges the two snapshots it is handed; mismatched ids
    # are the caller's problem, but it must still answer with a valid label.
    a = campaign(id='111', conversions=10, cpa=160.0)
    b = campaign(id='999', conversions=12, cpa=100.0)
    assert pb.verify_outcome(a, b, 'cpa_above_target') in (
        'improved', 'worsened', 'unchanged', 'insufficient_data')


def test_verify_outcome_extreme_values_do_not_raise():
    a = campaign(conversions=10, cpa=1e308, roas=1e-300)
    b = campaign(conversions=10, cpa=1e-300, roas=1e308)
    assert pb.verify_outcome(a, b, 'cpa_above_target') == 'improved'
    assert pb.verify_outcome(a, b, 'roas_below_target') == 'improved'


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_determinism_same_input_same_output():
    campaigns = [
        rich_campaign(),
        campaign(id='222', spend=100.0, clicks=50, impressions=2000, ctr_percent=2.5,
                 conversions=3),
        campaign(id='333', spend=0.0, impressions=0, clicks=0),
        campaign(id='444', spend=900.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=40, cpa=50.0, bid_target_cpa=100.0,
                 bidding_strategy='MANUAL_CPC'),
    ]
    baselines = pb.compute_baselines(
        [{'id': '111', 'cpa': 100.0, 'roas': 5.0, 'period': f'W{i}'} for i in range(3)])
    snapshot_of_input = copy.deepcopy(campaigns)
    first = pb.evaluate_campaigns(campaigns, 'google', 'USD', goal_cpa(100.0), baselines)
    second = pb.evaluate_campaigns(campaigns, 'google', 'USD', goal_cpa(100.0), baselines)
    assert first == second
    assert [f['code'] for f in first] == [f['code'] for f in second]
    # Inputs are not mutated by evaluation (conflict guard copies findings).
    assert campaigns == snapshot_of_input
    assert pb.compute_baselines(
        [{'id': '111', 'cpa': 100.0, 'roas': 5.0, 'period': f'W{i}'} for i in range(3)]
    ) == baselines
    assert pb.evaluate_account(campaigns, 'google', 'USD', goal_cpa(100.0)) == \
        pb.evaluate_account(campaigns, 'google', 'USD', goal_cpa(100.0))
