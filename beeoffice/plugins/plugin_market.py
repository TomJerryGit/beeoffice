# beeoffice/plugins/plugin_market.py
"""
插件市场：展示已安装插件、安装本地插件、卸载插件

v5.0.1 修复（P1-6）：
  - _on_enabled_changed 改用 int(state) == 2 判断启用状态
    原实现 `state == Qt.Checked.value or state == 2` 在 PySide6 6.x
    上 Qt.Checked 位于 Qt.CheckState 枚举下，不同版本 .value 行为
    不一致，可能 AttributeError 或误判。
    stateChanged 信号始终传递 int（0=Unchecked, 1=Partial, 2=Checked），
    直接用 int 比较最安全。
"""
import logging
import zipfile
import tempfile
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMessageBox, QFileDialog, QGroupBox,
    QTextEdit, QSplitter, QCheckBox, QWidget
)
from PySide6.QtCore import Qt


class PluginMarketDialog(QDialog):
    """插件市场对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("🔌 插件市场")
        self.resize(720, 520)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 顶部说明
        tip_label = QLabel("管理已安装的插件。插件目录：beeoffice/plugins/")
        tip_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(tip_label)

        # 主体：左侧列表 + 右侧详情
        splitter = QSplitter(Qt.Horizontal)

        # ---- 左侧：插件列表 ----
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("已安装插件："))
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setStyleSheet(
            "QListWidget::item { padding: 8px; } "
            "QListWidget::item:selected { background: #FFE0A0; color: #000; }"
        )
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        left_layout.addWidget(self.list_widget)

        splitter.addWidget(left_widget)

        # ---- 右侧：插件详情 ----
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_layout.addWidget(QLabel("插件详情："))
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setStyleSheet(
            "QTextEdit { font-size: 13px; padding: 8px; "
            "background: #FAFAFA; border: 1px solid #DDD; border-radius: 6px; }"
        )
        right_layout.addWidget(self.detail_text)

        # 启用/禁用
        self.enabled_check = QCheckBox("启用此插件")
        self.enabled_check.stateChanged.connect(self._on_enabled_changed)
        right_layout.addWidget(self.enabled_check)

        splitter.addWidget(right_widget)
        splitter.setSizes([300, 400])
        layout.addWidget(splitter)

        # ---- 底部按钮栏 ----
        btn_layout = QHBoxLayout()

        self.install_btn = QPushButton("📦 安装插件")
        self.install_btn.clicked.connect(self._install_plugin)
        btn_layout.addWidget(self.install_btn)

        self.uninstall_btn = QPushButton("🗑 卸载插件")
        self.uninstall_btn.clicked.connect(self._uninstall_plugin)
        btn_layout.addWidget(self.uninstall_btn)

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self._refresh_list)
        btn_layout.addWidget(self.refresh_btn)

        btn_layout.addStretch()

        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

        # 初始加载
        self._refresh_list()

    # ---------- 刷新列表 ----------
    def _refresh_list(self):
        """重新加载插件列表"""
        self.list_widget.clear()
        self.detail_text.clear()
        self.enabled_check.setEnabled(False)

        plugin_manager = getattr(self.parent, "plugin_manager", None)
        if plugin_manager is None:
            item = QListWidgetItem("插件管理器未初始化")
            item.setFlags(Qt.NoItemFlags)
            self.list_widget.addItem(item)
            return

        if not plugin_manager.plugin_info:
            item = QListWidgetItem("（暂无已安装插件）")
            item.setFlags(Qt.NoItemFlags)
            self.list_widget.addItem(item)
            return

        for info in plugin_manager.plugin_info:
            name = info.get("name", "未命名")
            version = info.get("version", "?")
            enabled = info.get("enabled", True)
            prefix = "✅" if enabled else "⛔"
            item = QListWidgetItem(f"{prefix} {name}  v{version}")
            item.setData(Qt.UserRole, info)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    # ---------- 列表选中 ----------
    def _on_item_changed(self, current, previous):
        """选中插件时更新详情"""
        if current is None:
            self.detail_text.clear()
            self.enabled_check.setEnabled(False)
            return

        info = current.data(Qt.UserRole)
        if not info:
            self.detail_text.clear()
            self.enabled_check.setEnabled(False)
            return

        # 显示详情
        name = info.get("name", "未命名")
        version = info.get("version", "?")
        description = info.get("description", "无描述")
        author = info.get("author", "未知")
        enabled = info.get("enabled", True)

        detail_html = f"""
        <h3 style="color:#FF8F00;">{name}</h3>
        <p><b>版本：</b>{version}</p>
        <p><b>作者：</b>{author}</p>
        <p><b>描述：</b>{description}</p>
        <p><b>状态：</b>{"已启用" if enabled else "已禁用"}</p>
        """
        self.detail_text.setHtml(detail_html)

        # 更新复选框状态
        self.enabled_check.blockSignals(True)
        self.enabled_check.setChecked(enabled)
        self.enabled_check.setEnabled(True)
        self.enabled_check.blockSignals(False)

    # ---------- 启用/禁用（P1-6 修复） ----------
    def _on_enabled_changed(self, state):
        """
        切换插件启用状态

        P1-6 修复：
          原实现 `state == Qt.Checked.value or state == 2` 在 PySide6 6.x
          上可能 AttributeError（Qt.Checked 在 6.x 里位于 Qt.CheckState
          枚举下）。
          stateChanged 信号始终传递 int：
            0 = Unchecked
            1 = PartiallyChecked
            2 = Checked
          直接用 int(state) == 2 判断，跨版本稳定。
        """
        current = self.list_widget.currentItem()
        if current is None:
            return
        info = current.data(Qt.UserRole)
        if not info:
            return

        # P1-6：stateChanged 传的是 int（0=Unchecked, 1=Partial, 2=Checked）
        # 不用 Qt.Checked.value，避免 PySide6 版本差异
        enabled = (int(state) == 2)

        plugin = info.get("instance")
        if plugin and hasattr(plugin, "set_enabled"):
            try:
                plugin.set_enabled(enabled)
                info["enabled"] = enabled
                # 更新列表显示
                name = info.get("name", "未命名")
                version = info.get("version", "?")
                prefix = "✅" if enabled else "⛔"
                current.setText(f"{prefix} {name}  v{version}")
                logging.info(
                    f"插件 {name} 已{'启用' if enabled else '禁用'}"
                )
            except Exception as e:
                logging.error(f"切换插件状态失败: {e}")
                QMessageBox.warning(self, "失败", f"切换状态失败：{e}")

    # ---------- 安装插件 ----------
    def _install_plugin(self):
        """从 ZIP 文件或目录安装插件"""
        # 选择方式
        reply = QMessageBox.question(
            self, "安装插件",
            "选择安装方式：\n\n"
            "是(Y) — 从 ZIP 文件安装\n"
            "否(N) — 从文件夹安装",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Cancel:
            return

        if reply == QMessageBox.Yes:
            self._install_from_zip()
        else:
            self._install_from_dir()

    def _install_from_zip(self):
        """从 ZIP 文件安装插件"""
        zip_path, _ = QFileDialog.getOpenFileName(
            self, "选择插件压缩包", "",
            "插件包 (*.zip *.beeplugin);;所有文件 (*)"
        )
        if not zip_path:
            return

        try:
            # 解压到临时目录
            with tempfile.TemporaryDirectory() as tmp_dir:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(tmp_dir)

                # 查找插件主文件（包含 Plugin 子类的 .py 文件）
                tmp_path = Path(tmp_dir)
                py_files = list(tmp_path.rglob("*.py"))
                if not py_files:
                    QMessageBox.warning(self, "安装失败", "插件包中没有 Python 文件")
                    return

                # 复制到 plugins 目录
                plugins_dir = Path(__file__).parent
                installed = 0
                for py_file in py_files:
                    # 跳过 __init__.py
                    if py_file.name == "__init__.py":
                        continue
                    # 检查是否包含 Plugin 子类
                    if not self._contains_plugin_class(py_file):
                        continue
                    dest = plugins_dir / py_file.name
                    if dest.exists():
                        reply = QMessageBox.question(
                            self, "文件已存在",
                            f"插件 {py_file.name} 已存在，是否覆盖？",
                            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                        )
                        if reply != QMessageBox.Yes:
                            continue
                    self._install_file(py_file, dest)
                    installed += 1

                if installed > 0:
                    QMessageBox.information(
                        self, "安装完成",
                        f"已安装 {installed} 个插件文件。\n\n"
                        f"请重启应用以加载新插件。"
                    )
                    self._refresh_list()
                else:
                    QMessageBox.warning(
                        self, "未安装",
                        "插件包中未找到有效的插件（无 Plugin 子类）"
                    )
        except zipfile.BadZipFile:
            QMessageBox.warning(self, "安装失败", "无效的 ZIP 文件")
        except Exception as e:
            logging.error(f"安装插件失败: {e}")
            QMessageBox.warning(self, "安装失败", str(e))

    def _install_from_dir(self):
        """从目录安装插件"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择插件目录")
        if not dir_path:
            return

        try:
            src_dir = Path(dir_path)
            py_files = list(src_dir.rglob("*.py"))
            if not py_files:
                QMessageBox.warning(self, "安装失败", "目录中没有 Python 文件")
                return

            plugins_dir = Path(__file__).parent
            installed = 0
            for py_file in py_files:
                if py_file.name == "__init__.py":
                    continue
                if not self._contains_plugin_class(py_file):
                    continue
                dest = plugins_dir / py_file.name
                if dest.exists():
                    reply = QMessageBox.question(
                        self, "文件已存在",
                        f"插件 {py_file.name} 已存在，是否覆盖？",
                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                    )
                    if reply != QMessageBox.Yes:
                        continue
                self._install_file(py_file, dest)
                installed += 1

            if installed > 0:
                QMessageBox.information(
                    self, "安装完成",
                    f"已安装 {installed} 个插件文件。\n\n"
                    f"请重启应用以加载新插件。"
                )
                self._refresh_list()
            else:
                QMessageBox.warning(
                    self, "未安装",
                    "目录中未找到有效的插件（无 Plugin 子类）"
                )
        except Exception as e:
            logging.error(f"安装插件失败: {e}")
            QMessageBox.warning(self, "安装失败", str(e))

    @staticmethod
    def _contains_plugin_class(py_file: Path) -> bool:
        """快速检查 Python 文件是否包含 Plugin 子类定义"""
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            return "Plugin" in content and "class " in content
        except Exception:
            return False

    # ---------- 用户安装标记 ----------
    # 安全（P0）：插件市场会把文件直接复制进 beeoffice/plugins/，
    # 与内置插件混在同一个目录。原实现的"卸载"会无条件 file_path.unlink()，
    # 于是用户点一次"卸载 蜜写"，beewrite_plugin.py 就从源码目录消失了。
    # 现在只删除带此标记的文件（由插件市场安装时写入）。
    _USER_PLUGIN_MARKER = "# BEEOFFICE_USER_PLUGIN: installed by plugin market"

    @classmethod
    def _is_user_installed(cls, path: Path) -> bool:
        """判断某个插件文件是否由插件市场安装（可安全删除）。"""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(4096)
            return head.lstrip("\ufeff").startswith(cls._USER_PLUGIN_MARKER)
        except Exception:
            return False

    @classmethod
    def _install_file(cls, src: Path, dest: Path) -> None:
        """复制插件文件并写入"用户安装"标记（用于区分内置插件）。"""
        data = src.read_bytes()
        marker = cls._USER_PLUGIN_MARKER.encode("utf-8") + b"\n"
        if not data.startswith(marker):
            data = marker + data
        dest.write_bytes(data)

    # ---------- 卸载插件 ----------
    def _uninstall_plugin(self):
        """卸载当前选中的插件（内置插件只允许禁用，不允许删除源文件）"""
        current = self.list_widget.currentItem()
        if current is None:
            QMessageBox.information(self, "提示", "请先选择一个插件")
            return

        info = current.data(Qt.UserRole)
        if not info:
            return

        name = info.get("name", "未命名")

        # 先判定目标文件能否删除，再决定是否真的卸载
        instance = info.get("instance")
        file_path = None
        if instance is not None:
            module = instance.__class__.__module__
            if module.startswith("beeoffice.plugins."):
                candidate = (
                    Path(__file__).parent / (module.split(".")[-1] + ".py")
                )
                if candidate.exists():
                    if not self._is_user_installed(candidate):
                        QMessageBox.information(
                            self, "无法卸载",
                            f"「{name}」是内置插件，不能删除源文件。\n\n"
                            f"如需停用，请使用右侧的「启用此插件」开关；\n"
                            f"内置插件文件位于：\n{candidate}"
                        )
                        return
                    file_path = candidate

        reply = QMessageBox.question(
            self, "卸载插件",
            f"确定要卸载插件「{name}」吗？\n\n"
            f"这会删除插件文件，且不可恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # 从插件管理器卸载
        plugin_manager = getattr(self.parent, "plugin_manager", None)
        if plugin_manager:
            try:
                plugin_manager.unload_plugin(name)
            except Exception as e:
                logging.error(f"从管理器卸载失败: {e}")

        # 删除插件文件（仅用户安装的）
        if file_path is not None:
            try:
                file_path.unlink()
                logging.info(f"已删除插件文件: {file_path}")
            except Exception as e:
                logging.error(f"删除插件文件失败: {e}")
                QMessageBox.warning(
                    self, "删除失败",
                    f"插件已停用，但文件删除失败：\n{e}"
                )

        QMessageBox.information(self, "已卸载", f"插件「{name}」已卸载。")
        self._refresh_list()

    # ---------- 关闭 ----------
    def closeEvent(self, event):
        """关闭时保存状态"""
        event.accept()


def show_plugin_market(parent):
    """
    显示插件市场对话框（对外入口）
    :param parent: 主窗口实例（BeeApp）
    """
    try:
        dialog = PluginMarketDialog(parent)
        dialog.exec()
    except Exception as e:
        logging.error(f"打开插件市场失败: {e}")
        QMessageBox.warning(parent, "错误", f"打开插件市场失败：\n{e}")