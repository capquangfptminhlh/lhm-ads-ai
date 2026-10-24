"""Build static, fail-closed LHM Ads AI PWA assets for Cloudflare Workers.

NO Python backend, OAuth token or secret is copied. The hosted Studio login stays
disabled until a real, server-side Cloudflare API explicitly reports readiness.
The intended custom-domain origin is https://ads.lhm.com (no project path).
"""
from __future__ import annotations

import argparse
import html
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
    for name in ("manifest.webmanifest", "sw.js"):
        shutil.copy2(STATIC / name, output / name)
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
        '<meta http-equiv="refresh" content="0;url=/studio/">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>LHM Ads AI</title></head><body>'
        '<p><a href="/studio/">Mở LHM Ads AI</a></p></body></html>',
        encoding="utf-8"
    )
    # Cloudflare Workers Static Assets: apply a strict same-origin execution policy.
    # The temporary hosted PWA never needs third-party script or API origins.
    (output / "_headers").write_text(
        "/*\\n"
        "  X-Content-Type-Options: nosniff\\n"
        "  Referrer-Policy: no-referrer\\n"
        "  X-Frame-Options: DENY\\n"
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()\\n"
        "  Content-Security-Policy: default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "font-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'; "
        "upgrade-insecure-requests\\n",
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
