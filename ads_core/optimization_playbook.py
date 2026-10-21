"""LHM Vòng lặp Tối ưu (LHM Optimization Loop) — playbook tối ưu quảng cáo 2026.

Hai tầng:

1. TẦNG KIẾN THỨC CÔNG KHAI (table stakes): các quy tắc heuristic theo ngưỡng
   trên dữ liệu chiến dịch 7 ngày (CPA/ROAS so với mục tiêu, lãng phí, lượng
   chuyển đổi cho đấu thầu thông minh, tracking). Đây là kiến thức ngành công
   khai — không phải bí mật của LHM.

2. TẦNG ĐỘC QUYỀN CỦA LHM (cơ chế, không phải chiêu thức):
   - Hồ sơ nền riêng từng tài khoản (account baselines): mỗi chiến dịch được
     so với CHÍNH lịch sử của nó (median CPA/ROAS qua các kỳ snapshot), không
     chỉ so với ngưỡng chung.
   - Vòng kiểm chứng kết quả (outcome verification): đề xuất → người duyệt →
     đo lại → phán quyết improved/worsened/unchanged/insufficient_data.
   - Chống tự mâu thuẫn (conflict guard): không bao giờ khuyên mở rộng một
     chiến dịch đang có cảnh báo cắt/giảm trong cùng một lần quét.

Nguyên tắc bất biến (học thuyết trung thực của sản phẩm):
- Chỉ tư vấn, KHÔNG tự sửa quảng cáo; mọi thay đổi cần người phụ trách duyệt.
- Không hứa kết quả. Tracking sai phải kiểm chứng TRƯỚC khi kết luận lãng phí.
- Tôn trọng pha học của nền tảng; mỗi bước chỉnh giá thầu/ngân sách ≤ 20%.
- Dữ liệu thiếu (None) thì quy tắc im lặng — không suy đoán từ số 0 giả.

Thuần dữ liệu vào/ra: module này không chạm DB, không gọi mạng. Tầng trên
(advisor) chịu trách nhiệm lấy dữ liệu và mục tiêu (ads_core.goals.goal_for).
"""
from __future__ import annotations

import math
import statistics

# ---------------------------------------------------------------------------
# Ngưỡng heuristic mặc định. Đây là HEURISTIC của ngành, có thể chỉnh theo
# tài khoản; không phải hằng số "đúng tuyệt đối" của Google/Meta.
# ---------------------------------------------------------------------------
NO_CONVERSION_MIN_CLICKS = 50          # clicks tối thiểu trước khi nghi tracking/vô hiệu quả
CPA_REVIEW_RATIO = 1.2                 # CPA > 1,2x mục tiêu -> review
CPA_CRITICAL_RATIO = 1.5               # CPA > 1,5x mục tiêu -> critical
CPA_MIN_CONVERSIONS = 5                # lượng chuyển đổi tối thiểu để kết luận CPA
SCALE_CPA_RATIO = 0.8                  # CPA < 0,8x mục tiêu -> cơ hội mở rộng
SCALE_MIN_CONVERSIONS = 10             # lượng chuyển đổi tối thiểu để khuyên mở rộng
ROAS_CRITICAL_RATIO = 0.7              # ROAS < 0,7x mục tiêu -> critical
ROAS_SCALE_RATIO = 1.3                 # ROAS > 1,3x mục tiêu -> cơ hội mở rộng
LOW_CTR_MAX_PERCENT = 0.5              # CTR (%) dưới mức này là thấp (khớp quy tắc cũ)
LOW_CTR_MIN_CLICKS = 100
LOW_CTR_MIN_IMPRESSIONS = 1000
HEALTHY_CTR_MIN_PERCENT = 1.0          # CTR từ mức này coi là khỏe
HIGH_CTR_NO_CONV_MIN_CLICKS = 100
SMART_BIDDING_MIN_CONVERSIONS_7D = 15  # dưới mức này/7 ngày: pha học thiếu ổn định
MAX_STEP_PERCENT = 20                  # mỗi bước chỉnh bid/budget tối đa 20%
DRIFT_CPA_REVIEW_RATIO = 1.25          # CPA lệch > +25% so với nền của chính chiến dịch
DRIFT_CPA_CRITICAL_RATIO = 1.5
DRIFT_ROAS_REVIEW_RATIO = 0.8          # ROAS tụt dưới 0,8x nền của chính chiến dịch
DRIFT_ROAS_CRITICAL_RATIO = 0.65
ACCOUNT_FRAGMENT_MIN_CAMPAIGNS = 4     # từ ngần này chiến dịch phân mảnh trở lên mới báo
ACCOUNT_FRAGMENT_MAX_CONVERSIONS = SMART_BIDDING_MIN_CONVERSIONS_7D
ACCOUNT_INEFFICIENT_SPEND_SHARE = 0.40  # >40% chi tiêu vào chiến dịch kém = cần tái phân bổ
ACCOUNT_INEFFICIENT_CPA_RATIO = CPA_CRITICAL_RATIO
OUTCOME_NOISE_BAND = 0.05              # biến động trong ±5% coi là nhiễu
OUTCOME_MIN_CONVERSIONS = 5            # kiểm chứng CPA/ROAS cần >=5 chuyển đổi ở cả hai kỳ
MAX_FINDINGS = 100

ACTIVE_STATUSES = ('ENABLED', 'ACTIVE')
APPROVAL_NOTE = ('Mọi thay đổi phải do người phụ trách duyệt trong trình quản lý quảng cáo; '
                 'hệ thống chỉ tư vấn, không tự sửa quảng cáo và không hứa kết quả.')

# Mã quy tắc thuộc nhóm "mở rộng" (scale-up). Conflict guard dùng danh sách này.
SCALE_CODES = ('cpa_well_below_target_scale', 'roas_above_target_scale')

