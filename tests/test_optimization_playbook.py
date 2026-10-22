"""Offline unit tests for ads_core.optimization_playbook (LHM Vòng lặp Tối ưu).

No network, no DB: the playbook is a pure function over campaign dicts,
an optional goals.goal_for dict, and optional per-account baselines.
"""
import pytest

from ads_core import optimization_playbook as pb


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


def goal_roas(target=4.0, **kw):
    g = {'enabled': 1, 'objective': 'roas', 'target': target, 'min_conversions': 5,
         'min_clicks': 100, 'currency': 'USD', 'meta_action_type': 'purchase'}
    g.update(kw)
    return g


def codes(findings):
    return [f['code'] for f in findings]


def only(findings, code):
    matches = [f for f in findings if f['code'] == code]
    assert len(matches) == 1, f'expected exactly one {code}, got {codes(findings)}'
    return matches[0]


# --------------------------------------------------------------------------
# spend_no_conversions
# --------------------------------------------------------------------------
def test_spend_no_conversions_fires_both_platforms():
    c = campaign(clicks=80, impressions=5000, ctr_percent=1.6, conversions=0, spend=250.0)
    for platform in ('google', 'meta'):
        status = 'ENABLED' if platform == 'google' else 'ACTIVE'
        f = pb.evaluate_campaigns([dict(c, status=status)], platform, 'USD')
        finding = only(f, 'spend_no_conversions')
        assert finding['level'] == 'review'
        assert 'tracking' in finding['message']
        # Tracking findings must demand verification, not a pause.
        assert any('tracking' in a.lower() or 'sự kiện' in a.lower()
                   for a in finding['playbook']['actions'])
        assert any('Không tự tắt' in g for g in finding['playbook']['guardrails'])


def test_spend_no_conversions_boundaries_and_none():
    base = dict(impressions=5000, ctr_percent=1.6, conversions=0, spend=250.0)
    assert 'spend_no_conversions' not in codes(pb.evaluate_campaigns(
        [campaign(clicks=49, **base)], 'google', 'USD'))  # below click floor
    assert 'spend_no_conversions' not in codes(pb.evaluate_campaigns(
        [campaign(clicks=50, **dict(base, spend=0.0))], 'google', 'USD'))  # no spend
    assert 'spend_no_conversions' not in codes(pb.evaluate_campaigns(
        [campaign(clicks=80, **dict(base, conversions=None))], 'google', 'USD'))  # unknown != 0
    assert 'spend_no_conversions' not in codes(pb.evaluate_campaigns(
        [campaign(clicks=80, **dict(base, conversions=1))], 'google', 'USD'))
    assert 'spend_no_conversions' in codes(pb.evaluate_campaigns(
        [campaign(clicks=50, **base)], 'google', 'USD'))  # exact boundary fires


# --------------------------------------------------------------------------
# CPA vs target
# --------------------------------------------------------------------------
def test_cpa_above_target_review_and_critical():
    c = campaign(spend=1300.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=10, cpa=130.0)
    f = pb.evaluate_campaigns([c], 'google', 'USD', goal_cpa(100.0))
    finding = only(f, 'cpa_above_target')
    assert finding['level'] == 'review'
    assert '130' in finding['message'] and '100' in finding['message']
    c2 = dict(c, cpa=160.0, spend=1600.0)
    f2 = pb.evaluate_campaigns([c2], 'google', 'USD', goal_cpa(100.0))
    assert only(f2, 'cpa_above_target')['level'] == 'critical'


def test_cpa_above_target_boundaries():
    base = dict(spend=1200.0, clicks=300, impressions=9000, ctr_percent=3.3, conversions=10)
    # exactly 1.2x is NOT above the review ratio
    assert 'cpa_above_target' not in codes(pb.evaluate_campaigns(
        [campaign(cpa=120.0, **base)], 'google', 'USD', goal_cpa(100.0)))
    # too few conversions: silent even when CPA is terrible
    assert 'cpa_above_target' not in codes(pb.evaluate_campaigns(
        [campaign(cpa=900.0, **dict(base, conversions=4, spend=3600.0))], 'google', 'USD', goal_cpa(100.0)))
    # cpa missing -> silent
    assert 'cpa_above_target' not in codes(pb.evaluate_campaigns(
        [campaign(cpa=None, **base)], 'google', 'USD', goal_cpa(100.0)))


