param(
  [string]$DumpFolder = "D:\beeofficeV\_ptmp\analysis\crashes"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $DumpFolder | Out-Null
$root = "HKCU:\Software\Microsoft\Windows\Windows Error Reporting\LocalDumps"
New-Item -Path $root -Force | Out-Null
foreach ($exe in @("python.exe","BeeOffice.exe","QtWebEngineProcess.exe")) {
  $key = Join-Path $root $exe
  New-Item -Path $key -Force | Out-Null
  New-ItemProperty -Path $key -Name DumpFolder -PropertyType ExpandString -Value $DumpFolder -Force | Out-Null
  New-ItemProperty -Path $key -Name DumpType -PropertyType DWord -Value 2 -Force | Out-Null
  New-ItemProperty -Path $key -Name DumpCount -PropertyType DWord -Value 5 -Force | Out-Null
}
Write-Host "WER LocalDumps enabled: $DumpFolder"
Write-Host "Reproduce: python -m pytest tests -q"
Write-Host "Dumps: Get-ChildItem '$DumpFolder'"
