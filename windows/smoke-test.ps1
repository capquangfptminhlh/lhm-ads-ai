$ErrorActionPreference = 'Stop'
$exe = Join-Path $PWD 'dist\LHM-Ads-AI.exe'
if (-not (Test-Path $exe)) { throw "EXE missing: $exe" }
$env:LHM_DATA_DIR = Join-Path $env:RUNNER_TEMP 'lhm-ads-ai-onboarding-smoke'
# The commercial preparation step replaces this file's edition markers BEFORE building.
# Detect the actual compiled edition from checked-in build inputs, not an untrusted EXE claim.
$releaseInfo = Get-Content 'ads_core/release_info.py' -Raw
$gmailOnly = $releaseInfo -match "CLOUD_LICENSE_MODE = 'required'"
if ($gmailOnly) { Write-Host 'Smoke mode: COMMERCIAL Google-only (no local password setup)' }
else { Write-Host 'Smoke mode: PILOT legacy first-run onboarding' }
$port = 18765
$proc = Start-Process -FilePath $exe -ArgumentList @('--headless', '--port', "$port") -PassThru
try {
    $healthy = $false
    for ($i=0; $i -lt 90; $i++) {
        if ($proc.HasExited) { throw "EXE exited early with code $($proc.ExitCode)" }
        Start-Sleep -Seconds 2
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/healthz" -TimeoutSec 2
            if ($health.ok -eq $true) { $healthy=$true; break }
        } catch { }
    }
    if (-not $healthy) { throw 'EXE failed the HTTP health check' }
    Write-Host 'PASS: packaged Windows EXE responds in headless mode'
    $setup = Invoke-WebRequest -Uri "http://127.0.0.1:$port/setup" -TimeoutSec 10
    if ($gmailOnly) {
        # /setup must redirect to /studio in Google-only mode; the old password
        # signup screen must never be offered to a commercial customer.
        if ($setup.StatusCode -ne 200 -or $setup.Content -notmatch 'LHM ADS AI' -or
            $setup.Content -match 'Tạo tài khoản quản trị') {
            throw 'Gmail-only commercial EXE exposed legacy password onboarding'
        }
        Write-Host 'PASS: commercial /setup redirects to Studio; no password onboarding'
    } else {
        if ($setup.StatusCode -ne 200 -or $setup.Content -notmatch 'Tạo tài khoản quản trị') { throw 'Onboarding page missing' }
        Write-Host 'PASS: pilot first-run onboarding page returned 200'
        if ($setup.Content -notmatch 'setup-dark.css' -or $setup.Content -notmatch 'Dashboard đen') { throw 'First-run screen does not match dark Studio theme' }
    }
    foreach ($path in @('/static/setup.css','/static/setup-dark.css','/static/setup.js','/static/finpoint-theme.css','/static/reference-theme.css','/static/provider-studio.css','/static/provider-studio.js')) {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port$path" -TimeoutSec 10
        if ($r.StatusCode -ne 200 -or $r.Content.Length -lt 150) { throw "Missing asset: $path" }
    }
    $bad = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/desktop/first-run" -Method POST -ContentType 'application/json' -Body '{"email":"x@example.com","password":"long_password_123","token":"invalid_invalid_invalid_invalid_invalid"}' -SkipHttpErrorCheck -TimeoutSec 10
    if ($bad.StatusCode -ne 403) { throw "Invalid setup token unexpectedly accepted" }
    Write-Host 'PASS: setup requires one-time token'
    $studio = Invoke-WebRequest -Uri "http://127.0.0.1:$port/studio" -TimeoutSec 10
    if ($studio.StatusCode -ne 200 -or $studio.Content -notmatch 'LHM ADS AI') { throw 'Studio HTML mismatch' }
    if ($studio.Content -notmatch 'data-provider-choice="google"' -or $studio.Content -notmatch 'data-provider-choice="meta"') { throw 'Separate Google/Meta wizard missing' }
    foreach ($path in @('/api/accounts', '/api/summary', '/api/desktop/readiness')) {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port$path" -SkipHttpErrorCheck -TimeoutSec 10
        $expected = if ($gmailOnly) { 402 } else { 401 }
        if ($r.StatusCode -ne $expected) { throw "Auth gate: $path returned $($r.StatusCode), expected $expected" }
    }
    foreach ($path in @('/mcp','/api/mcp','/automation')) {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port$path" -SkipHttpErrorCheck -TimeoutSec 10
        if ($r.StatusCode -ne 404) { throw "Unexpected MCP route: $path" }
    }
    $backup = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/desktop/backup/export" -Method POST -ContentType 'application/json' -Body '{"passphrase":"good-backup-passphrase-12345"}' -SkipHttpErrorCheck -TimeoutSec 10
    $expected = if ($gmailOnly) { 402 } else { 401 }
    if ($backup.StatusCode -ne $expected) { throw "Backup auth/license gate: expected $expected, got $($backup.StatusCode)" }
    Write-Host 'PASS: desktop backup and diagnostic endpoints require authentication / active Gmail plan'
    Write-Host 'PASS: Ads endpoints protected, MCP disabled'
} finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    $log = Join-Path $env:LHM_DATA_DIR 'logs\startup.log'
    if (Test-Path $log) { Get-Content $log -Tail 30 }
}
