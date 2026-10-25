"""Fail closed before building a paid commercial Windows candidate.

The owner must replace all draft legal copy with reviewed, accurate terms and
privacy information. This is a mechanical publication gate, NOT legal advice
or evidence of compliance. The pilot/dev CI must remain unaffected.
"""
from __future__ import annotations

import argparse
from html import unescape
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LEGAL_PAGES = ("static/legal-terms.html", "static/legal-privacy.html")
DRAFT_MARKERS = (
    re.compile(r"\[\s*CẦN\s+ĐIỀN\b", re.IGNORECASE),
    re.compile(r"\bBẢN\s+NHÁP\b", re.IGNORECASE),
    re.compile(r"\b(?:TODO|TBD)\b", re.IGNORECASE),
)


def check_legal_pages(root: Path = ROOT) -> list[str]:
    """Return issues; do not fill in seller identity or legal policy by guessing."""
    problems: list[str] = []
    for relative in LEGAL_PAGES:
        path = Path(root) / relative
        if not path.is_file():
            problems.append(f"{relative}: missing required legal page")
            continue
        text = unescape(path.read_text(encoding="utf-8"))
        if len(text.strip()) < 400 or "<main" not in text or "</main>" not in text:
            problems.append(f"{relative}: missing or incomplete legal content")
        for marker in DRAFT_MARKERS:
            if marker.search(text):
                problems.append(f"{relative}: unresolved draft marker ({marker.pattern})")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check commercial legal pages before paid build")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    problems = check_legal_pages(args.root)
    if problems:
        for issue in problems:
            print("FAIL: " + issue)
        print("BLOCKED: owner must complete and review both legal pages before a commercial build.")
        return 1
    print("PASS: no obvious draft placeholders in required legal pages.")
    print("NOTE: manual owner/legal approval is STILL required before any sale.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
