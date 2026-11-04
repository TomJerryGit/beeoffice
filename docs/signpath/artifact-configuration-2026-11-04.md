# SignPath Artifact Configuration 配置清单

审核通过后在 SignPath 控制台创建，项目名建议 `BeeOffice`，策略 `release`。

## 需要签名的文件

| 顺序 | 文件 | 说明 |
|---:|---|---|
| 1 | `dist/BeeOffice/BeeOffice.exe` | 主程序；必须先签名，再打入安装器 |
| 2 | `BeeOffice-Setup-v*.exe` | Inno Setup 安装器；最后签名 |

## 建议的签名策略

- 签名类型：Authenticode；
- 哈希：SHA-256；
- 时间戳：RFC3161；
- 策略：仅允许 `release` 工作流（main / tag）触发；
- 不接受 PR 构建直接签名。

## CI 流程

```text
1. 构建 dist\BeeOffice\BeeOffice.exe（未签名）
2. 提交 SignPath 签名请求 → 下载签名后的 exe
3. 用签名后的 exe 构建 Inno Setup 安装器
4. 再次提交安装器签名请求
5. signtool verify /pa
6. 上传 GitHub Release
```

## 注意

- SignPath 的 artifact configuration 在 Web 控制台维护，仓库仅保存工作流与申请材料；
- 不要在仓库或 CI 日志中输出 `SIGNPATH_API_TOKEN`；
- 通过后更新 README 的签名说明：
  “Free code signing provided by SignPath.io, certificate by SignPath Foundation”。