# Nhóm finding "cắt/giảm" chặn mở rộng khi ở mức review: hiệu quả vượt mục
# tiêu, lệch khỏi nền, hoặc chi tiền mà không ghi nhận chuyển đổi. Các cảnh
# báo cấu trúc (CTR thấp, lượng chuyển đổi thấp) là lưu ý song song, KHÔNG
# chặn mở rộng — chúng không mâu thuẫn với việc mua thêm chuyển đổi. Mọi
# finding mức critical ở bất kỳ mã nào cũng chặn.
CUT_CODES = ('cpa_above_target', 'roas_below_target', 'cpa_drift_vs_baseline',
             'roas_drift_vs_baseline', 'spend_no_conversions', 'high_ctr_no_conversions')


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------
def _num(value):
    """Trả float hữu hạn hoặc None; không bao giờ biến dữ liệu thiếu thành 0."""
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _money(value, currency):
    value = _num(value)
    if value is None:
        return '—'
    if (currency or '').upper() == 'VND':
        return f"{value:,.0f}".replace(',', '.') + ' VND'
    return f"{value:,.2f} {currency or ''}".strip()


def _ratio(value):
    value = _num(value)
    return '—' if value is None else f"{value:.2f}"


def _pct_delta(actual, reference):
    """Phần trăm chênh lệch actual so với reference (số nguyên, có dấu)."""
    if not reference:
        return 0
    return round((actual / reference - 1) * 100)


def _is_active(campaign, platform):
    if campaign.get('status') not in ACTIVE_STATUSES:
        return False
    if platform == 'meta':
        # Khớp goals.evaluate_goals: Meta còn phải ACTIVE ở effective_status.
        if campaign.get('effective_status') not in (None, 'ACTIVE'):
            return False
    return True


def _goal_targets(goal, currency):
    """Trích mục tiêu dùng được từ dict của goals.goal_for (hoặc None).

    goal_for trả: enabled, objective ('cpa'|'roas'), target (một số duy nhất),
    min_conversions, min_clicks, currency, meta_action_type. Mục tiêu bị tắt,
    khác tiền tệ với tài khoản, hoặc target không hợp lệ -> coi như không có.
    """
    out = {'cpa_target': None, 'roas_target': None, 'min_conversions': CPA_MIN_CONVERSIONS}
    if not goal or not goal.get('enabled'):
        return out
    if goal.get('currency') and currency and goal['currency'] != currency:
        return out
    target = _num(goal.get('target'))
    if target is None or target <= 0:
        return out
    if goal.get('objective') == 'cpa':
        out['cpa_target'] = target
    elif goal.get('objective') == 'roas':
        out['roas_target'] = target
    min_conv = goal.get('min_conversions')
    if isinstance(min_conv, int) and min_conv > 0:
        out['min_conversions'] = max(CPA_MIN_CONVERSIONS, min_conv)
    return out


def _finding(campaign_id, entry, level, message, why, actions, guardrails):
    return {
        'campaign_id': str(campaign_id),
        'level': level,
        'code': entry['code'],
        'category': entry['category'],
        'message': message,
        'playbook': {
            'title': entry['title'],
            'why': why,
            'actions': list(actions),
            'guardrails': list(guardrails) + [APPROVAL_NOTE],
        },
    }


# ---------------------------------------------------------------------------
# Điều kiện từng quy tắc. Mỗi hàm nhận (campaign, targets, ctx) và trả None
# (im lặng) hoặc dict {level, message, why, actions, guardrails}.
# ctx: {'platform': ..., 'currency': ..., 'baselines': {...}}
# ---------------------------------------------------------------------------
def _cond_spend_no_conversions(c, t, ctx):
    clicks, conversions, spend = _num(c.get('clicks')), _num(c.get('conversions')), _num(c.get('spend'))
    if clicks is None or conversions is None or spend is None:
        return None
    if clicks < NO_CONVERSION_MIN_CLICKS or conversions != 0 or spend <= 0:
        return None
    platform_name = 'Google Ads' if ctx['platform'] == 'google' else 'Meta Ads'
    return {
        'level': 'review',
        'message': (f"Đã chi {_money(spend, ctx['currency'])} với {int(clicks)} lượt nhấp trong 7 ngày "
                    f"nhưng chưa ghi nhận chuyển đổi nào. Kiểm tra tracking trước khi kết luận lãng phí."),
        'why': ('0 chuyển đổi trên dữ liệu thật thường do một trong ba nguyên nhân: đo lường hỏng/thiếu, '
                'độ trễ ghi nhận chuyển đổi, hoặc lưu lượng không tạo chuyển đổi. Cắt ngân sách khi chưa '
                'kiểm chứng tracking sẽ phá dữ liệu học của nền tảng.'),
        'actions': [
            'Kiểm tra sự kiện chuyển đổi có bắn đúng: Google Tag/Tag Assistant (Google) hoặc Events Manager + Test Events, gồm cả CAPI nếu có (Meta).',
            'Đối chiếu số đơn/lead thực tế trong CRM hoặc kênh bán hàng với số chuyển đổi nền tảng báo, tính cả độ trễ quy đổi (attribution lag).',
            'Kiểm tra trang đích: tải được, form/thanh toán hoạt động, không lỗi trên di động.',
            'Chỉ sau khi tracking được xác nhận đúng mới đánh giá lại chất lượng lưu lượng của chiến dịch này.',
        ],
        'guardrails': [
            'Không tự tắt/dừng chiến dịch vì cảnh báo này.',
            f'Đây là tín hiệu cấp {platform_name}: kiểm chứng trên đúng nền tảng đang chạy.',
        ],
    }


def _cond_cpa_above_target(c, t, ctx):
    target = t['cpa_target']
    cpa, conversions, spend = _num(c.get('cpa')), _num(c.get('conversions')), _num(c.get('spend'))
    if target is None or cpa is None or conversions is None:
        return None
    if conversions < t['min_conversions'] or cpa <= target * CPA_REVIEW_RATIO:
        return None
    level = 'critical' if cpa > target * CPA_CRITICAL_RATIO else 'review'
    over = _pct_delta(cpa, target)
    return {
        'level': level,
        'message': (f"CPA thực tế {_money(cpa, ctx['currency'])} cao hơn mục tiêu {_money(target, ctx['currency'])} "
                    f"khoảng {over}% (dựa trên {int(conversions)} chuyển đổi, chi {_money(spend, ctx['currency'])} trong 7 ngày). "
                    f"Xem xét giảm giá thầu/ngân sách theo từng bước nhỏ."),
        'why': ('CPA vượt mục tiêu có đủ lượng chuyển đổi làm bằng chứng cho thấy đấu thầu đang mua chuyển đổi '
                'đắt hơn mức tổ chức chấp nhận. Nhưng CPA cũng bị nhiễu bởi độ trễ chuyển đổi và pha học, '
                'nên phải chỉnh từng bước nhỏ thay vì cắt mạnh.'),
        'actions': [
            'Kiểm chứng nhanh tracking và độ trễ chuyển đổi (cảnh báo tracking phải được loại trừ trước).',
            f"Nếu CPA cao kéo dài qua nhiều kỳ: hạ mục tiêu tCPA hoặc giá thầu tối đa từng bước tối đa {MAX_STEP_PERCENT}%, chờ ít nhất 7 ngày sau mỗi bước.",
            'Chuyển dần ngân sách sang các chiến dịch đang đạt mục tiêu CPA trong cùng tài khoản.',
            'Rà soát chất lượng lưu lượng theo checklist: truy vấn tìm kiếm/từ khóa (Google), đối tượng và vị trí (Meta) — công cụ này không nhìn thấy các lớp dữ liệu đó.',
        ],
        'guardrails': [
            f'Không chỉnh quá {MAX_STEP_PERCENT}% trong một lần; không đổi đồng thời giá thầu và ngân sách.',
            'Tôn trọng pha học: sau mỗi lần chỉnh, nền tảng cần thời gian học lại trước khi đánh giá tiếp.',
        ],
    }