def test_cpa_scale_opportunity():
    c = campaign(spend=700.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=10, cpa=70.0)
    f = pb.evaluate_campaigns([c], 'google', 'USD', goal_cpa(100.0))
    finding = only(f, 'cpa_well_below_target_scale')
    assert finding['level'] == 'opportunity'
    assert any('20%' in a for a in finding['playbook']['actions'])
    # exactly 0.8x is not below the scale ratio; too few conversions also silent
    assert 'cpa_well_below_target_scale' not in codes(pb.evaluate_campaigns(
        [dict(c, cpa=80.0)], 'google', 'USD', goal_cpa(100.0)))
    assert 'cpa_well_below_target_scale' not in codes(pb.evaluate_campaigns(
        [dict(c, conversions=9, cpa=63.0)], 'google', 'USD', goal_cpa(100.0)))


# --------------------------------------------------------------------------
# ROAS vs target
# --------------------------------------------------------------------------
def test_roas_below_target_review_and_critical():
    c = campaign(status='ACTIVE', spend=1000.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=10, conversion_value=3000.0, roas=3.0)
    f = pb.evaluate_campaigns([c], 'meta', 'USD', goal_roas(4.0))
    assert only(f, 'roas_below_target')['level'] == 'review'
    c2 = dict(c, roas=2.5, conversion_value=2500.0)
    f2 = pb.evaluate_campaigns([c2], 'meta', 'USD', goal_roas(4.0))
    assert only(f2, 'roas_below_target')['level'] == 'critical'


def test_roas_rules_need_value_and_objective():
    c = campaign(spend=1000.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=10, conversion_value=None, roas=None)
    f = pb.evaluate_campaigns([c], 'google', 'USD', goal_roas(4.0))
    assert 'roas_below_target' not in codes(f) and 'roas_above_target_scale' not in codes(f)
    # ROAS numbers present but goal objective is CPA -> roas rules silent
    c2 = dict(c, conversion_value=3000.0, roas=3.0, cpa=100.0)
    f = pb.evaluate_campaigns([c2], 'google', 'USD', goal_cpa(100.0))
    assert 'roas_below_target' not in codes(f)


def test_roas_scale_opportunity():
    c = campaign(spend=1000.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=12, conversion_value=6000.0, roas=6.0)
    f = pb.evaluate_campaigns([c], 'google', 'USD', goal_roas(4.0))
    finding = only(f, 'roas_above_target_scale')
    assert finding['level'] == 'opportunity'
    # exactly 1.3x does not fire
    assert 'roas_above_target_scale' not in codes(pb.evaluate_campaigns(
        [dict(c, roas=5.2)], 'google', 'USD', goal_roas(4.0)))


# --------------------------------------------------------------------------
# Goal absent / disabled / currency mismatch -> goal rules silent
# --------------------------------------------------------------------------
def test_goal_absent_or_disabled_silences_goal_rules_only():
    c = campaign(spend=1600.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=10, cpa=160.0)
    for goal in (None, goal_cpa(100.0, enabled=0), goal_cpa(100.0, currency='VND')):
        f = pb.evaluate_campaigns([c], 'google', 'USD', goal)
        assert 'cpa_above_target' not in codes(f), goal
    # threshold rules still work with no goal at all
    dead = campaign(spend=0.0, impressions=0, clicks=0)
    assert 'dead_campaign' in codes(pb.evaluate_campaigns([dead], 'google', 'USD', None))


