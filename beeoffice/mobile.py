# beeoffice/mobile.py
"""
移动端 HTTP 服务器：让手机通过浏览器访问当前打开的文档

v5.0.1 修复：
  - P0-3：删除 os.chdir() 调用，避免劫持整个进程的工作目录
  - P1-17：MobileServer 每次实例化使用独立子目录，避免多实例 index.html 冲突
  - P1-17：stop() 时清理本次会话的临时目录

v5.0.5 安全加固（优化规划 §1.4）：
  原实现存在三个叠加问题，使"打开移动端查看"等于把当前所有打开的文档
  暴露给整个局域网与同机的任意网页：

    1. `_ThreadingHTTPServer(("", port), ...)` 绑定 0.0.0.0（所有网卡），
       且没有任何鉴权 —— 同一 Wi-Fi 下任何人访问 /api/docs 就能列出并读取
       全部文档。
    2. 两个 API 都发送 `Access-Control-Allow-Origin: *`，于是用户在本机
       浏览器打开的任意网页都能跨域 fetch 这些接口并读取响应体。
    3. 首页把 /api/view 返回的 HTML 直接 `innerHTML` 注入，而服务端用
       python-markdown 渲染时默认放行原始 HTML —— 文档里的
       `<img src=x onerror=...>` 会在手机浏览器里执行同源脚本。

  加固后：
    - 默认只监听 127.0.0.1；需要手机访问时必须显式开启 allow_lan。
    - 每次启动生成一次性令牌（secrets.token_urlsafe），仅出现在应用展示
      给用户的 URL 里；/api/* 必须携带 `?t=` 或 Bearer 令牌，否则 403。
    - 不再发送任何 CORS 头（跨站读取响应体被浏览器阻断）。
    - 校验 Host 头，抵御 DNS rebinding；显式拒绝 HEAD（继承实现会绕过
      令牌校验并可用于枚举目录）。
    - 首页改为「静态 HTML + 外部 app.js」，并下发
      `script-src 'self'` 的 CSP：注入的 <script>、on* 事件属性与
      javascript: URL 一律不会执行。
"""
import json
import socket
import secrets
import threading
import http.server
import socketserver
import tempfile
import uuid
import logging
from pathlib import Path
from urllib.parse import urlparse, parse_qs