def _cond_cpa_well_below_target_scale(c, t, ctx):
    target = t['cpa_target']
    cpa, conversions = _num(c.get('cpa')), _num(c.get('conversions'))
    if target is None or cpa is None or conversions is None:
        return None
    if conversions < SCALE_MIN_CONVERSIONS or cpa >= target * SCALE_CPA_RATIO:
        return None
    under = abs(_pct_delta(cpa, target))
    return {
        'level': 'opportunity',
        'message': (f"CPA thực tế {_money(cpa, ctx['currency'])} thấp hơn mục tiêu {_money(target, ctx['currency'])} "
                    f"khoảng {under}% với {int(conversions)} chuyển đổi trong 7 ngày: có dư địa mở rộng để mua thêm chuyển đổi."),
        'why': ('Khi CPA ổn định dưới mục tiêu với lượng chuyển đổi đủ lớn, mục tiêu/ngân sách hiện tại có thể '
                'đang kìm lưu lượng rẻ. Nới dần từng bước giúp mua thêm chuyển đổi trong khi CPA còn trong tầm kiểm soát.'),
        'actions': [
            f"Tăng ngân sách ngày HOẶC nới mục tiêu tCPA từng bước tối đa {MAX_STEP_PERCENT}% — chỉ chọn một biến mỗi lần.",
            'Theo dõi CPA 3–7 ngày sau mỗi bước; dừng mở rộng khi CPA tiệm cận mục tiêu.',
            'Ưu tiên mở rộng ở khung giờ/nhóm quảng cáo đang có CPA tốt nhất thay vì tăng đều toàn chiến dịch.',
        ],
        'guardrails': [
            'Cơ hội không phải cam kết: CPA có thể tăng khi mở rộng lưu lượng.',
            'Cơ hội này tự động bị ẩn khi chiến dịch có cảnh báo cắt/giảm (conflict guard) — xử lý cảnh báo đó trước.',
        ],
    }


def _cond_roas_below_target(c, t, ctx):
    target = t['roas_target']
    roas, value, conversions = _num(c.get('roas')), _num(c.get('conversion_value')), _num(c.get('conversions'))
    if target is None or roas is None or value is None or conversions is None:
        return None
    if conversions < t['min_conversions'] or roas >= target:
        return None
    level = 'critical' if roas < target * ROAS_CRITICAL_RATIO else 'review'
    return {
        'level': level,
        'message': (f"ROAS thực tế {_ratio(roas)} thấp hơn mục tiêu {_ratio(target)} "
                    f"(doanh thu ghi nhận {_money(value, ctx['currency'])}, {int(conversions)} chuyển đổi trong 7 ngày). "
                    f"Kiểm tra ghi nhận doanh thu và xem xét giảm tốc chi tiêu theo từng bước."),
        'why': ('ROAS dưới mục tiêu với doanh thu đã được ghi nhận cho thấy đấu thầu theo giá trị đang mua doanh thu '
                'kém hiệu quả hơn mức chấp nhận. Cần loại trừ lỗi ghi nhận doanh thu/độ trễ trước khi chỉnh, '
                'vì thiếu doanh thu ghi nhận sẽ làm ROAS trông tệ giả tạo.'),
        'actions': [
            'Đối chiếu doanh thu nền tảng báo với doanh thu thực (đơn hoàn/hủy, độ trễ thanh toán, cửa sổ quy đổi).',
            f"Nếu ROAS thấp là thật và kéo dài: giảm ngân sách chiến dịch này từng bước tối đa {MAX_STEP_PERCENT}% hoặc tăng mục tiêu tROAS một bước nhỏ.",
            'Chuyển dần ngân sách sang chiến dịch có ROAS đạt mục tiêu.',
            'Rà soát nhóm sản phẩm/dịch vụ giá trị thấp đang ăn ngân sách (checklist — công cụ không thấy dữ liệu cấp sản phẩm).',
        ],
        'guardrails': [
            f'Không chỉnh quá {MAX_STEP_PERCENT}% trong một lần; chờ qua pha học rồi mới đánh giá bước tiếp.',
            'Không kết luận từ ROAS khi doanh thu chưa được ghi nhận đầy đủ.',
        ],
    }


def _cond_roas_above_target_scale(c, t, ctx):
    target = t['roas_target']
    roas, value, conversions, spend = (_num(c.get('roas')), _num(c.get('conversion_value')),
                                       _num(c.get('conversions')), _num(c.get('spend')))
    if target is None or roas is None or value is None or conversions is None or spend is None:
        return None
    if conversions < SCALE_MIN_CONVERSIONS or spend <= 0 or roas <= target * ROAS_SCALE_RATIO:
        return None
    return {
        'level': 'opportunity',
        'message': (f"ROAS thực tế {_ratio(roas)} vượt mục tiêu {_ratio(target)} với {int(conversions)} chuyển đổi "
                    f"và chi {_money(spend, ctx['currency'])} trong 7 ngày: có dư địa tăng ngân sách để mở rộng doanh thu."),
        'why': ('ROAS cao bền vững trên lượng chuyển đổi đủ lớn cho thấy chiến dịch còn "đói" ngân sách: '
                'tăng dần giúp mua thêm doanh thu trước khi hiệu quả bị pha loãng.'),
        'actions': [
            f"Tăng ngân sách ngày từng bước tối đa {MAX_STEP_PERCENT}%, theo dõi ROAS sau 3–7 ngày mỗi bước.",
            'Hoặc nới mục tiêu tROAS một bước nhỏ (tối đa 10–20%) để hệ thống dám chi rộng hơn — chỉ chọn một biến.',
            'Dừng mở rộng khi ROAS tiệm cận mục tiêu.',
        ],
        'guardrails': [
            'ROAS thường giảm khi mở rộng; đó là đánh đổi có chủ đích, không phải lỗi.',
            'Cơ hội này tự động bị ẩn khi chiến dịch có cảnh báo cắt/giảm (conflict guard) — xử lý cảnh báo đó trước.',
        ],
    }


