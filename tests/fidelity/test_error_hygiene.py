# tests/fidelity/test_error_hygiene.py
"""
异常卫生（审计 §2.7 / §4 第 4 项）：**新增代码禁用裸 except**。

## 为什么
仓库里有 **170 处** `except:` / `except Exception:`（历史债）。
它们会在开发期掩盖真实异常 —— 这轮审计里就被"宽泛 except 吞掉日志"坑过
（比如 `_write_docx` 返回 True 但写出空文档、`_has_status` 漏定义被吞）。

全量改存量风险太大（且会污染 diff），所以本文件只对**新增模块**上规矩：
* 不允许裸 `except:`
* 不允许 `except Exception:` / `except BaseException:`，除非显式标注
  `# noqa: BLE001`（表示"这里确实要兜底，且已审查"）
* 不允许 `except Exception` 后**静默 pass**（必须记日志或返回可观察结果）

## 适用范围
`NEW_MODULES`（新增模块清单）。以后写新模块，加进来即可；
**存量文件不在本门禁范围内**（这是有意的取舍，写在这里避免误解）。
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 新增模块（审计后要求：异常处理有明确意图）
NEW_MODULES = [
    "beeoffice/drafts.py",
    "beeoffice/beecmd.py",
    "beeoffice/plugins/ai_errors.py",
    "beeoffice/plugins/beeshow_pptx_import.py",
]

BARE_EXCEPT = re.compile(r"^\s*except\s*:\s*(#.*)?$")
BROAD_EXCEPT = re.compile(
    r"^\s*except\s+(Exception|BaseException)\s*(as\s+\w+)?\s*:\s*(#.*)?$"
)
NOQA = "noqa: BLE001"


def _lines(path: Path):
    return path.read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("rel", NEW_MODULES)
def test_no_bare_except(rel):
    """裸 `except:` 一律禁止（会把 KeyboardInterrupt/SystemExit 也吞掉）。"""
    hits = [
        f"{rel}:{i}: {line.strip()}"
        for i, line in enumerate(_lines(ROOT / rel), 1)
        if BARE_EXCEPT.match(line)
    ]
    assert not hits, "发现裸 except：\n" + "\n".join(hits)


@pytest.mark.parametrize("rel", NEW_MODULES)
def test_broad_except_must_be_marked(rel):
    """宽泛 except 必须显式 `# noqa: BLE001`（= 已审查的兜底）。"""
    hits = []
    for i, line in enumerate(_lines(ROOT / rel), 1):
        if BROAD_EXCEPT.match(line) and NOQA not in line:
            hits.append(f"{rel}:{i}: {line.strip()}")
    assert not hits, (
        "宽泛 except 缺少 `# noqa: BLE001` 标注（说明为什么必须兜底）：\n"
        + "\n".join(hits)
    )


@pytest.mark.parametrize("rel", NEW_MODULES)
def test_broad_except_does_not_silently_pass(rel):
    """
    **宽泛** except 后紧跟 `pass` 要禁止（= 把真异常吞掉）。
    具体异常（`except OSError: pass`）不在此列 —— 那是明确的预期分支。
    """
    lines = _lines(ROOT / rel)
    offenders = []
    for i, line in enumerate(lines):
        if not BROAD_EXCEPT.match(line):
            continue
        for offset in (1, 2):
            if i + offset >= len(lines):
                break
            body = lines[i + offset].strip()
            if not body:
                continue
            if body == "pass":
                offenders.append(
                    f"{rel}:{i + offset + 1}: 宽泛 except 后静默 pass"
                )
            break
    assert not offenders, "静默吞异常：\n" + "\n".join(offenders)


def test_module_list_is_not_empty():
    """防止有人把清单清空让本门禁形同虚设。"""
    assert len(NEW_MODULES) >= 3
    for rel in NEW_MODULES:
        assert (ROOT / rel).is_file(), f"清单里的文件不存在：{rel}"
