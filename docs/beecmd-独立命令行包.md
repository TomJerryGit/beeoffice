# 独立命令行包：`beecmd.exe`（阶段③交付物）

> 日期：2026-10-20 · 代码基线：`bb4b7f7`（v5.0.15 之后，未发新 tag）
> 目的：让**外部用户不装 Python、不打开 GUI**，用一条命令完成真实工作 ——
> 这是"90 天可验证交付"里最容易先拿到的一块证据。

---

## 0. 一页结论

| 项 | 结果 |
|---|---|
| 构建命令 | `python tools/build_cli.py`（PyInstaller 6.22.3 onefile，显式排除 Qt） |
| 产物 | `beecmd.exe` **77.5 MB**；`BeeOffice-beecmd-v0.4.0-windows.zip` **76.8 MB** |
| ZIP SHA-256 | `aab09dc326f9dfbcdf01db63c494581db1affcd8e64fa4abda145bbb467f8739` |
| ZIP 内容 | `beecmd.exe` + `README-beecmd.txt`（含支持矩阵与安全提示） |
| 归档 | `release-archive/cli/BeeOffice-beecmd-v0.4.0-windows.zip` |
| 冒烟矩阵 | **8/8 命令 exit 0**（version/convert×2/verify/merge/clean/beshow/ai） |
| 总耗时 | 152.1 s（其中 AI 摘要 65.0 s，本地 Ollama CPU） |
| 依赖 | 零 Python、零 Qt；运行时只需 Windows + 可写 `%TEMP%` |
| 已知限制 | 不支持 `md → docx/pdf`（那两条依赖 Qt 打印引擎）；exe 未签名 |

**重要区别**：这是 **内部冒烟验证**，不是"真实外部用户验证"。
外部用户证据仍需一个人在一台干净机器上按本文 §5 跑一次并留痕。

---

## 1. 为什么打这个包

阶段③的原始目标（分析报告 §6/§8）：

> 在 90 天内拿到"**外部用户不开 GUI、用一条命令完成一件真实工作**"的证据。

在此之前，`beecmd` 只能从源码运行（需要 Python + 依赖），外部用户门槛太高。
GUI 安装包按设计又不含 `beecmd`/`tools`。所以补一个独立 exe：

- 体积 77.5 MB（对比 GUI 包 224.7 MB）；
- 启动即用，不装 Python；
- 覆盖阶段③最有价值的 CLI 路径：表格转换/汇总/校验/清洗、`md → beshow`、AI 六任务。

## 2. 支持矩阵（实测，全部 exit 0）

在 **干净目录、`PYTHONPATH` 清空** 下运行 `dist_cli/beecmd.exe`：

| 命令 | 结果 |
|---|---|
| `beecmd.exe --version` | `beecmd 0.4.0` |
| `convert 一月.csv --to xlsx` | 生成 xlsx |
| `convert 一月.xlsx --to csv` | 往返 csv（2 行） |
| `verify 一月.xlsx 一月_round.csv --report verify.json` | `ok=true`，`mismatches=0` |
| `merge 一月.csv 二月.csv -o 汇总.xlsx --mode append` | 2 文件 / 5 行 |
| `clean 脏数据.csv -o 清洗后.xlsx --plan plan.json --report clean_report.json` | 行 6→2，10 项操作/9 处修改，`original_untouched=true` |
| `convert 季度汇报.md --to beshow` | 产出 `.beshow`（首行 `<!-- beeshow-deck v1 -->`） |
| `ai summarize 经营摘要.md --api-base http://127.0.0.1:11434/v1 --model llama3.2` | `source=ai`，64.97 s，5 行摘要 |

不支持的：`md → docx` / `md → pdf` —— 这两条走蜜写的 Qt 打印引擎，本 exe 明确排除
PySide6；需要它们时请用 GUI 或源码运行 `beecmd`。

## 3. 冒烟中发现并修掉的真 bug（不是假绿）

第一次冒烟：**8 条命令全部 exit 1**，但文件其实已生成。错误：

```
UnicodeEncodeError: 'gbk' codec can't encode character '\u2705'
```

