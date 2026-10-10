# tests/regression/v5/test_v505_annotation_backup_persistence.py
"""
优化规划 §1.8 回归：消除「用户以为存住了、其实没有」的静默失败。

覆盖三处：
  1. Annotation.from_dict 缺字段即 KeyError → 旁挂文件里一条坏数据会让
     **整份**批注都读不出来。现在所有字段都有默认值。
  2. PDFAnnotator 原本没有 closeEvent → 关窗即静默丢弃未保存的批注。
  3. 蜜算自动备份原本写在 ~/.beeoffice_backups/ 且失败 `except: pass`：
     表格明文长期驻留主目录、关闭文档不清理、失败无提示。
"""
import json

import fitz
import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from beeoffice.plugins.pdf_annotator import Annotation, PDFAnnotator


@pytest.fixture(autouse=True)
def _no_modal(monkeypatch):
    """headless 下把提示框换成记录器，避免模态框挂死测试。"""
    shown = []

    def _record(*args, **kwargs):
        shown.append(args)
        return QMessageBox.Ok

    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(_record))
    return shown


def _make_pdf(path):
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()
    return path


# ==================== 1. from_dict 的容错 ====================

class TestAnnotationFromDict:
    def test_full_dict_roundtrip(self):
        a = Annotation(2, fitz.Rect(1, 2, 3, 4), "underline", "hello", (0.1, 0.2, 0.3))
        b = Annotation.from_dict(a.to_dict())
        assert b.page == 2
        assert b.type == "underline"
        assert b.text == "hello"
        assert tuple(round(c, 3) for c in b.color) == (0.1, 0.2, 0.3)

    def test_missing_color_uses_default(self):
        """原实现 data["color"] 会直接 KeyError 并毁掉整份文件。"""
        a = Annotation.from_dict(
            {"page": 1, "rect": [0, 0, 10, 10], "type": "highlight"}
        )
        assert a.color == (1, 1, 0)
        assert a.text == ""

    def test_missing_page_and_type(self):
        a = Annotation.from_dict({"rect": [0, 0, 1, 1]})
        assert a.page == 0
        assert a.type == "highlight"

    def test_bad_rect_falls_back(self):
        a = Annotation.from_dict({"page": 0, "rect": "not-a-rect"})
        assert a.rect.is_empty or a.rect.width == 0

    def test_bad_color_falls_back(self):
        a = Annotation.from_dict({"page": 0, "rect": [0, 0, 1, 1], "color": [1, 2]})
        assert a.color == (1, 1, 0)

    def test_non_dict_raises(self):
        with pytest.raises(ValueError):
            Annotation.from_dict(["not", "a", "dict"])


# ==================== 2. 旁挂文件读取：坏条目不得拖垮整份 ====================

