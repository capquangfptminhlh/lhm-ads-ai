"""Local desktop Internet reachability signal.

Fixed HTTPS probes only; no auth headers, account metadata, provider tokens or
user-provided URLs leave the machine. No inbound remote listener or MCP.
"""
import time
import httpx
from fastapi import Depends
from .app import app, require

PROBES = (
    ('https://www.google.com/generate_204', 204),
    ('https://www.cloudflare.com/cdn-cgi/trace', 200),
)
CACHE_SECONDS = 30
CACHE = {'checked_at': -float('inf'), 'online': False}


async def probe_internet():
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(3.0, connect=2.0),
        trust_env=True,
        follow_redirects=False,
    ) as client:
        for url, expected in PROBES:
            try:
                response = await client.head(url)
                if response.status_code == expected:
                    return True
            except httpx.HTTPError:
                continue
    return False


@app.get('/api/network/status')
async def network_status(ident=Depends(require('admin', 'operator', 'reader'))):
    del ident
    now = time.monotonic()
    if now - CACHE['checked_at'] >= CACHE_SECONDS:
        try:
            CACHE['online'] = await probe_internet()
        except (httpx.HTTPError, OSError):
            CACHE['online'] = False
        CACHE['checked_at'] = time.monotonic()
    return {'online': bool(CACHE['online']), 'method': 'fixed_https_probes'}
