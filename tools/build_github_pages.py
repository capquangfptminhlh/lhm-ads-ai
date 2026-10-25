"""Build static, fail-closed LHM Ads AI PWA assets for Cloudflare Workers.

NO Python backend, OAuth token or secret is copied. The hosted Studio login stays
disabled until a real, server-side Cloudflare API explicitly reports readiness.
The intended custom-domain origin is https://ads.lhmcrm.com (no project path).
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def build(output: Path) -> Path:
    output = output.resolve()
    if output == ROOT or output == STATIC:
        raise ValueError("Refusing to overwrite source tree")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(STATIC, output / "static", ignore=shutil.ignore_patterns("*.pyc", "__pycache__"))
    # Build-specific service worker is allowed to cache ONLY a generic local
    # workspace page and its public source assets; NEVER authenticated routes.
    manifest=json.loads((STATIC / "manifest.webmanifest").read_text(encoding="utf-8"))
    manifest["start_url"]="/local/"
    manifest["id"]="/local/"
    (output / "manifest.webmanifest").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    sw=(STATIC / "sw.js").read_text(encoding="utf-8")
    assert "const SHELL = [" in sw and "if (req.mode === 'navigate')" in sw
    pre_cache=[
        "/local/","/static/device-vault.js","/static/device-vault-ui.js",
        "/static/device-insights.js","/static/device-mcp.js","/static/device-vault.css",
        "/static/device-insights.css","/static/device-local.css","/static/soft-motion-ui.css",
        "/static/device-studio.css","/static/device-studio.js",
        "/static/license-check.js","/static/customer-login.js","/static/customer-login.css","/static/fonts.css",
        "/static/marketing.css","/static/marketing-refresh.css",
        "/static/pwa-refresh.css"
    ]
    sw=sw.replace("const SHELL = [","const SHELL = [\n"+
      "".join(f"  '{name}',\n" for name in pre_cache),1)
    sw=sw.replace("lhm-pwa-v1-20261023","lhm-pwa-cloudflare-v11-20261025",1)
    sw=sw.replace("if (req.mode === 'navigate') {",
      "if (req.mode === 'navigate') {\n"+
      "    if (url.pathname === '/local/' || url.pathname === '/local') {\n"+
      "      event.respondWith(fetch(req).catch(async () => (await caches.match('/local/')) || Response.error()));\n"+
      "      return;\n"+
      "    }",1)
    (output / "sw.js").write_text(sw,encoding="utf-8")
    # Reuse one first-party Studio-like PWA shell, with no Python/backend links.
    local_html = (STATIC / "device-studio.html").read_text(encoding="utf-8")
    assert 'id="lhm-local-workspace"' in local_html
    assert 'device-studio.js' in local_html and 'device-vault.js' in local_html
    local=output / "local"
    local.mkdir()
    (local / "index.html").write_text(local_html,encoding="utf-8")
    studio = (STATIC / "studio.html").read_text(encoding="utf-8")
    assert '<form id="login-form">' in studio and '</body>' in studio
    # Unlike the FastAPI-hosted Studio, this static bundle cannot authenticate anyone.
    # Hide the form before first paint and gate it behind a working backend.
    style = (
        '<style id="lhm-static-api-guard">'
        '#login-form{display:none!important}'
        '</style>'
    )
    banner = (
        '<div id="lhm-hosted-status" role="status" aria-live="polite"'
        ' style="padding:12px 14px;border:1px solid #ca884f;'
        'border-radius:12px;margin:14px 0;color:#ffe6c7;'
        'font-size:13px;line-height:1.5">'
        'Bản PWA đang được triển khai qua Cloudflare. '
        'Đăng nhập và kết nối Ads sẽ chỉ mở khi Cloudflare API đã được kiểm thử.'
        '</div>'
    )
    studio = studio.replace('</head>', '<link rel="stylesheet" href="/static/device-vault.css">' +
                              '<link rel="stylesheet" href="/static/device-insights.css">' + style + '</head>', 1)
    studio = studio.replace('<form id="login-form">', banner + '<form id="login-form">', 1)
    studio = studio.replace(
        '</body>', ('<script src="/static/cloudflare-hosting-gate.js" defer></script>'
                   '<script src="/static/device-vault.js" defer></script>'
                   '<script src="/static/device-vault-ui.js" defer></script>'
                   '<script src="/static/device-insights.js" defer></script>'
                   '<script src="/static/device-mcp.js" defer></script></body>'), 1
    )
    page = output / "studio"
    page.mkdir()
    (page / "index.html").write_text(studio, encoding="utf-8")
    # Cloudflare Access-protected admin page; API independently verifies signed Access JWT.
    admin = output / "admin"
    admin.mkdir()
    (admin / "index.html").write_text((STATIC / "admin.html").read_text(encoding="utf-8"), encoding="utf-8")
    # Public landing page at /; entry to the cryptographically locked PWA at /local/.
    # No OAuth/login server is implied or deployed by this static marketing page.
    marketing=(STATIC / "marketing.html").read_text(encoding="utf-8")
    assert '<a class="mk-btn mk-btn-primary" href="/local/">' in marketing
    assert 'id="bang-gia"' in marketing and '499.000đ' in marketing
    assert '<link rel="stylesheet" href="/static/marketing.css">' in marketing
    (output / "index.html").write_text(marketing,encoding="utf-8")
    # Cloudflare Workers Static Assets: apply a strict same-origin execution policy.
    # The temporary hosted PWA never needs third-party script or API origins.
    (output / "_headers").write_text(
        "/*\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: no-referrer\n"
        "  X-Frame-Options: DENY\n"
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
        "  Content-Security-Policy: default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: https://img.vietqr.io https://*.googleusercontent.com; "
        "font-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'; "
        "upgrade-insecure-requests\n",
        encoding="utf-8"
    )
    return output


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="_site", type=Path)
    args = p.parse_args()
    print("Built Cloudflare static PWA at:", build(args.output))


if __name__ == "__main__":
    main()
