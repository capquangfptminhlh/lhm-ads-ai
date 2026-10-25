"""Generate tests/fixtures/core/parity.json from the Windows app's Python code.

The PWA's JS core (static/core/*.js) must reproduce these outputs exactly.
Inputs are synthetic and deterministic (seeded); the expected outputs come from
the real ads_core functions, driven through fake HTTP clients. Nothing here
touches a network, a database or real credentials.

  python tools/gen_core_fixtures.py          # rewrite the fixture file
  python tools/gen_core_fixtures.py --check  # exit 1 if the file is stale
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "tests" / "fixtures" / "core" / "parity.json"


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def raise_for_status(self):
        return None
    def json(self):
        return self.payload


class FakeClient:
    """Answers the exact calls ads_core makes, from canned payloads."""
    def __init__(self, google_pages=None, meta=None):
        self.google_pages = google_pages
        self.meta = meta or {}
    async def __aenter__(self):
        return self
    async def __aexit__(self, *exc):
        return False
    async def post(self, url, **kwargs):
        if "oauth2.googleapis.com" in url:
            return FakeResponse({"access_token": "fixture-access-token"})
        return FakeResponse(self.google_pages)
    async def get(self, url, **kwargs):
        for suffix in ("/campaigns", "/insights", "/adsets"):
            if url.endswith(suffix):
                return FakeResponse({"data": self.meta.get(suffix.strip("/"), [])})
        return FakeResponse(self.meta.get("daily", {"data": []}))


def as_json(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def error_text(exc):
    detail = getattr(exc, "detail", None)
    return {"error": str(detail if detail is not None else exc)}


# ---------------------------------------------------------------- random inputs
def maybe(rng, value, p_none=0.12):
    return None if rng.random() < p_none else value


def random_campaign(rng, platform, idx):
    clicks = rng.choice([0, 3, 40, 49, 50, 99, 100, 150, 400, 1200])
    impressions = rng.choice([0, 500, 999, 1000, 5000, 40000, 120000])
    conversions = rng.choice([0, 0, 1, 2.5, 4, 5, 9, 10, 14, 15, 29, 30, 45, 80])
    spend = rng.choice([0, 0.0, 125000.5, 99.995, 2.5, 3500000, 812345.125, 49.99, 1e6/3])
    value = rng.choice([0, 1500000, 999.5, 4.2e7, 12345.678])
    ctr = round(clicks * 100 / impressions, 2) if impressions else None
    cpa = round(spend / conversions, 2) if conversions else None
    roas = round(value / spend, 3) if spend else None
    c = {
        "id": str(10000 + idx), "name": f"Campaign {idx}",
        "status": rng.choice(["ENABLED", "ENABLED", "ACTIVE", "PAUSED"]),
        "spend": maybe(rng, spend), "clicks": maybe(rng, clicks), "impressions": maybe(rng, impressions),
        "conversions": maybe(rng, conversions), "conversion_value": maybe(rng, value),
        "ctr_percent": maybe(rng, ctr), "cpa": maybe(rng, cpa), "roas": maybe(rng, roas),
        "bidding_strategy": rng.choice([None, "MANUAL_CPC", "TARGET_CPA", "MAXIMIZE_CONVERSIONS",
                                        "LOWEST_COST_WITH_BID_CAP", "LOWEST_COST_WITHOUT_CAP"]),
        "bid_target_cpa": maybe(rng, rng.choice([None, 50000.0, 1.0, 250.0, 120000.0]), 0.3),
        "bid_target_roas": maybe(rng, rng.choice([None, 2.0, 4.5, 0.8]), 0.4),
    }
    if platform == "google":
        c["budget_lost_is"] = maybe(rng, rng.choice([0.05, 0.2, 0.35, 0.8]), 0.3)
    else:
        c["status"] = rng.choice(["ACTIVE", "ACTIVE", "PAUSED"])
        c["effective_status"] = rng.choice(["ACTIVE", "ACTIVE", "CAMPAIGN_PAUSED", None])
        c["frequency"] = maybe(rng, rng.choice([1.2, 3.99, 4.0, 5.5, 6.0, 9.1]), 0.25)
        c["adset_bid_target_cpa"] = maybe(rng, rng.choice([None, 40000.0, 300.0]), 0.3)
    if rng.random() < 0.04:
        c["spend"] = "123.5"           # strings and junk must behave like Python
    if rng.random() < 0.03:
        c["clicks"] = True
    return c


def random_goal(rng, currency):
    kind = rng.random()
    if kind < 0.3:
        return None
    goal = {"enabled": rng.random() > 0.1, "objective": rng.choice(["cpa", "roas"]),
            "target": rng.choice([50000, 120.5, 2.0, 3.5, 0, -1, 250000]),
            "min_conversions": rng.choice([None, 3, 5, 8, 20]),
            "currency": rng.choice([currency, currency, "USD", None])}
    return goal


def playbook_cases(rng, count):
    from ads_core import optimization_playbook as pb
    cases = []
    for n in range(count):
        platform = rng.choice(["google", "meta"])
        currency = rng.choice(["VND", "VND", "USD", "", "eur"])
        campaigns = [random_campaign(rng, platform, n * 20 + i) for i in range(rng.randint(1, 9))]
        if rng.random() < 0.05:
            campaigns.append("not-a-dict")
        goal = random_goal(rng, currency)
        baselines = None
        if rng.random() < 0.5:
            snapshots = []
            for c in campaigns:
                if not isinstance(c, dict):
                    continue
                for _ in range(rng.randint(1, 4)):
                    snapshots.append({"id": c["id"], "cpa": maybe(rng, rng.choice([800.0, 41000.0, 52000.5, 90.0]), 0.2),
                                      "roas": maybe(rng, rng.choice([1.1, 2.5, 4.0, 6.75]), 0.2)})
            baselines = pb.compute_baselines(snapshots)
        args = {"campaigns": campaigns, "platform": platform, "currency": currency,
                "goal": goal, "baselines": baselines}
        cases.append({"kind": "playbook", "input": as_json(args),
                      "expected": as_json(pb.evaluate_campaigns(campaigns, platform, currency, goal, baselines))})
    return cases


def baseline_and_outcome_cases(rng):
    from ads_core import optimization_playbook as pb
    cases = []
    for _ in range(40):
        snapshots = [{"id": rng.choice(["1", "2", "3", None]),
                      "cpa": maybe(rng, rng.choice([10, 12.5, 13.0, 40.25, -3, "7"]), 0.2),
                      "roas": maybe(rng, rng.choice([1.0, 2.25, 3.1, 0]), 0.2)} for _ in range(rng.randint(0, 9))]
        cases.append({"kind": "baselines", "input": {"snapshots": as_json(snapshots)},
                      "expected": as_json(pb.compute_baselines(snapshots))})
    codes = [e["code"] for e in pb.PLAYBOOK] + ["unknown_code"]
    for _ in range(160):
        def snap():
            return {"conversions": maybe(rng, rng.choice([0, 3, 5, 6, 20, 21])),
                    "ctr_percent": maybe(rng, rng.choice([0, 0.4, 0.42, 1.0, 1.06])),
                    "impressions": maybe(rng, rng.choice([0, 100])),
                    "cpa": maybe(rng, rng.choice([0, 100.0, 104.0, 106.0, 90.0])),
                    "roas": maybe(rng, rng.choice([0, 2.0, 2.1, 2.2, 1.8])),
                    "bid_target_roas": maybe(rng, rng.choice([None, 3.0]), 0.5)}
        base, cur, code = snap(), snap(), rng.choice(codes)
        cases.append({"kind": "verify", "input": {"base": base, "cur": cur, "code": code},
                      "expected": pb.verify_outcome(base, cur, code)})
    return cases


def date_cases():
    from ads_core.report_dates import resolve_date_range, PERIODS
    cases = []
    todays = ["2026-10-25", "2026-01-01", "2026-03-31", "2026-07-01", "2024-02-29", "2026-12-31", "2026-10-26"]
    for today in todays:
        for period in PERIODS:
            for frm, to in ([None, None], ["2026-10-01", "2026-10-20"], ["2026-10-20", "2026-10-01"],
                            ["2026-2-01", "2026-10-02"], ["2025-01-01", "2026-10-24"]):
                try:
                    expected = list(resolve_date_range(period, frm, to, today=date.fromisoformat(today)))
                except Exception as exc:  # noqa: BLE001 - recorded as the expected error
                    expected = error_text(exc)
                cases.append({"kind": "date_range", "input": {"period": period, "from": frm, "to": to, "today": today},
                              "expected": expected})
    return cases


def report_cases(rng):
    from ads_core import providers
    cases = []
    for _ in range(60):
        rows = []
        with_conv = rng.random() < 0.6
        for d in range(rng.randint(0, 8)):
            row = {"date": f"2026-10-{d+1:02d}", "spend": rng.choice([0, 1.005, 2.5, 123456.789, 0.125]),
                   "impressions": rng.choice([0, 10, 3000]), "clicks": rng.choice([0, 1, 7, 300])}
            if with_conv:
                row["conversions"] = rng.choice([0, 1.5, 3, 12.25])
                if rng.random() < 0.9:
                    row["conversion_value"] = rng.choice([0, 1500.5, 9999.99])
            rows.append(row)
        source, currency = rng.choice(["google_live", "meta_live", "demo"]), rng.choice(["VND", "USD"])
        cases.append({"kind": "report_output", "input": {"rows": rows, "currency": currency, "source": source},
                      "expected": as_json(providers.report_output(rows, currency, source))})
    return cases


def google_report_cases(rng):
    from ads_core import providers
    providers.account_token = lambda acc: json.dumps({"client_id": "c", "refresh_token": "r"})
    cases = []
    for _ in range(25):
        pages = []
        for _p in range(rng.randint(1, 3)):
            results = []
            for _r in range(rng.randint(0, 6)):
                metrics = {"costMicros": str(rng.choice([0, 1, 125000, 999999, 250000000, 1234567891])),
                           "impressions": str(rng.choice([0, 15, 4000])), "clicks": str(rng.choice([0, 2, 90]))}
                if rng.random() < 0.8:
                    metrics["conversions"] = rng.choice([0, 1.0, 2.5])
                if rng.random() < 0.7:
                    metrics["conversionsValue"] = rng.choice([0, 100.5, 77.25])
                results.append({"segments": {"date": f"2026-10-{rng.randint(1, 7):02d}"}, "metrics": metrics})
            pages.append({"results": results})
        acc = {"external_id": "1234567890", "currency": "VND", "platform": "google", "token_ciphertext": "x"}
        providers.httpx.AsyncClient = lambda **kw: FakeClient(google_pages=pages)
        expected = asyncio.run(providers.google_report(acc, "custom", date_from="2026-10-01", date_to="2026-10-07"))
        cases.append({"kind": "google_report", "input": {"pages": pages, "currency": "VND"}, "expected": as_json(expected)})
    return cases


def meta_report_cases(rng):
    from ads_core import providers
    providers.account_token = lambda acc: "fixture-token"
    cases = []
    for _ in range(15):
        data = [{"date_start": f"2026-10-0{i+1}", "spend": rng.choice(["0", "12.5", "300000.25"]),
                 "impressions": rng.choice(["0", "1500"]), "clicks": rng.choice(["0", "33"])}
                for i in range(rng.randint(0, 7))]
        acc = {"external_id": "act_123456", "currency": "VND", "platform": "meta", "token_ciphertext": "x"}
        # The daily report reads act_<id>/insights, like the campaign scan.
        providers.httpx.AsyncClient = lambda **kw: FakeClient(meta={"insights": data})
        expected = asyncio.run(providers.fetch_report(acc, "custom", "2026-10-01", "2026-10-07"))
        cases.append({"kind": "meta_report", "input": {"body": {"data": data}, "currency": "VND"},
                      "expected": as_json(expected)})
    return cases


def campaign_cases(rng):
    from ads_core import optimizations, goals
    optimizations.account_token = lambda acc: (json.dumps({"client_id": "c", "refresh_token": "r"})
                                               if acc["platform"] == "google" else "fixture-token")
    cases = []
    for n in range(30):
        results = []
        for i in range(rng.randint(0, 7)):
            campaign = {"id": rng.choice([str(50000 + n * 10 + i), "12", "abc"]),
                        "name": rng.choice(["Search VN", None, "x" * 130]),
                        "status": rng.choice(["ENABLED", "PAUSED", None]),
                        "biddingStrategyType": rng.choice([None, "TARGET_CPA", "MANUAL_CPC"])}
            if rng.random() < 0.4:
                campaign["targetCpa"] = {"targetCpaMicros": str(rng.choice([50000000, 1250000]))}
            if rng.random() < 0.3:
                campaign["maximizeConversionValue"] = {"targetRoas": rng.choice([2.5, 4.0])}
            metrics = {"costMicros": str(rng.choice([0, 3500000000, 1250001])), "impressions": str(rng.choice([0, 9000])),
                       "clicks": str(rng.choice([0, 120])), "conversions": rng.choice([0, 3.0, 17.5]),
                       "conversionsValue": rng.choice([0, 90000.0]),
                       "searchBudgetLostImpressionShare": rng.choice([None, 0.25, "0.1", "n/a"])}
            entry = {"campaign": campaign, "metrics": metrics}
            if rng.random() < 0.6:
                entry["campaignBudget"] = {"amountMicros": str(rng.choice([1000000000, 5000000])),
                                           "period": rng.choice(["DAILY", None, "CUSTOM_PERIOD"])}
            results.append(entry)
        pages = [{"results": results}]
        acc = {"external_id": "123-456-7890", "currency": "VND", "platform": "google", "token_ciphertext": "x"}
        try:
            expected = asyncio.run(optimizations.google_campaigns(acc, FakeClient(google_pages=pages)))
        except Exception as exc:  # noqa: BLE001
            expected = error_text(exc)
        cases.append({"kind": "google_campaigns", "input": {"pages": pages}, "expected": as_json(expected)})

    for n in range(30):
        ids = [str(70000 + n * 10 + i) for i in range(rng.randint(0, 6))]
        entries = [{"id": cid, "name": rng.choice(["Prospecting", None]), "status": "ACTIVE",
                    "effective_status": rng.choice(["ACTIVE", None]),
                    "bid_strategy": rng.choice([None, "LOWEST_COST_WITH_BID_CAP"]),
                    "daily_budget": rng.choice([None, "500000", "", "abc"]),
                    "lifetime_budget": rng.choice([None, "12000000"])} for cid in ids]
        chosen = rng.choice([None, "purchase", "lead", "offsite_conversion.fb_pixel_purchase"])
        insights = []
        for cid in ids:
            if rng.random() < 0.15:
                continue
            row = {"campaign_id": cid, "spend": rng.choice(["0", "1500000.5", "99.99"]),
                   "clicks": rng.choice(["0", "250"]), "impressions": rng.choice(["0", "30000"]),
                   "frequency": rng.choice([None, "4.2", "", "0", "7"]), "reach": rng.choice([None, "15000", "0"])}
            if chosen:
                row["account_currency"] = rng.choice(["VND", "VND", "USD"])
                row["actions"] = rng.choice([[{"action_type": chosen, "7d_click": "12"}],
                                             [{"action_type": chosen, "value": "3"}],
                                             [{"action_type": chosen, "value": "3"}, {"action_type": chosen, "value": "4"}],
                                             []])
                row["action_values"] = [{"action_type": chosen, "7d_click": rng.choice(["900000", "0"])}]
            insights.append(row)
        adsets = [{"id": f"9{i}", "campaign_id": rng.choice(ids or ["70000"]), "bid_amount": rng.choice([None, "150000", 2500, "x"])}
                  for i in range(rng.randint(0, 6))]
        goal = {"enabled": True, "meta_action_type": chosen} if chosen else None
        goals.goal_for = lambda org, account_id, g=goal: g
        acc = {"external_id": "act_99887766", "currency": "VND", "platform": "meta", "token_ciphertext": "x",
               "org_id": 1, "id": 1}
        try:
            expected = asyncio.run(optimizations.meta_campaigns(
                acc, FakeClient(meta={"campaigns": entries, "insights": insights, "adsets": adsets})))
        except Exception as exc:  # noqa: BLE001
            expected = error_text(exc)
        cases.append({"kind": "meta_campaigns", "input": {"entries": entries, "insights": insights, "adsets": adsets,
                                                          "chosenAction": chosen, "currency": "VND"},
                      "expected": as_json(expected)})
    return cases


def build() -> dict:
    rng = random.Random(20261025)
    cases = []
    cases += date_cases()
    cases += report_cases(rng)
    cases += google_report_cases(rng)
    cases += meta_report_cases(rng)
    cases += campaign_cases(rng)
    cases += baseline_and_outcome_cases(rng)
    cases += playbook_cases(rng, 260)
    return {"generated_by": "tools/gen_core_fixtures.py", "cases": cases}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    import os
    os.environ.setdefault("MASTER_KEY", "Zml4dHVyZS1vbmx5LW5vdC1hLXJlYWwta2V5LTMyYg==")
    os.environ.setdefault("SESSION_SECRET", "fixture-only")
    data = json.dumps(build(), ensure_ascii=False, indent=0, sort_keys=True) + "\n"
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != data:
            raise SystemExit("tests/fixtures/core/parity.json is stale: run python tools/gen_core_fixtures.py")
        print("core parity fixtures are up to date")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(data, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(json.loads(data)['cases'])} cases)")


if __name__ == "__main__":
    main()
