# S0 基准报告：WPS vs BeeOffice（2026-10-29）

> 目的：为 S0“同机基准”提供第一份真实运行数据，并明确**能得出什么、不能得出什么**。
> 脚本：[tools/bench_wps_vs_bee.py](../../tools/bench_wps_vs_bee.py)
> 原始数据：`_ptmp/analysis/bench_wps_s0.json` / `bench_wps_s0.md`

## 1. 环境与方法

| 项 | 值 |
|---|---|
| 机器 | 本机（Windows，LocalSystem/管理员同机） |
| Python | 3.11.9 |
| WPS | 本机 COM：`KWps.Application` / `Ket.Application` / `Kwpp.Application` 可用 |
| 样本 | `test+files` + `tests/fidelity/corpus` 中 ≤5MB 文件，按大小取前 6 |
| 预热/重复 | warmup=1，repeat=2；报告 P50/P95 |
| BeeOffice 操作 | DOCX：`import_from_docx + read_docx_extras`；XLSX：`read_workbook` |
| WPS 操作 | COM 隐藏窗口 `Open(..., ReadOnly=True)`，仅计时 open，不计 close |

### 重要口径
- **不是 GUI 冷启动对比**：WPS 走 COM、BeeOffice 走导入函数，均不含窗口渲染/首次启动；
- **不是完整打开体验**：不含排版、首屏绘制、滚动；
- **样本小**（3 个 DOCX + 1 个 XLSX），只代表这一组文件，不能外推到全部文档；
- COM 的 `Open` 含 WPS 内部转换/格式解析，和 BeeOffice 的自定义导入不是同一实现路径。

## 2. 实测结果（本机，2026-10-29）

| 类型 | 文件 | 大小 | BeeOffice P50 | WPS P50 | WPS/Bee |
|---|---|---:|---:|---:|---:|
| DOCX | Linux系统CentOS7在虚拟机VMware下的安装.docx | 2.54 MB | **146.3 ms** | 235.5 ms | 0.62x |
| DOCX | 永遇乐·京口北固亭怀古.docx | 2.48 MB | **231.5 ms** | 712.9 ms | 0.32x |
| DOCX | Test永遇乐·京口北固亭怀古.docx | 2.48 MB | **170.8 ms** | 605.3 ms | 0.28x |
| XLSX | 测试文档_20 万条.xlsx | 2.28 MB | **909.9 ms** | 6874.0 ms | 0.13x |

> ratio < 1 表示 BeeOffice 更快；这里只说明**本组文件、本口径**下 BeeOffice 读取更快。
> WPS 的 COM `Open` 可能包含更多内部初始化/格式转换工作，不能据此断言 WPS GUI 打开一定更慢。

## 3. 解释

1. **BeeOffice 在这组小样本上更快**，尤其是 20 万行 XLSX 的读取；
2. 但 WPS 的价值在**打开后的版式渲染、公式重算、对象编辑**，本脚本没有测；
3. WPS COM 计时容易受首次/隐藏窗口/格式转换影响，需要下一轮引入：
   - 更一致的文件集（同格式同大小）；
   - GUI 首屏时间（人工/自动窗口就绪信号）；
   - 打开后滚动/重算/保存的端到端时间；
   - 冷/热缓存分离；
   - 至少 20 个文件、P50/P95、置信区间。

## 4. 结论与下一步

- **S0 基准框架已可运行**，并已产出可复现数据；
- 当前结果只能作为“读取路径”的参考，**不能作为对外性能结论**；
- 下一轮（S0 收口后）补：
  1. PPTX / PDF 样本（本组 6 个按大小取，未覆盖）；
  2. BeeOffice 完整 UI 打开（含窗口/渲染）；
  3. WPS 非 COM 的 GUI 冷启动（需人工或窗口事件）；
  4. 性能门禁：启动 <1.5s、DOCX <1.5s、5 万字 <1s、滚动 P95 <30ms（项目既有基线）。

## 5. 附：项目既有优化基线（来自 docs/baseline.md）

| 指标 | 优化前 | 优化后 |
|---|---:|---:|
| DOCX 打开 | 17.7 s | 1.38 s |
| 5 万字 DOCX 首次打开 | 5.85 s | 0.83 s |
| 蜜算滚动重绘 | 337 ms/帧 | 23.6 ms/帧 |
| 插件发现+加载 | 3177 ms（冷启动 8–11s） | 555 ms |

这些是本项目在真实路径上的历史测量，与本报告的小样本 COM 数据口径不同，不能混用。