def _cond_low_ctr(c, t, ctx):
    clicks, impressions, ctr = _num(c.get('clicks')), _num(c.get('impressions')), _num(c.get('ctr_percent'))
    if clicks is None or impressions is None or ctr is None:
        return None
    if clicks < LOW_CTR_MIN_CLICKS or impressions < LOW_CTR_MIN_IMPRESSIONS or ctr >= LOW_CTR_MAX_PERCENT:
        return None
    return {
        'level': 'review',
        'message': (f"CTR {_ratio(ctr)}% dưới 0,5% với {int(clicks)} lượt nhấp / {int(impressions)} lượt hiển thị: "
                    f"kiểm tra mức độ liên quan của nội dung và đối tượng; không tự tắt quảng cáo."),
        'why': ('CTR thấp trên mẫu đủ lớn thường nghĩa là quảng cáo chưa khớp ý định người xem hoặc đối tượng quá rộng/sai. '
                'CTR thấp cũng kéo chất lượng quảng cáo và giá mỗi nhấp đi xuống theo thời gian.'),
        'actions': [
            'So thông điệp quảng cáo với nội dung trang đích: hứa gì ở quảng cáo phải thấy ngay ở trang đích.',
            'Rà soát creative: thử biến thể tiêu đề/hình ảnh mới thay vì sửa nhỏ giọt trên mẫu cũ (checklist — công cụ không thấy cấp quảng cáo).',
            'Kiểm tra độ khớp đối tượng/từ khóa với ý định mua hàng; loại trừ vị trí hiển thị kém liên quan nếu có dữ liệu.',
        ],
        'guardrails': ['Không tắt quảng cáo chỉ vì CTR: CTR thấp nhưng chuyển đổi tốt vẫn có thể có lãi.'],
    }


def _cond_high_ctr_no_conversions(c, t, ctx):
    clicks, ctr, conversions = _num(c.get('clicks')), _num(c.get('ctr_percent')), _num(c.get('conversions'))
    if clicks is None or ctr is None or conversions is None:
        return None
    if ctr < HEALTHY_CTR_MIN_PERCENT or clicks < HIGH_CTR_NO_CONV_MIN_CLICKS or conversions != 0:
        return None
    return {
        'level': 'review',
        'message': (f"CTR khỏe {_ratio(ctr)}% với {int(clicks)} lượt nhấp nhưng 0 chuyển đổi: quảng cáo thu hút được nhấp "
                    f"mà trang đích/tracking không chuyển thành kết quả — kiểm tra độ khớp thông điệp và đo lường."),
        'why': ('Nhấp nhiều chứng tỏ quảng cáo hứa hẹn hấp dẫn; 0 chuyển đổi ở cuối phễu thường do trang đích không '
                'giữ đúng lời hứa, trải nghiệm sau nhấp kém, hoặc sự kiện chuyển đổi không ghi nhận. Đây là tín hiệu '
                'lệch phễu, khác với quảng cáo yếu.'),
        'actions': [
            'Kiểm chứng sự kiện chuyển đổi bắn đúng sau hành động thật (đặt đơn/gửi form thử nghiệm).',
            'Đọc lại trang đích bằng mắt người mua: thông điệp, giá, bằng chứng tin cậy và nút hành động có khớp quảng cáo không.',
            'Kiểm tra tốc độ tải và lỗi form/thanh toán trên di động.',
        ],
        'guardrails': ['Không tăng ngân sách cho chiến dịch này trước khi rõ nguyên nhân ở cuối phễu.'],
    }


def _cond_low_conversion_volume(c, t, ctx):
    conversions, spend = _num(c.get('conversions')), _num(c.get('spend'))
    if conversions is None or spend is None:
        return None
    if not (0 < conversions < SMART_BIDDING_MIN_CONVERSIONS_7D) or spend <= 0:
        return None
    if ctx['platform'] == 'google':
        learning = ('Google Smart Bidding (tCPA/tROAS) cần lượng chuyển đổi ổn định để học; '
                    'dưới ~15 chuyển đổi/7 ngày, pha học kéo dài và CPA dao động mạnh.')
        actions = [
            'Gộp các chiến dịch/nhóm quảng cáo cùng mục tiêu bị phân mảnh để dồn lượng chuyển đổi về một chỗ học.',
            'Đánh giá theo cửa sổ 14–30 ngày thay vì phản ứng theo từng tuần.',
            'Cân nhắc nới mục tiêu tCPA/tROAS tạm thời để hệ thống có thêm tín hiệu, chỉnh lại khi lượng tăng.',
        ]
    else:
        learning = ('Meta cần đủ chuyển đổi mỗi nhóm quảng cáo để thoát giai đoạn học (Learning/Learning Limited); '
                    'dưới ~15 chuyển đổi/7 ngày, phân phối thiếu ổn định và CPA dao động mạnh.')
        actions = [
            'Gộp các nhóm quảng cáo (ad set) cùng mục tiêu bị phân mảnh để dồn lượng chuyển đổi.',
            'Đánh giá theo cửa sổ 14–30 ngày thay vì phản ứng theo từng tuần.',
            'Cân nhắc dùng sự kiện chuyển đổi gần hơn (micro-conversion) làm tín hiệu tối ưu nếu sự kiện chính quá thưa — chỉ khi sự kiện đó có ý nghĩa kinh doanh thật.',
        ]
    return {
        'level': 'review',
        'message': (f"Chỉ {conversions:g} chuyển đổi trong 7 ngày (chi {_money(spend, ctx['currency'])}): lượng quá thấp "
                    f"để đấu thầu thông minh học ổn định. Ưu tiên gộp và dồn tín hiệu thay vì chỉnh giá thầu liên tục."),
        'why': learning,
        'actions': actions,
        'guardrails': ['Tránh chỉnh giá thầu/ngân sách liên tục khi đang thiếu dữ liệu — mỗi lần chỉnh đều khởi động lại pha học.'],
    }