# --------------------------------------------------------------------------
# CTR rules
# --------------------------------------------------------------------------
def test_low_ctr_parity_with_existing_rule():
    c = campaign(clicks=150, impressions=20000, ctr_percent=0.4, spend=100.0)
    f = pb.evaluate_campaigns([c], 'google', 'USD')
    assert only(f, 'low_ctr')['level'] == 'review'
    assert 'low_ctr' not in codes(pb.evaluate_campaigns(
        [dict(c, ctr_percent=0.5)], 'google', 'USD'))  # 0.5% is not below 0.5%
    assert 'low_ctr' not in codes(pb.evaluate_campaigns(
        [dict(c, clicks=99, ctr_percent=0.4)], 'google', 'USD'))
    assert 'low_ctr' not in codes(pb.evaluate_campaigns(
        [dict(c, impressions=999, ctr_percent=0.4)], 'google', 'USD'))


def test_high_ctr_no_conversions():
    c = campaign(clicks=200, impressions=10000, ctr_percent=2.0, conversions=0, spend=400.0)
    f = pb.evaluate_campaigns([c], 'google', 'USD')
    finding = only(f, 'high_ctr_no_conversions')
    assert 'trang đích' in finding['message']
    assert 'high_ctr_no_conversions' not in codes(pb.evaluate_campaigns(
        [dict(c, ctr_percent=0.9)], 'google', 'USD'))
    assert 'high_ctr_no_conversions' not in codes(pb.evaluate_campaigns(
        [dict(c, clicks=99)], 'google', 'USD'))


# --------------------------------------------------------------------------
# Smart-bidding volume + dead campaign
# --------------------------------------------------------------------------
def test_low_conversion_volume_platform_wording():
    c = campaign(spend=300.0, clicks=120, impressions=4000, ctr_percent=3.0, conversions=3)
    f = pb.evaluate_campaigns([c], 'google', 'USD')
    g = only(f, 'low_conversion_volume_for_smart_bidding')
    assert 'Smart Bidding' in g['playbook']['why']
    m = pb.evaluate_campaigns([dict(c, status='ACTIVE')], 'meta', 'USD')
    assert 'giai đoạn học' in only(m, 'low_conversion_volume_for_smart_bidding')['playbook']['why']
    # 0 conversions is a tracking case, not a volume case; 15 is enough volume
    assert 'low_conversion_volume_for_smart_bidding' not in codes(pb.evaluate_campaigns(
        [dict(c, conversions=0)], 'google', 'USD'))
    assert 'low_conversion_volume_for_smart_bidding' not in codes(pb.evaluate_campaigns(
        [dict(c, conversions=15)], 'google', 'USD'))


def test_dead_campaign():
    dead = campaign(spend=0.0, impressions=0, clicks=0)
    assert only(pb.evaluate_campaigns([dead], 'google', 'USD'), 'dead_campaign')['level'] == 'review'
    assert 'dead_campaign' not in codes(pb.evaluate_campaigns(
        [dict(dead, impressions=5)], 'google', 'USD'))
    assert 'dead_campaign' not in codes(pb.evaluate_campaigns(
        [dict(dead, spend=None, impressions=None)], 'google', 'USD'))  # unknown != dead
    paused = dict(dead, status='PAUSED')
    assert 'dead_campaign' not in codes(pb.evaluate_campaigns([paused], 'google', 'USD'))


def test_inactive_and_meta_effective_status_skipped():
    c = campaign(status='PAUSED', clicks=200, impressions=10000, ctr_percent=0.2, spend=50.0)
    assert pb.evaluate_campaigns([c], 'google', 'USD') == []
    m = campaign(status='ACTIVE', effective_status='DISAPPROVED', clicks=200,
                 impressions=10000, ctr_percent=0.2, spend=50.0)
    assert pb.evaluate_campaigns([m], 'meta', 'USD') == []


def test_every_finding_has_playbook_and_approval_note():
    c = campaign(spend=1600.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=10, cpa=160.0)
    for f in pb.evaluate_campaigns([c], 'google', 'USD', goal_cpa(100.0)):
        assert f['playbook']['title'] and f['playbook']['why']
        assert f['playbook']['actions'] and f['playbook']['guardrails']
        assert any('người phụ trách duyệt' in g for g in f['playbook']['guardrails'])
        assert 'tự động' not in f['message'] or 'không' in f['message']


