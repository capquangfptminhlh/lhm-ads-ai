"""Validate the public Admin UI uses CSP-compliant external JS only."""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/"static/admin.html").read_text(encoding="utf-8")
js=ROOT/"static/admin.js"
if "<script>" in html or "<script " not in html:
    raise SystemExit("Admin inline scripting is blocked by CSP")
if '<script src="/static/admin.js" defer></script>' not in html:
    raise SystemExit("Admin external JavaScript not loaded")
if '<link rel="stylesheet" href="/static/admin-refresh.css">' not in html:
    raise SystemExit("Admin design stylesheet missing")
if not js.is_file():
    raise SystemExit("Admin script file missing")
script=js.read_text(encoding="utf-8")
if "/api/admin/" not in script:
    raise SystemExit("Admin UI does not call the control-plane backend")
subprocess.run(["node","--check",str(js)],check=True)
print("Admin CSP-safe JavaScript PASS")