class TestLoadAnnotations:
    def test_bad_entry_skipped_others_kept(self, qapp, tmp_path):
        pdf = _make_pdf(tmp_path / "doc.pdf")
        anno_file = tmp_path / "doc.beeanno"
        anno_file.write_text(
            json.dumps([
                {"page": 0, "rect": [1, 1, 5, 5], "type": "highlight",
                 "text": "", "color": [1, 1, 0]},
                ["this entry is garbage"],
                {"page": 0, "rect": [2, 2, 6, 6], "type": "underline",
                 "text": "", "color": [0, 0, 1]},
            ], ensure_ascii=False),
            encoding="utf-8",
        )

        annotator = PDFAnnotator()
        annotator.open_pdf(str(pdf))

        assert len(annotator._annotations) == 2, (
            "坏条目只应跳过自己，其余批注必须保留"
        )
        assert annotator._doc is not None, "旁挂文件有问题不应导致 PDF 打不开"
        annotator.close()

    def test_new_dict_format_loads(self, qapp, tmp_path):
        pdf = _make_pdf(tmp_path / "doc2.pdf")
        (tmp_path / "doc2.beeanno").write_text(
            json.dumps({
                "version": 1,
                "annotations": [
                    {"page": 0, "rect": [0, 0, 4, 4], "type": "highlight",
                     "text": "x", "color": [1, 1, 0]},
                ],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        annotator = PDFAnnotator()
        annotator.open_pdf(str(pdf))
        assert len(annotator._annotations) == 1
        annotator.close()

    def test_unparseable_sidecar_still_opens_pdf(self, qapp, tmp_path):
        pdf = _make_pdf(tmp_path / "doc3.pdf")
        (tmp_path / "doc3.beeanno").write_text("{ not json", encoding="utf-8")

        annotator = PDFAnnotator()
        annotator.open_pdf(str(pdf))

        assert annotator._doc is not None, "旁挂文件坏了也必须能打开 PDF"
        assert annotator._annotations == []
        annotator.close()

    def test_save_then_reload_roundtrip(self, qapp, tmp_path):
        pdf = _make_pdf(tmp_path / "doc4.pdf")
        annotator = PDFAnnotator()
        annotator.open_pdf(str(pdf))
        annotator._annotations = [
            Annotation(0, fitz.Rect(1, 1, 9, 9), "highlight", "note", (1, 0.5, 0))
        ]
        annotator._save_annotations()
        annotator.close()

        again = PDFAnnotator()
        again.open_pdf(str(pdf))
        assert len(again._annotations) == 1
        assert again._annotations[0].text == "note"
        again.close()


# ==================== 3. 关闭前保护未保存批注 ====================

class TestCloseEvent:
    def test_no_prompt_when_clean(self, qapp, monkeypatch):
        def _boom(*a, **k):
            raise AssertionError("没有脏批注时不应弹确认框")

        monkeypatch.setattr(QMessageBox, "question", staticmethod(_boom))
        annotator = PDFAnnotator()
        annotator._annotations = []
        ev = QCloseEvent()
        annotator.closeEvent(ev)
        assert ev.isAccepted()

    def test_no_prompt_when_not_visible(self, qapp, monkeypatch):
        """
        未 show() 的窗口（headless 测试）不应弹模态框——否则会把测试挂死。
        """
        def _boom(*a, **k):
            raise AssertionError("窗口未显示时不应弹确认框")

        monkeypatch.setattr(QMessageBox, "question", staticmethod(_boom))
        annotator = PDFAnnotator()
        annotator._annotations = [Annotation(0, fitz.Rect(0, 0, 1, 1))]
        annotator._dirty_annotations = True
        ev = QCloseEvent()
        annotator.closeEvent(ev)
        assert ev.isAccepted()

    def test_undo_marks_dirty(self, qapp, tmp_path):
        """撤销过批注就应被视为有未保存改动。"""
        pdf = _make_pdf(tmp_path / "doc5.pdf")
        annotator = PDFAnnotator()
        annotator.open_pdf(str(pdf))
        annotator._annotations = [Annotation(0, fitz.Rect(0, 0, 1, 1))]
        annotator._dirty_annotations = False

        annotator._undo_annotation()

        assert annotator._dirty_annotations is True
        annotator.close()

    def test_close_event_cancel_keeps_window(self, qapp, monkeypatch):
        """选择「取消」时窗口不应关闭。"""
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: QMessageBox.Cancel),
        )
        annotator = PDFAnnotator()
        annotator._annotations = [Annotation(0, fitz.Rect(0, 0, 1, 1))]
        annotator._dirty_annotations = True
        monkeypatch.setattr(PDFAnnotator, "isVisible", lambda self: True)

        ev = QCloseEvent()
        annotator.closeEvent(ev)
        assert not ev.isAccepted(), "用户取消后不应关闭窗口"


# ==================== 4. 蜜算自动备份的落点与清理 ====================

class TestSheetBackupHygiene:
    def _host(self, monkeypatch, tmp_path):
        from beeoffice.plugins import beesheet as beesheet_mod
        from beeoffice.plugins.beesheet import BeeSheetView

        monkeypatch.setattr(
            beesheet_mod, "get_app_data_dir", lambda: tmp_path / "appdata"
        )

        class _Host:
            _backup_session_dir = None

            def _set_status(self, *a, **k):
                pass

        host = _Host()
        host._backup_dir = BeeSheetView._backup_dir.__get__(host)
        host._cleanup_backups = BeeSheetView._cleanup_backups.__get__(host)
        return host

    def test_backup_dir_under_app_data_not_home(self, monkeypatch, tmp_path):
        host = self._host(monkeypatch, tmp_path)
        d = host._backup_dir()

        assert str(tmp_path) in str(d), "备份必须落在应用数据目录下"
        assert ".beeoffice_backups" not in str(d), (
            "不得再写入用户主目录 ~/.beeoffice_backups"
        )
        assert d.parent.name == "sheet_backups"

    def test_cleanup_removes_backups(self, monkeypatch, tmp_path):
        host = self._host(monkeypatch, tmp_path)
        d = host._backup_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / "backup_20260101_000000.json").write_text("[]", encoding="utf-8")

        host._cleanup_backups()

        assert not d.exists(), "关闭文档时必须删除本次会话的备份"
        assert host._backup_session_dir is None
