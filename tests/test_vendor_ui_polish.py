"""Seller UI needs fast local lookup and visually distinct expiring licenses."""
from pathlib import Path

SRC=(Path(__file__).resolve().parents[1]/'windows'/'vendor_manager.py').read_text(encoding='utf-8')


def test_seller_search_is_local_and_matches_device_and_customer():
    assert "self.customer_search=tk.StringVar()" in SRC
    assert "self.customer_search.trace_add('write'" in SRC
    assert "query in row['customer_ref'].casefold()" in SRC
    assert "query in row['device'].casefold()" in SRC
    assert "def _render_customers(self):" in SRC
    assert "self._records=ledger.subscriptions(db)" in SRC


def test_seller_renewal_priority_and_color_coded_rows():
    assert "priority={'expired':0,'expiring':1,'not_activated':2,'active':3}" in SRC
    for state in ('expired','expiring','active','not_activated'):
        assert f"self.tree.tag_configure('{state}'" in SRC
    assert "tags=(record['state'],)" in SRC
