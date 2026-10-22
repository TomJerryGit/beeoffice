# beecmd PDF 工具（v0.5.0，2026-10-22）

> 定位：WPS 会员权益里**唯一能用现有依赖低成本追平**的一类（PyMuPDF 早就是
> BeeOffice 的必需依赖）。只做「页面管理 + 权限 + 水印 + 提取」，**不做**
> PDF 转 Word/Excel/PPT、PDF 版面编辑、OCR、全文翻译（这些是云服务+模型能力）。

## 1. 命令一览

| 命令 | 作用 | 示例 |
|---|---|---|
| `pdf-merge` | 多个 PDF 合并成一个新文件 | `beecmd pdf-merge a.pdf b.pdf -o out.pdf` |
| `pdf-split` | 拆分（默认每页一个；可按区间） | `beecmd pdf-split in.pdf -o dir --ranges "1-3;4-6;7-"` |
| `pdf-extract` | 提取指定页为新 PDF | `beecmd pdf-extract in.pdf -o p2-3.pdf --pages 2-3` |
| `pdf-delete` | 删除指定页，其余生成新 PDF | `beecmd pdf-delete in.pdf -o out.pdf --pages 2,4-5` |
| `pdf-encrypt` | 加打开密码/权限（AES-256） | `beecmd pdf-encrypt in.pdf -o locked.pdf --user-password s3cret --no-copy` |
| `pdf-watermark` | 叠加文字水印（支持中文） | `beecmd pdf-watermark in.pdf -o wm.pdf --text 内部资料 --opacity 0.2` |
| `pdf-text` | 提取文本到 UTF-8 .txt（按页分隔） | `beecmd pdf-text in.pdf -o out.txt --pages 1-3` |
| `pdf-images` | 导出页面里的图片 | `beecmd pdf-images in.pdf -o imgs/ --pages 1-2` |
| `version` | 打印版本（等价 `--version`） | `beecmd version` |

页码统一 **1 基**，支持 `1`、`1-3`、`3-`、`-3`、`1,3-5,7-`、`all`。

## 2. 安全/正确性约束（测试锁住）

- **不改源文件**：所有操作都生成新路径；`test_source_pdf_never_modified` 用字节比对锁住；
- **加密不是破解**：只支持「写入」打开密码/权限（AES-256），不做解密/破解/签名验签；
  已加密的输入文件会明确报错「需要先解密」而不是静默失败；
- **坏输入不崩溃**：不存在/损坏/已加密/页码越界都抛 `PdfToolError`，CLI 以非 0 退出码返回；
- **中文水印**：使用 PyMuPDF 内置 CJK 字体（`china-s`），否则 `helv` 会渲染成 `????`；
- 页数/密码/水印文字均有产物级断言（`tests/fidelity/test_beecmd_pdf_tools.py`，13 条）。

## 3. 验证

```powershell
cd D:\beeofficeV
$env:PYTHONPATH='D:\beeofficeV'; $env:PYTHONIOENCODING='utf-8'
python -m pytest tests/fidelity/test_beecmd_pdf_tools.py -q      # 13 passed
python -m beeoffice.beecmd version                              # beecmd 0.5.0

# 手工验收（任意 PDF）
python -m beeoffice.beecmd pdf-split "某.pdf" -o out/
python -m beeoffice.beecmd pdf-watermark "某.pdf" -o wm.pdf --text 内部资料
python -m beeoffice.beecmd pdf-encrypt "某.pdf" -o locked.pdf --user-password pw123
```

## 4. 与 WPS 会员的对应关系

| WPS 会员能力 | BeeOffice | 说明 |
|---|---|---|
| PDF 合并 / 拆分 / 提取 / 删除页 | ✅ `pdf-merge/split/extract/delete` | 命令行 + 可脚本化（BeeOffice 差异化） |
| PDF 加密/权限（限打印/复制） | ✅ `pdf-encrypt` | AES-256；不提供破解 |
| PDF 水印 | ✅ `pdf-watermark` | 文本水印，支持中文 |
| PDF 提取文字/图片 | ✅ `pdf-text/images` | 图片按原格式导出 |
| PDF 转 Word/Excel/PPT、OCR、版面编辑 | ❌ 不做 | 云服务+模型+排版引擎，ROI 不成立 |

## 5. 限制

- 水印是**文字平铺**（居中、半透明），不做倾斜/图片水印/骑缝章；图片签名/图章在下一批；
- 加密只支持 AES-256；不读取/修改已有加密文档的权限；
- 独立 `beecmd.exe` 包仍为 v0.4.0（本次是源码命令）；发布新 GUI 版本时会重新打包 CLI 并校验 SHA-256。
