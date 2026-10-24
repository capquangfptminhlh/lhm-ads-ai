"""LHM Growth Intelligence v0.1: conservative, read-only decision skills.

The library is deterministic and runs on the customer's device. It never sends
Ads data to LHM, sends notifications, or writes to advertising providers.
It intentionally does NOT use a generic LLM to decide whether to mutate Ads.

Inputs must be VERIFIED observations from connected provider/CRM/website tools;
not model guesses. Thresholds below are local pilot policies, not universal
Google Ads rules. This module returns review candidates, never permission.
"""
from __future__ import annotations

import math
from typing import Any

SKILL_ID = 'lhm.marketing.change-readiness'
SKILL_VERSION = '0.1.0'
# Conservative review policy: 2 full weeks OR 2 conversion cycles, whichever
# is longer. Google describes 1–2 cycles for adaptation; the 14-day floor is
# our initial conservative pilot policy, not a platform-wide requirement.
MIN_REVIEW_HOURS = 14 * 24
MIN_REVIEW_CONVERSIONS = 10  # eligibility heuristic, NOT statistical significance


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if math.isfinite(n) and n >= 0 else None


def _result(status: str, reasons: list[str], next_steps: list[str]) -> dict:
    return {
        'skill_id': SKILL_ID,
        'skill_version': SKILL_VERSION,
        'status': status,
        'reason_codes': reasons,
        'next_steps': next_steps,
        'requires_human_approval': True,
        'may_write_ads': False,
    }


def assess_change_readiness(observation: dict | None) -> dict:
    """Assess whether an Ads change is even ready to be *proposed*.

    Expected inputs (not automatically queried):
      critical_incident: none/site_down/payment_failure/unexpected_spend
      tracking_verified: True only after real cross-check with CRM/GA4
      website_healthy: True after a real page/form/checkout test
      learning_status: stable/learning/unknown as actually observed
      conversion_cycle_hours: observed lag estimate, not a guessed constant
      hours_since_major_change: audited time since last relevant change
      evaluation_window_hours: matured, comparable observation window
      matured_conversions: conversions fully attributed in that window
      experiment_supported: True only after API capability check

    Readiness is NOT a promise of lift or statistically valid significance.
    No proposal, including urgent alerts, authorizes an Ads API write.
    """
    if not isinstance(observation, dict):
        return _result('diagnose_first', ['missing_observation'],
                       ['Thu thập dữ liệu thực tế và xác minh nguồn trước.'])

    incident = observation.get('critical_incident', 'none')
    if incident in {'site_down', 'payment_failure', 'unexpected_spend'} or observation.get('website_healthy') is False:
        return _result('urgent_review', ['critical_incident'], [
            'Gửi cảnh báo ngay; kiểm tra sự cố trang web, thanh toán hoặc hạn mức.',
            'Không tự dừng/sửa Ads. Gửi phương án xử lý riêng để người có quyền duyệt.',
        ])
    if observation.get('tracking_verified') is not True:
        return _result('diagnose_first', ['tracking_unverified'], [
            'Đối chiếu conversion với CRM/đơn hàng và độ trễ ghi nhận.',
            'Không cắt ngân sách vì số chuyển đổi 0 khi tracking chưa được kiểm chứng.',
        ])
    if observation.get('website_healthy') is not True:
        return _result('diagnose_first', ['website_unverified'], [
            'Kiểm tra tốc độ mobile, trang đích, biểu mẫu và thanh toán thực tế.',
        ])
    if observation.get('learning_status') != 'stable':
        return _result('observe_only', ['learning_or_unknown'], [
            'Kiểm tra trạng thái bid strategy; không suy đoán từ số liệu tổng hợp.',
            'Tiếp tục quan sát, trừ khi có sự cố nghiêm trọng cần người duyệt.',
        ])

    cycle = _number(observation.get('conversion_cycle_hours'))
    since = _number(observation.get('hours_since_major_change'))
    window = _number(observation.get('evaluation_window_hours'))
    conversions = _number(observation.get('matured_conversions'))
    if None in (cycle, since, window, conversions) or cycle == 0:
        return _result('diagnose_first', ['insufficient_context'], [
            'Cần thời gian chuyển đổi, mốc thay đổi gần nhất và dữ liệu đã đủ độ trễ.',
        ])
    review_hours = max(MIN_REVIEW_HOURS, 2 * cycle)
    if since < 2 * cycle or window < review_hours:
        return _result('observe_only', ['conversion_cycle_or_window_incomplete'], [
            'Đợi đủ ít nhất hai chu kỳ chuyển đổi và cửa sổ so sánh đủ dài.',
            'Ngưỡng 14 ngày là chính sách pilot thận trọng, có thể hiệu chỉnh theo ngành.',
        ])
    if conversions < MIN_REVIEW_CONVERSIONS:
        return _result('observe_only', ['low_matured_conversion_volume'], [
            'Dữ liệu ít, tránh kết luận nhân quả hoặc thay đổi dựa trên nhiễu.',
        ])
    if observation.get('experiment_supported') is not True:
        return _result('diagnose_first', ['experiment_capability_unverified'], [
            'Xác minh loại chiến dịch và phương pháp thử nghiệm mà API hỗ trợ.',
        ])
    return _result('proposal_ready', ['verified_context_and_window'], [
        'Tạo giả thuyết đo được và thiết kế test đối chứng với một thay đổi chính.',
        'Gửi phương án, ngân sách, thời gian, rủi ro và cách khôi phục để người dùng duyệt.',
    ])


def hourly_cohort_candidates(buckets: list[dict] | None) -> list[dict]:
    """Find historical click-hour cohorts worth investigation, not bid edits.

    Each bucket aggregates one weekday (0=Monday) and hour in the AD ACCOUNT
    timezone, using *click-time attributed* and fully matured conversions.
    Required: weekday, hour, days_observed, clicks, conversions, spend,
    matured=True. Buckets with less than 4 distinct comparable days, 50 clicks,
    5 matured conversions, or missing inputs are dropped. CPA sorting is only
    descriptive: different hours may have different audiences or seasonality.
    """
    if not isinstance(buckets, list):
        return []
    candidates: list[dict] = []
    for row in buckets:
        if not isinstance(row, dict) or row.get('matured') is not True:
            continue
        day, hour = row.get('weekday'), row.get('hour')
        if type(day) is not int or not 0 <= day <= 6:
            continue
        if type(hour) is not int or not 0 <= hour <= 23:
            continue
        days = _number(row.get('days_observed'))
        clicks = _number(row.get('clicks'))
        conv = _number(row.get('conversions'))
        spend = _number(row.get('spend'))
        if any(x is None for x in (days, clicks, conv, spend)):
            continue
        if days < 4 or clicks < 50 or conv < 5 or spend <= 0 or conv > clicks:
            continue
        candidates.append({
            'weekday': day, 'hour': hour,
            'cpa': round(spend / conv, 2),
            'conversions': conv,
            'days_observed': days,
            'status': 'research_candidate_only',
            'may_adjust_schedule': False,
        })
    return sorted(candidates, key=lambda x: (x['cpa'], x['weekday'], x['hour']))
