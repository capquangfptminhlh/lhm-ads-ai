# LHM Ads AI commercial package: LOCAL vendor workstation only.
# Fail closed unless the candidate matches CI, all direct acceptance evidence
# has owner approval, and a real trusted publisher code-signing cert is present.
# Private Ed25519 license key never enters this process or the EXE.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$CandidateDir,
  [Parameter(Mandatory=$true)][string]$VendorPublicFile,
  [Parameter(Mandatory=$true)][string]$AcceptanceFile,
  [Parameter(Mandatory=$true)][string]$PublisherThumbprint,
  [Parameter(Mandatory=$true)][string]$TimestampUrl,
  [Parameter(Mandatory=$true)][string]$OutputDir
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 5) { throw 'PowerShell 5.1+ is required' }
if ($PublisherThumbprint -notmatch '^[0-9a-fA-F]{40}$') { throw 'PublisherThumbprint must be 40 hex characters (SHA1 certificate thumbprint)' }
if ($TimestampUrl -notmatch '^https://[A-Za-z0-9.-]+(?::443)?(?:/[A-Za-z0-9/_-]*)?$') {
  throw 'Timestamp URL must be an explicit HTTPS URL of the trusted time-stamping service'
}
$candidate = (Resolve-Path -LiteralPath $CandidateDir -ErrorAction Stop).Path
$vendorPublic = (Resolve-Path -LiteralPath $VendorPublicFile -ErrorAction Stop).Path
$acceptance = (Resolve-Path -LiteralPath $AcceptanceFile -ErrorAction Stop).Path
$exePath = Join-Path $candidate 'LHM-Ads-AI.exe'
$checksumPath = Join-Path $candidate 'LHM-Ads-AI.sha256'
$manifestPath = Join-Path $candidate 'release-manifest.json'
$releaseGate = Join-Path (Split-Path -Parent $PSScriptRoot) 'tools/release_gate.py'
foreach ($path in @($exePath,$checksumPath,$manifestPath,$releaseGate)) {
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing release file: $path" }
}
if (Test-Path -LiteralPath $OutputDir) { throw 'OutputDir already exists: choose a new path to protect previous releases' }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python not found on vendor signing workstation' }
& python $releaseGate verify-candidate --exe $exePath --checksum $checksumPath --manifest $manifestPath --vendor-public $vendorPublic --acceptance $acceptance
if ($LASTEXITCODE -ne 0) { throw 'Vendor public key, CI hash or manual acceptance is not valid' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$thumbprint = $PublisherThumbprint.ToUpperInvariant()
$cert = @(Get-ChildItem -Path 'Cert:\CurrentUser\My','Cert:\LocalMachine\My' -ErrorAction SilentlyContinue |
  Where-Object { $_.Thumbprint -eq $thumbprint -and $_.HasPrivateKey } | Select-Object -First 1)
if ($cert.Count -ne 1) { throw 'An installed code-signing certificate with a private key matching the expected thumbprint is required' }
$eku = @($cert[0].Extensions |
  Where-Object { $_ -is [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension] } |
  ForEach-Object { $_.EnhancedKeyUsages } | ForEach-Object { $_.Value })
if (-not ($eku -contains '1.3.6.1.5.5.7.3.3')) { throw 'Certificate does not have the Code Signing extended key usage' }
$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
if (-not $signtool) { throw 'signtool.exe (Windows SDK) not found; install official Windows SDK signing tools' }
$out = [System.IO.Path]::GetFullPath($OutputDir)
$stage = Join-Path $out 'staging'
New-Item -ItemType Directory -Path $stage -Force:$false | Out-Null
try {
  $signedExe = Join-Path $stage 'LHM-Ads-AI.exe'
  Copy-Item -LiteralPath $exePath -Destination $signedExe
  & $signtool.Source sign /sha1 $thumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $signedExe
  if ($LASTEXITCODE -ne 0) { throw 'signtool signing failed: do NOT distribute the EXE' }
  & $signtool.Source verify /pa /all /v $signedExe
  if ($LASTEXITCODE -ne 0) { throw 'Signed PE does not pass Windows Authenticode trust verification' }
  $verified = Get-AuthenticodeSignature -LiteralPath $signedExe
  if ($verified.Status -ne 'Valid' -or $null -eq $verified.SignerCertificate) {
    throw 'Authenticode signer status is not Valid after signing'
  }
  if ($verified.SignerCertificate.Thumbprint.ToUpperInvariant() -ne $thumbprint) {
    throw 'Unexpected Authenticode signer thumbprint'
  }
  $signedHash = (Get-FileHash -LiteralPath $signedExe -Algorithm SHA256).Hash.ToLowerInvariant()
  Set-Content -LiteralPath (Join-Path $stage 'LHM-Ads-AI-SIGNED.sha256') -Value "$signedHash  LHM-Ads-AI.exe" -Encoding ascii
  $final = [ordered]@{
    product = 'LHM Ads AI'
    edition = 'commercial-signed'
    product_version = $manifest.product_version
    source_commit = $manifest.source_commit
    source_artifact_sha256 = $manifest.sha256
    executable = 'LHM-Ads-AI.exe'
    sha256 = $signedHash
    license_public_key_sha256 = $manifest.license_public_key_sha256
    authenticode = 'SIGNED_VERIFIED'
    publisher_thumbprint = $thumbprint
    signed_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    owner_approved = $true
    acceptance_attestation = 'Owner manually reviewed matching commit/version and all 8 documented checks'
    distribution = 'OWNER_APPROVED'
  }
  $final | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stage 'release-manifest.json') -Encoding UTF8
  @(
    'LHM Ads AI - signed commercial distribution'
    "Version: $($manifest.product_version)"
    "Source commit: $($manifest.source_commit)"
    "Publisher certificate SHA1: $thumbprint"
    "License public key SHA256: $($manifest.license_public_key_sha256)"
    "Signed EXE SHA256: $signedHash"
    'Only download this file from the publisher-authorized distribution channel.'
    'Keep your Ads credentials local. Do not share token or backup passwords with support.'
    'If a license is unavailable, obtain it directly from the authorized LHM seller.'
  ) | Set-Content -LiteralPath (Join-Path $stage 'README-CUSTOMER.txt') -Encoding UTF8
  $zipName = 'LHM-Ads-AI-' + $manifest.product_version + '-COMMERCIAL-SIGNED.zip'
  $zipFile = Join-Path $out $zipName
  Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zipFile -CompressionLevel Optimal
  Write-Host "PASS: signed release candidate packaged: $zipFile"
  Write-Host "Signed SHA256: $signedHash"
  Write-Host 'Do not advertise Google/Meta API acceptance beyond the human-verified evidence file.'
} catch {
  Write-Error $_
  throw
} finally {
  # Leave the signed staging folder for vendor inspection. Never delete the
  # original unsigned CI candidate or overwrite earlier release artifacts.
}