# --------------------------------------------------------------------------
# Account-level evaluation
# --------------------------------------------------------------------------
def test_account_fragmentation():
    frag = [campaign(id=str(100 + i), spend=100.0, clicks=50, impressions=2000,
                     ctr_percent=2.5, conversions=3) for i in range(4)]
    f = pb.evaluate_account(frag, 'google', 'USD')
    finding = only(f, 'account_fragmentation')
    assert finding['campaign_id'] == 'ACCOUNT'
    assert finding['level'] == 'opportunity'
    # only 3 fragmented campaigns -> below the "many" threshold
    assert 'account_fragmentation' not in codes(pb.evaluate_account(frag[:3], 'google', 'USD'))
    # healthy-volume campaigns do not count as fragmented
    healthy = [campaign(id=str(200 + i), spend=900.0, clicks=300, impressions=9000,
                        ctr_percent=3.3, conversions=30) for i in range(4)]
    assert 'account_fragmentation' not in codes(pb.evaluate_account(healthy, 'google', 'USD'))


def test_account_budget_reallocation():
    bad = campaign(id='1', spend=600.0, clicks=300, impressions=9000, ctr_percent=3.3,
                   conversions=10, cpa=160.0)  # > 1.5x target
    good = campaign(id='2', spend=400.0, clicks=300, impressions=9000, ctr_percent=3.3,
                    conversions=10, cpa=100.0)
    f = pb.evaluate_account([bad, good], 'google', 'USD', goal_cpa(100.0))
    finding = only(f, 'account_budget_reallocation')
    assert '60%' in finding['message']
    # no goal -> cannot judge inefficiency -> silent
    assert pb.evaluate_account([bad, good], 'google', 'USD', None) == []
    # inefficient share below 40% -> silent
    mostly_good = [dict(bad, spend=300.0), dict(good, spend=700.0)]
    assert 'account_budget_reallocation' not in codes(
        pb.evaluate_account(mostly_good, 'google', 'USD', goal_cpa(100.0)))


def test_evaluate_campaigns_includes_account_findings():
    frag = [campaign(id=str(100 + i), spend=100.0, clicks=50, impressions=2000,
                     ctr_percent=2.5, conversions=3) for i in range(4)]
    f = pb.evaluate_campaigns(frag, 'google', 'USD')
    assert 'account_fragmentation' in codes(f)


# --------------------------------------------------------------------------
# ĐỘC QUYỀN 1 — baselines + drift
# --------------------------------------------------------------------------
def snapshots_for(cid, cpas, roases=None, period_prefix='W'):
    out = []
    for i, cpa in enumerate(cpas):
        out.append(campaign(id=cid, cpa=cpa, roas=(roases[i] if roases else None),
                            period=f'2026-{period_prefix}{i}'))
    return out


def test_compute_baselines_median_and_volatility():
    snaps = snapshots_for('111', [100.0, 110.0, 90.0, None, 105.0],
                          roases=[4.0, 4.4, 3.6, 4.2, None])
    baselines = pb.compute_baselines(snaps)
    b = baselines['111']
    assert b['periods'] == 5
    assert b['median_cpa'] == pytest.approx(102.5)   # median of 90,100,105,110
    assert b['median_roas'] == pytest.approx(4.1)    # median of 3.6,4.0,4.2,4.4
    assert b['cpa_volatility'] == pytest.approx((110 - 90) / 102.5, rel=1e-3)
    # single-period baseline: median exists, volatility unknown
    single = pb.compute_baselines(snapshots_for('222', [80.0]))['222']
    assert single['median_cpa'] == 80.0 and single['cpa_volatility'] is None
    # empty/garbage input is safe
    assert pb.compute_baselines([]) == {}
    assert pb.compute_baselines([{'period': 'W1'}, 'junk']) == {}