原因：Windows 默认控制台代码页是 cp936（GBK），`beecmd` 成功时会 `print("✅ …")`，
emoji 编码失败 → 命令在最后一行输出时崩掉。**外部用户会以为工具坏了**。

修复：`beecmd._make_console_safe()` 在 `main()` 最先执行，
把 stdout/stderr 的 `errors` 改为 `replace`（保留原编码；emoji 显示为 `?`，不再崩）。
新增：
- 测试 `tests/fidelity/test_beecmd_console_encoding.py`（2 条：GBK 流不崩 / main 先兜底）；
- 门禁 `beecmd-console`（第 **46** 项）。

修复后重跑冒烟：**8/8 exit 0**（本文 §2 的结果）。

## 4. 构建与产物校验

```powershell
cd D:\beeofficeV
$env:PYTHONPATH='D:\beeofficeV'
python tools\build_cli.py
```

构建脚本做三件事：
1. PyInstaller `--onefile` 分析 `tools/beecmd_entry.py`（真正的入口转发到 `beeoffice.beecmd.main`）；
2. 显式排除 `PySide6/shiboken6/PySide2/PyQt5/PyQt6/tkinter/matplotlib/scipy/IPython/jupyter`
   —— 保证"服务器可跑"、控制体积；
3. 生成 ZIP + `.sha256` + 使用说明（`README-beecmd.txt`）。

本机产物校验（`_ptmp/dist_cli/`）：

```
beecmd.exe                         77.5 MB
BeeOffice-beecmd-v0.4.0-windows.zip 76.8 MB
zip sha256  aab09dc326f9dfbcdf01db63c494581db1affcd8e64fa4abda145bbb467f8739
zip entries ["beecmd.exe", "README-beecmd.txt"]
```

## 5. 外部验证 Runbook（需要你/同事做一次）

1. 把 `release-archive/cli/BeeOffice-beecmd-v0.4.0-windows.zip` 传到一台
   **没有 Python、没装 BeeOffice** 的 Windows 机器；
2. 解压，核对 `SHASUMS`（ZIP 的 sha256 见 §4）；
3. 用它做一件真实工作（任选其一）：
   - `beecmd.exe merge 一月.xlsx 二月.xlsx -o 汇总.xlsx`（真实月报）；
   - `beecmd.exe clean 真实脏表.csv -o 清洗后.xlsx`（先人工看一眼报告）；
   - `beecmd.exe convert 真实文稿.md --to beshow`；
4. 保留：命令原文、`退出码`、产物文件、`audit.jsonl`/报告 JSON、耗时；
5. 把结果贴回来 —— 这就是"外部用户不开 GUI 用一条命令完成真实工作"的证据。

> 注意：exe 未签名，Windows SmartScreen 可能提示"未知发布者"；
> 这是独立分发的正常现象，核对 sha256 后再运行。

## 6. 边界（如实）

- 本包**不是** GUI 安装包替代品：GUI 版仍是 224.7 MB 的 onedir 包，含蜜写/蜜算/蜜演界面；
- 不支持 `md → docx/pdf`（需要 Qt，exe 已排除）；
- onefile 解压需要**可写 `%TEMP%`**；若机器 TEMP 受限，可用 `--onedir` 变体（未构建，
  修改 `tools/build_cli.py` 的 `--onefile` 即可）；
- 中文在 cp936 控制台正常显示，但捕获/重定向到 UTF-8 文件时可能出现乱码；
- AI 任务需要可用的 OpenAI 兼容端点（本地 Ollama 或云端 Key）；
- 体积 77.5 MB 主要来自 pandas/numpy/openpyxl/pymupdf/python-docx/pptx，未进一步裁剪。

## 7. 复跑

```powershell
# 构建（会跑 PyInstaller，约 2–4 分钟）
python tools\build_cli.py

# 快速自检
.\_ptmp\dist_cli\beecmd.exe --version

# 回归（不跑打包）
python -m pytest tests/unit/test_build_cli.py -q
python tools\check_gates.py --only beecmd-console
```
