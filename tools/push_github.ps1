<#
push_to_github.ps1 - retry-safe `git push origin main --tags` for Windows PowerShell 5.1.

Retries transient failures, classifies auth / network / non-fast-forward, and
never hides a real failure. Works for any repo (default = the script's directory).

USAGE:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\push_to_github.ps1
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\push_to_github.ps1 -Retries 12 -Delay 10
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\push_to_github.ps1 -RepoPath D:\beeofficeV
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\push_to_github.ps1 -DryRun
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\push_to_github.ps1 -SkipTags

EXIT CODES:
  0 pushed   1 other error   2 preflight error   3 auth error
  4 network error   5 rejected/non-fast-forward
#>
[CmdletBinding()]
param(
    [string]$RepoPath = "",
    [string]$Remote = "origin",
    [string]$Branch = "main",
    [int]$Retries = 8,
    [int]$Delay = 5,
    [switch]$SkipTags,
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$env:GIT_TERMINAL_PROMPT = "0"

function Fail([string]$msg, [int]$code) {
    Write-Host ""
    Write-Host "ERROR: $msg" -ForegroundColor Red
    exit $code
}

function Run-Git([string[]]$gitArgs) {
    $out = & git @gitArgs 2>&1
    return @{ Code = $LASTEXITCODE; Output = (($out | Out-String).Trim()) }
}

function Run-GitCmd([string[]]$gitArgs) {
    # cmd /c keeps native stderr as plain text (no PowerShell NativeCommandError noise)
    $quoted = ($gitArgs | ForEach-Object {
        if ($_ -match "\s") { '"' + $_ + '"' } else { $_ }
    }) -join " "
    $out = & cmd.exe /c ("git " + $quoted + " 2>&1")
    return @{ Code = $LASTEXITCODE; Output = (($out | Out-String).Trim()) }
}

if (-not $RepoPath -or $RepoPath.Trim() -eq "") {
    $detected = & git -C $PSScriptRoot rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0 -and $detected) {
        $RepoPath = ($detected | Select-Object -First 1).Trim()
    } else {
        $RepoPath = $PSScriptRoot
    }
}
if (-not (Test-Path -LiteralPath $RepoPath)) {
    Fail "repository path not found: $RepoPath" 2
}
Set-Location -LiteralPath $RepoPath

$inside = Run-Git @("rev-parse", "--is-inside-work-tree")
if ($inside.Code -ne 0 -or $inside.Output -notmatch "true") {
    Fail "not a git work tree: $RepoPath" 2
}
Write-Host "Repository: $RepoPath"

$remoteUrl = Run-Git @("remote", "get-url", $Remote)
if ($remoteUrl.Code -ne 0) {
    Write-Host "No remote '$Remote'. Add one first, e.g.:" -ForegroundColor Yellow
    Write-Host "  git remote add $Remote https://github.com/<user>/<repo>.git"
    Fail "remote '$Remote' is not configured" 2
}
Write-Host "Remote $Remote : $($remoteUrl.Output)"

$branchCheck = Run-Git @("show-ref", "--verify", "--quiet", "refs/heads/$Branch")
if ($branchCheck.Code -ne 0) {
    $cur = (Run-Git @("branch", "--show-current")).Output
    Write-Host "Local branch '$Branch' does not exist. Current branch: '$cur'" -ForegroundColor Yellow
    Write-Host "Create the branch or pass -Branch <name>."
    Fail "local branch '$Branch' not found" 2
}
$cur = (Run-Git @("branch", "--show-current")).Output
if ($cur -ne $Branch) {
    Write-Host "NOTE: current branch is '$cur'; pushing local branch '$Branch'." -ForegroundColor Yellow
}
$head = (Run-Git @("log", "-1", "--format=%h %s")).Output
$dirty = (Run-Git @("status", "--porcelain")).Output
if ($dirty) {
    Write-Host "WARNING: working tree has uncommitted changes (push only sends commits):" -ForegroundColor Yellow
    $dirty -split "`n" | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" }
}
$tagLines = (Run-Git @("tag", "--list")).Output -split "`n" | Where-Object { $_ -ne "" }
$tagCount = @($tagLines).Count
Write-Host "HEAD: $head"
if (-not $SkipTags) { Write-Host "Tags to push: $tagCount" } else { Write-Host "Tags: skipped (-SkipTags)" }

$pushArgs = @("push", $Remote, $Branch)
if (-not $SkipTags) { $pushArgs += "--tags" }
Write-Host ""
Write-Host "Command: git $($pushArgs -join ' ')"

if ($DryRun) {
    Write-Host "DRY RUN: not pushing." -ForegroundColor Cyan
    exit 0
}

# Best-effort fetch so the merge-base check can use the remote ref.
$fetch = Run-Git @("fetch", $Remote, $Branch)
if ($fetch.Code -ne 0) {
    Write-Host "NOTE: git fetch failed (push will still be attempted): $($fetch.Output)" -ForegroundColor Yellow
}

for ($i = 1; $i -le $Retries; $i++) {
    Write-Host ""
    Write-Host ("=" * 60)
    Write-Host ("Attempt {0}/{1} at {2}" -f $i, $Retries, (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
    $r = Run-GitCmd $pushArgs
    if ($r.Output) { Write-Host $r.Output }
    if ($r.Code -eq 0) {
        Write-Host ""
        Write-Host "PUSHED OK" -ForegroundColor Green
        Write-Host "  remote: $Remote ($($remoteUrl.Output))"
        Write-Host "  branch: $Branch"
        Write-Host "  HEAD:   $head"
        if (-not $SkipTags) { Write-Host "  tags:   $tagCount" }
        exit 0
    }

    $err = $r.Output
    if ($err -match "Authentication failed|Permission denied|terminal prompts disabled|403|access denied|invalid username or password|repository not found") {
        Fail ("authentication failed. Fix credentials first: gh auth login (or PAT / credential manager). Details:`n" + $err) 3
    }
    if ($err -match "non-fast-forward|fetch first|rejected|diverged") {
        # NEVER suggest pull --rebase for UNRELATED histories: that can rewrite
        # the branch or merge two independent repos. Refuse and point to a branch.
        $mergeBase = Run-Git @("merge-base", "HEAD", "$Remote/$Branch")
        if ($mergeBase.Code -ne 0 -or -not $mergeBase.Output) {
            Write-Host "UNRELATED HISTORIES: local '$Branch' and $Remote/$Branch share no common ancestor." -ForegroundColor Red
            Write-Host "Do NOT force-push, and do NOT run 'git pull --rebase' on this branch."
            Write-Host "Push local work to a NEW branch instead (remote main untouched):"
            Write-Host "  git push $Remote HEAD:<new-branch-name>"
            Fail "push rejected: unrelated histories; remote main left untouched" 5
        }
        Write-Host "Remote has commits you do not have. Try:" -ForegroundColor Yellow
        Write-Host "  git pull --rebase $Remote $Branch"
        Write-Host "then run this script again."
        Fail "push rejected (non-fast-forward)" 5
    }
    if ($err -match "Failed to connect|Could not resolve|Empty reply|timed out|timeout|Connection refused|Unable to access") {
        Write-Host "Network error (this attempt)." -ForegroundColor Yellow
    } else {
        Write-Host "Unclassified git error (this attempt)." -ForegroundColor Yellow
    }
    if ($i -lt $Retries) {
        $wait = $Delay * [Math]::Min($i, 4)
        Write-Host "Retrying in $wait seconds ..." -ForegroundColor Cyan
        Start-Sleep -Seconds $wait
    }
}

Write-Host ""
Write-Host "Push failed after $Retries attempts." -ForegroundColor Red
Write-Host "If this is a network problem, check: proxy, VPN, DNS, firewall to github.com:443."
Write-Host "Offline fallback (local bare backup, no cloud needed):"
Write-Host "  git init --bare D:\<repo>_backup.git"
Write-Host "  git remote add backup D:\<repo>_backup.git"
Write-Host "  git push -u backup $Branch --tags"
exit 4
