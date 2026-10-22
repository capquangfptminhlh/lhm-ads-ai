#requires -Version 5.1
<#
On the VENDOR'S Windows PC only. Creates encrypted Ed25519 license issuer
key locally, uploads PUBLIC key only, launches Commercial Candidate CI.
Requires Python+cryptography and authenticated GitHub CLI.
#>
[CmdletBinding()]
param(
  [ValidateSet('setup','build','setup-and-build','status')]
  [string]$Action='setup-and-build',
  [ValidatePattern('^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$')]
  [string]$Repo='capquangfptminhlh/lhm-ads-ai'
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $env:LOCALAPPDATA) { throw 'Requires local Windows profile LOCALAPPDATA' }
$homeDir=Join-Path $env:LOCALAPPDATA 'LHMAdsAI-Vendor'
$keyDir=Join-Path $homeDir 'keys'
$private=Join-Path $keyDir 'vendor-private-key.pem'
$public=Join-Path $keyDir 'vendor-public.b64'

function Assert-Exit([string]$step) {
  if ($LASTEXITCODE -ne 0) { throw "$step failed (exit $LASTEXITCODE)" }
}
function Python-Ready {
  if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Official Python 3.12+ is required on this Windows PC.'
  }
  & python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey"
  Assert-Exit 'Python cryptography dependency'
}
function Ensure-Keys {
  param([switch]$CreateIfMissing)
  $hasPrivate=Test-Path -LiteralPath $private -PathType Leaf
  $hasPublic=Test-Path -LiteralPath $public -PathType Leaf
  if ($hasPrivate -xor $hasPublic) {
    throw "Incomplete vendor key pair in $keyDir. NEVER silently regenerate keys."
  }
  if (-not $hasPrivate) {
    if (-not $CreateIfMissing) {
      throw 'Local vendor key does not exist. Run -Action setup ON THE ORIGINAL seller PC; never silently rotate keys.'
    }
    New-Item -ItemType Directory -Path $keyDir -Force | Out-Null
    Write-Host "Creating encrypted vendor signing key ONLY on this PC in: $keyDir"
    & python (Join-Path $root 'tools/license_issuer.py') keygen --private $private --public $public
    Assert-Exit 'Vendor key generation'
  } else {
    Write-Host 'Reusing your existing private issuer key; no key rotation.'
  }
  $pemFirst=(Get-Content -LiteralPath $private -TotalCount 1 -Encoding Ascii)
  if ($pemFirst -ne '-----BEGIN ENCRYPTED PRIVATE KEY-----') {
    throw 'Vendor private issuer key is not password-encrypted. Aborting.'
  }
  $bytes=[Convert]::FromBase64String((Get-Content -LiteralPath $public -Raw -Encoding Ascii).Trim())
  if ($bytes.Length -ne 32) { throw 'Invalid vendor public Ed25519 key' }
  $sha=[System.Security.Cryptography.SHA256]::Create()
  try { $fingerprint=([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant() }
  finally { $sha.Dispose() }
  Write-Host "Vendor PUBLIC fingerprint: $fingerprint"
  Write-Host 'Keep encrypted private PEM and its password OFFLINE; NEVER send them to GitHub/ChatGPT.'
}
function GitHub-Ready {
  if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'Official GitHub CLI missing: https://cli.github.com/'
  }
  & gh auth status --hostname github.com *> $null
  if ($LASTEXITCODE -ne 0) {
    Write-Host 'GitHub requires your approval. Sign in through the browser.'
    & gh auth login --hostname github.com --web
    Assert-Exit 'GitHub login'
  }
  & gh repo view $Repo --json nameWithOwner --jq '.nameWithOwner'
  Assert-Exit 'GitHub repo access'
}
function Setup-Vendor {
  Python-Ready
  Ensure-Keys -CreateIfMissing
  GitHub-Ready
  $publicText=(Get-Content -LiteralPath $public -Raw -Encoding Ascii).Trim()
  # PUBLIC ONLY: no vendor private key or passphrase is ever uploaded.
  & gh secret set LHM_COMMERCIAL_PUBLIC_KEY_B64 --repo $Repo --body $publicText
  Assert-Exit 'Saving PUBLIC repo secret'
  Write-Host 'PASS: Only vendor PUBLIC key was installed into GitHub Actions.'
}
function Build-Commercial {
  Python-Ready
  Ensure-Keys
  GitHub-Ready
  $priorRuns=@(& gh run list --repo $Repo --workflow windows-exe.yml --event workflow_dispatch --limit 30 --json databaseId | ConvertFrom-Json)
  Assert-Exit 'List previous workflow runs'
  $prior=@{}
  foreach ($run in $priorRuns) { $prior[[string]$run.databaseId]=$true }
  Write-Host 'Starting commercial=true Windows build with your PUBLIC license key...'
  & gh workflow run windows-exe.yml --repo $Repo --ref main --field commercial=true
  Assert-Exit 'Commercial Candidate workflow dispatch'
  $current=$null
  for ($i=0;$i -lt 24;$i++) {
    Start-Sleep -Seconds 5
    $runs=@(& gh run list --repo $Repo --workflow windows-exe.yml --event workflow_dispatch --limit 30 --json databaseId,headBranch | ConvertFrom-Json)
    Assert-Exit 'Find commercial build run'
    $newRuns=@($runs | Where-Object { -not $prior.ContainsKey([string]$_.databaseId) -and $_.headBranch -eq 'main' })
    if ($newRuns.Count -eq 1) { $current=$newRuns[0]; break }
    if ($newRuns.Count -gt 1) {
      throw 'Multiple new manual build runs detected. Choose the correct run on GitHub; will not guess.'
    }
  }
  if ($null -eq $current) { throw 'Workflow dispatched but its run ID was not uniquely found. Check GitHub Actions.' }
  $runId=[string]$current.databaseId
  Write-Host "GitHub run: https://github.com/$Repo/actions/runs/$runId"
  & gh run watch $runId --repo $Repo --exit-status
  Assert-Exit 'Commercial Candidate Windows CI'
  $candidateDir=Join-Path $homeDir ('candidate-'+$runId)
  if (Test-Path -LiteralPath $candidateDir) { throw 'Refusing to overwrite candidate folder' }
  New-Item -ItemType Directory -Path $candidateDir | Out-Null
  & gh run download $runId --repo $Repo --name LHM-Ads-AI-COMMERCIAL-CANDIDATE-UNSIGNED --dir $candidateDir
  Assert-Exit 'Download Commercial Candidate'
  & python (Join-Path $root 'tools/release_gate.py') inspect-candidate --exe (Join-Path $candidateDir 'LHM-Ads-AI.exe') --checksum (Join-Path $candidateDir 'LHM-Ads-AI.sha256') --manifest (Join-Path $candidateDir 'release-manifest.json') --vendor-public $public
  Assert-Exit 'Verify unsigned candidate SHA256/commit/vendor public key'
  Write-Host "PASS: Verified unsigned COMMERCIAL Candidate at $candidateDir"
  Write-Host 'NOT YET APPROVED FOR SALE: finish real Google/Meta acceptance and owner sign-off first.'
}
if ($Action -eq 'setup' -or $Action -eq 'setup-and-build') { Setup-Vendor }
if ($Action -eq 'build' -or $Action -eq 'setup-and-build') { Build-Commercial }
if ($Action -eq 'status') {
  Python-Ready
  if ((Test-Path -LiteralPath $private) -and (Test-Path -LiteralPath $public)) {
    Ensure-Keys
  } else {
    Write-Host 'Vendor key pair not fully present. No new key will be created by status.'
  }
  Write-Host "Vendor keys: $keyDir"
  Write-Host "GitHub repository: $Repo"
  Write-Host 'No private key or password has been uploaded.'
}
