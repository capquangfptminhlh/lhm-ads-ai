$ErrorActionPreference = 'Stop'
$exe = Join-Path $PWD 'dist\LHM-Ads-AI.exe'
if (-not (Test-Path $exe)) { throw "EXE missing: $exe" }
$env:LHM_DATA_DIR = Join-Path $env:RUNNER_TEMP 'lhm-ads-ai-smoke-test'
$port = 18765
$proc = Start-Process -FilePath $exe -ArgumentList @('--headless', '--port', "$port") -PassThru -RedirectStandardOutput (Join-Path $env:RUNNER_TEMP 'lhm-stdout.log') -RedirectStandardError (Join-Path $env:RUNNER_TEMP 'lhm-stderr.log')
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
    Write-Host 'PASS: actual Windows EXE responds /healthz'

    $studio = Invoke-WebRequest -Uri "http://127.0.0.1:$port/studio" -TimeoutSec 10
    if ($studio.StatusCode -ne 200 -or $studio.Content -notmatch 'LHM ADS AI') { throw 'Studio HTML mismatch' }
    Write-Host 'PASS: real Studio dashboard returned 200'

    $theme = Invoke-WebRequest -Uri "http://127.0.0.1:$port/static/reference-theme.css" -TimeoutSec 10
    if ($theme.StatusCode -ne 200 -or $theme.Content.Length -lt 100) { throw 'CSS not bundled' }
    Write-Host 'PASS: desktop visual theme bundled into EXE'

    foreach ($path in @('/api/accounts', '/api/summary')) {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port$path" -SkipHttpErrorCheck -TimeoutSec 10
        if ($r.StatusCode -ne 401) { throw "Auth bypass: $path returned $($r.StatusCode)" }
    }
    Write-Host 'PASS: advertising API requires user session'

    foreach ($path in @('/mcp', '/api/mcp', '/automation')) {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port$path" -SkipHttpErrorCheck -TimeoutSec 10
        if ($r.StatusCode -ne 404) { throw "Unexpected external-access route $path = $($r.StatusCode)" }
    }
    Write-Host 'PASS: retired MCP/automation routes are not available'
} finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    Get-Content (Join-Path $env:RUNNER_TEMP 'lhm-stdout.log') -ErrorAction SilentlyContinue
    Get-Content (Join-Path $env:RUNNER_TEMP 'lhm-stderr.log') -ErrorAction SilentlyContinue
}