def test_cpa_drift_vs_baseline():
    baselines = pb.compute_baselines(snapshots_for('111', [100.0, 100.0, 100.0]))
    now = campaign(spend=1300.0, clicks=300, impressions=9000, ctr_percent=3.3,
                   conversions=10, cpa=130.0)
    f = pb.evaluate_campaigns([now], 'google', 'USD', None, baselines)
    finding = only(f, 'cpa_drift_vs_baseline')
    assert finding['level'] == 'review' and '+30%' in finding['message']
    critical = pb.evaluate_campaigns([dict(now, cpa=160.0)], 'google', 'USD', None, baselines)
    assert only(critical, 'cpa_drift_vs_baseline')['level'] == 'critical'
    # exactly +25% does not fire; without baselines the drift rule is silent
    assert 'cpa_drift_vs_baseline' not in codes(pb.evaluate_campaigns(
        [dict(now, cpa=125.0)], 'google', 'USD', None, baselines))
    assert 'cpa_drift_vs_baseline' not in codes(pb.evaluate_campaigns(
        [now], 'google', 'USD', None, None))
    # other campaign id has no baseline
    assert 'cpa_drift_vs_baseline' not in codes(pb.evaluate_campaigns(
        [dict(now, id='999')], 'google', 'USD', None, baselines))


def test_roas_drift_vs_baseline():
    baselines = pb.compute_baselines(snapshots_for('111', [None] * 3, roases=[5.0, 5.0, 5.0]))
    now = campaign(spend=1000.0, clicks=300, impressions=9000, ctr_percent=3.3,
                   conversions=10, conversion_value=3800.0, roas=3.8)
    f = pb.evaluate_campaigns([now], 'google', 'USD', None, baselines)
    assert only(f, 'roas_drift_vs_baseline')['level'] == 'review'
    bad = pb.evaluate_campaigns([dict(now, roas=3.0)], 'google', 'USD', None, baselines)
    assert only(bad, 'roas_drift_vs_baseline')['level'] == 'critical'


# --------------------------------------------------------------------------
# ĐỘC QUYỀN 2 — verify_outcome: all four labels
# --------------------------------------------------------------------------
def test_verify_outcome_cpa_codes():
    base = campaign(conversions=10, cpa=160.0)
    assert pb.verify_outcome(base, campaign(conversions=12, cpa=140.0), 'cpa_above_target') == 'improved'
    assert pb.verify_outcome(base, campaign(conversions=12, cpa=180.0), 'cpa_above_target') == 'worsened'
    assert pb.verify_outcome(base, campaign(conversions=12, cpa=163.0), 'cpa_above_target') == 'unchanged'  # within ±5%
    # not enough conversions in the re-measure -> cannot judge
    assert pb.verify_outcome(base, campaign(conversions=2, cpa=100.0), 'cpa_above_target') == 'insufficient_data'
    assert pb.verify_outcome(base, campaign(conversions=12, cpa=None), 'cpa_above_target') == 'insufficient_data'


def test_verify_outcome_roas_codes():
    base = campaign(conversions=10, roas=3.0)
    assert pb.verify_outcome(base, campaign(conversions=10, roas=3.6), 'roas_below_target') == 'improved'
    assert pb.verify_outcome(base, campaign(conversions=10, roas=2.7), 'roas_below_target') == 'worsened'
    assert pb.verify_outcome(base, campaign(conversions=10, roas=3.1), 'roas_below_target') == 'unchanged'


