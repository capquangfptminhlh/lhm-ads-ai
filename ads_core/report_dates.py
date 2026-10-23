"""Single calendar-date contract for Google/Meta/demo report filters.

Dates represent calendar days in the machine's local timezone. Each provider
interprets day boundaries using its *ad account* timezone, which may differ.
Never interpolate user-supplied text into GAQL before ISO date validation.
"""
from datetime import date, timedelta
from fastapi import HTTPException

PERIODS = (
    'today', 'yesterday', 'last_7d', 'last_14d', 'last_30d', 'last_90d',
    'this_week', 'last_week', 'this_month', 'last_month',
    'this_quarter', 'last_quarter', 'this_year', 'last_year', 'custom'
)


def resolve_date_range(period='last_7d', date_from=None, date_to=None, *, today=None):
    now = today or date.today()
    if period not in PERIODS:
        raise HTTPException(422, 'Khoảng thời gian không được hỗ trợ')
    if period == 'custom':
        if not isinstance(date_from, str) or not isinstance(date_to, str):
            raise HTTPException(422, 'Chọn đủ ngày bắt đầu và ngày kết thúc')
        try:
            # Exact YYYY-MM-DD, not timestamps or GAQL fragments.
            if len(date_from) != 10 or len(date_to) != 10:
                raise ValueError()
            start = date.fromisoformat(date_from)
            end = date.fromisoformat(date_to)
            if start.isoformat() != date_from or end.isoformat() != date_to:
                raise ValueError()
        except ValueError:
            raise HTTPException(422, 'Ngày phải có định dạng YYYY-MM-DD')
    elif date_from is not None or date_to is not None:
        raise HTTPException(422, 'Ngày tùy chỉnh chỉ dùng khi chọn Tùy chỉnh')
    elif period == 'today':
        start = end = now
    elif period == 'yesterday':
        start = end = now - timedelta(days=1)
    elif period in ('last_7d', 'last_14d', 'last_30d', 'last_90d'):
        # Include current day, following everyday Google Ads dashboard use.
        n = int(period.split('_')[1][:-1])
        start, end = now - timedelta(days=n - 1), now
    elif period == 'this_week':
        start, end = now - timedelta(days=now.weekday()), now
    elif period == 'last_week':
        end = now - timedelta(days=now.weekday() + 1)
        start = end - timedelta(days=6)
    elif period == 'this_month':
        start, end = now.replace(day=1), now
    elif period == 'last_month':
        end = now.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    elif period == 'this_quarter':
        first_month = (now.month - 1) // 3 * 3 + 1
        start, end = now.replace(month=first_month, day=1), now
    elif period == 'last_quarter':
        quarter_start = now.replace(month=(now.month - 1) // 3 * 3 + 1, day=1)
        end = quarter_start - timedelta(days=1)
        start = end.replace(month=(end.month - 1) // 3 * 3 + 1, day=1)
    elif period == 'this_year':
        start, end = now.replace(month=1, day=1), now
    else:  # last_year
        start, end = now.replace(year=now.year - 1, month=1, day=1), now.replace(year=now.year - 1, month=12, day=31)
    if start > end or end > now or (end - start).days > 365:
        raise HTTPException(422, 'Ngày không hợp lệ, nằm trong tương lai hoặc vượt quá 366 ngày')
    return start.isoformat(), end.isoformat()