class MobileServer:
    """移动端 HTTP 服务器"""

    #: 首页内容安全策略。关键点是 script-src 'self'——内联脚本与内联事件
    #: 处理器（onerror= 等）都被禁止，因此即便文档内容里带脚本也无法执行。
    CSP = (
        "default-src 'none'; "
        "script-src 'self'; "
        "style-src 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "base-uri 'none'; "
        "form-action 'none'"
    )

    def __init__(self, parent, allow_lan: bool = False):
        """
        :param parent: 主窗口实例（BeeApp）
        :param allow_lan: 是否允许局域网访问。默认 False，只监听回环地址。
        """
        self.parent = parent
        self.server = None
        self.thread = None
        self.port = None
        self.ip = None
        self.allow_lan = bool(allow_lan)
        # 一次性访问令牌：只出现在展示给用户的 URL 中
        self.token = secrets.token_urlsafe(16)
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
            QMessageBox = self._qmessagebox()
            QMessageBox.information(
                self.parent, "提示",
                f"移动端服务已在运行，地址：{self.access_url()}"
            )
            return

        # 获取当前文档
        widget = self.parent.tab_manager.currentWidget()
        if not widget:
            self._qmessagebox().information(self.parent, "提示", "请先打开文档")
            return

        # 准备临时目录
        try:
            self.temp_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logging.error(f"创建临时目录失败: {e}")
            self._qmessagebox().warning(
                self.parent, "错误", f"创建临时目录失败: {e}"
            )
            return

        # 生成首页与脚本
        self._generate_index()

        # 展示用地址：未开启局域网时只对本机有意义
        try:
            lan_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            lan_ip = "127.0.0.1"
        self.ip = lan_ip if self.allow_lan else "127.0.0.1"

        # 绑定地址（优化规划 §1.4）：默认只监听回环，避免无鉴权暴露到局域网
        bind_host = self._bind_host()

        # 寻找可用端口（从 8888 开始递增）
        port = 8888
        max_attempts = 100
        for _ in range(max_attempts):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((bind_host, port))
                s.close()
                break
            except OSError:
                port += 1
        else:
            self._qmessagebox().warning(self.parent, "错误", "无法找到可用端口")
            return
        self.port = port

        # P0-3：原实现此处有 os.chdir(str(self.temp_dir))，
        # 会劫持整个进程的工作目录，导致用户相对路径操作全部指向临时目录。
        # _create_handler() 已通过 directory=temp_dir 指定根目录，无需 chdir。

        # 创建自定义 HTTP 服务器
        handler = self._create_handler()
        try:
            server = _ThreadingHTTPServer((bind_host, port), handler)
        except Exception as e:
            logging.error(f"启动 HTTP 服务器失败: {e}")
            self._qmessagebox().warning(self.parent, "错误", f"启动失败: {e}")
            return
        self.server = server

        # 后台线程运行
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()

        url = self.access_url()
        if self.allow_lan:
            self._qmessagebox().information(
                self.parent, "📱 移动端查看",
                f"在手机浏览器访问（手机需与本机在同一局域网）：\n{url}\n\n"
                "⚠ 该服务对同一局域网内所有设备开放，"
                "查看结束后请及时停止。"
            )
        else:
            self._qmessagebox().information(
                self.parent, "📱 移动端查看",
                f"仅限本机浏览器访问：\n{url}\n\n"
                "如需用手机访问，请改用「允许局域网访问」。"
            )

    # ---------- 辅助 ----------
    def _bind_host(self) -> str:
        """
        实际监听地址。

        优化规划 §1.4：默认只绑定回环（127.0.0.1）。原实现固定绑定 ""
        （即 0.0.0.0，所有网卡）且没有任何鉴权，同一个 Wi-Fi 下任何人都能
        读取当前打开的全部文档。只有用户显式开启局域网访问才绑定所有网卡。

        独立成方法是为了让"生产绑定地址"可被测试直接断言——原测试自行用
        127.0.0.1 建服务器，恰好掩盖了生产路径的 0.0.0.0。
        """
        return "0.0.0.0" if self.allow_lan else "127.0.0.1"

    def access_url(self) -> str:
        """展示给用户的完整访问地址（含一次性令牌）。"""
        return f"http://{self.ip}:{self.port}/?t={self.token}"

    @staticmethod
    def _qmessagebox():
        """延迟导入 QMessageBox，便于无 GUI 环境下导入本模块做测试。"""
        from PySide6.QtWidgets import QMessageBox
        return QMessageBox

    def _allowed_hosts(self) -> set:
        """Host 头白名单，用于抵御 DNS rebinding。"""
        port = self.port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.allow_lan and self.ip:
            hosts.add(f"{self.ip}:{port}")
        return hosts

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
        """
        生成首页 HTML 与外部脚本。

        首页本身不含任何文档内容，因此不需要令牌；真正敏感的 /api/* 一律
        要求令牌并在浏览器侧由 app.js 从 location.search 取出后附带。

        脚本必须放在外部文件里：这样 CSP 才能用 script-src 'self'
        （内联脚本/内联事件处理器会被禁止），从而封住"文档 HTML 注入"路径。
        """
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
    <script src="/app.js"></script>
</body>
</html>"""

        script = """// 蜜蜂办公 移动端查看（外部脚本，配合 CSP script-src 'self'）
const app = document.getElementById('app');

// 一次性访问令牌：由应用展示的 URL（?t=...）带入
const TOKEN = new URLSearchParams(window.location.search).get('t') || '';

function apiUrl(path) {
    if (!TOKEN) return path;
    return path + (path.includes('?') ? '&' : '?') + 't=' + encodeURIComponent(TOKEN);
}

function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
}

function loadDocs() {
    fetch(apiUrl('/api/docs'))
        .then(res => res.json())
        .then(data => {
            if (!data.length) {
                app.innerHTML = '<div class="empty">当前没有打开的文档</div>';
                return;
            }
            let html = '';
            data.forEach(doc => {
                html += '<a class="doc-item" href="#/view/' + encodeURIComponent(doc.id) + '">'
                     + '<div class="doc-title">' + escapeHtml(doc.title) + '</div>'
                     + '<div class="doc-type">' + escapeHtml(doc.type) + '</div>'
                     + '</a>';
            });
            app.innerHTML = html;
        })
        .catch(err => {
            app.innerHTML = '<div class="empty">加载失败：' + escapeHtml(err) + '</div>';
        });
}

