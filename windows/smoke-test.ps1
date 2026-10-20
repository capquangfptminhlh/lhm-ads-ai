$ErrorActionPreference = 'Stop'
$exe = Join-Path $PWD 'dist\LHM-Ads-AI.exe'
if (-not (Test-Path $exe)) { throw "EXE missing: $exe" }
$env:LHM_DATA_DIR = Join-Path $env:RUNNER_TEMP 'lhm-ads-ai-onboarding-smoke'
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
    Write-Host 'PASS: actual windowed EXE responds'
    $setup = Invoke-WebRequest -Uri "http://127.0.0.1:$port/setup" -TimeoutSec 10
    if ($setup.StatusCode -ne 200 -or $setup.Content -notmatch 'Tạo tài khoản quản trị') { throw 'Onboarding page missing' }
    Write-Host 'PASS: first-run onboarding page returned 200'
    foreach ($path in @('/static/setup.css','/static/setup.js','/static/reference-theme.css')) {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port$path" -TimeoutSec 10
        if ($r.StatusCode -ne 200 -or $r.Content.Length -lt 150) { throw "Missing asset: $path" }
    }
    $bad = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/desktop/first-run" -Method POST -ContentType 'application/json' -Body '{"email":"x@example.com","password":"long_password_123","token":"invalid_invalid_invalid_invalid_invalid"}' -SkipHttpErrorCheck -TimeoutSec 10
    if ($bad.StatusCode -ne 403) { throw "Invalid setup token unexpectedly accepted" }
    Write-Host 'PASS: setup requires one-time token'
    $studio = Invoke-WebRequest -Uri "http://127.0.0.1:$port/studio" -TimeoutSec 10
    if ($studio.StatusCode -ne 200 -or $studio.Content -notmatch 'LHM ADS AI') { throw 'Studio HTML mismatch' }
    foreach ($path in @('/api/accounts', '/api/summary')) {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port$path" -SkipHttpErrorCheck -TimeoutSec 10
        if ($r.StatusCode -ne 401) { throw "Auth bypass: $path returned $($r.StatusCode)" }
    }
    foreach ($path in @('/mcp','/api/mcp','/automation')) {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port$path" -SkipHttpErrorCheck -TimeoutSec 10
        if ($r.StatusCode -ne 404) { throw "Unexpected MCP route: $path" }
    }
    Write-Host 'PASS: Ads endpoints protected, MCP disabled'
} finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    $log = Join-Path $env:LHM_DATA_DIR 'logs\startup.log'
    if (Test-Path $log) { Get-Content $log -Tail 30 }
}
