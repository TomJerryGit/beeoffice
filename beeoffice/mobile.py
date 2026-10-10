# beeoffice/mobile.py
"""
移动端 HTTP 服务器：让手机通过浏览器访问当前打开的文档

v5.0.1 修复：
  - P0-3：删除 os.chdir() 调用，避免劫持整个进程的工作目录
  - P1-17：MobileServer 每次实例化使用独立子目录，避免多实例 index.html 冲突
  - P1-17：stop() 时清理本次会话的临时目录
"""
import json
import socket
import threading
import http.server
import socketserver
import tempfile
import uuid
import logging
from pathlib import Path

from PySide6.QtWidgets import QMessageBox


class MobileServer:
    """移动端 HTTP 服务器"""

    def __init__(self, parent):
        """
        :param parent: 主窗口实例（BeeApp）
        """
        self.parent = parent
        self.server = None
        self.thread = None
        self.port = None
        self.ip = None
        # P1-17：每次实例化用独立的临时目录，避免多实例互相覆盖 index.html
        session_id = uuid.uuid4().hex[:8]
        self.temp_dir = (
            Path(tempfile.gettempdir()) / "beeoffice_mobile" / session_id
        )

    # ---------- 启动 ----------
    def start(self):
        """启动移动端服务"""
        # 若已在运行，提示并返回
        if self.server is not None:
            QMessageBox.information(
                self.parent, "提示",
                f"移动端服务已在运行，地址：http://{self.ip}:{self.port}"
            )
            return

        # 获取当前文档
        widget = self.parent.tab_manager.currentWidget()
        if not widget:
            QMessageBox.information(self.parent, "提示", "请先打开文档")
            return

        # 准备临时目录
        try:
            self.temp_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logging.error(f"创建临时目录失败: {e}")
            QMessageBox.warning(self.parent, "错误", f"创建临时目录失败: {e}")
            return

        # 生成首页
        self._generate_index()

        # 获取本机 IP
        try:
            self.ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            self.ip = "127.0.0.1"

        # 寻找可用端口（从 8888 开始递增）
        port = 8888
        max_attempts = 100
        for _ in range(max_attempts):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((self.ip, port))
                s.close()
                break
            except OSError:
                port += 1
        else:
            QMessageBox.warning(self.parent, "错误", "无法找到可用端口")
            return
        self.port = port

        # P0-3：原实现此处有 os.chdir(str(self.temp_dir))，
        # 会劫持整个进程的工作目录，导致用户相对路径操作全部指向临时目录。
        # _create_handler() 已通过 directory=temp_dir 指定根目录，无需 chdir。

        # 创建自定义 HTTP 服务器
        handler = self._create_handler()
        try:
            server = _ThreadingHTTPServer(("", port), handler)
        except Exception as e:
            logging.error(f"启动 HTTP 服务器失败: {e}")
            QMessageBox.warning(self.parent, "错误", f"启动失败: {e}")
            return
        self.server = server

        # 后台线程运行
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()

        QMessageBox.information(
            self.parent, "📱 移动端查看",
            f"在手机浏览器访问：\nhttp://{self.ip}:{self.port}\n\n"
            f"（确保手机与本机在同一局域网）"
        )

    # ---------- 停止 ----------
    def stop(self):
        """停止移动端服务（P1-17：清理临时目录）"""
        if self.server is None:
            return
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception as e:
            logging.error(f"停止服务器失败: {e}")
        finally:
            self.server = None
            self.thread = None
            self.port = None
            self.ip = None

            # P1-17：删除本次会话的临时目录
            try:
                import shutil
                if self.temp_dir.exists():
                    shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception as e:
                logging.error(f"清理临时目录失败: {e}")

    # ---------- 生成首页 ----------
    def _generate_index(self):
        """生成首页 HTML（单页应用风格）"""
        html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🐝 蜜蜂办公</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                         "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
            max-width: 800px; margin: 0 auto; padding: 16px;
            background: #f5f5f5; color: #333;
        }
        h1 { color: #FFB300; margin: 0 0 16px; font-size: 24px; }
        .doc-item {
            padding: 16px; margin: 10px 0; background: #fff;
            border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            cursor: pointer; transition: transform 0.15s, box-shadow 0.15s;
            text-decoration: none; color: inherit; display: block;
        }
        .doc-item:active { transform: scale(0.98); }
        .doc-item:hover { box-shadow: 0 3px 8px rgba(0,0,0,0.15); }
        .doc-title { font-size: 18px; font-weight: 500; margin-bottom: 4px; }
        .doc-type { color: #888; font-size: 13px; }
        .empty { text-align: center; color: #888; padding: 40px 20px; }
        .back { display: inline-block; margin-bottom: 16px; color: #FFB300; text-decoration: none; font-size: 15px; }
        .content { background: #fff; padding: 20px; border-radius: 8px; line-height: 1.7; }
        .content img { max-width: 100%; }
        .content pre { background: #f4f4f4; padding: 12px; border-radius: 4px; overflow-x: auto; }
        .content code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
        .content table { border-collapse: collapse; width: 100%; margin: 10px 0; }
        .content th, .content td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        .content th { background: #f0f0f0; }
        .content h1, .content h2, .content h3 { color: #333; }
        .loading { text-align: center; padding: 40px; color: #888; }
    </style>
</head>
<body>
    <h1>🐝 蜜蜂办公</h1>
    <div id="app"><div class="loading">加载中...</div></div>

    <script>
        const app = document.getElementById('app');

        // 加载文档列表
        function loadDocs() {
            fetch('/api/docs')
                .then(res => res.json())
                .then(data => {
                    if (!data.length) {
                        app.innerHTML = '<div class="empty">当前没有打开的文档</div>';
                        return;
                    }
                    let html = '';
                    data.forEach(doc => {
                        html += `<a class="doc-item" href="#/view/${doc.id}">
                            <div class="doc-title">${escapeHtml(doc.title)}</div>
                            <div class="doc-type">${escapeHtml(doc.type)}</div>
                        </a>`;
                    });
                    app.innerHTML = html;
                })
                .catch(err => {
                    app.innerHTML = '<div class="empty">加载失败：' + err + '</div>';
                });
        }

        // 加载文档内容
        function loadDoc(id) {
            app.innerHTML = '<div class="loading">加载中...</div>';
            fetch('/api/view/' + id)
                .then(res => res.json())
                .then(data => {
                    if (data.error) {
                        app.innerHTML = `<a class="back" href="#/">← 返回</a>
                            <div class="empty">${escapeHtml(data.error)}</div>`;
                        return;
                    }
                    app.innerHTML = `<a class="back" href="#/">← 返回</a>
                        <div class="content">${data.html}</div>`;
                })
                .catch(err => {
                    app.innerHTML = `<a class="back" href="#/">← 返回</a>
                        <div class="empty">加载失败：${err}</div>`;
                });
        }

        // 简单 HTML 转义
        function escapeHtml(s) {
            if (!s) return '';
            return String(s).replace(/[&<>"']/g, c => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            })[c]);
        }

        // 路由处理
        function route() {
            const hash = window.location.hash || '#/';
            if (hash.startsWith('#/view/')) {
                const id = hash.substring(7);
                loadDoc(id);
            } else {
                loadDocs();
            }
        }

        window.addEventListener('hashchange', route);
        route();
    </script>
</body>
</html>"""
        try:
            (self.temp_dir / "index.html").write_text(html, encoding="utf-8")
        except Exception as e:
            logging.error(f"写入首页失败: {e}")

    # ---------- 请求处理器 ----------
    def _create_handler(self):
        """创建自定义 HTTP 请求处理器"""
        parent = self.parent
        temp_dir = str(self.temp_dir)

        class MobileHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=temp_dir, **kwargs)

            def log_message(self, format, *args):
                """静默访问日志"""
                pass

            def do_GET(self):
                if self.path.startswith("/api/docs"):
                    self._handle_docs_api()
                elif self.path.startswith("/api/view/"):
                    self._handle_view_api()
                else:
                    super().do_GET()

            def _handle_docs_api(self):
                """返回文档列表 JSON"""
                docs = []
                try:
                    for i in range(parent.tab_manager.count()):
                        widget = parent.tab_manager.widget(i)
                        title = parent.tab_manager.tabText(i)
                        doc_type = self._get_doc_type(widget)
                        docs.append({"id": i, "title": title, "type": doc_type})
                except Exception as e:
                    logging.error(f"获取文档列表失败: {e}")

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(docs, ensure_ascii=False).encode("utf-8"))

            def _handle_view_api(self):
                """返回单个文档内容 JSON"""
                try:
                    doc_id = int(self.path.split("/")[-1])
                    widget = parent.tab_manager.widget(doc_id)
                    if widget is None:
                        raise ValueError("文档不存在")

                    html = self._render_widget(widget)
                    data = {"html": html}
                except Exception as e:
                    data = {"error": str(e)}

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

            def _render_widget(self, widget):
                """将控件内容渲染为 HTML"""
                # 蜜写：Markdown 转 HTML
                if hasattr(widget, "content") and not hasattr(widget, "model"):
                    try:
                        import markdown
                        content = widget.content()
                        return markdown.markdown(
                            content,
                            extensions=["tables", "fenced_code", "nl2br"]
                        )
                    except Exception as e:
                        logging.error(f"Markdown 渲染失败: {e}")
                        return f"<p>渲染失败: {e}</p>"

                # 蜜算：DataFrame 转 HTML
                if hasattr(widget, "model") and hasattr(widget.model, "df"):
                    try:
                        df = widget.model.df
                        # 限制行数，避免超大表格
                        if len(df) > 1000:
                            df = df.head(1000)
                        return df.to_html(index=False, escape=True)
                    except Exception as e:
                        logging.error(f"表格渲染失败: {e}")
                        return f"<p>表格渲染失败: {e}</p>"

                # 蜜演：返回提示
                if hasattr(widget, "slide_widgets"):
                    return "<p>蜜演演示文稿暂不支持移动端预览</p>"

                # 纯文本编辑器
                if hasattr(widget, "toPlainText"):
                    text = widget.toPlainText()
                    escaped = (
                        text.replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                            .replace("\n", "<br>")
                    )
                    return f"<p>{escaped}</p>"

                return "<p>该类型文档暂不支持移动端预览</p>"

            def _get_doc_type(self, widget):
                """识别文档类型"""
                if hasattr(widget, "slide_widgets"):
                    return "蜜演"
                if hasattr(widget, "model") and hasattr(widget.model, "df"):
                    return "蜜算"
                if hasattr(widget, "editor") and hasattr(widget, "preview"):
                    return "蜜写"
                if hasattr(widget, "toPlainText"):
                    return "文本"
                return "其他"

        return MobileHandler


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """支持多线程的 HTTP 服务器，允许地址复用"""
    allow_reuse_address = True
    daemon_threads = True