function loadDoc(id) {
    app.innerHTML = '<div class="loading">加载中...</div>';
    fetch(apiUrl('/api/view/' + encodeURIComponent(id)))
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                app.innerHTML = '<a class="back" href="#/">← 返回</a>'
                    + '<div class="empty">' + escapeHtml(data.error) + '</div>';
                return;
            }
            app.innerHTML = '<a class="back" href="#/">← 返回</a>'
                + '<div class="content"></div>';
            // 用 DOM 赋值而不是拼字符串，避免把内容当 HTML 解析
            app.querySelector('.content').innerHTML = data.html;
        })
        .catch(err => {
            app.innerHTML = '<a class="back" href="#/">← 返回</a>'
                + '<div class="empty">加载失败：' + escapeHtml(err) + '</div>';
        });
}

function route() {
    const hash = window.location.hash || '#/';
    if (hash.startsWith('#/view/')) {
        const raw = hash.substring(7);
        if (!/^\\d+$/.test(raw)) {
            app.innerHTML = '<div class="empty">无效的文档编号</div>';
            return;
        }
        loadDoc(raw);
    } else {
        loadDocs();
    }
}

window.addEventListener('hashchange', route);
route();
"""
        try:
            (self.temp_dir / "index.html").write_text(html, encoding="utf-8")
            (self.temp_dir / "app.js").write_text(script, encoding="utf-8")
        except Exception as e:
            logging.error(f"写入首页失败: {e}")

    # ---------- 请求处理器 ----------
    def _create_handler(self):
        """创建自定义 HTTP 请求处理器"""
        parent = self.parent
        temp_dir = str(self.temp_dir)
        expected_token = self.token
        allowed_hosts = self._allowed_hosts()

        class MobileHandler(http.server.SimpleHTTPRequestHandler):
            server_version = "BeeOfficeMobile/1.0"

            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=temp_dir, **kwargs)

            def log_message(self, format, *args):
                """静默访问日志"""
                pass

            # ---------- 访问控制（优化规划 §1.4） ----------
            def _client_token(self):
                qs = parse_qs(urlparse(self.path).query)
                if qs.get("t"):
                    return qs["t"][0]
                auth = self.headers.get("Authorization", "")
                if auth.lower().startswith("bearer "):
                    return auth[7:].strip()
                return ""

            def _host_ok(self):
                host = (self.headers.get("Host") or "").strip().lower()
                return bool(host) and host in allowed_hosts

            def _deny(self, code, message):
                body = message.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def end_headers(self):
                """
                统一附加安全响应头。

                这里**故意不发送** Access-Control-Allow-Origin：
                通配 CORS 会让同机浏览器中的任意网页跨域读取本服务返回的
                文档内容。
                """
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                if self.path in ("/", "/index.html") or self.path.startswith("/?"):
                    self.send_header("Content-Security-Policy", MobileServer.CSP)
                super().end_headers()

            def do_HEAD(self):
                # 继承实现会绕过令牌校验、并按进程 CWD 解析路径，
                # 可用于枚举文件/目录的存在性、大小与修改时间。
                self._deny(403, "不支持 HEAD 请求")

            def do_GET(self):
                if not self._host_ok():
                    self._deny(403, "非法的 Host")
                    return

                path_only = urlparse(self.path).path

                # 首页与脚本是静态外壳，不含文档内容；数据接口一律需要令牌
                if path_only.startswith("/api/"):
                    if not secrets.compare_digest(
                        self._client_token(), expected_token
                    ):
                        self._deny(
                            403,
                            "缺少或无效的访问令牌。"
                            "请使用应用内给出的完整地址（含 ?t=...）访问。",
                        )
                        return

                if path_only == "/api/docs":
                    self._handle_docs_api()
                elif path_only.startswith("/api/view/"):
                    self._handle_view_api()
                elif path_only.startswith("/api/"):
                    self._deny(404, "未知接口")
                else:
                    super().do_GET()

            def _send_json(self, payload):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header(
                    "Content-Type", "application/json; charset=utf-8"
                )
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

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
                self._send_json(docs)

            def _handle_view_api(self):
                """返回单个文档内容 JSON"""
                try:
                    raw_id = urlparse(self.path).path.rsplit("/", 1)[-1]
                    doc_id = int(raw_id)
                    widget = parent.tab_manager.widget(doc_id)
                    if widget is None:
                        raise ValueError("文档不存在")
                    data = {"html": self._render_widget(widget)}
                except Exception as e:
                    data = {"error": str(e)}
                self._send_json(data)

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
