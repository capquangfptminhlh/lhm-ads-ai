# Vendor workstation ONLY. Verify EXE after authentic code signing, never in unsigned CI.
param(
  [Parameter(Mandatory=$true)][string]$Exe,
  [Parameter(Mandatory=$true)][string]$ExpectedThumbprint,
  [string]$HashOut = ""
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) { throw 'EXE file missing' }
if ($ExpectedThumbprint -notmatch '^[A-Fa-f0-9]{40,64}$') { throw 'Provide the trusted publisher certificate thumbprint' }
$signature = Get-AuthenticodeSignature -LiteralPath $Exe
if ($signature.Status -ne 'Valid' -or $null -eq $signature.SignerCertificate) {
  throw "Authenticode is not valid ($($signature.Status)): do not distribute this EXE"
}
$actual = ($signature.SignerCertificate.Thumbprint -replace '\s','').ToUpperInvariant()
$expected = ($ExpectedThumbprint -replace '\s','').ToUpperInvariant()
if ($actual -ne $expected) { throw 'Signer thumbprint differs from the approved vendor certificate' }
$hash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "PASS: signed by $($signature.SignerCertificate.Subject)"
Write-Host "SHA256: $hash"
Write-Host 'Hash must be published AFTER signing, not reused from the unsigned GitHub candidate.'
if ($HashOut) {
  if (Test-Path -LiteralPath $HashOut) { throw 'Checksum output already exists; avoid overwriting past releases' }
  $name = Split-Path -Leaf $Exe
  Set-Content -Path $HashOut -Encoding ascii -Value "$hash  $name"
}