def _cond_dead_campaign(c, t, ctx):
    spend, impressions = _num(c.get('spend')), _num(c.get('impressions'))
    if spend is None or impressions is None:
        return None
    if spend != 0 or impressions != 0:
        return None
    return {
        'level': 'review',
        'message': ('Chiến dịch đang bật nhưng 7 ngày qua không chi tiêu và không có lượt hiển thị nào: '
                    'nhiều khả năng là sự cố phân phối, cần kiểm tra theo danh sách trước khi kết luận.'),
        'why': ('Một chiến dịch đang bật mà im lặng hoàn toàn thường do ngân sách/lịch/giá thầu/đối tượng chặn phân phối, '
                'hoặc quảng cáo bị từ chối — không phải do hiệu quả kém.'),
        'actions': [
            'Kiểm tra ngân sách ngày và ngân sách dùng chung có bị chiến dịch khác ăn hết không.',
            'Kiểm tra giá thầu có thấp hơn sàn đấu giá, đối tượng có quá hẹp hoặc chồng chéo tự cạnh tranh không.',
            'Kiểm tra lịch chạy, vị trí địa lý, ngày bắt đầu/kết thúc chiến dịch.',
            'Kiểm tra trạng thái duyệt quảng cáo trong trình quản lý (công cụ này không nhìn thấy lý do từ chối).',
        ],
        'guardrails': ['Chỉ bật lại phân phối sau khi rõ nguyên nhân; tránh tăng giá thầu mù để "ép chạy".'],
    }


def _cond_cpa_drift_vs_baseline(c, t, ctx):
    baseline = (ctx.get('baselines') or {}).get(str(c.get('id')))
    if not baseline:
        return None
    median_cpa, cpa = _num(baseline.get('median_cpa')), _num(c.get('cpa'))
    conversions = _num(c.get('conversions'))
    if median_cpa is None or median_cpa <= 0 or cpa is None or conversions is None:
        return None
    if conversions < CPA_MIN_CONVERSIONS or cpa <= median_cpa * DRIFT_CPA_REVIEW_RATIO:
        return None
    level = 'critical' if cpa > median_cpa * DRIFT_CPA_CRITICAL_RATIO else 'review'
    drift = _pct_delta(cpa, median_cpa)
    band = baseline.get('cpa_volatility')
    band_text = f" (biên dao động lịch sử ±{round(band * 100)}%)" if band is not None else ''
    return {
        'level': level,
        'message': (f"CPA kỳ này {_money(cpa, ctx['currency'])} lệch +{drift}% so với CPA trung vị của chính chiến dịch "
                    f"({_money(median_cpa, ctx['currency'])} qua {baseline.get('periods', '?')} kỳ){band_text}: hiệu quả đang xấu đi "
                    f"so với nền của chính nó, kể cả khi chưa chạm ngưỡng mục tiêu."),
        'why': ('So với nền lịch sử của chính chiến dịch bắt được suy giảm sớm hơn so với mục tiêu chung: một chiến dịch '
                'quen chạy CPA thấp bỗng đắt lên thường do cạnh tranh tăng, creative mệt, hoặc thay đổi ở trang đích.'),
        'actions': [
            'Xác định thời điểm CPA bắt đầu lệch và đối chiếu thay đổi đã làm (creative, đối tượng, trang đích, ngân sách).',
            'Kiểm chứng tracking vẫn ghi nhận đúng (loại trừ nguyên nhân đo lường trước).',
            f"Nếu lệch là thật: giảm tốc theo từng bước tối đa {MAX_STEP_PERCENT}% và theo dõi CPA quay về vùng nền.",
        ],
        'guardrails': ['Nền dựa trên dữ liệu quá khứ của chính tài khoản này; kỳ nền quá ít (dưới 3 kỳ) thì chỉ nên tham khảo.'],
    }


def _cond_roas_drift_vs_baseline(c, t, ctx):
    baseline = (ctx.get('baselines') or {}).get(str(c.get('id')))
    if not baseline:
        return None
    median_roas, roas = _num(baseline.get('median_roas')), _num(c.get('roas'))
    conversions = _num(c.get('conversions'))
    if median_roas is None or median_roas <= 0 or roas is None or conversions is None:
        return None
    if conversions < CPA_MIN_CONVERSIONS or roas >= median_roas * DRIFT_ROAS_REVIEW_RATIO:
        return None
    level = 'critical' if roas < median_roas * DRIFT_ROAS_CRITICAL_RATIO else 'review'
    drift = abs(_pct_delta(roas, median_roas))
    return {
        'level': level,
        'message': (f"ROAS kỳ này {_ratio(roas)} tụt {drift}% so với ROAS trung vị của chính chiến dịch "
                    f"({_ratio(median_roas)} qua {baseline.get('periods', '?')} kỳ): hiệu quả đang xấu đi so với nền của chính nó."),
        'why': ('ROAS tụt so với nền của chính chiến dịch thường báo hiệu creative mệt, cạnh tranh tăng, hoặc thay đổi '
                'ghi nhận doanh thu — cần tìm nguyên nhân trước khi chỉnh ngân sách.'),
        'actions': [
            'Đối chiếu doanh thu ghi nhận với doanh thu thực để loại trừ lỗi đo lường.',
            'Xác định thời điểm ROAS bắt đầu tụt và các thay đổi đã làm quanh thời điểm đó.',
            f"Nếu tụt là thật: giảm tốc chi tiêu từng bước tối đa {MAX_STEP_PERCENT}% ở phần kém hiệu quả nhất.",
        ],
        'guardrails': ['Nền dựa trên dữ liệu quá khứ của chính tài khoản này; kỳ nền quá ít (dưới 3 kỳ) thì chỉ nên tham khảo.'],
    }