def test_verify_outcome_tracking_and_other_codes():
    base = campaign(conversions=0, clicks=120)
    assert pb.verify_outcome(base, campaign(conversions=6, clicks=130), 'spend_no_conversions') == 'improved'
    assert pb.verify_outcome(base, campaign(conversions=0, clicks=130), 'spend_no_conversions') == 'unchanged'
    assert pb.verify_outcome(base, campaign(conversions=None), 'spend_no_conversions') == 'insufficient_data'
    # delivery recovery for a dead campaign
    dead = campaign(conversions=0, impressions=0, spend=0.0)
    assert pb.verify_outcome(dead, campaign(impressions=500), 'dead_campaign') == 'improved'
    assert pb.verify_outcome(dead, campaign(impressions=0), 'dead_campaign') == 'unchanged'
    # CTR improvement for low_ctr
    low = campaign(ctr_percent=0.3, conversions=10)
    assert pb.verify_outcome(low, campaign(ctr_percent=0.45, conversions=10), 'low_ctr') == 'improved'
    # unknown code never gets a verdict
    assert pb.verify_outcome(base, base, 'no_such_code') == 'insufficient_data'
    assert pb.verify_outcome(None, base, 'cpa_above_target') == 'insufficient_data'


# --------------------------------------------------------------------------
# ĐỘC QUYỀN 3 — conflict guard
# --------------------------------------------------------------------------
def test_conflict_guard_suppresses_scale_when_problem_exists():
    # CPA is below goal target (scale opportunity) BUT has drifted +60% vs its
    # own baseline (critical): the loop must not advise scaling it.
    baselines = pb.compute_baselines(snapshots_for('111', [40.0, 40.0, 40.0]))
    c = campaign(spend=760.0, clicks=300, impressions=9000, ctr_percent=3.3,
                 conversions=10, cpa=76.0)  # < 0.8x target (scale) but +90% vs own baseline (drift)
    f = pb.evaluate_campaigns([c], 'google', 'USD', goal_cpa(100.0), baselines)
    assert 'cpa_well_below_target_scale' not in codes(f)
    drift = only(f, 'cpa_drift_vs_baseline')
    assert drift['level'] == 'critical'
    assert drift.get('suppressed') == ['cpa_well_below_target_scale']
    # without the baseline problem, the same campaign DOES get the opportunity
    f2 = pb.evaluate_campaigns([c], 'google', 'USD', goal_cpa(100.0), None)
    assert 'cpa_well_below_target_scale' in codes(f2)


def test_conflict_guard_leaves_clean_campaigns_and_account_alone():
    # A clean, high-volume campaign keeps its scale opportunity untouched.
    clean = campaign(spend=1400.0, clicks=400, impressions=12000, ctr_percent=3.3,
                     conversions=20, cpa=70.0)
    f = pb.evaluate_campaigns([clean], 'google', 'USD', goal_cpa(100.0))
    assert 'cpa_well_below_target_scale' in codes(f)
    assert all('suppressed' not in x for x in f)
    # Structural cautions (low conversion volume) do NOT trigger the guard:
    # a 10-conversion campaign below target may still be shown the scale path.
    small = campaign(spend=700.0, clicks=300, impressions=9000, ctr_percent=3.3,
                     conversions=10, cpa=70.0)
    f2 = pb.evaluate_campaigns([small], 'google', 'USD', goal_cpa(100.0))
    assert 'low_conversion_volume_for_smart_bidding' in codes(f2)
    assert 'cpa_well_below_target_scale' in codes(f2)
    # ACCOUNT-level opportunities are never suppressed by the guard.
    frag = [campaign(id=str(100 + i), spend=100.0, clicks=50, impressions=2000,
                     ctr_percent=2.5, conversions=3) for i in range(4)]
    f3 = pb.evaluate_campaigns(frag, 'google', 'USD')
    account_finding = only(f3, 'account_fragmentation')
    assert 'suppressed' not in account_finding


def test_playbook_registry_is_consistent():
    playbook_codes = {e['code'] for e in pb.PLAYBOOK}
    assert set(pb.CONDITIONS) | {'account_fragmentation', 'account_budget_reallocation'} == playbook_codes
    for entry in pb.PLAYBOOK:
        assert entry['platform'] in ('google', 'meta', 'both')
        assert entry['category'] in ('bid_cost', 'roas', 'waste', 'scale', 'tracking', 'structure')
        assert entry['severity'] in ('critical', 'review', 'opportunity')
