# tools/verify_pptx_animations.py
"""PPTX 动画时间轴回归验证（可作门禁）。

默认做**结构化校验**（不需要 PowerPoint）：
  - 每页必须有 p:timing；
  - 必须有 p:bldLst / p:set / grpId / nodeType；
  - 动画数量/切换效果符合预期。

加 `--powerpoint` 后用真实 PowerPoint COM 再验一次：
  - MainSequence 效果数；
  - 每个效果的形状、时长、触发类型（1=点击，3=接续）。

用法：
  python tools/verify_pptx_animations.py
  python tools/verify_pptx_animations.py --pptx file.pptx --powerpoint --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sample_pptx(path: Path) -> None:
    from beeoffice.plugins.beeshow_pptx_engine import (
        MeasuredElement, MeasuredSlide, PPTXGenerator,
    )

    ms1 = MeasuredSlide(elements=[
        MeasuredElement(tag="h1", text="标题", x=80, y=80,
                        width=500, height=70, font_size=30),
        MeasuredElement(tag="p", text="正文", x=80, y=190,
                        width=500, height=60, font_size=20),
    ])
    ms2 = MeasuredSlide(elements=[
        MeasuredElement(tag="h1", text="第二页", x=80, y=80,
                        width=500, height=70, font_size=30),
    ])
    PPTXGenerator().generate(
        [ms1, ms2], str(path),
        transitions=["fade", "wipe"],
        element_animations=[
            {"pptx_element": True, "click_each": False, "entries": [
                {"selector": "h1", "effect": "fade_in",
                 "duration": 600, "delay": 0},
                {"selector": "p", "effect": "fade_in",
                 "duration": 400, "delay": 300},
                {"selector": "h1", "effect": "pulse",
                 "duration": 300, "delay": 0},
            ]},
            {"pptx_element": True, "click_each": True, "entries": [
                {"selector": "h1", "effect": "shake",
                 "duration": 500, "delay": 0},
            ]},
        ],
    )


def _slide_xml(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist()
                       if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
        return [z.read(n).decode("utf-8", errors="replace") for n in names]


def verify_structure(path: Path) -> dict:
    slides = _slide_xml(path)
    checks = []
    if len(slides) != 2:
        checks.append({"name": "幻灯片数", "ok": False, "detail": len(slides)})
    for i, xml in enumerate(slides, 1):
        checks.append({
            "name": f"第{i}页 p:timing",
            "ok": "<p:timing>" in xml,
            "detail": "",
        })
        checks.append({
            "name": f"第{i}页 bldLst/set/grpId",
            "ok": all(k in xml for k in
                      ("<p:bldLst>", "<p:set>", "grpId=")),
            "detail": "",
        })
        checks.append({
            "name": f"第{i}页 切换效果",
            "ok": "<p:transition" in xml,
            "detail": "",
        })
    s1 = slides[0] if slides else ""
    checks.append({
        "name": "第1页 3 个动画、自动接续",
        "ok": s1.count("<p:animEffect ") + s1.count("<p:animScale") >= 3
              and 'nodeType="afterEffect"' in s1,
        "detail": "",
    })
    s2 = slides[1] if len(slides) > 1 else ""
    checks.append({
        "name": "第2页 点击触发（indefinite）",
        "ok": 'delay="indefinite"' in s2 and 'nodeType="clickEffect"' in s2,
        "detail": "",
    })
    return {"file": str(path), "checks": checks,
            "ok": all(c["ok"] for c in checks)}


def verify_powerpoint(path: Path) -> dict:
    try:
        import win32com.client
    except ImportError as e:
        return {"ok": False, "checks": [
            {"name": "PowerPoint COM", "ok": False, "detail": str(e)}]}

    app = win32com.client.DispatchEx("PowerPoint.Application")
    checks = []
    try:
        pres = app.Presentations.Open(str(path), ReadOnly=True,
                                      WithWindow=False)
        for i in range(1, pres.Slides.Count + 1):
            seq = pres.Slides(i).TimeLine.MainSequence
            effects = [seq.Item(j) for j in range(1, seq.Count + 1)]
            checks.append({
                "name": f"第{i}页 MainSequence 效果数",
                "ok": bool(effects),
                "detail": seq.Count,
            })
            for eff in effects:
                checks.append({
                    "name": f"第{i}页 {eff.Shape.Name} 时长/触发",
                    "ok": eff.Timing.Duration > 0
                          and eff.Timing.TriggerType in (1, 3),
                    "detail": f"{eff.Timing.Duration:.2f}s "
                              f"trigger={eff.Timing.TriggerType}",
                })
        pres.Close()
    finally:
        try:
            app.Quit()
        except Exception:
            pass
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pptx", type=Path, default=None)
    ap.add_argument("--powerpoint", action="store_true")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    path = args.pptx
    tmp = None
    if path is None:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".pptx", delete=False)
        tmp.close()
        path = Path(tmp.name)
        _sample_pptx(path)

    result = verify_structure(path)
    if args.powerpoint:
        result["powerpoint"] = verify_powerpoint(path)
        result["ok"] = result["ok"] and result["powerpoint"]["ok"]

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    if tmp:
        Path(tmp.name).unlink(missing_ok=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
