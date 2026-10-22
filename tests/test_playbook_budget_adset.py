"""Two playbook rules consuming adapter fields added in parallel:
- budget_constrained_winner (Google): metrics.search_impression_share lost
  to budget ('budget_lost_is') >= 0.20 while the campaign meets a goal or
  platform target.
- adset_target_missed (Meta): CPA vs the MEDIAN ad-set cost goal
  ('adset_bid_target_cpa') when the campaign has no campaign-level target.
Plus their verify_outcome branches. Pure functions — no HTTP, no DB."""
from ads_core.optimization_playbook import evaluate_campaigns, verify_outcome


def camp(**kw):
    base = dict(id='1', name='C', status='ENABLED', spend=1_000_000.0, clicks=300,
                impressions=30000, ctr_percent=1.0, conversions=20,
                conversion_value=20_000_000.0, cpa=50_000.0, roas=20.0,
                bidding_strategy=None, bid_target_cpa=None, bid_target_roas=None,
                daily_budget=None, budget_lost_is=None, adset_bid_target_cpa=None)
    base.update(kw)
    return base


def codes(findings):
    return {f['code'] for f in findings}


# --------------------------------------------------------------------------
# budget_constrained_winner
# --------------------------------------------------------------------------

def test_budget_winner_fires_for_each_health_variant():
    # healthy via platform tCPA target
    f = evaluate_campaigns([camp(budget_lost_is=0.35, bid_target_cpa=60_000.0)],
                           'google', 'VND')
    hit = next(x for x in f if x['code'] == 'budget_constrained_winner')
    assert hit['level'] == 'opportunity'
    assert '35%' in hit['playbook']['title'] + hit['message'] or '35%' in hit['message']
    assert 'Search' in hit['message']  # must tell the reader to confirm type
    # healthy via platform tROAS target
    f = evaluate_campaigns([camp(budget_lost_is=0.20, bid_target_roas=15.0)],
                           'google', 'VND')
    assert 'budget_constrained_winner' in codes(f)
    # healthy via the organisation's own goal
    goal = {'enabled': 1, 'objective': 'cpa', 'target': 55_000.0,
            'currency': 'VND', 'min_conversions': 5}
    f = evaluate_campaigns([camp(budget_lost_is=0.5)], 'google', 'VND', goal=goal)
    assert 'budget_constrained_winner' in codes(f)


def test_budget_winner_silent_boundaries():
    base = dict(budget_lost_is=0.35, bid_target_cpa=60_000.0)
    # below the lost-share threshold
    assert 'budget_constrained_winner' not in codes(
        evaluate_campaigns([camp(**{**base, 'budget_lost_is': 0.19})], 'google', 'VND'))
    # field missing entirely (older adapter data) -> never treated as 0 or 1
    assert 'budget_constrained_winner' not in codes(
        evaluate_campaigns([camp(bid_target_cpa=60_000.0)], 'google', 'VND'))
    # not healthy: CPA above every target
    assert 'budget_constrained_winner' not in codes(
        evaluate_campaigns([camp(budget_lost_is=0.35, bid_target_cpa=40_000.0)],
                           'google', 'VND'))
    # too few conversions
    assert 'budget_constrained_winner' not in codes(
        evaluate_campaigns([camp(**{**base, 'conversions': 9})], 'google', 'VND'))
    # google-only rule
    assert 'budget_constrained_winner' not in codes(
        evaluate_campaigns([camp(status='ACTIVE', **base)], 'meta', 'VND'))


def test_budget_winner_outcome_verdicts():
    before = camp(conversions=20)
    more = camp(conversions=28)   # +40% volume after raising budget
    assert verify_outcome(before, more, 'budget_constrained_winner') == 'improved'
    fewer = camp(conversions=15)  # -25%
    assert verify_outcome(before, fewer, 'budget_constrained_winner') == 'worsened'
    same = camp(conversions=20.5)  # within the ±5% noise band
    assert verify_outcome(before, same, 'budget_constrained_winner') == 'unchanged'
    thin = camp(conversions=3)
    assert verify_outcome(before, thin, 'budget_constrained_winner') == 'insufficient_data'


# --------------------------------------------------------------------------
# adset_target_missed
# --------------------------------------------------------------------------

def test_adset_target_missed_fires_review_and_critical():
    meta = dict(status='ACTIVE')
    f = evaluate_campaigns([camp(adset_bid_target_cpa=35_000.0, **meta)], 'meta', 'VND')
    hit = next(x for x in f if x['code'] == 'adset_target_missed')
    assert hit['level'] == 'review'  # 50k vs 35k = 1.43x: above 1.3, below 1.6
    f = evaluate_campaigns([camp(adset_bid_target_cpa=30_000.0, **meta)], 'meta', 'VND')
    hit = next(x for x in f if x['code'] == 'adset_target_missed')
    assert hit['level'] == 'critical'  # 50k vs 30k = 1.67x > 1.6
    f = evaluate_campaigns([camp(cpa=42_000.0, adset_bid_target_cpa=30_000.0, **meta)],
                           'meta', 'VND')
    hit = next(x for x in f if x['code'] == 'adset_target_missed')
    assert hit['level'] == 'review'  # 1.4x: above 1.3, below 1.6
    # message must disclose the median approximation
    assert 'trung vị' in hit['message'] and 'ad set' in hit['message']


def test_adset_target_missed_silent_boundaries():
    meta = dict(status='ACTIVE')
    # within tolerance of the ad-set target
    assert 'adset_target_missed' not in codes(
        evaluate_campaigns([camp(cpa=38_000.0, adset_bid_target_cpa=30_000.0, **meta)],
                           'meta', 'VND'))
    # campaign-level target present -> platform_target_missed owns the case
    assert 'adset_target_missed' not in codes(
        evaluate_campaigns([camp(adset_bid_target_cpa=30_000.0,
                                 bid_target_cpa=60_000.0, **meta)], 'meta', 'VND'))
    # no ad-set target data -> silent, never treated as 0
    assert 'adset_target_missed' not in codes(
        evaluate_campaigns([camp(**meta)], 'meta', 'VND'))
    # too few conversions
    assert 'adset_target_missed' not in codes(
        evaluate_campaigns([camp(adset_bid_target_cpa=30_000.0, conversions=4, **meta)],
                           'meta', 'VND'))
    # meta-only rule
    assert 'adset_target_missed' not in codes(
        evaluate_campaigns([camp(adset_bid_target_cpa=30_000.0)], 'google', 'VND'))


def test_adset_target_missed_outcome_verdicts():
    before = camp(cpa=50_000.0)
    better = camp(cpa=40_000.0)   # CPA -20%
    assert verify_outcome(before, better, 'adset_target_missed') == 'improved'
    worse = camp(cpa=58_000.0)    # CPA +16%
    assert verify_outcome(before, worse, 'adset_target_missed') == 'worsened'
    flat = camp(cpa=51_000.0)     # +2% within noise band
    assert verify_outcome(before, flat, 'adset_target_missed') == 'unchanged'
    thin = camp(cpa=40_000.0, conversions=2)
    assert verify_outcome(before, thin, 'adset_target_missed') == 'insufficient_data'
