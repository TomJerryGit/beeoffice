# 第三方组件许可说明

BeeOffice 自身源代码以 **MIT** 发布（见 [LICENSE](LICENSE)）。
但打包运行依赖以下第三方组件，它们各有自己的许可证。

**只使用源码（`python -m beeoffice.main`）时**，主要义务是按 MIT 保留版权声明。
**分发打包好的二进制（`dist/BeeOffice`）时**，需要同时满足下列组件的条款。

---

## ⚠️ 最需要注意的一个：PyMuPDF

| 组件 | 许可证 | 影响 |
|---|---|---|
| **PyMuPDF**（`pymupdf` / `fitz`） | **AGPL-3.0** | **分发二进制时**，AGPL 要求向接收者提供完整对应源码，且衍生作品也须以 AGPL 授权 |

这意味着：如果你把 `dist/BeeOffice` 公开发布，严格来说整个分发物需要按 AGPL-3.0 提供源码，
而不只是"MIT + 一个声明"。

**三个可选出路**（需要产品决策，代码层面都可行）：

1. **遵守 AGPL**：发布二进制时同时提供完整源码，并在程序内提供获取源码的入口；
2. **购买商业授权**：Artifex 提供 PyMuPDF 商业许可，可解除 AGPL 义务；
3. **打包时排除 PDF 批注模块**：仓库已支持精简打包（`BEEOFFICE_LITE=1`），
   可以进一步把 `pymupdf` 也排除，得到不含 AGPL 依赖的发行版
   （需要额外改 `beeoffice.spec` 的 excludes 并让 PDF 插件优雅降级）。

> 当前 `v5.2.0` 的发布**只是源码**，没有附带二进制，所以暂时不触发这些义务。

---

## 其余主要依赖

| 组件 | 用途 | 许可证 |
|---|---|---|
| PySide6 / Qt 6 | GUI 框架 | LGPL-3.0（动态链接可闭源使用） |
| pandas | 表格数据 | BSD-3-Clause |
| numpy | 数值计算 | BSD-3-Clause |
| matplotlib | 图表 | PSF-based（BSD 兼容） |
| python-docx | DOCX 读写 | MIT |
| python-pptx | PPTX 读写 | MIT |
| openpyxl | XLSX 读写 | MIT |
| python-calamine | 快速读 Excel | MIT |
| beautifulsoup4 / lxml | HTML 解析 | MIT / BSD-3-Clause |
| markdown | Markdown 渲染 | BSD-3-Clause |
| Pillow | 图像处理 | MIT-CMU |
| requests | HTTP | Apache-2.0 |
| fonttools | 字体子集化 | MIT |

完整清单以 `requirements.txt` 为准；各组件许可证见其发行包内的 LICENSE 文件。

---

## Qt / PySide6 的特别说明

Qt 6 采用 **LGPL-3.0**。以动态链接方式使用（PySide6 默认就是动态链接）时，
可以闭源分发你的应用，但需要：

- 保留 Qt 的版权声明与许可证文本；
- 允许用户替换 Qt 库（动态链接天然满足）；
- 若修改了 Qt 源码，需公开修改部分。

PyInstaller 打包属于动态链接，通常满足要求；但**需要随包附带 LGPL 文本**。
当前打包产物未包含，若要正式分发二进制，应补充。
