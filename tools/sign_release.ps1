param(
  [string]$Thumbprint = "",
  [string]$TimestampUrl = "http://timestamp.digicert.com",
  [string[]]$Files = @(),
  [switch]$AllowTestCert
)
$ErrorActionPreference = "Stop"
$signtool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -match '\\x64\\|\\x86\\' } |
  Sort-Object { if ($_.FullName -match '\\x64\\') { 0 } else { 1 } } | Select-Object -First 1
if (-not $signtool) { throw "signtool.exe not found" }

if (-not $Thumbprint) {
  $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.HasPrivateKey } | Sort-Object NotAfter -Descending | Select-Object -First 1
  if (-not $cert) { throw "No code signing certificate in Cert:\CurrentUser\My" }
  if ($cert.Subject -match "Local Test" -and -not $AllowTestCert) {
    throw "Only a local test certificate is available; pass -AllowTestCert for local verification, or install a trusted cert."
  }
  $Thumbprint = $cert.Thumbprint
}
if (-not $Files -or $Files.Count -eq 0) {
  throw "Provide -Files (main exe, installer, dlls)"
}
$results = @()
foreach ($file in $Files) {
  if (-not (Test-Path $file)) { throw "Missing file: $file" }
  Write-Host "Signing $file"
  & $signtool.FullName sign /sha1 $Thumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $file
  if ($LASTEXITCODE -ne 0) { throw "signtool sign failed: $file" }
  $verify = & $signtool.FullName verify /pa $file 2>&1
  $ok = $LASTEXITCODE -eq 0
  $results += [pscustomobject]@{ file=$file; verify_ok=$ok; output=($verify -join "`n") }
}
$results | ConvertTo-Json -Depth 4 | Set-Content "$PSScriptRoot\..\release-archive\sign-report.json" -Encoding UTF8
$results | Format-Table -AutoSize
