# -*- coding: utf-8 -*-
"""S4 UI 审计：盘点菜单、快捷键、工具栏与可访问性缺口。

用法：
    python tools/ui_audit.py --json _ptmp/analysis/ui_audit.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    args = ap.parse_args()

    from PySide6.QtWidgets import (
        QApplication, QComboBox, QLineEdit, QMessageBox, QPushButton,
        QToolButton,
    )

    for meth in ("warning", "critical", "information", "question"):
        setattr(QMessageBox, meth, staticmethod(lambda *a, **k: QMessageBox.Ok))

    app = QApplication.instance() or QApplication([])
    from beeoffice.app import BeeApp

    window = BeeApp()
    window._lazy_load_modules()
    window.show()
    window._new_beewrite()
    window._new_beesheet()
    window._new_beeshow()
    app.processEvents()

    menus = []
    shortcuts = defaultdict(list)

    def walk_menu(menu, path):
        for action in menu.actions():
            if action.isSeparator():
                continue
            text = action.text().replace("&", "")
            sub = action.menu()
            item = {
                "menu": path,
                "text": text,
                "shortcut": action.shortcut().toString(),
                "enabled": action.isEnabled(),
                "has_submenu": bool(sub),
            }
            menus.append(item)
            key = item["shortcut"]
            if key:
                shortcuts[key].append(f"{path}/{text}")
            if sub:
                walk_menu(sub, f"{path}/{text}" if text else path)

    walk_menu(window.menuBar(), "菜单栏")

    duplicate_shortcuts = {
        key: names for key, names in shortcuts.items() if len(names) > 1
    }

    class_counts = Counter(w.__class__.__name__ for w in QApplication.allWidgets())
    interactive = []
    for w in QApplication.allWidgets():
        if not isinstance(w, (QPushButton, QToolButton, QLineEdit, QComboBox)):
            continue
        if not w.isVisible():
            continue
        name = w.accessibleName()
        text = ""
        for attr in ("text", "currentText", "placeholderText"):
            try:
                text = getattr(w, attr)() or text
            except Exception:
                pass
        if not name and not text:
            interactive.append(w.__class__.__name__)

    result = {
        "menu_actions": len(menus),
        "menu_items": menus,
        "shortcut_count": len(shortcuts),
        "duplicate_shortcuts": duplicate_shortcuts,
        "widget_class_counts": dict(class_counts.most_common()),
        "visible_interactive_without_name": dict(Counter(interactive)),
        "visible_interactive_without_name_total": len(interactive),
    }
    Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("menu_items", "widget_class_counts")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
