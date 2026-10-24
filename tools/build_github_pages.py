"""Build static, fail-closed LHM Ads AI PWA assets for Cloudflare Workers.

NO Python backend, OAuth token or secret is copied. The hosted Studio login stays
disabled until a real, server-side Cloudflare API explicitly reports readiness.
The intended custom-domain origin is https://ads.lhm.com (no project path).
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
        "/static/device-insights.css","/static/device-local.css"
    ]
    sw=sw.replace("const SHELL = [","const SHELL = [\n"+
      "".join(f"  '{name}',\n" for name in pre_cache),1)
    sw=sw.replace("lhm-pwa-v1-20261023","lhm-local-vault-v3-20261024",1)
    sw=sw.replace("if (req.mode === 'navigate') {",
      "if (req.mode === 'navigate') {\n"+
      "    if (url.pathname === '/local/' || url.pathname === '/local') {\n"+
      "      event.respondWith(fetch(req).catch(async () => (await caches.match('/local/')) || Response.error()));\n"+
      "      return;\n"+
      "    }",1)
    (output / "sw.js").write_text(sw,encoding="utf-8")
    local_html = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d1117">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/static/icons/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="LHM Ads AI">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="stylesheet" href="/static/device-local.css">
<link rel="stylesheet" href="/static/device-vault.css">
<link rel="stylesheet" href="/static/device-insights.css">
<title>LHM Ads AI — Không gian cục bộ</title></head>
<body id="lhm-local-workspace">
<header class="local-header"><div class="local-inner">
  <div><div class="brand">✦ LHM <span>ADS AI</span></div>
    <small>Không gian quảng cáo cục bộ trên thiết bị</small></div>
  <div class="local-actions"><span class="local-safe">🔒 Dữ liệu lưu trên thiết bị</span>
    <button id="pwa-install-button" class="pwa-install-button" type="button">Cài ứng dụng</button>
    <a class="local-link" href="/studio/">Bản Studio (cần backend)</a>
  </div></div></header>
<main class="local-main">
  <h1>Quản lý dữ liệu Ads ngay trên thiết bị</h1>
  <p>Tự lưu tài khoản, nhập báo cáo CSV, xem xu hướng và cảnh báo ngân sách.
    Không cần máy chủ lưu tài khoản Ads. Các chỉ số CSV không phải dữ liệu quảng cáo trực tiếp.</p>
  <section id="login"><div class="login-box"></div></section>
</main>
<dialog id="pwa-install-guide" class="pwa-install-guide" aria-labelledby="pwa-install-guide-title">
 <h2 id="pwa-install-guide-title">Cài LHM Ads AI</h2>
 <p id="pwa-install-guide-message">Android: mở Chrome → menu → Cài ứng dụng.
 iPhone: Safari → Chia sẻ → Thêm vào Màn hình chính.</p>
 <button id="pwa-install-guide-close" type="button">Đóng</button>
</dialog>
<script src="/static/pwa-install.js" defer></script>
<script src="/static/device-vault.js" defer></script>
<script src="/static/device-vault-ui.js" defer></script>
<script src="/static/device-insights.js" defer></script>
<script src="/static/device-mcp.js" defer></script>
</body></html>"""
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
    (output / "index.html").write_text(
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=/local/">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>LHM Ads AI</title></head><body>'
        '<p><a href="/local/">Mở LHM Ads AI</a></p></body></html>',
        encoding="utf-8"
    )
    # Cloudflare Workers Static Assets: apply a strict same-origin execution policy.
    # The temporary hosted PWA never needs third-party script or API origins.
    (output / "_headers").write_text(
        "/*\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: no-referrer\n"
        "  X-Frame-Options: DENY\n"
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
        "  Content-Security-Policy: default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
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
