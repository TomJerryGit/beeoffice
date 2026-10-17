<#
.SYNOPSIS
    在 github.com 被按 SNI 阻断的网络环境下，把本地仓库推送到 GitHub。

.DESCRIPTION
    本机实测结论（2026-10-17）：
      - github.com:443 的 TCP 能连上，但 TLS 握手被重置（按 SNI 阻断）；
      - api.github.com / codeload.github.com 正常；
      - GitHub 的不同边缘 IP 存活情况不一致，且会随时间变化。

    git 支持 `http.curloptResolve=host:port:addr`，可以把 github.com
    强制解析到指定 IP。本脚本逐个探测候选 IP，找到当前能完成 TLS
    握手的那一个，用它执行推送。

.PARAMETER Remote
    远程名，默认 origin。

.PARAMETER Branch
    分支名，默认 main。

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\push_github.ps1

.NOTES
    如果所有 IP 都不可用，说明当前网络对该域名的阻断比较严格，
    请改用代理/VPN，或换网络（手机热点）后重试。
#>
param(
    [string]$Remote = "origin",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

# ---- 定位 git ----
$Git = "C:\Program Files\Git\cmd\git.exe"
if (-not (Test-Path $Git)) {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if (-not $cmd) { Write-Error "未找到 git，请先安装 Git for Windows。"; exit 1 }
    $Git = $cmd.Source
}

# ---- 候选 IP（GitHub 边缘节点，可按需增删）----
$Candidates = @(
    "20.201.28.151", "20.205.243.166", "20.200.245.247", "20.233.83.145",
    "20.175.192.147", "20.26.156.215", "140.82.112.3", "140.82.113.3",
    "140.82.114.3", "140.82.116.3", "4.237.22.38", "4.208.26.197"
)

function Test-GitHubTls {
    param([string]$Ip)
    # 只有完成 TLS 并拿到 200 才算可用；000 表示握手失败/超时
    $code = & curl.exe -s -o NUL -m 8 --resolve "github.com:443:$Ip" `
        -w "%{http_code}" https://github.com 2>$null
    return ($code -eq "200")
}

$chosen = $null
foreach ($ip in $Candidates) {
    Write-Host ("探测 {0,-16} ... " -f $ip) -NoNewline
    if (Test-GitHubTls -Ip $ip) {
        Write-Host "可用" -ForegroundColor Green
        $chosen = $ip
        break
    }
    Write-Host "不可用"
}

if (-not $chosen) {
    Write-Host ""
    Write-Host "没有可用的 GitHub IP。" -ForegroundColor Red
    Write-Host "请开启代理/VPN，或改用手机热点后重试。" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "使用 $chosen 推送 $Branch → $Remote ..." -ForegroundColor Cyan
& $Git -c "http.curloptResolve=github.com:443:$chosen" push -u $Remote $Branch
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) {
    Write-Host "推送成功。" -ForegroundColor Green
    & $Git log --oneline -1
} else {
    Write-Host "推送失败（exit=$code）。" -ForegroundColor Yellow
    Write-Host "按报错对照处理："
    Write-Host "  · 'could not read Username' / 'Authentication failed'"
    Write-Host "      仓库可能尚未创建，或需要凭据。先在 GitHub 新建空仓库"
    Write-Host "      （不要勾选 README / .gitignore / license），然后："
    Write-Host "        方式一：重新运行本脚本，在弹出的 Git Credential Manager 里登录"
    Write-Host "        方式二：用 PAT（注意会明文存进 .git/config）"
    Write-Host "          git remote set-url origin https://<TOKEN>@github.com/TomJerryGit/beeoffice.git"
    Write-Host "  · 'Repository not found'"
    Write-Host "      确认仓库名与账号（当前配置：$(& $Git remote get-url $Remote)）"
    Write-Host "  · 仍然是连接失败"
    Write-Host "      说明该 IP 刚失效，重跑本脚本会自动换一个"
}
exit $code
