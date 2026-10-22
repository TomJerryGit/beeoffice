# beeoffice/plugins/beesheet_data_mixin.py
"""
蜜算数据操作 Mixin：导出、筛选、行列操作、批量处理、粘贴、
数据验证、名称管理、智能填充、选中统计
"""
import re
import json
import logging
from pathlib import Path
import pandas as pd
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QListWidget,
    QListWidgetItem, QTextEdit, QMenu, QMessageBox, QFileDialog,
    QApplication, QDialogButtonBox, QInputDialog
)
from PySide6.QtCore import Qt, QPoint, QRect

from beeoffice.plugins.beesheet_commands import (
    EditCellCommand, SortCommand, TrimCommand
)
from beeoffice.utils import atomic_replace


class DataMixin:
    """数据操作相关功能的 Mixin"""

    # ==================== R1 安全门 ====================
    def _ensure_full_data(self, action: str) -> bool:
        """
        **安全门**：会动到"整表"的操作，必须先确保内存里是完整数据。

        为什么必须有（实测，不是推断）：`write_workbook` 是"打开源工作簿、
        只更新值"，拿**部分载入**的数据去写，**后面的行会保留源文件旧值**。
        实测：部分载入 10 行 → 排序 → 保存 → 前 10 行倒序、第 11–40 行旧值，
        **文件内容与界面显示不一致**。
        （见 `tests/fidelity/test_beesheet_lazy_load.py` 的排序那条。）

        **为什么定义在这里而不是视图类上**：既有
        `test_beesheet_export_wiring.py` 用"只混入 `DataMixin` 的精简替身"
        驱动真实的 `_export_xlsx()`。把门放在视图类上会让那个替身报
        AttributeError（我第一版就把 4 条既有测试弄挂了）。放在 mixin 上，
        替身与真实视图都能用，且**只有一处定义**。

        对精简宿主容错：`model` 缺失或没有 `is_fully_loaded` 属性时按
        "已加载完"处理（等价于老行为），避免把测试桩/第三方宿主弄崩。

        :return: True = 可以继续；False = 补全失败（**调用方必须中止**）
        """
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox

        model = getattr(self, "model", None)
        if model is None or getattr(model, "is_fully_loaded", True):
            return True
        # `ensure_fully_loaded` 不存在时同样按"已加载完"处理（老宿主/桩）
        if not hasattr(model, "ensure_fully_loaded"):
            return True

        status = getattr(self, "_set_status", None)
        if callable(status):
            status(f"⏳ 正在加载完整数据以便{action}…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ok = model.ensure_fully_loaded()
        finally:
            QApplication.restoreOverrideCursor()

        if not ok:
            QMessageBox.warning(
                self,
                f"无法{action}",
                f"{getattr(model, 'load_error', '') or '完整数据加载失败'}\n\n"
                "为避免把**不完整的数据**写回文件，本次操作已取消。\n"
                "请重新打开该文件后再试。",
            )
            if callable(status):
                status(f"⚠️ 已取消{action}（数据未完整加载）", 6000)
            return False
        if callable(status):
            status("✅ 已加载完整数据", 3000)
        return True

    # ==================== 导出 ====================
    def _show_export_menu(self):
        """导出菜单"""
        menu = QMenu(self)
        menu.addAction("📊 Excel (.xlsx)").triggered.connect(self._export_xlsx)
        menu.addAction("📄 CSV (.csv)").triggered.connect(self._export_csv)
        menu.addAction("🌐 HTML (.html)").triggered.connect(
            self._export_html_table
        )
        menu.addAction("📝 Markdown (.md)").triggered.connect(
            self._export_markdown_file
        )
        menu.addAction("📋 JSON (.json)").triggered.connect(self._export_json)
        menu.addSeparator()
        menu.addAction("🖼️ 图片 (.png)").triggered.connect(
            self._export_as_image
        )
        menu.exec(self._export_btn.mapToGlobal(
            self._export_btn.rect().bottomLeft()
        ))

    def _get_export_df(self):
        """获取用于导出的 DataFrame（去掉末尾空行）"""
        return self._trim_empty_tail(self.model.df.copy())

    def _write_xlsx(self, path: str) -> bool:
        """
        把当前表格写进 `path`（**不含对话框**）。

        抽出来是为了让「保存 / 另存为 / 导出」共用**同一套写盘逻辑** ——
        否则三条路会各自漂移（审计报告里"应用内格式不落盘"那类问题就是这么来的）。

        保真度阶段 A：若导入时保留了工作簿（`self._workbook`），则把
        **全部工作表与公式**写回；否则退回 `df.to_excel()`。

        P1（本刀）：写完再**贴一遍视图侧格式**（加粗/斜体/下划线/对齐/数字格式、
        合并、批注、条件格式）。两条写入路径共用同一个后处理函数，
        避免"改了一个、另一个没改"。

        P0 止血（审计 §4.3 G2）：两条写入路径 + 样式后处理全部先写到
        **同目录临时文件**，最后 `os.replace` 原子替换。这样中途崩溃/磁盘满
        不会把用户原工作簿留成半份 zip；失败时原文件保持不变。
        """
        target = Path(path)
        try:
            df = self._get_export_df()
            sheet_name = getattr(self, "_active_sheet_name", "") or "Sheet1"
            workbook = getattr(self, "_workbook", None)
            # 这条路径是不是**重建**文件？重建（`df.to_excel`）意味着文件里
            # 之前写进去的图表等结构都没了 → 图表规格必须**全部重写**；
            # 而更新源工作簿时结构天然保留 → 只写还没写过的规格（否则叠加）。
            fresh_file = True
            with atomic_replace(target) as tmp_path:
                tmp = str(tmp_path)
                if workbook is not None and workbook.sheets:
                    from beeoffice.plugins.beesheet_workbook import (
                        sync_active_sheet,
                        write_workbook,
                    )

                    name = getattr(self, "_active_sheet_name", "") \
                        or workbook.active
                    sync_active_sheet(workbook, name, df)
                    write_workbook(workbook, tmp)
                    sheet_name = name
                    fresh_file = False
                else:
                    df.to_excel(tmp, index=False, sheet_name=sheet_name)

                self._apply_view_styles_to(
                    tmp, sheet_name, len(df), fresh_file=fresh_file
                )
            return True
        except Exception as e:  # noqa: BLE001
            logging.error(f"[蜜算] 写 xlsx 失败 {path}: {e}")
            return False

    def _apply_view_styles_to(self, path: str, sheet_name: str,
                              row_count: int, fresh_file: bool = False):
        """
        把视图侧格式贴到刚写好的文件上（失败**不影响数据**）。

        审计报告 §2.9：`_cell_formats`/`_merged_cells`/`_cell_comments`/
        `_conditional_formats` 在导出链上**零引用** —— 用户自己加的加粗、数字格式、
        合并、批注、条件格式保存后全部消失。这里补上。
        """
        try:
            from beeoffice.plugins.beesheet_style_export import (
                apply_view_styles,
            )

            # ⚠️ 不能写 `getattr(...) or []`：`df.columns` 是 pandas **Index**，
            # 对非空 Index 做真值判断会抛"The truth value of a Index is ambiguous"
            # （我第一版就是这么写的，结果整套样式写入被 except 吞掉、只留一行日志）。
            try:
                col_count = len(self.model.df.columns)
            except Exception:  # noqa: BLE001
                col_count = 0

            counts = apply_view_styles(
                path,
                sheet_name,
                formats=getattr(self, "_cell_formats", None),
                merges=getattr(self, "_merged_cells", None),
                comments=getattr(self, "_cell_comments", None),
                conditional=getattr(self, "_conditional_formats", None),
                table_style=getattr(self, "_table_style", None),
                validations=getattr(self, "_data_validations", None),
                comment_authors=getattr(self, "_comment_authors", None),
                default_comment_author=self._comment_author_name()
                if hasattr(self, "_comment_author_name") else "",
                named_ranges=getattr(self, "_named_ranges", None),
                freeze_panes=getattr(self, "_freeze_panes", None),
                charts=getattr(self, "_charts", None),
                charts_fresh_file=fresh_file,
                row_count=row_count,
                col_count=col_count,
            )
            if any(counts.values()):
                logging.info(f"[蜜算] 已写入视图侧格式: {counts}")

            # P1：透视表规格 + 数据快照（让文件自洽、可刷新）
            self._write_pivot_package_to(path, sheet_name)
        except Exception as e:  # noqa: BLE001 - 格式写失败不该毁掉数据
            logging.warning(f"[蜜算] 写入视图侧格式失败（数据已安全写入）: {e}")

    def _write_pivot_package_to(self, path: str, sheet_name: str):
        """
        把**透视表规格 + 数据快照**写进文件（若有）。

        审计里的缺口：透视表原先只把结果值放进新标签页，`config` 当场丢弃 →
        存成文件后只剩死数字，看不出怎么汇总的、也无法刷新。
        """
        spec = getattr(self, "_pivot_spec", None)
        if not spec:
            return
        try:
            from beeoffice.plugins.beesheet_pivot import write_pivot_package

            counts = write_pivot_package(
                path,
                pivot_sheet=sheet_name,
                spec=spec.get("spec") or {},
                source_df=getattr(self, "_pivot_source_df", None),
            )
            if any(counts.values()):
                logging.info(f"[蜜算] 已写入透视表规格: {counts}")
        except Exception as e:  # noqa: BLE001 - 元数据写失败不影响数据
            logging.warning(f"[蜜算] 写入透视表规格失败（数据已安全写入）: {e}")

    def _refresh_pivot(self):
        """
        「刷新透视表」：按文件里保存的规格**重算**并写回。

        数据来源优先级：**当前表格 → 文件内快照**，并在状态栏说明用的是哪一份
        （不让用户猜自己刷的是哪份数据）。
        """
        from PySide6.QtWidgets import QMessageBox

        from beeoffice.plugins.beesheet_pivot import (
            read_pivot_package, refresh_pivot_package,
        )

        path = getattr(self, "_current_file_path", None)
        if not path:
            QMessageBox.information(
                self, "刷新透视表",
                "这份表格还没有保存到文件。\n"
                "请先保存（Ctrl+S），透视表规格才会写进文件、之后才能刷新。",
            )
            return
        package = read_pivot_package(path)
        if not package and not getattr(self, "_pivot_spec", None):
            QMessageBox.information(
                self, "刷新透视表",
                "这个文件里没有保存过透视表配置，无法刷新。",
            )
            return

        if not self._ensure_full_data("刷新透视表"):
            return
        from beeoffice.plugins.beesheet_pivot import drop_empty_rows

        # 必须与生成路径一样先过滤空行：模型会把数据补齐到 1000 行，
        # 尾部空值参与 sum 会把结果算错（实测：本该 1 的求和变成 0）
        filtered = drop_empty_rows(self.model.df)
        data = filtered if filtered is not None and not filtered.empty else None
        ok, message, pivot = refresh_pivot_package(path, data_df=data)
        self._set_status(("✅ " if ok else "⚠ ") + message, 6000)
        if not ok:
            QMessageBox.warning(self, "刷新透视表", message)
            return
        # 界面同步显示重算结果（文件已经写好，这里只是把视图刷新一下）
        if pivot is not None:
            self.model.set_full_dataframe(pivot)
            self.table_view.setModel(self.model)
            self._auto_resize_columns()

    def _load_view_styles_from(self, path: str, sheet_name: str = ""):
        """
        从刚打开的文件**读回**视图侧格式（格式/合并/批注）。

        ## 为什么必须有这一半
        只写不读等于"存了却看不到"：用户设了货币格式、保存、重开 →
        文件里是对的，界面却是朴素的 —— 看起来就像保存坏了。
        所以"保存"和"打开"必须成对。

        合并要顺带 `setSpan` 恢复，否则数据在、视觉不在。

        已知未读回：**条件格式**（规则类型多、反向映射容易错；
        且写盘只新增规则、从不删除，所以读不回来也不会丢）。

        ⚠️ **大文件跳过**：读回要再 `load_workbook()` 打开一次文件，
        几十 MB 的表上这个代价很实在。所以超过 `_STYLE_READ_MAX_BYTES`
        就跳过（并在日志里说明）—— 大表通常也不是靠手工格式在用的。

        ⚠️ **稀疏大表也要跳过**（2026-10-21 实测新增）：有些表磁盘只有 2 MB，
        但 `<dimension>` 声明 20 万行（大量空样式行）。只看文件大小会漏掉它，
        `read_view_styles` 会按声明区域扫满 260 万格，实测 **119–154 s**
        （2.28 MB 的「20 万条」表打开 62.5–142.8 s）。所以再按**声明行数**
        设一道 5 万行的阈值。
        """
        #: 超过这个大小就不读样式（避免为格式让打开变慢）
        max_bytes = 5 * 1024 * 1024
        #: 声明行数超过这个值也不读样式（覆盖"磁盘小、声明极大"的稀疏表）
        max_rows = 50_000
        try:
            size = Path(path).stat().st_size
        except OSError:
            size = 0
        if size > max_bytes:
            logging.info(
                f"[蜜算] 文件较大（{size / 1048576:.1f} MB），跳过格式读回"
                "（数据不受影响）"
            )
            return
        try:
            from beeoffice.plugins.beesheet_workbook import (
                _declared_row_count,
            )

            declared_rows = _declared_row_count(Path(path))
        except Exception:  # noqa: BLE001 - 探测失败就不阻断样式读回
            declared_rows = 0
        if declared_rows >= max_rows:
            logging.info(
                f"[蜜算] 声明行数较大（{declared_rows:,} 行，文件仅 "
                f"{size / 1048576:.1f} MB，疑似稀疏表），跳过格式读回"
                "（数据不受影响）"
            )
            return
        try:
            from beeoffice.plugins.beesheet_style_export import (
                read_view_styles,
            )

            styles = read_view_styles(path, sheet_name or None)
            formats = styles.get("formats") or {}
            merges = styles.get("merges") or {}
            comments = styles.get("comments") or {}
            table_style = styles.get("table_style") or {}
            validations = styles.get("validations") or {}

            if formats:
                self._cell_formats = formats
            if comments:
                self._cell_comments = comments
            if table_style:
                # 表格样式要同时给视图和模型的引用（模型渲染时读它）
                self._table_style = table_style
                self.model._table_style_ref = table_style
                self.model.layoutChanged.emit()
            if validations:
                self._data_validations = validations
                self.model._validations_ref = validations
            # 条件格式（数据条/色阶）—— 模型渲染时读 `_conditional_formats_ref`
            conditional = styles.get("conditional") or {}
            if conditional:
                self._conditional_formats = conditional
                self.model._conditional_formats_ref = conditional
            # P1：批注作者 / 命名区域 / 冻结窗格
            authors = styles.get("comment_authors") or {}
            if authors:
                self._comment_authors = authors
            if styles.get("named_ranges"):
                self._named_ranges = styles["named_ranges"]
            if styles.get("freeze_panes"):
                self._freeze_panes = styles["freeze_panes"]
                # 状态栏与信息面板沿用既有的"冻结信息"字段
                self._frozen_top, self._frozen_left = self._parse_freeze_ref(
                    self._freeze_panes
                )
            if hasattr(self, "_apply_freeze_from_state"):
                self._apply_freeze_from_state()

            # P1：文件里若有透视表规格，读进来（供「刷新透视表」用）
            try:
                from beeoffice.plugins.beesheet_pivot import (
                    read_pivot_package,
                )

                package = read_pivot_package(path)
                if package:
                    self._pivot_spec = package
                    self._pivot_source_df = package.get("snapshot")
                    logging.info("[蜜算] 读回透视表规格（可刷新）")
            except Exception as e:  # noqa: BLE001
                logging.debug(f"[蜜算] 读回透视表规格失败（忽略）: {e}")
            if merges:
                self._merged_cells = merges
                for (r1, c1), (n_rows, n_cols) in merges.items():
                    try:
                        self.table_view.setSpan(
                            int(r1), int(c1), int(n_rows), int(n_cols)
                        )
                    except Exception as e:  # noqa: BLE001
                        logging.debug(f"[蜜算] 恢复合并显示失败 {r1},{c1}: {e}")
            if any((formats, merges, comments, table_style, validations)):
                logging.info(
                    "[蜜算] 已读回格式："
                    f"格式 {len(formats)} 格 / 合并 {len(merges)} 处 / "
                    f"批注 {len(comments)} 条 / 表格样式 "
                    f"{'有' if table_style else '无'} / "
                    f"数据验证 {len(validations)} 格"
                )
        except Exception as e:  # noqa: BLE001 - 读格式失败不该影响打开文件
            logging.warning(f"[蜜算] 读回视图侧格式失败（数据已正常打开）: {e}")

    def _export_xlsx(self):
        """
        导出为 Excel（"另存为"语义：总是问路径）。
        """
        path, _ = QFileDialog.getSaveFileName(
            self, "导出", "表格.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            self._save_canceled = True
            return
        # R1 安全门：保存**必须**在数据完整的前提下进行。
        # 实测（tests/fidelity/test_beesheet_lazy_load.py）：
        # 拿"只载入了前 N 行"的数据写回源文件，第 1–N 行会被覆盖、
        # 其余行仍留旧值 —— 文件内容与界面显示不一致（用户重开看到乱序/重复）。
        if not self._ensure_full_data("保存"):
            return
        if self._write_xlsx(path):
            # P1：记住当前文件，让 Ctrl+S / 自动保存 / 保存前备份都能工作
            self._current_file_path = str(path)
            if hasattr(self, "_remember_saved_path"):
                self._remember_saved_path(path)
            QMessageBox.information(self, "成功", f"已保存：\n{path}")
        else:
            QMessageBox.warning(self, "失败", f"写入失败：{path}")

    # ==================================================================
    # P1：当前文件 + 保存（Ctrl+S / 自动保存 / 备份覆盖面）
    # ==================================================================
    def save(self) -> bool:
        """
        保存到**当前文件**（没有当前文件时退化为"另存为"）。

        审计报告 §2.6：蜜算原先没有 `save()`/`_current_file_path` →
        ① 平台级 5 分钟自动保存**跳过蜜算**；
        ② 保存前自动备份**不覆盖蜜算**（手动点还弹"还没有保存到文件"）；
        ③ Ctrl+S 每次都要重新选路径（没有"当前文件"这个概念，与 Excel/WPS 不符）。

        ⚠️ 旧版 `.xls` 的**写入**守卫：现在能**读** `.xls` 了（xlrd），
        但我们**写不了** BIFF（openpyxl 只写 OOXML、xlwt 未随包分发）。
        若不拦，导入 `.xls` 后按 Ctrl+S 会走到 `df.to_excel('*.xls')` ——
        轻则报错、重则产出坏文件。所以这里明确告诉用户"另存为 .xlsx"，
        **绝不在 .xls 上原地写**。
        """
        path = getattr(self, "_current_file_path", None)
        self._save_canceled = False
        if path and str(path).lower().endswith(".xls"):
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(
                self, "另存为 Excel 工作簿",
                "旧版 .xls 是二进制格式，本软件**只能读、不能写**（写入会损坏文件）。\n\n"
                "接下来请选择保存位置，文件会以 .xlsx 保存；"
                "原 .xls 文件保持不变。",
            )
            self._current_file_path = None      # 走"另存为"，并让默认名变 .xlsx
            self._export_xlsx()
            return bool(getattr(self, "_current_file_path", None))
        if not path:
            self._export_xlsx()          # 退回"另存为"
            return bool(getattr(self, "_current_file_path", None))
        if not self._ensure_full_data("保存"):
            return False
        if self._write_xlsx(path):
            if hasattr(self, "_remember_saved_path"):
                self._remember_saved_path(path)
            return True
        return False

    def save_as(self) -> bool:
        """另存为（忽略当前路径，重新选）。"""
        self._save_canceled = False
        self._current_file_path = None
        self._export_xlsx()
        return bool(getattr(self, "_current_file_path", None))

    def set_current_file_path(self, path):
        """记录当前文件路径（导入/打开文件后由调用方设置）。"""
        self._current_file_path = str(path) if path else None
        if hasattr(self, "_remember_saved_path"):
            self._remember_saved_path(path)

    def _remember_saved_path(self, path):
        """同步给主窗口（标签标题 / 最近文件 / 备份都依赖它）。"""
        try:
            parent = self.window()
            if path and hasattr(parent, "sync_tab_title"):
                parent.sync_tab_title(self, str(path))
        except Exception as e:  # noqa: BLE001
            logging.debug(f"[蜜算] 同步标签标题失败（忽略）: {e}")

    # ==================== WPS 式工作表页签（2026-10-22） ====================
    def _refresh_sheet_tabs(self):
        """按 `self._workbook` 重建底部工作表页签，并同步当前选中项。"""
        bar = getattr(self, "_sheet_tab_bar", None)
        if bar is None:
            return
        workbook = getattr(self, "_workbook", None)
        names = list(workbook.sheet_names) if workbook is not None else []
        current = getattr(self, "_active_sheet_name", "") or (
            names[0] if names else ""
        )
        container = getattr(self, "_sheet_tabs_container", None)
        if container is not None:
            container.setVisible(bool(names))
        bar.blockSignals(True)
        try:
            while bar.count() > 0:
                bar.removeTab(0)
            for name in names:
                bar.addTab(str(name))
            if names and current in names:
                bar.setCurrentIndex(names.index(current))
            elif names:
                bar.setCurrentIndex(0)
        finally:
            bar.blockSignals(False)

    def _current_sheet_index(self) -> int:
        workbook = getattr(self, "_workbook", None)
        if workbook is None:
            return -1
        name = getattr(self, "_active_sheet_name", "")
        names = workbook.sheet_names
        return names.index(name) if name in names else 0

    def _on_sheet_tab_changed(self, index: int):
        """点击工作表页签：把当前表写回工作簿，再加载目标表数据。"""
        workbook = getattr(self, "_workbook", None)
        if workbook is None or not (0 <= index < len(workbook.sheets)):
            return
        target = workbook.sheets[index]
        if not getattr(self.model, "is_fully_loaded", True):
            self._set_status(
                "完整数据仍在后台加载，暂不能切换工作表，请稍候", 4000
            )
            self._refresh_sheet_tabs()
            return
        old_name = getattr(self, "_active_sheet_name", "") or ""
        if old_name and old_name != target.name:
            try:
                from beeoffice.plugins.beesheet_workbook import (
                    sync_active_sheet,
                )

                sync_active_sheet(workbook, old_name, self.model.df.copy())
            except Exception as e:  # noqa: BLE001 - 切换不能被同步失败阻断
                logging.warning(f"[蜜算] 切换工作表前回写失败（继续）: {e}")
        self._active_sheet_name = target.name
        df = target.df if target.df is not None else pd.DataFrame()
        self.model.set_full_dataframe(df.copy())
        self.table_view.setModel(self.model)
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._auto_resize_columns()
        path = getattr(self, "_current_file_path", None)
        if path:
            self._load_view_styles_from(path, target.name)
        self._set_status(f"已切换到工作表：{target.name}", 3000)
        try:
            self.contentChanged.emit()
        except Exception:  # noqa: BLE001
            pass

    def _show_sheet_tab_menu(self, pos):
        """工作表页签右键菜单：新建 / 重命名 / 删除。"""
        bar = getattr(self, "_sheet_tab_bar", None)
        if bar is None:
            return
        index = bar.tabAt(pos)
        menu = QMenu(self)
        menu.addAction("➕ 新建工作表", self._add_workbook_sheet)
        if index >= 0:
            menu.addSeparator()
            menu.addAction(
                "✏️ 重命名…",
                lambda: self._rename_workbook_sheet(index),
            )
            menu.addAction(
                "🗑 删除工作表",
                lambda: self._delete_workbook_sheet(index),
            )
        menu.exec(bar.mapToGlobal(pos))

    def _ensure_workbook_for_sheets(self):
        """没有工作簿时创建一个（用于空白表格的新建工作表）。"""
        from beeoffice.plugins.beesheet_workbook import (
            SheetData, WorkbookData,
        )

        workbook = getattr(self, "_workbook", None)
        if workbook is not None:
            return workbook
        name = getattr(self, "_active_sheet_name", "") or "Sheet1"
        df = self.model.df if self.model is not None else pd.DataFrame()
        workbook = WorkbookData(
            sheets=[SheetData(name=str(name), df=df)],
            active=str(name),
        )
        self._workbook = workbook
        self._active_sheet_name = str(name)
        return workbook

    def _add_workbook_sheet(self):
        workbook = self._ensure_workbook_for_sheets()
        from beeoffice.plugins.beesheet_workbook import SheetData

        base = "Sheet"
        index = len(workbook.sheets) + 1
        names = set(workbook.sheet_names)
        while f"{base}{index}" in names:
            index += 1
        name = f"{base}{index}"
        workbook.sheets.append(
            SheetData(name=name, df=pd.DataFrame({"A": []}))
        )
        self._refresh_sheet_tabs()
        bar = getattr(self, "_sheet_tab_bar", None)
        if bar is not None:
            bar.setCurrentIndex(len(workbook.sheets) - 1)
        self._set_status(f"已新建工作表：{name}", 3000)
        try:
            self.contentChanged.emit()
        except Exception:  # noqa: BLE001
            pass

    def _rename_workbook_sheet(self, index: int):
        workbook = getattr(self, "_workbook", None)
        if workbook is None or not (0 <= index < len(workbook.sheets)):
            return
        sheet = workbook.sheets[index]
        name, ok = QInputDialog.getText(
            self, "重命名工作表", "工作表名称：", text=sheet.name
        )
        if not ok:
            return
        new_name = (name or "").strip()
        if not new_name:
            QMessageBox.warning(self, "重命名失败", "工作表名称不能为空")
            return
        if new_name != sheet.name and new_name in workbook.sheet_names:
            QMessageBox.warning(self, "重命名失败", f"已存在工作表：{new_name}")
            return
        old_name = sheet.name
        sheet.name = new_name
        if getattr(self, "_active_sheet_name", "") == old_name:
            self._active_sheet_name = new_name
        if workbook.active == old_name:
            workbook.active = new_name
        self._refresh_sheet_tabs()
        if getattr(self, "_sheet_tab_bar", None) is not None:
            self._sheet_tab_bar.setCurrentIndex(index)
        self._set_status(f"工作表已重命名：{old_name} → {new_name}", 3000)
        try:
            self.contentChanged.emit()
        except Exception:  # noqa: BLE001
            pass

    def _delete_workbook_sheet(self, index: int):
        workbook = getattr(self, "_workbook", None)
        if workbook is None or len(workbook.sheets) <= 1:
            self._set_status("至少保留一张工作表", 3000)
            return
        if not (0 <= index < len(workbook.sheets)):
            return
        removed = workbook.sheets.pop(index)
        if getattr(self, "_active_sheet_name", "") == removed.name:
            new_index = min(index, len(workbook.sheets) - 1)
            self._active_sheet_name = workbook.sheets[new_index].name
        self._refresh_sheet_tabs()
        bar = getattr(self, "_sheet_tab_bar", None)
        if bar is not None:
            bar.setCurrentIndex(self._current_sheet_index())
        self._set_status(f"已删除工作表：{removed.name}", 3000)
        try:
            self.contentChanged.emit()
        except Exception:  # noqa: BLE001
            pass

    def _toggle_wps_headers(self):
        """切换 WPS 式表头（A/B/C 列字母 + 行号）与纯列名显示。"""
        button = getattr(self, "_wps_headers_btn", None)
        enabled = bool(button.isChecked()) if button is not None else True
        self.model.wps_headers = enabled
        rows = self.model.rowCount()
        cols = self.model.columnCount()
        if cols:
            self.model.headerDataChanged.emit(Qt.Horizontal, 0, cols - 1)
        if rows:
            self.model.headerDataChanged.emit(Qt.Vertical, 0, rows - 1)
        self._auto_resize_columns()
        self._set_status(
            "表头：WPS 式行列号" if enabled else "表头：仅列名", 2500
        )

    def _export_csv(self):
        """导出为 CSV（带 UTF-8 BOM）"""
        # R1 安全门：导出必须基于完整数据（否则导出的文件只有前 N 行）
        if not self._ensure_full_data("导出 CSV"):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", "表格.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            df = self._get_export_df()
            df.to_csv(path, index=False, encoding='utf-8-sig')
            QMessageBox.information(self, "成功", f"已保存：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    def _export_html_table(self):
        """导出为 HTML 表格"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 HTML", "表格.html", "HTML (*.html)"
        )
        if not path:
            return
        try:
            df = self._get_export_df()
            html_table = df.to_html(index=False, escape=True, border=1)
            full_html = (
                f'<!DOCTYPE html><html><head><meta charset="UTF-8">\n'
                f'<title>BeeOffice 表格导出</title>\n'
                f'<style>body{{font-family:sans-serif;padding:20px;'
                f'background:#f5f5f5;}}\n'
                f'h1{{color:#FF8F00;}}'
                f'table{{border-collapse:collapse;background:#FFF;'
                f'box-shadow:0 2px 8px rgba(0,0,0,0.1);}}\n'
                f'th,td{{border:1px solid #DDD;padding:8px 12px;'
                f'text-align:left;}}\n'
                f'th{{background:#FFF3E0;color:#E65100;}}'
                f'tr:nth-child(even){{background:#FAFAFA;}}</style>\n'
                f'</head><body><h1>🐝 BeeOffice 表格导出</h1>{html_table}\n'
                f'<p>导出于 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}，'
                f'共 {len(df)} 行 × {len(df.columns)} 列</p>\n'
                f'</body></html>'
            )
            with open(path, 'w', encoding='utf-8') as f:
                f.write(full_html)
            QMessageBox.information(self, "成功", f"已保存：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    def _export_markdown_file(self):
        """导出为 Markdown 表格"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Markdown", "表格.md", "Markdown (*.md)"
        )
        if not path:
            return
        try:
            df = self._get_export_df()
            lines = ["# 🐝 BeeOffice 表格导出\n"]
            lines.append(
                f"> 导出于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            lines.append(f"> 共 {len(df)} 行 × {len(df.columns)} 列\n")
            cols = [str(c) for c in df.columns]
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("|" + "|".join(["---"] * len(cols)) + "|")
            for _, row in df.iterrows():
                vals = []
                for v in row:
                    if pd.isna(v):
                        vals.append("")
                    else:
                        s = str(v).replace("|", "\\|").replace("\n", " ")
                        vals.append(s)
                lines.append("| " + " | ".join(vals) + " |")
            with open(path, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines))
            QMessageBox.information(self, "成功", f"已保存：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    def _export_json(self):
        """导出为 JSON"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 JSON", "表格.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            df = self._get_export_df()
            data = df.to_dict(orient='records')

            def clean(v):
                if pd.isna(v):
                    return None
                if hasattr(v, 'isoformat'):
                    return v.isoformat()
                return v

            data = [{k: clean(v) for k, v in row.items()} for row in data]
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "成功", f"已保存：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    def _export_as_image(self):
        """导出为 PNG 图片（整个视图）"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出图片", "表格.png", "PNG (*.png)"
        )
        if not path:
            return
        try:
            viewport = self.table_view.viewport()
            pixmap = viewport.grab()
            pixmap.save(path, "PNG")
            QMessageBox.information(self, "成功", f"已保存：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    @staticmethod
    def _trim_empty_tail(df):
        """裁掉末尾全空行"""
        if df is None or df.empty:
            return df

        def is_empty_row(row):
            for v in row:
                if v is not None \
                   and not (isinstance(v, float) and pd.isna(v)) \
                   and str(v).strip() != '':
                    return False
            return True

        last_non_empty = -1
        for i in range(len(df) - 1, -1, -1):
            if not is_empty_row(df.iloc[i]):
                last_non_empty = i
                break
        if last_non_empty < 0:
            return df.iloc[:0]
        return df.iloc[:last_non_empty + 1]

    # ==================== 清洗 ====================
    def _show_clean_menu(self):
        """清洗菜单"""
        col = self.table_view.currentIndex().column()
        if col < 0:
            return
        menu = QMenu(self)
        menu.addAction("去除首尾空格").triggered.connect(
            lambda: self._clean_trim(col)
        )
        menu.addAction("文本转数字").triggered.connect(
            lambda: self._clean_to_number(col)
        )
        menu.addAction("删除重复行").triggered.connect(
            lambda: self._clean_remove_dups()
        )
        menu.addAction("分列...").triggered.connect(
            lambda: self._split_column(col)
        )
        menu.exec(self.table_view.viewport().mapToGlobal(
            self.table_view.visualRect(self.model.index(0, col)).center()
        ))

    def _clean_trim(self, col):
        """去除列中的首尾空格"""
        cn = self.model.df.columns[col]
        old = self.model.df[cn].copy()
        self.model._loaded_df[cn] = self.model.df[cn].astype(str).str.strip()
        self._push_command(TrimCommand(col, old))
        self._set_status("已去空格", 2000)

    def _clean_to_number(self, col):
        """列转为数字"""
        cn = self.model.df.columns[col]
        old = self.model.df[cn].copy()
        self.model._loaded_df[cn] = pd.to_numeric(
            self.model.df[cn], errors='coerce'
        )
        self._push_command(TrimCommand(col, old))
        self._set_status("已转数字", 2000)

    def _clean_remove_dups(self):
        """删除完全重复的行"""
        old = self.model.df.copy()
        new = self.model.df.drop_duplicates(ignore_index=True)
        self._push_command(SortCommand(old, new))
        self._set_status("已删除重复行", 2000)

    def _split_column(self, col):
        """按分隔符分列"""
        delim, ok = QInputDialog.getText(self, "分列", "分隔符:")
        if ok and delim:
            cn = self.model.df.columns[col]
            split_data = self.model.df[cn].astype(str).str.split(
                delim, expand=True
            )
            for i in range(split_data.shape[1]):
                new_name = f"{cn}_{i+1}"
                while new_name in self.model._loaded_df.columns:
                    new_name += "_1"
                self.model._loaded_df.insert(col + i + 1, new_name,
                                              split_data[i])
            self.model._total_cols = len(self.model._loaded_df.columns)
            self.model.layoutChanged.emit()
            self._set_status(f"已分列", 3000)

    # ==================== 筛选 ====================
    def _show_filter_dialog(self):
        """筛选对话框"""
        # R1 安全门：筛选会隐藏/重排行，必须基于完整数据
        if not self._ensure_full_data("筛选"):
            return
        dlg = QDialog(self)
        form = QFormLayout(dlg)
        cc = QComboBox()
        cc.addItems(list(self.model.df.columns))
        form.addRow("列:", cc)
        ti = QLineEdit()
        form.addRow("包含:", ti)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(
            lambda: [self.filter_contains(cc.currentIndex(), ti.text()),
                     dlg.accept()]
        )
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        dlg.exec()

    def filter_contains(self, col, text):
        """按列包含文本筛选"""
        mask = self.model.df.iloc[:, col].astype(str).str.contains(
            text, case=False, na=False
        )
        if mask.any():
            self.model._loaded_df = self.model.df[mask].copy()
            self.model.layoutChanged.emit()

    def _on_header_clicked(self, column):
        """点击列头时弹出快速筛选"""
        if column < 0:
            return
        self._show_filter_popup(column)

    def _show_filter_popup(self, column):
        """列头快速筛选弹窗"""
        if hasattr(self, '_filter_popup') and self._filter_popup \
           and self._filter_popup.isVisible():
            self._filter_popup.close()
        col_name = self.model.df.columns[column]
        self._filter_popup = QDialog(
            self, Qt.Popup | Qt.FramelessWindowHint
        )
        self._filter_popup.setMinimumWidth(220)
        layout = QVBoxLayout(self._filter_popup)
        layout.addWidget(QLabel(f"筛选: {col_name}"))
        self._filter_search = QLineEdit()
        self._filter_search.setPlaceholderText("搜索...")
        self._filter_search.textChanged.connect(
            lambda t: self._update_filter_list(column, t)
        )
        layout.addWidget(self._filter_search)
        bl = QHBoxLayout()
        bl.addWidget(QPushButton(
            "全选", clicked=lambda: self._select_all_filter(True)
        ))
        bl.addWidget(QPushButton(
            "清除", clicked=lambda: self._select_all_filter(False)
        ))
        bl.addStretch()
        bl.addWidget(QPushButton(
            "确定", clicked=lambda: self._apply_filter(column)
        ))
        layout.addLayout(bl)
        self._filter_list = QListWidget()
        layout.addWidget(self._filter_list)
        self._update_filter_list(column, "")
        header = self.table_view.horizontalHeader()
        x = header.sectionViewportPosition(column)
        y = header.height()
        self._filter_popup.move(header.mapToGlobal(QPoint(x, y)))
        self._filter_popup.show()

    def _update_filter_list(self, column, search_text=""):
        """更新筛选列表"""
        if not self._filter_list:
            return
        self._filter_list.clear()
        col_name = self.model.df.columns[column]
        vc = self.model.df[col_name].astype(str).value_counts()
        for v, c in vc.items():
            if search_text and search_text.lower() not in v.lower():
                continue
            item = QListWidgetItem(f"{v}  ({c})")
            item.setData(Qt.UserRole, v)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self._filter_list.addItem(item)

    def _select_all_filter(self, select_all):
        """全选/清除筛选列表"""
        if not self._filter_list:
            return
        state = Qt.Checked if select_all else Qt.Unchecked
        for i in range(self._filter_list.count()):
            self._filter_list.item(i).setCheckState(state)

    def _apply_filter(self, column):
        """应用筛选"""
        if not self._filter_list:
            return
        col_name = self.model.df.columns[column]
        total = self._filter_list.count()
        sv = set()
        for i in range(self._filter_list.count()):
            if self._filter_list.item(i).checkState() == Qt.Checked:
                sv.add(self._filter_list.item(i).data(Qt.UserRole))
        self._filter_popup.close()
        if len(sv) == total:
            if column in self._active_filters:
                del self._active_filters[column]
            return
        self._active_filters[column] = sv
        mask = self.model.df[col_name].astype(str).isin(sv)
        fd = self.model.df[mask].copy()
        if len(fd) == 0:
            return
        self.model._loaded_df = fd
        self.model.layoutChanged.emit()
        self._set_status(
            f"筛选: {len(sv)}/{total}个值→{len(fd)}行", 3000
        )

    # ==================== 表头菜单与行列操作 ====================
    def _show_header_context_menu(self, pos):
        """列头右键菜单"""
        column = self.table_view.horizontalHeader().logicalIndexAt(pos)
        if column < 0:
            return
        col_name = self.model.df.columns[column]
        menu = QMenu(self)
        menu.addSection(f"列: {col_name}")
        menu.addAction("🔍 快速筛选").triggered.connect(
            lambda: self._show_filter_popup(column)
        )
        menu.addAction("⬆️ 升序").triggered.connect(
            lambda: self.sort_by_column(column, True)
        )
        menu.addAction("⬇️ 降序").triggered.connect(
            lambda: self.sort_by_column(column, False)
        )
        menu.addSeparator()
        menu.addAction("📋 复制此列").triggered.connect(
            lambda: self._copy_column(column)
        )
        menu.addAction("➕ 在左侧插入列").triggered.connect(
            lambda: self._insert_column_at(column)
        )
        menu.addAction("➕ 在右侧插入列").triggered.connect(
            lambda: self._insert_column_at(column + 1)
        )
        menu.addAction("🗑️ 删除此列").triggered.connect(
            lambda: self._delete_column_at(column)
        )
        menu.addSeparator()
        batch_menu = menu.addMenu("⚙️ 批量操作")
        batch_menu.addAction("✏️ 重命名此列").triggered.connect(
            lambda: self._rename_column(column)
        )
        batch_menu.addAction("🔢 转为数字").triggered.connect(
            lambda: self._batch_convert_column(column, 'number')
        )
        batch_menu.addAction("📝 转为文本").triggered.connect(
            lambda: self._batch_convert_column(column, 'text')
        )
        batch_menu.addAction("🔤 大写化").triggered.connect(
            lambda: self._batch_transform_column(column, 'upper')
        )
        batch_menu.addAction("🔡 小写化").triggered.connect(
            lambda: self._batch_transform_column(column, 'lower')
        )
        batch_menu.addAction("✂️ 去除空格").triggered.connect(
            lambda: self._batch_transform_column(column, 'trim')
        )
        batch_menu.addAction("🔍 删除重复值").triggered.connect(
            lambda: self._batch_deduplicate_column(column)
        )
        batch_menu.addSeparator()
        batch_menu.addAction("⬆️ 上移此列").triggered.connect(
            lambda: self._move_column(column, -1)
        )
        batch_menu.addAction("⬇️ 下移此列").triggered.connect(
            lambda: self._move_column(column, 1)
        )
        menu.addSeparator()
        fmt_menu = menu.addMenu("🎨 条件格式")
        fmt_menu.addAction("数据条").triggered.connect(
            lambda: self._add_data_bars(column)
        )
        fmt_menu.addAction("色阶").triggered.connect(
            lambda: self._add_color_scale(column)
        )
        fmt_menu.addAction("图标集").triggered.connect(
            lambda: self._add_icon_set(column)
        )
        fmt_menu.addSeparator()
        fmt_menu.addAction("清除本列条件格式").triggered.connect(
            lambda: self._clear_cond_format(column)
        )
        menu.addAction("💬 批注").triggered.connect(self._add_comment)
        menu.exec(self.table_view.horizontalHeader().mapToGlobal(
            QPoint(pos.x(),
                   pos.y() + self.table_view.horizontalHeader().height())
        ))

    def _show_row_header_menu(self, pos):
        """行号右键菜单"""
        row = self.table_view.verticalHeader().logicalIndexAt(pos)
        if row < 0:
            return
        menu = QMenu(self)
        menu.addAction("📋 复制此行").triggered.connect(
            lambda: self._copy_row(row)
        )
        menu.addSeparator()
        menu.addAction("➕ 在上方插入行").triggered.connect(
            lambda: self._insert_row_at(row)
        )
        menu.addAction("➕ 在下方插入行").triggered.connect(
            lambda: self._insert_row_at(row + 1)
        )
        menu.addSeparator()
        menu.addAction("🗑️ 删除此行").triggered.connect(
            lambda: self._delete_row_at(row)
        )
        menu.exec(self.table_view.verticalHeader().mapToGlobal(pos))

    def _copy_row(self, row):
        """复制整行"""
        cols = self.model.columnCount()
        vals = [str(self.model.get_value(row, c)) for c in range(cols)]
        QApplication.clipboard().setText("\t".join(vals))
        self._set_status(f"已复制第 {row+1} 行", 2000)

    def _insert_row_at(self, row):
        """在指定位置插入空行"""
        df = self.model._loaded_df
        new_row = pd.DataFrame(
            [['' for _ in range(len(df.columns))]],
            columns=df.columns
        )
        self.model._loaded_df = pd.concat(
            [df.iloc[:row], new_row, df.iloc[row:]]
        ).reset_index(drop=True)
        self.model._total_rows = len(self.model._loaded_df)
        self.model.layoutChanged.emit()
        self._set_status(f"已在第 {row+1} 行插入", 2000)

    def _delete_row_at(self, row):
        """删除指定行"""
        if len(self.model._loaded_df) <= 1:
            self._set_status("至少保留一行", 2000)
            return
        reply = QMessageBox.question(
            self, "删除行",
            f"确定删除第 {row+1} 行？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.model._loaded_df = self.model._loaded_df.drop(
            index=row
        ).reset_index(drop=True)
        self.model._total_rows = len(self.model._loaded_df)
        self.model.layoutChanged.emit()
        self._set_status(f"已删除第 {row+1} 行", 2000)

    def _copy_column(self, col):
        """复制整列"""
        vals = [str(self.model.get_value(r, col))
                for r in range(self.model.rowCount())]
        QApplication.clipboard().setText("\n".join(vals))
        self._set_status(
            f"已复制第 {self._col_index_to_name(col)} 列", 2000
        )

    def _insert_column_at(self, col):
        """在指定位置插入空列"""
        df = self.model._loaded_df
        new_name = f"新列_{col+1}"
        while new_name in df.columns:
            new_name += "_1"
        df.insert(col, new_name, '')
        self.model._loaded_df = df
        self.model._total_cols = len(df.columns)
        self.model.layoutChanged.emit()
        self._set_status(
            f"已在位置 {col+1} 插入列「{new_name}」", 2000
        )

    def _delete_column_at(self, col):
        """删除指定列"""
        if len(self.model._loaded_df.columns) <= 1:
            self._set_status("至少保留一列", 2000)
            return
        col_name = self.model.df.columns[col]
        reply = QMessageBox.question(
            self, "删除列",
            f"确定删除列「{col_name}」？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.model._loaded_df = self.model._loaded_df.drop(
            columns=[col_name]
        )
        self.model._total_cols = len(self.model._loaded_df.columns)
        self.model.layoutChanged.emit()
        self._set_status(f"已删除列「{col_name}」", 2000)

    def _rename_column(self, col):
        """重命名列"""
        old_name = self.model.df.columns[col]
        new_name, ok = QInputDialog.getText(
            self, "重命名列", "新列名：", text=str(old_name)
        )
        if ok and new_name.strip():
            new_name = new_name.strip()
            if new_name in self.model._loaded_df.columns \
               and new_name != old_name:
                QMessageBox.warning(
                    self, "失败", f"列名「{new_name}」已存在"
                )
                return
            self.model._loaded_df = self.model._loaded_df.rename(
                columns={old_name: new_name}
            )
            self.model.layoutChanged.emit()
            self._set_status(f"✅ 已重命名为「{new_name}」", 2000)

    def _batch_convert_column(self, col, target_type):
        """批量转换列类型"""
        cn = self.model.df.columns[col]
        try:
            if target_type == 'number':
                self.model._loaded_df[cn] = pd.to_numeric(
                    self.model._loaded_df[cn], errors='coerce'
                )
                self._set_status(f"✅ 列「{cn}」已转为数字", 2000)
            elif target_type == 'text':
                self.model._loaded_df[cn] = self.model._loaded_df[cn].astype(str)
                self.model._loaded_df[cn] = self.model._loaded_df[cn].replace(
                    'nan', ''
                ).replace('None', '')
                self._set_status(f"✅ 列「{cn}」已转为文本", 2000)
            self.model.layoutChanged.emit()
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    def _batch_transform_column(self, col, op):
        """批量转换列内容"""
        cn = self.model.df.columns[col]
        try:
            series = self.model._loaded_df[cn].astype(str)
            if op == 'upper':
                self.model._loaded_df[cn] = series.str.upper()
            elif op == 'lower':
                self.model._loaded_df[cn] = series.str.lower()
            elif op == 'trim':
                self.model._loaded_df[cn] = series.str.strip()
                self.model._loaded_df[cn] = \
                    self.model._loaded_df[cn].str.replace(
                        r'\s+', ' ', regex=True
                    )
            self.model.layoutChanged.emit()
            op_names = {'upper': '大写', 'lower': '小写', 'trim': '去空格'}
            self._set_status(
                f"✅ 列「{cn}」已{op_names.get(op, '转换')}", 2000
            )
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    def _batch_deduplicate_column(self, col):
        """删除该列中的重复值（保留首次出现）"""
        cn = self.model.df.columns[col]
        try:
            before = len(self.model._loaded_df)
            self.model._loaded_df = self.model._loaded_df.drop_duplicates(
                subset=[cn], keep='first'
            ).reset_index(drop=True)
            self.model._total_rows = len(self.model._loaded_df)
            self.model.layoutChanged.emit()
            removed = before - len(self.model._loaded_df)
            self._set_status(f"✅ 已删除 {removed} 个重复行", 3000)
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    def _move_column(self, col, offset):
        """移动列位置"""
        new_col = col + offset
        if new_col < 0 or new_col >= len(self.model._loaded_df.columns):
            return
        try:
            cols = list(self.model._loaded_df.columns)
            cols.insert(new_col, cols.pop(col))
            self.model._loaded_df = self.model._loaded_df[cols]
            self.model.layoutChanged.emit()
            self._set_status(f"✅ 列已移动", 2000)
        except Exception as e:
            QMessageBox.warning(self, "失败", str(e))

    # ==================== 条件格式 ====================
    def _add_data_bars(self, col):
        """添加数据条"""
        nd = pd.to_numeric(
            self.model.df.iloc[:, col], errors='coerce'
        ).dropna()
        if len(nd) == 0:
            return
        self._conditional_formats[col] = {
            "type": "data_bars",
            "min": nd.min(),
            "max": nd.max()
        }
        self.model.dataChanged.emit(
            self.model.index(0, col),
            self.model.index(len(self.model.df) - 1, col)
        )
        self._set_status("已添加数据条", 2000)

    def _add_color_scale(self, col):
        """添加色阶"""
        nd = pd.to_numeric(
            self.model.df.iloc[:, col], errors='coerce'
        ).dropna()
        if len(nd) == 0:
            return
        self._conditional_formats[col] = {
            "type": "color_scale",
            "min": nd.min(),
            "max": nd.max()
        }
        self.model.dataChanged.emit(
            self.model.index(0, col),
            self.model.index(len(self.model.df) - 1, col)
        )
        self._set_status("已添加色阶", 2000)

    def _add_icon_set(self, col):
        """添加图标集"""
        nd = pd.to_numeric(
            self.model.df.iloc[:, col], errors='coerce'
        ).dropna()
        if len(nd) == 0:
            return
        self._conditional_formats[col] = {
            "type": "icon_set",
            "min": nd.min(),
            "max": nd.max()
        }
        self.model.dataChanged.emit(
            self.model.index(0, col),
            self.model.index(len(self.model.df) - 1, col)
        )
        self._set_status("已添加图标集（🔴🟡🟢）", 2000)

    def _clear_cond_format(self, col):
        """清除指定列的条件格式"""
        if col in self._conditional_formats:
            del self._conditional_formats[col]
            self.model.dataChanged.emit(
                self.model.index(0, col),
                self.model.index(len(self.model.df) - 1, col)
            )
            self._set_status("已清除条件格式", 2000)

    # ==================== 复制/粘贴 ====================
    def _copy_as_markdown(self):
        """复制选中区域为 Markdown 表格"""
        indexes = sorted(
            [(i.row(), i.column()) for i in
             self.table_view.selectionModel().selection().indexes()],
            key=lambda x: (x[0], x[1])
        )
        if not indexes:
            return
        rows = sorted(set(r for r, _ in indexes))
        cols = sorted(set(c for _, c in indexes))
        lines = [
            "| " + " | ".join(self.model.df.columns[c] for c in cols) + " |"
        ]
        lines.append("|" + "|".join(["---"] * len(cols)) + "|")
        for r in rows:
            lines.append(
                "| " + " | ".join(
                    str(self.model.get_value(r, c))
                    if not pd.isna(self.model.get_value(r, c)) else ""
                    for c in cols
                ) + " |"
            )
        QApplication.clipboard().setText("\n".join(lines))
        self._set_status("已复制", 2000)

    def _copy_selection_as_image(self):
        """复制选中区域为图片"""
        sel = self.table_view.selectionModel().selection()
        if not sel or not sel.indexes():
            QMessageBox.information(self, "提示", "请先选中要复制的区域")
            return
        indexes = sel.indexes()
        r1 = min(i.row() for i in indexes)
        c1 = min(i.column() for i in indexes)
        r2 = max(i.row() for i in indexes)
        c2 = max(i.column() for i in indexes)

        hh = self.table_view.horizontalHeader()
        vh = self.table_view.verticalHeader()

        left = hh.sectionViewportPosition(c1)
        right = left
        for c in range(c1, c2 + 1):
            right += hh.sectionSize(c)
        width = right - left

        top = vh.sectionViewportPosition(r1)
        bottom = top
        for r in range(r1, r2 + 1):
            bottom += vh.sectionSize(r)
        height = bottom - top

        if width <= 0 or height <= 0:
            QMessageBox.warning(self, "失败", "选中区域尺寸无效")
            return

        viewport = self.table_view.viewport()
        try:
            pixmap = viewport.grab(
                QRect(int(left), int(top), int(width), int(height))
            )
        except Exception as e:
            QMessageBox.warning(self, "失败", f"截取失败：{e}")
            return

        QApplication.clipboard().setPixmap(pixmap)
        self._set_status(
            f"✅ 已复制图片到剪贴板 ({width}×{height})", 3000
        )

        reply = QMessageBox.question(
            self, "保存图片",
            "已复制到剪贴板。是否同时保存为 PNG 文件？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            path, _ = QFileDialog.getSaveFileName(
                self, "保存图片", "选中区域.png", "PNG (*.png)"
            )
            if path:
                pixmap.save(path, "PNG")
                self._set_status(f"✅ 已保存: {path}", 3000)

    def _smart_paste(self):
        """智能粘贴：自动识别 TSV / CSV / 单值"""
        clipboard = QApplication.clipboard()
        text = clipboard.mimeData().text().strip() \
            if clipboard.mimeData().hasText() else ""
        if not text:
            return
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            idx = self.model.index(0, 0)
        sr, sc = idx.row(), idx.column()
        for delim, name in [('\t', 'TSV'), (',', 'CSV')]:
            data = self._parse_csv(text, delim)
            if data and len(data) >= 2:
                self._paste_data(data, sr, sc, name)
                return
        self._paste_single_value(text, sr, sc)

    def _parse_csv(self, text, delimiter):
        """解析 CSV / TSV 文本"""
        lines = text.split('\n')
        data = []
        for line in lines:
            if not line.strip():
                continue
            row = []
            cur = ""
            in_q = False
            for char in line:
                if char == '"':
                    in_q = not in_q
                elif char == delimiter and not in_q:
                    row.append(cur.strip().strip('"'))
                    cur = ""
                else:
                    cur += char
            row.append(cur.strip().strip('"'))
            if row:
                data.append(row)
        return data

    def _paste_data(self, data, sr, sc, format_name):
        """粘贴二维数据"""
        nr, nc = len(data), max(len(r) for r in data)
        while sr + nr > len(self.model._loaded_df):
            self.model._loaded_df.loc[len(self.model._loaded_df)] = \
                [None] * max(1, len(self.model._loaded_df.columns))
            self.model._total_rows = len(self.model._loaded_df)
        while sc + nc > len(self.model._loaded_df.columns):
            self.model._loaded_df[
                f"列{len(self.model._loaded_df.columns)+1}"
            ] = ''
            self.model._total_cols = len(self.model._loaded_df.columns)
        for r, rd in enumerate(data):
            for c, cv in enumerate(rd):
                ri, ci = sr + r, sc + c
                if ri < len(self.model._loaded_df) \
                   and ci < len(self.model._loaded_df.columns):
                    try:
                        cv = float(cv) if '.' in str(cv) else int(cv)
                    except:
                        pass
                    self.model._loaded_df.iloc[ri, ci] = cv
        self.model.layoutChanged.emit()
        self._dirty = True
        self._set_status(f"已粘贴{format_name}({nr}行×{nc}列)", 3000)

    def _paste_single_value(self, text, sr, sc):
        """粘贴单值列"""
        lines = text.split('\n')
        for r, line in enumerate(lines):
            if sr + r < len(self.model._loaded_df) \
               and sc < len(self.model._loaded_df.columns):
                try:
                    val = float(line) if '.' in line else int(line)
                except:
                    val = line
                self.model._loaded_df.iloc[sr + r, sc] = val
        self.model.layoutChanged.emit()

    # ==================== 数据验证 ====================
    def _show_data_validation_dialog(self):
        """数据验证对话框"""
        sel = self.table_view.selectionModel().selection()
        if not sel or not sel.indexes():
            QMessageBox.information(
                self, "提示", "请先选中要添加验证的单元格"
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("📋 数据验证")
        dlg.resize(420, 280)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("选择验证类型："))
        type_combo = QComboBox()
        type_combo.addItems(
            ["下拉列表", "数值范围", "文本长度", "清除验证"]
        )
        layout.addWidget(type_combo)

        list_label = QLabel("下拉选项（每行一个）：")
        list_edit = QTextEdit()
        list_edit.setPlaceholderText("例如：\n北京\n上海\n广州")
        list_edit.setMaximumHeight(120)

        range_label = QLabel("数值范围：")
        range_layout = QHBoxLayout()
        min_edit = QLineEdit()
        min_edit.setPlaceholderText("最小值")
        max_edit = QLineEdit()
        max_edit.setPlaceholderText("最大值")
        range_layout.addWidget(min_edit)
        range_layout.addWidget(QLabel("~"))
        range_layout.addWidget(max_edit)

        def on_type_changed(text):
            list_label.setVisible(text == "下拉列表")
            list_edit.setVisible(text == "下拉列表")
            range_label.setVisible(text == "数值范围")
            min_edit.setVisible(text == "数值范围")
            max_edit.setVisible(text == "数值范围")

        type_combo.currentTextChanged.connect(on_type_changed)
        layout.addWidget(list_label)
        layout.addWidget(list_edit)
        layout.addWidget(range_label)
        layout.addLayout(range_layout)

        cur = sel.indexes()[0]
        existing = self._data_validations.get((cur.row(), cur.column()))
        if isinstance(existing, list):
            list_edit.setPlainText("\n".join(existing))
        on_type_changed("下拉列表")

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        layout.addWidget(btns)

        def on_ok():
            vtype = type_combo.currentText()
            if vtype == "清除验证":
                for idx in sel.indexes():
                    self._data_validations.pop(
                        (idx.row(), idx.column()), None
                    )
                self.model.layoutChanged.emit()
                dlg.accept()
                self._set_status("✅ 已清除验证", 2000)
                return
            if vtype == "下拉列表":
                options = [
                    line.strip() for line in
                    list_edit.toPlainText().split("\n") if line.strip()
                ]
                if not options:
                    QMessageBox.warning(
                        dlg, "提示", "请至少输入一个选项"
                    )
                    return
                for idx in sel.indexes():
                    self._data_validations[
                        (idx.row(), idx.column())
                    ] = options
                self.model.layoutChanged.emit()
                self._set_status(
                    f"✅ 已为 {len(sel.indexes())} 个单元格添加下拉"
                    f"（{len(options)} 项）", 3000
                )
            elif vtype == "数值范围":
                try:
                    lo = float(min_edit.text()) if min_edit.text() else None
                    hi = float(max_edit.text()) if max_edit.text() else None
                except ValueError:
                    QMessageBox.warning(
                        dlg, "提示", "请输入有效数字"
                    )
                    return
                for idx in sel.indexes():
                    self._data_validations[
                        (idx.row(), idx.column())
                    ] = {"_type": "range", "min": lo, "max": hi}
                self._set_status("✅ 已添加数值验证", 2000)
            dlg.accept()

        btns.accepted.connect(on_ok)
        btns.rejected.connect(dlg.reject)
        dlg.exec()

    # ==================== 名称管理 ====================
    def _show_name_manager(self):
        """名称管理器"""
        dlg = QDialog(self)
        dlg.setWindowTitle("🏷️ 名称管理器")
        dlg.resize(500, 400)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("已定义的名称："))
        lst = QListWidget()
        for name, ref in sorted(self._named_ranges.items()):
            item = QListWidgetItem(f"{name}  →  {ref}")
            item.setData(Qt.UserRole, name)
            lst.addItem(item)
        layout.addWidget(lst)

        form = QFormLayout()
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("例如：销售额")
        form.addRow("名称:", name_edit)
        ref_edit = QLineEdit()
        ref_edit.setPlaceholderText("例如：A1:A10")
        form.addRow("引用:", ref_edit)

        def fill_from_selection():
            sel = self.table_view.selectionModel().selection()
            if sel and sel.indexes():
                indexes = sel.indexes()
                r1 = min(i.row() for i in indexes)
                c1 = min(i.column() for i in indexes)
                r2 = max(i.row() for i in indexes)
                c2 = max(i.column() for i in indexes)
                if r1 == r2 and c1 == c2:
                    ref = f"{self._col_index_to_name(c1)}{r1+1}"
                else:
                    ref = (f"{self._col_index_to_name(c1)}{r1+1}:"
                           f"{self._col_index_to_name(c2)}{r2+1}")
                ref_edit.setText(ref)

        fill_btn = QPushButton("从当前选区填充")
        fill_btn.clicked.connect(fill_from_selection)
        form.addRow(fill_btn)
        layout.addLayout(form)

        bl = QHBoxLayout()
        add_btn = QPushButton("➕ 添加/更新")
        del_btn = QPushButton("🗑️ 删除选中")
        bl.addWidget(add_btn)
        bl.addWidget(del_btn)
        bl.addStretch()
        close_btn = QPushButton("关闭")
        bl.addWidget(close_btn)
        layout.addLayout(bl)

        def refresh():
            lst.clear()
            for name, ref in sorted(self._named_ranges.items()):
                item = QListWidgetItem(f"{name}  →  {ref}")
                item.setData(Qt.UserRole, name)
                lst.addItem(item)

        def on_add():
            name = name_edit.text().strip()
            ref = ref_edit.text().strip().upper()
            if not name:
                QMessageBox.warning(dlg, "提示", "请输入名称")
                return
            if not re.match(
                r'^[\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z0-9_]*$',
                name
            ):
                QMessageBox.warning(
                    dlg, "提示",
                    "名称只能包含中文、字母、数字、下划线"
                )
                return
            if name.upper() in ("SUM", "AVERAGE", "IF", "VLOOKUP"):
                QMessageBox.warning(
                    dlg, "提示", "名称不能与函数名冲突"
                )
                return
            if not ref:
                QMessageBox.warning(dlg, "提示", "请输入引用区域")
                return
            self._named_ranges[name] = ref
            refresh()
            name_edit.clear()
            self._set_status(f"✅ 已定义名称「{name}」→ {ref}", 3000)

        def on_del():
            item = lst.currentItem()
            if not item:
                return
            name = item.data(Qt.UserRole)
            if name in self._named_ranges:
                del self._named_ranges[name]
                refresh()
                self._set_status(f"✅ 已删除名称「{name}」", 2000)

        add_btn.clicked.connect(on_add)
        del_btn.clicked.connect(on_del)
        close_btn.clicked.connect(dlg.accept)
        dlg.exec()

    # ==================== 智能填充 ====================
    def _flash_fill(self):
        """
        智能填充：学习用户在第一行输入的示例，自动填充整列
        支持模式：取前/后 N 字符、提取数字、提取中文、
                  大写/小写、加前缀/后缀、按分隔符拆分
        """
        idx = self.table_view.currentIndex()
        if not idx.isValid():
            QMessageBox.information(self, "提示", "请先选中要填充的列")
            return
        col = idx.column()

        # 找第一个非空单元格作为示例
        sample_row = -1
        for r in range(len(self.model._loaded_df)):
            v = self.model.get_value(r, col)
            if v is not None and str(v).strip() != '':
                sample_row = r
                break
        if sample_row < 0:
            QMessageBox.information(self, "提示", "该列没有示例数据")
            return

        sample_value = str(self.model.get_value(sample_row, col))
        source_col = self._detect_source_column(
            sample_row, col, sample_value
        )
        if source_col is None:
            QMessageBox.information(
                self, "提示",
                "无法识别填充模式。\n"
                "请先手动填写前 1-3 行的示例，再使用智能填充。"
            )
            return

        pattern = self._learn_pattern(
            str(self.model.get_value(sample_row, source_col)),
            sample_value
        )
        if not pattern:
            QMessageBox.information(
                self, "提示", "未能识别出填充规则，请检查示例内容"
            )
            return

        count = 0
        for r in range(sample_row + 1, len(self.model._loaded_df)):
            src_val = self.model.get_value(r, source_col)
            if src_val is None or str(src_val).strip() == '':
                continue
            try:
                result = self._apply_pattern(pattern, str(src_val))
                if result is not None:
                    old = self.model.get_value(r, col)
                    self._push_command(
                        EditCellCommand(r, col, old, result)
                    )
                    count += 1
            except Exception:
                continue
        self.model.layoutChanged.emit()
        self._set_status(f"✅ 智能填充完成：{count} 行", 3000)

    def _detect_source_column(self, sample_row, target_col, sample_value):
        """检测目标列的值来源于哪一列"""
        for c in range(target_col - 1, -1, -1):
            src_val = self.model.get_value(sample_row, c)
            if src_val is None or str(src_val).strip() == '':
                continue
            if self._is_pattern_source(str(src_val).strip(), sample_value):
                return c
        for c in range(target_col + 1, len(self.model._loaded_df.columns)):
            src_val = self.model.get_value(sample_row, c)
            if src_val is None or str(src_val).strip() == '':
                continue
            if self._is_pattern_source(str(src_val).strip(), sample_value):
                return c
        return None

    def _is_pattern_source(self, src, sample):
        """判断 src 是否是 sample 的来源"""
        if not src or not sample:
            return False
        if sample in src:
            return True
        nums_src = re.findall(r'\d+', src)
        nums_sample = re.findall(r'\d+', sample)
        if nums_src and nums_sample and nums_src == nums_sample:
            return True
        cn_src = re.findall(r'[\u4e00-\u9fff]+', src)
        cn_sample = re.findall(r'[\u4e00-\u9fff]+', sample)
        if cn_src and cn_sample:
            for c1 in cn_src:
                for c2 in cn_sample:
                    if c1 in c2 or c2 in c1:
                        return True
        if sample == src.upper() or sample == src.lower():
            return True
        return False

    def _learn_pattern(self, src, sample):
        """从 src → sample 学习转换模式"""
        if src == sample:
            return ("copy", None)
        if sample == src.upper() and src != sample:
            return ("upper", None)
        if sample == src.lower() and src != sample:
            return ("lower", None)
        for n in range(1, min(len(src), 10) + 1):
            if sample == src[:n]:
                return ("prefix", n)
        for n in range(1, min(len(src), 10) + 1):
            if sample == src[-n:]:
                return ("suffix", n)
        nums = re.findall(r'\d+', src)
        if nums:
            sample_nums = re.findall(r'\d+', sample)
            if len(nums) == 1 and nums[0] == sample.strip():
                return ("extract_number", None)
            if sample_nums and ''.join(nums) == ''.join(sample_nums):
                return ("extract_number", None)
        cn = ''.join(re.findall(r'[\u4e00-\u9fff]+', src))
        if cn == sample:
            return ("extract_chinese", None)
        if len(sample) == 1 and src.startswith(sample):
            return ("prefix", 1)
        if len(sample) == 1 and src.endswith(sample):
            return ("suffix", 1)
        for delim in [' ', '-', '_', ',', '.', '/', '|', ':', '：', '，']:
            if delim in src:
                parts = src.split(delim)
                for i, part in enumerate(parts):
                    if part.strip() == sample:
                        return ("split", (delim, i))
        if src in sample and sample != src:
            prefix = sample[:sample.index(src)]
            if prefix:
                return ("add_prefix", prefix)
        if src in sample and sample != src:
            suffix = sample[sample.index(src) + len(src):]
            if suffix:
                return ("add_suffix", suffix)
        return None

    def _apply_pattern(self, pattern, value):
        """将模式应用到值上"""
        kind, param = pattern
        try:
            if kind == "copy":
                return value
            elif kind == "upper":
                return value.upper()
            elif kind == "lower":
                return value.lower()
            elif kind == "prefix":
                return value[:param]
            elif kind == "suffix":
                return value[-param:]
            elif kind == "extract_number":
                nums = re.findall(r'\d+', value)
                return ''.join(nums) if nums else ""
            elif kind == "extract_chinese":
                return ''.join(re.findall(r'[\u4e00-\u9fff]+', value))
            elif kind == "split":
                delim, idx = param
                parts = value.split(delim)
                if idx < len(parts):
                    return parts[idx].strip()
                return ""
            elif kind == "add_prefix":
                return param + value
            elif kind == "add_suffix":
                return value + param
        except Exception:
            return None
        return None

    # ==================== 选中统计 ====================
    def _show_selection_stats(self):
        """显示选中区域的统计信息"""
        sel = self.table_view.selectionModel().selection()
        if not sel or not sel.indexes():
            QMessageBox.information(
                self, "提示", "请先选中要统计的区域"
            )
            return
        indexes = sel.indexes()
        numeric_values = []
        text_count = 0
        empty_count = 0
        total_count = len(indexes)
        for idx in indexes:
            v = self.model.get_value(idx.row(), idx.column())
            if v is None or str(v).strip() == '':
                empty_count += 1
                continue
            try:
                numeric_values.append(float(v))
            except (ValueError, TypeError):
                text_count += 1

        dlg = QDialog(self)
        dlg.setWindowTitle("📊 选中统计")
        dlg.resize(360, 340)
        layout = QVBoxLayout(dlg)

        header = QLabel(f"<b>选中区域：{total_count} 个单元格</b>")
        header.setStyleSheet("font-size:14px;padding:8px;")
        layout.addWidget(header)

        stats = [
            ("📌 总数", total_count),
            ("🔢 数值个数", len(numeric_values)),
            ("📝 文本个数", text_count),
            ("⬜ 空单元格", empty_count),
        ]
        if numeric_values:
            stats.extend([
                ("➕ 求和", f"{sum(numeric_values):,.4g}"),
                ("➗ 平均",
                 f"{sum(numeric_values)/len(numeric_values):,.4g}"),
                ("🔺 最大值", f"{max(numeric_values):,.4g}"),
                ("🔻 最小值", f"{min(numeric_values):,.4g}"),
            ])

        for label, value in stats:
            row = QHBoxLayout()
            l = QLabel(label)
            l.setStyleSheet("font-size:13px;color:#555;")
            v = QLabel(str(value))
            v.setStyleSheet(
                "font-size:13px;color:#0D47A1;font-weight:bold;"
                "background:#F5F5F5;padding:4px 10px;border-radius:4px;"
                "min-width:120px;"
            )
            v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(l)
            row.addStretch()
            row.addWidget(v)
            layout.addLayout(row)

        layout.addStretch()
        bl = QHBoxLayout()

        def copy_stats():
            lines = [f"选中统计（{total_count} 个单元格）"]
            for label, value in stats:
                lines.append(f"{label}: {value}")
            QApplication.clipboard().setText("\n".join(lines))

        copy_btn = QPushButton("📋 复制统计")
        copy_btn.clicked.connect(copy_stats)
        bl.addWidget(copy_btn)
        bl.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dlg.reject)
        bl.addWidget(close_btn)
        layout.addLayout(bl)
        dlg.exec()