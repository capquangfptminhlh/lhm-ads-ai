"""The commercial legal gate is intentionally separate from pilot CI."""
from pathlib import Path

from tools.check_commercial_legal import check_legal_pages, main


def _pages(root: Path, *, text: str) -> None:
    for name in ("legal-privacy.html", "legal-terms.html"):
        page = root / "static" / name
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("<html><main><h1>Thông tin pháp lý</h1><p>" +
                        text + "</p></main></html>", encoding="utf-8")


def test_commercial_legal_gate_rejects_drafts_and_missing_pages(tmp_path):
    assert any("missing required legal page" in issue for issue in check_legal_pages(tmp_path))
    assert main(["--root", str(tmp_path)]) == 1
    _pages(tmp_path, text="BẢN NHÁP [CẦN ĐIỀN thông tin bên cung cấp] " + "nội dung " * 80)
    errors = check_legal_pages(tmp_path)
    assert len(errors) == 4
    assert main(["--root", str(tmp_path)]) == 1


def test_commercial_legal_gate_rejects_empty_and_todo(tmp_path):
    _pages(tmp_path, text="Một đoạn ngắn")
    assert any("incomplete" in problem for problem in check_legal_pages(tmp_path))
    _pages(tmp_path, text="Bên cung cấp sẽ xác nhận TODO. " * 25)
    assert any("unresolved draft marker" in problem for problem in check_legal_pages(tmp_path))


def test_commercial_legal_gate_accepts_populated_pages_but_not_legal_approval(tmp_path, capsys):
    _pages(tmp_path, text="Thông tin đầy đủ đã được bên bán rà soát. " * 25)
    assert check_legal_pages(tmp_path) == []
    assert main(["--root", str(tmp_path)]) == 0
    assert "manual owner/legal approval" in capsys.readouterr().out

def test_real_legal_templates_use_individual_provider():
    root = Path(__file__).resolve().parents[1]
    for name in ("static/legal-terms.html", "static/legal-privacy.html"):
        page = (root / name).read_text(encoding="utf-8")
        assert "<strong>cá nhân</strong>" in page
        assert "Đơn vị cung cấp:" not in page
        # Actual contact/registration details are intentionally not invented.
        # Commercial builds must still fail closed until the owner reviews copy.
