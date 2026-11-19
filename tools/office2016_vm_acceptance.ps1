param(
  [Parameter(Mandatory=$true)][string]$SharedDir,
  [string]$OutputDir = "C:\BeeOfficeAcceptance",
  [string]$OfficeVersion = "16.0"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $OutputDir | Out-Null
$report = [ordered]@{
  started = (Get-Date).ToString("o")
  computer = $env:COMPUTERNAME
  os = (Get-CimInstance Win32_OperatingSystem).Caption
  osVersion = (Get-CimInstance Win32_OperatingSystem).Version
  office = @{}
  checks = @()
}

function Add-Check($name, $ok, $detail) {
  $script:report.checks += [ordered]@{name=$name; ok=$ok; detail=$detail}
}

try {
  $word = New-Object -ComObject Word.Application
  $word.Visible = $false; $word.DisplayAlerts = 0
  $report.office.word = $word.Version
  Add-Check "office2016-word" ($word.Version -like "$OfficeVersion*") "version=$($word.Version)"
  $word.Quit()
} catch { Add-Check "office2016-word" $false $_.Exception.Message }

try {
  $excel = New-Object -ComObject Excel.Application
  $excel.Visible = $false; $excel.DisplayAlerts = $false
  $report.office.excel = $excel.Version
  Add-Check "office2016-excel" ($excel.Version -like "$OfficeVersion*") "version=$($excel.Version)"
  $excel.Quit()
} catch { Add-Check "office2016-excel" $false $_.Exception.Message }

try {
  $ppt = New-Object -ComObject PowerPoint.Application
  $report.office.ppt = $ppt.Version
  Add-Check "office2016-ppt" ($ppt.Version -like "$OfficeVersion*") "version=$($ppt.Version)"
  $ppt.Quit()
} catch { Add-Check "office2016-ppt" $false $_.Exception.Message }

$acceptance = Join-Path $SharedDir "tools\ms_office_acceptance.ps1"
if (Test-Path $acceptance) {
  & powershell -NoProfile -ExecutionPolicy Bypass -File $acceptance -Dir (Join-Path $SharedDir "analysis\ms-office")
  Add-Check "acceptance-script" ($LASTEXITCODE -eq 0) "ms_office_acceptance.ps1"
} else {
  Add-Check "acceptance-script" $false "missing $acceptance"
}

# 截图（如桌面可用）
try {
  Add-Type -AssemblyName System.Windows.Forms, System.Drawing
  $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
  $shot = Join-Path $OutputDir "desktop.png"
  $bmp.Save($shot, [System.Drawing.Imaging.ImageFormat]::Png)
  Add-Check "screenshot" $true $shot
} catch { Add-Check "screenshot" $false $_.Exception.Message }

$report.finished = (Get-Date).ToString("o")
$report.ok = ($report.checks | Where-Object { -not $_.ok }).Count -eq 0
$json = Join-Path $OutputDir "office2016-vm-report.json"
$report | ConvertTo-Json -Depth 6 | Set-Content $json -Encoding UTF8
Write-Host "REPORT=$json OK=$($report.ok)"
