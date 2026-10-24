"""Parse browser-side script embedded in the Admin page using the Node parser."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / "static" / "admin.html").read_text(encoding="utf-8")
start = html.find("<script>")
end = html.find("</script>", start)
if start < 0 or end < 0 or html.find("<script>", end + 9) != -1:
    raise SystemExit("Expected one inline Admin script")
script = html[start + len("<script>"):end]
if "/api/admin/" not in script:
    raise SystemExit("Admin UI is not connected to its backend")
with tempfile.TemporaryDirectory() as temp:
    js = Path(temp) / "admin-inline.js"
    js.write_text(script, encoding="utf-8")
    subprocess.run(["node", "--check", str(js)], check=True)
print("Admin inline JavaScript syntax PASS")
