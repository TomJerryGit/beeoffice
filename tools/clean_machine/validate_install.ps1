param(
  [Parameter(Mandatory=$true)][string]$Installer,
  [string]$ExpectedVersion = "",
  [int]$LaunchSeconds = 15
)
$ErrorActionPreference = "Stop"
$report = [ordered]@{
  started = (Get-Date).ToString("o")
  os = (Get-CimInstance Win32_OperatingSystem).Caption
  version = (Get-CimInstance Win32_OperatingSystem).Version
  installer = (Resolve-Path $Installer).Path
  steps = @()
}
function Add-Step($name, $ok, $detail = "") {
  $script:report.steps += [ordered]@{name=$name; ok=$ok; detail=$detail; time=(Get-Date).ToString("o")}
}
try {
  $python = Get-Command python -ErrorAction SilentlyContinue
  Add-Step "no-python" ($null -eq $python) ($python.Source)
  $wps = Get-Command wps -ErrorAction SilentlyContinue
  Add-Step "no-wps" ($null -eq $wps) ($wps.Source)

  $p = Start-Process -FilePath $report.installer -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" -Wait -PassThru
  Add-Step "install" ($p.ExitCode -eq 0) "exit=$($p.ExitCode)"

  $app = Get-ChildItem "$env:LOCALAPPDATA\BeeOffice","$env:ProgramFiles\BeeOffice" -Filter BeeOffice.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  Add-Step "app-exists" ($null -ne $app) ($(if($app){$app.FullName}else{""}))
  if ($app) {
    $proc = Start-Process -FilePath $app.FullName -PassThru
    Start-Sleep -Seconds $LaunchSeconds
    $alive = -not $proc.HasExited
    Add-Step "launch" $alive "pid=$($proc.Id)"
    if ($alive) { Stop-Process -Id $proc.Id -Force }
  }
  $uninstaller = Get-ChildItem "$env:LOCALAPPDATA\BeeOffice","$env:ProgramFiles\BeeOffice" -Filter unins*.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($uninstaller) {
    $u = Start-Process -FilePath $uninstaller.FullName -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" -Wait -PassThru
    Add-Step "uninstall" ($u.ExitCode -eq 0) "exit=$($u.ExitCode)"
  } else {
    Add-Step "uninstall" $false "未找到卸载器"
  }
} catch {
  Add-Step "exception" $false $_.Exception.Message
} finally {
  $report.finished = (Get-Date).ToString("o")
  $report.ok = ($report.steps | Where-Object { -not $_.ok }).Count -eq 0
  $out = Join-Path (Get-Location) "clean-machine-report.json"
  $report | ConvertTo-Json -Depth 6 | Set-Content $out -Encoding UTF8
  Write-Host "REPORT=$out OK=$($report.ok)"
}
