"""Nuitka builds are audited from the compilation report (modules compiled to C)."""
import pytest

from tools.check_customer_bundle import BundleAuditError, verify_nuitka_report


def report(tmp_path, names):
    body = "".join(f'<module name="{n}" kind="CompiledPythonModule"/>' for n in names)
    path = tmp_path / "report.xml"
    path.write_text(f'<?xml version="1.0"?><nuitka-compilation-report>{body}</nuitka-compilation-report>', encoding="utf-8")
    return path


def test_clean_customer_build_passes(tmp_path):
    assert verify_nuitka_report(report(tmp_path, ["windows.desktop_window", "ads_core.licensing", "uvicorn"]))["safe"]


def test_seller_only_code_is_refused(tmp_path):
    with pytest.raises(BundleAuditError, match="vendor_ledger"):
        verify_nuitka_report(report(tmp_path, ["windows.desktop_window", "ads_core.licensing", "tools.vendor_ledger"]))


def test_missing_desktop_window_is_refused(tmp_path):
    with pytest.raises(BundleAuditError, match="desktop_window"):
        verify_nuitka_report(report(tmp_path, ["ads_core.licensing"]))