# ---------------------------------------------------------------------------
# PLAYBOOK: danh mục quy tắc dạng dữ liệu + registry điều kiện theo code.
# ---------------------------------------------------------------------------
PLAYBOOK = [
    {'code': 'spend_no_conversions', 'platform': 'both', 'category': 'tracking', 'severity': 'review',
     'title': 'Chi tiêu chưa ghi nhận chuyển đổi — kiểm tra tracking trước'},
    {'code': 'cpa_above_target', 'platform': 'both', 'category': 'bid_cost', 'severity': 'review',
     'title': 'CPA vượt mục tiêu — giảm tốc theo bước nhỏ'},
    {'code': 'cpa_well_below_target_scale', 'platform': 'both', 'category': 'scale', 'severity': 'opportunity',
     'title': 'CPA thấp hơn mục tiêu — cơ hội mở rộng có kiểm soát'},
    {'code': 'roas_below_target', 'platform': 'both', 'category': 'roas', 'severity': 'review',
     'title': 'ROAS dưới mục tiêu — kiểm tra doanh thu rồi giảm tốc'},
    {'code': 'roas_above_target_scale', 'platform': 'both', 'category': 'scale', 'severity': 'opportunity',
     'title': 'ROAS vượt mục tiêu — cơ hội tăng ngân sách theo bước'},
    {'code': 'low_ctr', 'platform': 'both', 'category': 'structure', 'severity': 'review',
     'title': 'CTR thấp — rà soát nội dung và đối tượng'},
    {'code': 'high_ctr_no_conversions', 'platform': 'both', 'category': 'tracking', 'severity': 'review',
     'title': 'CTR khỏe nhưng 0 chuyển đổi — lệch ở trang đích/tracking'},
    {'code': 'low_conversion_volume_for_smart_bidding', 'platform': 'both', 'category': 'bid_cost', 'severity': 'review',
     'title': 'Lượng chuyển đổi thấp cho đấu thầu thông minh — gộp và dồn tín hiệu'},
    {'code': 'dead_campaign', 'platform': 'both', 'category': 'structure', 'severity': 'review',
     'title': 'Chiến dịch đang bật nhưng không phân phối'},
    {'code': 'cpa_drift_vs_baseline', 'platform': 'both', 'category': 'bid_cost', 'severity': 'review',
     'title': 'CPA lệch khỏi nền của chính chiến dịch'},
    {'code': 'roas_drift_vs_baseline', 'platform': 'both', 'category': 'roas', 'severity': 'review',
     'title': 'ROAS lệch khỏi nền của chính chiến dịch'},
    {'code': 'account_fragmentation', 'platform': 'both', 'category': 'structure', 'severity': 'opportunity',
     'title': 'Tài khoản phân mảnh — cơ hội gộp chiến dịch'},
    {'code': 'account_budget_reallocation', 'platform': 'both', 'category': 'scale', 'severity': 'opportunity',
     'title': 'Tái phân bổ ngân sách khỏi chiến dịch kém hiệu quả'},
]

CONDITIONS = {
    'spend_no_conversions': _cond_spend_no_conversions,
    'cpa_above_target': _cond_cpa_above_target,
    'cpa_well_below_target_scale': _cond_cpa_well_below_target_scale,
    'roas_below_target': _cond_roas_below_target,
    'roas_above_target_scale': _cond_roas_above_target_scale,
    'low_ctr': _cond_low_ctr,
    'high_ctr_no_conversions': _cond_high_ctr_no_conversions,
    'low_conversion_volume_for_smart_bidding': _cond_low_conversion_volume,
    'dead_campaign': _cond_dead_campaign,
    'cpa_drift_vs_baseline': _cond_cpa_drift_vs_baseline,
    'roas_drift_vs_baseline': _cond_roas_drift_vs_baseline,
}

_BY_CODE = {entry['code']: entry for entry in PLAYBOOK}
assert set(_BY_CODE) == {e['code'] for e in PLAYBOOK}, 'PLAYBOOK codes must be unique'


# ---------------------------------------------------------------------------
# ĐỘC QUYỀN 1 — Hồ sơ nền riêng từng tài khoản (account baselines)
# ---------------------------------------------------------------------------
def compute_baselines(snapshots):
    """Tính nền lịch sử cho từng chiến dịch từ các kỳ snapshot đã qua.

    snapshots: list các dict chiến dịch (cùng định dạng dữ liệu 7 ngày) kèm
    khóa 'period' (nhãn kỳ, ví dụ 'last_7d' hoặc '2026-W27'). Mỗi phần tử là
    MỘT chiến dịch trong MỘT kỳ. Trả về {campaign_id: baseline} với median
    CPA/ROAS, biên dao động (spread/median) và số kỳ có dữ liệu. Kỳ thiếu
    số liệu (None) bị bỏ qua cho chỉ số đó — không tính là 0.
    """
    grouped = {}
    for snap in snapshots or []:
        if not isinstance(snap, dict) or snap.get('id') is None:
            continue
        grouped.setdefault(str(snap['id']), []).append(snap)
    baselines = {}
    for campaign_id, rows in grouped.items():
        cpas = [v for v in (_num(r.get('cpa')) for r in rows) if v is not None]
        roases = [v for v in (_num(r.get('roas')) for r in rows) if v is not None]
        baseline = {'campaign_id': campaign_id, 'periods': len(rows),
                    'median_cpa': None, 'median_roas': None,
                    'cpa_volatility': None, 'roas_volatility': None}
        if cpas:
            median = statistics.median(cpas)
            baseline['median_cpa'] = round(median, 4)
            if len(cpas) >= 2 and median > 0:
                baseline['cpa_volatility'] = round((max(cpas) - min(cpas)) / median, 4)
        if roases:
            median = statistics.median(roases)
            baseline['median_roas'] = round(median, 4)
            if len(roases) >= 2 and median > 0:
                baseline['roas_volatility'] = round((max(roases) - min(roases)) / median, 4)
        baselines[campaign_id] = baseline
    return baselines


# ---------------------------------------------------------------------------
# ĐỘC QUYỀN 2 — Vòng kiểm chứng kết quả (outcome verification)
# ---------------------------------------------------------------------------
_TRACKING_CODES = ('spend_no_conversions', 'high_ctr_no_conversions')
_CPA_CODES = ('cpa_above_target', 'cpa_well_below_target_scale', 'cpa_drift_vs_baseline')
_ROAS_CODES = ('roas_below_target', 'roas_above_target_scale', 'roas_drift_vs_baseline')


