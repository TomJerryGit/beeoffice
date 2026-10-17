# beeoffice/plugins/beesheet_loaders.py
"""
蜜算后台加载线程：分块加载、大文件加载

v5.0.1 修复（P0-15）：
  - LargeFileLoader 支持中断
    - 新增 cancelled 信号
    - run() 加载完成后检查 isInterruptionRequested()，是则发 cancelled 而非 finished
    - _load_csv() 每处理一块前检查中断
    - _load_excel() 每 1000 行检查一次中断（避免性能损耗），
      中断时先 wb.close() 再返回
  - 异常处理：中断时不再发出 error_occurred，避免误导用户
"""
import pandas as pd
from pathlib import Path
from PySide6.QtCore import QThread, Signal


class ChunkLoader(QThread):
    """分块加载线程（用于滚动时按需加载）"""

    chunk_loaded = Signal(int)
    all_loaded = Signal()
    progress = Signal(float)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self._pending_chunks = set()
        self._running = True

    def add_chunks(self, chunks):
        """添加待加载的分块索引集合"""
        self._pending_chunks.update(chunks)
        if not self.isRunning():
            self.start()

    def run(self):
        """循环处理待加载分块"""
        while self._running and self._pending_chunks:
            chunk = self._pending_chunks.pop()
            if self.model.load_chunk(chunk):
                self.chunk_loaded.emit(chunk)
            if self.model.loading_progress >= 1.0:
                self.all_loaded.emit()
                break
            self.msleep(10)

    def stop(self):
        """请求停止线程"""
        self._running = False


class LargeFileLoader(QThread):
    """
    大文件分块加载线程（P0-15：支持中断）

    信号说明：
      - chunk_ready(df_chunk, chunk_index, total_chunks)：每加载一块发出
      - finished_loading(full_df)：全部完成发出
      - error_occurred(msg)：发生错误发出
      - progress_updated(pct)：进度百分比（0~100）
      - cancelled()：用户取消加载时发出
    """

    chunk_ready = Signal(object, int, int)   # (df_chunk, chunk_index, total_chunks)
    finished_loading = Signal(object)        # 完整 DataFrame
    error_occurred = Signal(str)             # 错误信息
    progress_updated = Signal(int)           # 进度百分比
    cancelled = Signal()                     # P0-15：取消信号

    def __init__(self, filepath, chunk_size=50000, parent=None):
        """
        :param filepath: 文件路径
        :param chunk_size: 每个分块的行数
        """
        super().__init__(parent)
        self.filepath = filepath
        self.chunk_size = chunk_size

    def run(self):
        """执行分块加载（P0-15：支持中断）"""
        try:
            path = self.filepath
            ext = Path(path).suffix.lower()
            chunks = []

            if ext in ('.csv', '.txt'):
                self._load_csv(path, chunks)
            elif ext in ('.xlsx', '.xls'):
                self._load_excel(path, chunks)
            else:
                self.error_occurred.emit(f"不支持的文件格式: {ext}")
                return

            # P0-15：加载完成后检查是否被中断
            if self.isInterruptionRequested():
                self.cancelled.emit()
                return

            if not chunks:
                self.error_occurred.emit("文件为空")
                return

            full_df = pd.concat(chunks, ignore_index=True)

            # P0-15：concat 之后再次检查（大文件 concat 可能耗时）
            if self.isInterruptionRequested():
                self.cancelled.emit()
                return

            self.progress_updated.emit(100)
            self.finished_loading.emit(full_df)

        except Exception as e:
            # P0-15：中断导致的异常不报告为 error
            if not self.isInterruptionRequested():
                self.error_occurred.emit(str(e))

    def _load_csv(self, path, chunks):
        """分块加载 CSV / TXT（P0-15：每块前检查中断）"""
        import chardet

        # 检测编码
        with open(path, 'rb') as f:
            raw = f.read(10000)
        encoding = chardet.detect(raw).get('encoding', 'utf-8') or 'utf-8'

        total_rows = 0
        for idx, chunk in enumerate(pd.read_csv(
            path,
            encoding=encoding,
            chunksize=self.chunk_size,
            low_memory=False,
            on_bad_lines='skip'
        )):
            # P0-15：每处理一块前检查中断
            if self.isInterruptionRequested():
                return

            chunks.append(chunk)
            total_rows += len(chunk)
            self.chunk_ready.emit(chunk, idx, -1)
            # 每 5 万行约 2% 进度
            self.progress_updated.emit(
                min(int(total_rows / 100000 * 2), 95)
            )

    def _load_excel(self, path, chunks):
        """分块加载 Excel（只读模式，P0-15：每 1000 行检查中断）"""
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = []
        total = 0
        header = None

        try:
            for row in ws.iter_rows(values_only=True):
                # P0-15：每 1000 行检查一次中断，避免性能损耗
                if total % 1000 == 0 and self.isInterruptionRequested():
                    wb.close()
                    return

                if header is None:
                    header = list(row)
                    continue
                rows.append(list(row))
                total += 1
                if len(rows) >= self.chunk_size:
                    df = pd.DataFrame(rows, columns=header)
                    chunks.append(df)
                    self.chunk_ready.emit(df, len(chunks) - 1, -1)
                    rows = []
                    self.progress_updated.emit(
                        min(int(total / 200000 * 2), 95)
                    )

            # 处理最后一批不足 chunk_size 的行
            if rows:
                df = pd.DataFrame(rows, columns=header)
                chunks.append(df)
        finally:
            # P0-15：确保 workbook 被关闭（无论正常结束还是中断）
            try:
                wb.close()
            except Exception:
                pass