"""Parse browser-side scripts embedded in the Admin page with real Node parser."""
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / "static" / "admin.html").read_text(encoding="utf-8")
scripts = re.findall(r"<script(?:\\s[^>]*)?>([\\s\\S]*?)</script>", html, flags=re.I)
if len(scripts) != 1:
    raise SystemExit(f"Expected exactly 1 inline admin script, got {len(scripts)}")
if "api/admin/" not in scripts[0] and "'/api/admin/'" not in scripts[0]:
    raise SystemExit("Admin is not using the backend API")
with tempfile.TemporaryDirectory() as temp:
    js = Path(temp) / "admin-inline.js"
    js.write_text(scripts[0], encoding="utf-8")
    subprocess.run(["node", "--check", str(js)], check=True)
print("Admin inline JavaScript syntax PASS")