def verify_outcome(baseline_snapshot, current_snapshot, finding_code):
    """Phán quyết kết quả của một đề xuất trước đó: improved | worsened |
    unchanged | insufficient_data.

    baseline_snapshot: dict chiến dịch tại kỳ đề xuất được đưa ra.
    current_snapshot: dict chiến dịch cùng chiến dịch ở kỳ đo lại.
    Chỉ số dùng để phán quyết tùy mã quy tắc: CPA giảm = tốt cho quy tắc CPA;
    ROAS tăng = tốt cho quy tắc ROAS; chuyển đổi hồi phục = tốt cho quy tắc
    tracking. Biến động trong ±5% coi là nhiễu (unchanged). CPA/ROAS chỉ được
    phán quyết khi cả hai kỳ có >= 5 chuyển đổi, ngược lại insufficient_data.
    """
    if not isinstance(baseline_snapshot, dict) or not isinstance(current_snapshot, dict):
        return 'insufficient_data'
    base_conv = _num(baseline_snapshot.get('conversions'))
    cur_conv = _num(current_snapshot.get('conversions'))

    if finding_code in _TRACKING_CODES:
        if base_conv is None or cur_conv is None:
            return 'insufficient_data'
        if base_conv == 0:
            return 'improved' if cur_conv >= OUTCOME_MIN_CONVERSIONS else 'unchanged'
        return 'insufficient_data'  # quy tắc tracking không thể đã kích hoạt

    if finding_code == 'low_ctr':
        base_ctr, cur_ctr = _num(baseline_snapshot.get('ctr_percent')), _num(current_snapshot.get('ctr_percent'))
        if base_ctr is None or cur_ctr is None or base_ctr <= 0:
            return 'insufficient_data'
        change = cur_ctr / base_ctr - 1
        if change > OUTCOME_NOISE_BAND:
            return 'improved'
        if change < -OUTCOME_NOISE_BAND:
            return 'worsened'
        return 'unchanged'

    if finding_code == 'low_conversion_volume_for_smart_bidding':
        if base_conv is None or cur_conv is None:
            return 'insufficient_data'
        if base_conv == 0:
            return 'improved' if cur_conv > 0 else 'unchanged'
        change = cur_conv / base_conv - 1
        if change > OUTCOME_NOISE_BAND:
            return 'improved'
        if change < -OUTCOME_NOISE_BAND:
            return 'worsened'
        return 'unchanged'

    if finding_code == 'dead_campaign':
        base_imp, cur_imp = _num(baseline_snapshot.get('impressions')), _num(current_snapshot.get('impressions'))
        if base_imp is None or cur_imp is None:
            return 'insufficient_data'
        if base_imp == 0:
            return 'improved' if cur_imp > 0 else 'unchanged'
        return 'insufficient_data'

    if finding_code in _CPA_CODES or finding_code in _ROAS_CODES:
        if (base_conv is None or cur_conv is None
                or base_conv < OUTCOME_MIN_CONVERSIONS or cur_conv < OUTCOME_MIN_CONVERSIONS):
            return 'insufficient_data'
        key = 'cpa' if finding_code in _CPA_CODES else 'roas'
        base_val, cur_val = _num(baseline_snapshot.get(key)), _num(current_snapshot.get(key))
        if base_val is None or cur_val is None or base_val <= 0:
            return 'insufficient_data'
        change = cur_val / base_val - 1
        if finding_code in _CPA_CODES:  # CPA giảm = cải thiện
            if change < -OUTCOME_NOISE_BAND:
                return 'improved'
            if change > OUTCOME_NOISE_BAND:
                return 'worsened'
        else:  # ROAS tăng = cải thiện
            if change > OUTCOME_NOISE_BAND:
                return 'improved'
            if change < -OUTCOME_NOISE_BAND:
                return 'worsened'
        return 'unchanged'

    return 'insufficient_data'


