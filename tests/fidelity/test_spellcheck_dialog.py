# tests/fidelity/test_spellcheck_dialog.py
"""
蜜写拼写检查对话框（P1-B ★，**按需**形态）。

## 为什么是"按需"而不是"常驻标红"
装上真英文词典后，对 `tests/fidelity/corpus/` 里 7 份**真实中文技术文档**
逐字实测，**误报 619 处**（`CentOS`/`mysql`/`yum`/`Xshell`/`VMware`/`ens33` 全被判错）：

    CentOS7 环境 mysql 的安装与使用  313
    yum 源更新                      217
    修改 Centos7 网卡 ens33 → eth0   60
    Win710 上使用 Xshell …           18
    Xshell 连接 VMware …             10
    Linux 系统 CentOS7 …              1
    Linux 安装 win764                 0

常驻红波浪线 = 用户满屏红字。所以形态是：**用户主动点** → 列表 → 逐条处理，
并提供「全部忽略」「加入词典」（写入 `~/.beeoffice_dictionary.txt` 永久生效）。

## 怎么测（本机没有可用后端）
对话框完全靠**依赖注入**：`service` 可传桩后端、`apply_replace` 由测试记录调用。
于是"列表内容/替换/忽略/加入词典/定位"都能**确定性**验证，
不需要真的英文词典，也不需要打开编辑器。

（拼写核心模块本身的测试在 `test_spellcheck.py`，由另一路完成：55 passed 1 skipped。）
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from beeoffice.plugins.beewrite_spellcheck_dialog import (      # noqa: E402
    SpellCheckDialog, user_dictionary_path,
)
from beeoffice.plugins.spellcheck import (                      # noqa: E402
    Misspelling, SpellBackend, SpellCheckerService,
)


class StubBackend(SpellBackend):
    """只认几个词的桩后端（确定性，不依赖任何词典）。"""

    name = "stub"
    available = True

    def __init__(self, known=("the", "hello", "world", "receive")):
        self.known = {w.lower() for w in known}

    def check(self, word):
        # ⚠️ 服务实际调用的是 `check()`，不是 `check_word()` ——
        # 我第一版只实现了 check_word，结果一个词都没报出来（异常被
        # 服务吞掉并按"正确"处理），列表恒为空。
        return word.lower() in self.known

    def suggest(self, word):
        if word.lower() == "recieve":
            return ["receive", "relieve"]
        if word.lower() == "teh":
            return ["the"]
        return []


@pytest.fixture(autouse=True)
def _no_modal_dialogs(monkeypatch):
    """
    拦截所有模态提示框。

    为什么必须有：`replace_all()` 在没有可替换建议时会弹
    `QMessageBox.information` —— 测试里没人点确定，**整个用例会挂死**
    （我第一次跑就是在这里超时的）。
    """
    from PySide6.QtWidgets import QMessageBox

    shown = []
    for name in ("information", "warning", "critical"):
        monkeypatch.setattr(
            QMessageBox, name,
            staticmethod(lambda *a, **k: shown.append(a)),
        )
    return shown


def make_service(dictionary=None):
    return SpellCheckerService(backend=StubBackend(), dictionary=dictionary)


@pytest.fixture
def dialog(qtbot, tmp_path):
    """造一个对话框：文本固定、替换动作被记录下来。"""
    calls = []

    def apply_replace(start, end, replacement):
        calls.append((start, end, replacement))

    text = "hello recieve the world teh"
    dlg = SpellCheckDialog(
        None, make_service(), text, apply_replace,
        dictionary_path=tmp_path / "dict.txt",
        text_provider=lambda: text,
    )
    qtbot.addWidget(dlg)
    dlg.calls = calls
    yield dlg
    dlg.close()


# ==================== 1. 列表内容 ====================

def test_lists_only_unknown_words(dialog):
    words = [item.word for item in dialog.items]

    assert words == ["recieve", "teh"], f"列出的词不对: {words}"
    assert dialog.table.rowCount() == 2


def test_summary_mentions_count(dialog):
    assert "2" in dialog.summary.text()


def test_suggestions_are_shown_in_combo(dialog):
    combo = dialog.table.cellWidget(0, 1)
    assert combo.currentText() == "receive", "第一条应预选 'receive'"


def test_positions_are_accurate(dialog):
    """位置必须能对上原文本 —— 替换靠它定位，错了会改坏文档。"""
    text = dialog.text

    for item in dialog.items:
        assert text[item.start:item.end] == item.word, (
            f"{item.word} 的下标 ({item.start},{item.end}) 取到 "
            f"{text[item.start:item.end]!r}"
        )


def test_line_number_is_reported(dialog):
    multi = SpellCheckDialog(
        None, make_service(), "第一行\n第二行 recieve 在这里", lambda *a: None,
        dictionary_path=Path("x.txt"),
    )
    try:
        assert multi.items[0].start > 0
        assert multi.table.item(0, 2).text() == "第 2 行"
    finally:
        multi.close()


def test_clean_text_reports_done(qtbot):
    dlg = SpellCheckDialog(
        None, make_service(), "hello the world", lambda *a: None,
        dictionary_path=Path("x.txt"),
    )
    qtbot.addWidget(dlg)
    try:
        assert dlg.items == []
        assert "没有发现拼写问题" in dlg.summary.text()
        assert not dlg.replace_btn.isEnabled(), "没有问题时按钮应禁用"
    finally:
        dlg.close()


# ==================== 2. 替换 ====================

def test_replace_current_calls_apply_with_offsets(dialog):
    dialog.table.selectRow(0)
    dialog.replace_current()

    assert dialog.calls == [(6, 13, "receive")], dialog.calls


def test_replace_uses_edited_suggestion(dialog):
    """用户把建议改成别的词，应该按用户输入的替换。"""
    from PySide6.QtWidgets import QComboBox

    # 文本: "hello recieve the world teh"
    #   hello 0-5 / recieve 6-13 / the 14-17 / world 18-23 / teh 24-27
    dialog.table.selectRow(1)
    combo = dialog.table.cellWidget(1, 1)
    assert isinstance(combo, QComboBox)
    combo.setCurrentText("the")
    dialog.replace_current()

    assert dialog.calls == [(24, 27, "the")], dialog.calls


def test_replace_all_replaces_every_suggestion(dialog):
    dialog.replace_all()

    replaced = [call[2] for call in dialog.calls]
    assert replaced == ["receive", "the"], dialog.calls


def test_replace_without_suggestion_warns_and_does_not_replace(
        dialog, monkeypatch):
    """建议为空时：提示用户，且**不能**乱替换。"""
    from PySide6.QtWidgets import QMessageBox

    shown = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *a, **k: shown.append(a)),
    )
    # 把该行的建议清空（用户视角：没有可用建议）
    dialog.table.selectRow(0)
    dialog.table.cellWidget(0, 1).setCurrentText("（无建议）")
    dialog.replace_current()

    assert shown, "没建议时应提示"
    assert dialog.calls == [], "没建议时不该替换"


# ==================== 3. 忽略 / 加入词典 ====================

def test_ignore_all_clears_list(dialog):
    dialog.ignore_all()

    assert dialog.items == [], "全部忽略后不该还有条目"


def test_ignored_word_does_not_come_back(dialog):
    dialog.table.selectRow(0)
    dialog.ignore_current()

    words = [item.word for item in dialog.items]
    assert "recieve" not in words, "忽略过的词又出现了"
    assert "teh" in words


def test_add_to_dictionary_persists_to_file(dialog):
    """**关键**：加入词典要真的落盘，下次打开还生效。"""
    from beeoffice.plugins.spellcheck import load_user_dictionary

    dialog.table.selectRow(0)
    dialog.add_current_to_dictionary()

    saved = load_user_dictionary(dialog.dictionary_path)
    assert "recieve" in saved, f"词典文件里没有该词: {saved}"
    assert dialog.items and dialog.items[0].word == "teh", (
        "加入词典后该词应从列表消失"
    )


def test_add_to_dictionary_keeps_existing_words(dialog):
    """加入新词不能把词典里原有的词冲掉。"""
    from beeoffice.plugins.spellcheck import (
        load_user_dictionary, save_user_dictionary,
    )

    save_user_dictionary(dialog.dictionary_path, ["CentOS", "mysql"])
    dialog.table.selectRow(0)
    dialog.add_current_to_dictionary()

    # 词典按小写归一化（大小写不敏感匹配），所以这里比小写
    saved = {word.lower() for word in load_user_dictionary(
        dialog.dictionary_path)}
    assert {"centos", "mysql", "recieve"} <= saved, saved


def test_dictionary_save_failure_still_ignores(qtbot, tmp_path, monkeypatch):
    """词典存不下时仍要本次生效，并如实告知（不能让检查流程崩掉）。"""
    from beeoffice.plugins import spellcheck as sc

    def boom(*args, **kwargs):
        raise OSError("模拟：字典目录不可写")

    monkeypatch.setattr(sc, "save_user_dictionary", boom)

    dlg = SpellCheckDialog(
        None, make_service(), "hello recieve", lambda *a: None,
        dictionary_path=tmp_path / "dict.txt",
    )
    qtbot.addWidget(dlg)
    try:
        dlg.table.selectRow(0)
        dlg.add_current_to_dictionary()

        assert "recieve" not in [item.word for item in dlg.items]
        assert "失败" in dlg.summary.text()
    finally:
        dlg.close()


# ==================== 4. 定位 ====================

def test_row_selection_triggers_locate(qtbot):
    located = []
    dlg = SpellCheckDialog(
        None, make_service(), "hello recieve", lambda *a: None,
        on_locate=lambda s, e: located.append((s, e)),
        dictionary_path=Path("x.txt"),
    )
    qtbot.addWidget(dlg)
    try:
        dlg.table.selectRow(0)
        assert located == [(6, 13)], located
    finally:
        dlg.close()


# ==================== 5. 不可用后端：入口要如实说明 ====================

def test_entry_point_explains_when_backend_unavailable(qtbot, monkeypatch):
    """
    没有可用词典时要**明确告知原因与启用办法**，不能假装检查过。
    （这是本机的真实情况：Windows 只有 zh-Latn 语言包，无 en 语言包。）
    """
    from PySide6.QtWidgets import QMessageBox

    from beeoffice.plugins.beewrite_export_mixin import ExportMixin

    shown = []
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda parent, title, text, *a, **k: shown.append(
            (title, text))),
    )

    class FakeEditor:
        _spell_service = None
        _edit_mode = "markdown"
        rich_editor = None
        markdown_editor = None

    fake = FakeEditor()
    ExportMixin.spell_check(fake)

    assert shown, "后端不可用时必须给出提示"
    title, text = shown[0]
    assert "不可用" in title
    assert "语言" in text or "pip" in text, "应告知启用办法"


def test_user_dictionary_path_is_beside_settings():
    """用户词典与设置文件同目录（沿用项目约定），便于用户找到/备份。"""
    path = user_dictionary_path()

    assert path.name == ".beeoffice_dictionary.txt"
    assert path.parent == Path.home()
