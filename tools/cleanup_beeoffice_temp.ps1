param(
  [switch]$Execute,
  [switch]$IncludeWorktrees,
  [switch]$IncludePackages,
  [switch]$IncludeCaches,
  [switch]$IncludeTempDirs
)
# BeeOffice 本地清理脚本：默认只 dry-run，不删除任何文件。
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\cleanup_beeoffice_temp.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\cleanup_beeoffice_temp.ps1 -Execute -IncludeWorktrees -IncludePackages -IncludeTempDirs
$ErrorActionPreference = "Stop"
$Repo = "D:\beeofficeV"
$Pt = Join-Path $Repo "_ptmp"
$S4 = Join-Path $Pt "s4"
$actions = @()

function Get-SizeMB($path) {
  if (-not (Test-Path -LiteralPath $path)) { return 0 }
  $files = Get-ChildItem -LiteralPath $path -Recurse -File -Force -ErrorAction SilentlyContinue
  return [math]::Round((($files | Measure-Object Length -Sum).Sum) / 1MB, 1)
}

function Add-Action($kind, $path, $sizeMB) {
  $script:actions += [pscustomobject]@{kind=$kind; path=$path; sizeMB=$sizeMB}
}

if ($IncludeWorktrees) {
  $lines = git -C $Repo worktree list --porcelain
  $cur = @{}
  $worktrees = @()
  foreach ($line in $lines) {
    if ($line -eq "") {
      if ($cur.Path) { $worktrees += [pscustomobject]$cur }
      $cur = @{}
    } elseif ($line -match '^worktree (.+)') { $cur.Path = $Matches[1] }
  }
  if ($cur.Path) { $worktrees += [pscustomobject]$cur }
  foreach ($wt in $worktrees) {
    $wtPath = $wt.Path.Replace("/", "\")
    if ($wtPath -notmatch [regex]::Escape($Pt)) { continue }
    if ($wtPath -match [regex]::Escape($S4)) { continue }
    if ($wtPath -match 'main_baseline\\_ptmp\\s3_baseline') { continue }
    Add-Action "worktree" $wtPath (Get-SizeMB $wtPath)
  }
}

if ($IncludeTempDirs) {
  $patterns = @("bt_*", "temp_build*", "test_*", "build_cli", "dist_cli", "probe_*", "isolated", "basetemp", "mintest", "timing")
  foreach ($pat in $patterns) {
    Get-ChildItem -LiteralPath $Pt -Force -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -like $pat } |
      ForEach-Object { Add-Action "dir" $_.FullName (Get-SizeMB $_.FullName) }
  }
  Get-ChildItem -LiteralPath $Pt -File -Force -Filter "*.txt" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^iso_' } |
    ForEach-Object { Add-Action "file" $_.FullName ([math]::Round($_.Length/1MB, 1)) }
}

if ($IncludePackages) {
  $keepZip = @("BeeOffice-v5.8.35-windows.zip", "BeeOffice-v5.7.0-windows.zip")
  $keepSetup = @("BeeOffice-Setup-v5.8.35.exe", "BeeOffice-Setup-v5.7.0.exe")
  Get-ChildItem -LiteralPath $S4 -File -Filter "BeeOffice-v*-windows.zip" -ErrorAction SilentlyContinue |
    Where-Object { $keepZip -notcontains $_.Name } |
    ForEach-Object { Add-Action "zip" $_.FullName ([math]::Round($_.Length/1MB, 1)) }
  $ra = Join-Path $S4 "release-archive"
  Get-ChildItem -LiteralPath $ra -File -Filter "BeeOffice-Setup-v*.exe" -ErrorAction SilentlyContinue |
    Where-Object { $keepSetup -notcontains $_.Name } |
    ForEach-Object { Add-Action "setup" $_.FullName ([math]::Round($_.Length/1MB, 1)) }
}

if ($IncludeCaches) {
  foreach ($p in @((Join-Path $Repo ".pytest_cache"), (Join-Path $Repo ".ruff_cache"),
                   (Join-Path $S4 ".pytest_cache"), (Join-Path $S4 ".ruff_cache"),
                   (Join-Path $S4 "debug.log"), (Join-Path $Repo "debug.log"))) {
    if (Test-Path -LiteralPath $p) { Add-Action "cache" $p (Get-SizeMB $p) }
  }
  $temp = Join-Path $env:LOCALAPPDATA "Temp"
  Get-ChildItem -LiteralPath $temp -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^(BeeOffice|_MEI|pyinstaller|pip-)' -or $_.Name -like 'tmp*' } |
    ForEach-Object { Add-Action "temp" $_.FullName (Get-SizeMB $_.FullName) }
}

# 去重：worktree 与 dir 不要重复统计/删除
$seen = @{}
$unique = @()
foreach ($a in $actions) {
  $key = $a.path.Replace("/", "\").ToLowerInvariant()
  if (-not $seen.ContainsKey($key)) { $seen[$key] = $true; $unique += $a }
}
$actions = $unique
$total = ($actions | Measure-Object sizeMB -Sum).Sum
$actions | Sort-Object sizeMB -Descending | Format-Table -AutoSize | Out-String -Width 180
"TOTAL_MB=$([math]::Round($total,1))"
"DRY_RUN=$(-not $Execute)"

if (-not $Execute) {
  Write-Host "DRY RUN：未删除。确认后加 -Execute 以及对应 -Include* 开关。"
  exit 0
}

foreach ($a in $actions) {
  try {
    if ($a.kind -eq "worktree") {
      git -C $Repo worktree remove --force $a.path
    } else {
      Remove-Item -LiteralPath $a.path -Recurse -Force -ErrorAction Stop
    }
    Write-Host "REMOVED $($a.path)"
  } catch {
    Write-Warning "FAILED $($a.path): $($_.Exception.Message)"
  }
}
Write-Host "DONE"