# ---------------------------------------------------------------------------
# Đánh giá cấp tài khoản (campaign_id = 'ACCOUNT')
# ---------------------------------------------------------------------------
def evaluate_account(campaigns, platform, currency='', goal=None):
    """Phát hiện ở cấp tài khoản — thứ không thể thấy từ một chiến dịch đơn lẻ."""
    targets = _goal_targets(goal, currency)
    ctx = {'platform': platform, 'currency': currency, 'baselines': {}}
    active = [c for c in (campaigns or []) if _is_active(c, platform)]
    findings = []

    # Phân mảnh: nhiều chiến dịch đang chạy mà mỗi chiến dịch thiếu lượng
    # chuyển đổi để học ổn định -> tín hiệu học bị chia nhỏ khắp tài khoản.
    fragmented = []
    for c in active:
        conversions, spend = _num(c.get('conversions')), _num(c.get('spend'))
        if conversions is not None and spend is not None and spend > 0 \
                and conversions < ACCOUNT_FRAGMENT_MAX_CONVERSIONS:
            fragmented.append(c)
    if len(fragmented) >= ACCOUNT_FRAGMENT_MIN_CAMPAIGNS:
        entry = _BY_CODE['account_fragmentation']
        total_spend = sum(_num(c.get('spend')) or 0 for c in fragmented)
        findings.append(_finding(
            'ACCOUNT', entry, 'opportunity',
            (f"{len(fragmented)} chiến dịch đang chạy đều dưới {ACCOUNT_FRAGMENT_MAX_CONVERSIONS} chuyển đổi trong 7 ngày "
             f"(tổng chi {_money(total_spend, currency)}): tín hiệu học đang bị phân mảnh khắp tài khoản. "
             f"Cân nhắc gộp các chiến dịch cùng mục tiêu."),
            ('Mỗi chiến dịch/con dấu quảng cáo là một "người học" riêng của nền tảng. Chia ngân sách cho quá nhiều '
             'chiến dịch ít chuyển đổi khiến không chiến dịch nào đủ dữ liệu để đấu thầu thông minh ổn định.'),
            ['Liệt kê các chiến dịch cùng mục tiêu/đối tượng/sản phẩm — đó là ứng viên gộp trước tiên.',
             'Gộp theo từng cụm nhỏ, giữ lại chiến dịch có dữ liệu lịch sử tốt nhất làm khung.',
             'Sau khi gộp, chờ ít nhất 7–14 ngày dữ liệu trước khi đánh giá lại; đừng gộp tất cả cùng lúc.'],
            ['Gộp là thay đổi cấu trúc lớn: làm từng cụm và giữ bản ghi để đối chiếu trước/sau.'],
        ))

    # Tái phân bổ: phần lớn chi tiêu đang dồn vào chiến dịch không đạt mục tiêu.
    cpa_target, roas_target = targets['cpa_target'], targets['roas_target']
    if cpa_target is not None or roas_target is not None:
        total_spend, inefficient_spend, inefficient_count = 0.0, 0.0, 0
        for c in active:
            spend = _num(c.get('spend'))
            if spend is None or spend <= 0:
                continue
            total_spend += spend
            cpa, roas = _num(c.get('cpa')), _num(c.get('roas'))
            inefficient = False
            if cpa_target is not None and cpa is not None and cpa > cpa_target * ACCOUNT_INEFFICIENT_CPA_RATIO:
                inefficient = True
            if roas_target is not None and roas is not None and roas < roas_target:
                inefficient = True
            if inefficient:
                inefficient_spend += spend
                inefficient_count += 1
        if total_spend > 0 and inefficient_spend / total_spend > ACCOUNT_INEFFICIENT_SPEND_SHARE:
            entry = _BY_CODE['account_budget_reallocation']
            share = round(inefficient_spend / total_spend * 100)
            if cpa_target is not None:
                yardstick = f"CPA trên {ACCOUNT_INEFFICIENT_CPA_RATIO:g}x mục tiêu {_money(cpa_target, currency)}"
            else:
                yardstick = f"ROAS dưới mục tiêu {_ratio(roas_target)}"
            findings.append(_finding(
                'ACCOUNT', entry, 'opportunity',
                (f"{share}% tổng chi 7 ngày ({_money(inefficient_spend, currency)} trên {_money(total_spend, currency)}) "
                 f"đang dồn vào {inefficient_count} chiến dịch không đạt mục tiêu ({yardstick}): cân nhắc tái phân bổ dần "
                 f"sang các chiến dịch đạt mục tiêu."),
                ('Ở cấp tài khoản, đòn bẩy lớn nhất thường không nằm trong từng chiến dịch mà ở cách ngân sách được '
                 'chia giữa các chiến dịch. Tiền đang nuôi các chiến dịch kém hiệu quả là tiền không mua được chuyển đổi rẻ.'),
                [f"Chuyển ngân sách theo từng bước tối đa {MAX_STEP_PERCENT}% mỗi lần từ chiến dịch kém sang chiến dịch đạt mục tiêu.",
                 'Giữ lại một phần ngân sách thử nghiệm cho chiến dịch đang cải thiện — đừng cắt về 0 ngay.',
                 'Đo lại sau mỗi bước bằng chính các quy tắc của playbook này (vòng kiểm chứng kết quả).'],
                ['Không tái phân bổ dựa trên một kỳ dữ liệu duy nhất nếu chuyển đổi còn độ trễ lớn.'],
            ))
    return findings


# ---------------------------------------------------------------------------
# Đánh giá chính: từng chiến dịch + cấp tài khoản, có conflict guard.
# ---------------------------------------------------------------------------
def evaluate_campaigns(campaigns, platform, currency, goal=None, baselines=None):
    """Trả list finding dict {campaign_id, level, code, category, message,
    playbook{title, why, actions, guardrails}}.

    - campaigns: list dict chiến dịch kỳ hiện tại (last_7d).
    - goal: dict của goals.goal_for hoặc None. Không có mục tiêu thì các quy
      tắc theo mục tiêu im lặng; quy tắc ngưỡng/tracking vẫn chạy.
    - baselines: dict từ compute_baselines() hoặc None. Có nền thì thêm các
      finding lệch-khỏi-nền của chính chiến dịch.

    Conflict guard (chống tự mâu thuẫn): nếu một chiến dịch vừa có cơ hội mở
    rộng vừa có finding thuộc nhóm cắt/giảm (CUT_CODES ở mức review trở lên,
    hoặc bất kỳ finding critical nào), finding mở rộng bị loại bỏ và mã của nó
    được ghi vào khóa 'suppressed' của finding được giữ lại.
    """
    targets = _goal_targets(goal, currency)
    ctx = {'platform': platform, 'currency': currency, 'baselines': baselines or {}}
    findings = []
    for c in campaigns or []:
        if not isinstance(c, dict) or c.get('id') is None or not _is_active(c, platform):
            continue
        for entry in PLAYBOOK:
            code = entry['code']
            if code not in CONDITIONS:
                continue  # quy tắc cấp tài khoản xử lý riêng ở evaluate_account
            if entry['platform'] not in ('both', platform):
                continue
            result = CONDITIONS[code](c, targets, ctx)
            if result:
                findings.append(_finding(c['id'], entry, result['level'], result['message'],
                                         result['why'], result['actions'], result['guardrails']))
    findings.extend(evaluate_account(campaigns, platform, currency, goal))
    findings = _apply_conflict_guard(findings)
    return findings[:MAX_FINDINGS]


def _apply_conflict_guard(findings):
    """Loại cơ hội mở rộng của chiến dịch đang có finding cắt/giảm/critical."""
    by_campaign = {}
    for f in findings:
        by_campaign.setdefault(f['campaign_id'], []).append(f)
    suppressed_by_campaign = {}
    for campaign_id, group in by_campaign.items():
        if campaign_id == 'ACCOUNT':
            continue
        blockers = [f for f in group
                    if f['level'] == 'critical' or (f['code'] in CUT_CODES and f['level'] == 'review')]
        scale = [f for f in group if f['code'] in SCALE_CODES]
        if blockers and scale:
            suppressed_by_campaign[campaign_id] = [f['code'] for f in scale]
    if not suppressed_by_campaign:
        return findings
    kept = []
    for f in findings:
        codes = suppressed_by_campaign.get(f['campaign_id'])
        if codes and f['code'] in SCALE_CODES:
            continue  # bị chặn bởi conflict guard
        if codes and (f['level'] == 'critical' or f['code'] in CUT_CODES):
            f = dict(f)
            f['suppressed'] = list(codes)
            suppressed_by_campaign[f['campaign_id']] = None  # ghi một lần
        kept.append(f)
    return kept
