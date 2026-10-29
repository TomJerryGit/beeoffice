# beeoffice/plugins/beeshow_sync_server.py
"""
蜜演远程同步服务器（任务 4.3）

职责：
  - 启动 / 停止 WebSocket 服务器
  - 广播演示者状态（当前页 / 激光笔 / 标注）
  - 提供观众端 HTML 页面
  - 提供幻灯片内容 API（观众端按需拉取）
  - 管理多个观众连接

设计：
  - 基于标准库 http.server + 简单的 WebSocket 协议实现
  - 不引入第三方依赖（websockets / aiohttp），保证轻量
  - 双端口策略：
      * HTTP 端口：提供观众页面 + 幻灯片内容 API（默认 8765）
      * WebSocket 端口：广播通道（默认 8766）

v5.1 增量汇总（3 处）：
  - __init__ 加 self._slides_html 初始化
  - ViewerHandler.do_GET 加 /api/slide/<idx> 路由
  - ViewerHandler 加 _serve_slide_content 方法
  - SyncServer 加 set_slides_html / get_slides_html 方法

对标：
  - WPS 365 的「观众扫码实时跟随翻页」

协议：
  广播消息（JSON）：
    {"type": "slide_change", "index": 3, "total": 10}
    {"type": "laser", "x": 0.45, "y": 0.62, "visible": true}
    {"type": "draw", "action": "start", "x": 0.3, "y": 0.4}
    {"type": "draw", "action": "move", "x": 0.5, "y": 0.6}
    {"type": "draw", "action": "end"}
    {"type": "black_screen", "visible": true}
    {"type": "theme_change", "theme": "科技黑"}

  HTTP API：
    GET /                    观众页面 HTML
    GET /sync                观众页面 HTML（别名）
    GET /api/info            服务器信息 JSON
    GET /api/slide/<idx>     第 idx 页的 HTML 片段

依赖：
  - 标准库（http.server / socketserver / threading / socket / json /
          base64 / hashlib / struct）
  - 无第三方依赖

注意：
  - WebSocket 协议实现简化版，仅支持服务端单向广播
  - 观众端只接收，不发送（除了握手）
  - 服务器运行在独立线程，不阻塞 UI
"""

import base64
import hashlib
import json
import logging
import secrets
import socket
import struct
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse, parse_qs


# WebSocket 握手用的魔术字符串（RFC 6455）
WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


# ==================== WebSocket 帧编解码 ====================
class WebSocketFrame:
    """WebSocket 帧的编解码"""

    @staticmethod
    def encode(payload: str) -> bytes:
        """
        把文本 payload 编码为 WebSocket 帧。

        简化实现：
          - FIN=1, opcode=1（文本帧）
          - 不用掩码（服务端发往客户端）
          - 支持 7 位和 16 位长度
        """
        data = payload.encode("utf-8")
        length = len(data)

        # 第一字节：FIN=1, opcode=1
        frame = bytearray([0x81])

        # 第二字节：MASK=0 + 长度
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(struct.pack(">H", length))
        else:
            frame.append(127)
            frame.extend(struct.pack(">Q", length))

        frame.extend(data)
        return bytes(frame)

    @staticmethod
    def decode_close_frame(data: bytes) -> bool:
        """判断是否是关闭帧"""
        if not data:
            return False
        opcode = data[0] & 0x0F
        return opcode == 0x8  # 关闭帧

    @staticmethod
    def decode_ping_frame(data: bytes) -> bool:
        """判断是否是 ping 帧"""
        if not data:
            return False
        opcode = data[0] & 0x0F
        return opcode == 0x9  # ping


# ==================== 观众连接管理 ====================
class ViewerConnection:
    """单个观众连接"""

    def __init__(self, client_socket: socket.socket, addr):
        self.socket = client_socket
        self.addr = addr
        self.connected_at = time.time()
        self.last_pong = time.time()

    def send(self, message: dict) -> bool:
        """
        发送消息（自动 JSON 序列化 + WebSocket 帧编码）。

        :param message: 消息字典
        :return: 是否成功
        """
        try:
            payload = json.dumps(message, ensure_ascii=False)
            frame = WebSocketFrame.encode(payload)
            self.socket.sendall(frame)
            return True
        except Exception as e:
            logging.debug(f"发送给 {self.addr} 失败：{e}")
            return False

    def close(self):
        """关闭连接"""
        try:
            self.socket.close()
        except Exception:
            pass


# ==================== 同步服务器 ====================
class SyncServer:
    """
    远程同步服务器。

    用法：
      server = SyncServer(http_port=8765, ws_port=8766)
      server.start()
      server.set_slides_html(slides_html)  # 供观众端拉取
      server.broadcast_slide(3, 10)
      server.broadcast_laser(0.5, 0.5, visible=True)
      server.stop()

    线程安全：
      所有 broadcast_* 方法内部加锁，可从任意线程调用。
    """

    def __init__(
        self,
        http_port: int = 8765,
        ws_port: int = 8766,
        allow_lan: bool = False,
        html_template_path: Optional[str] = None,
        host: Optional[str] = None,
    ):
        """
        :param allow_lan: 是否允许局域网观众连接（优化规划 §1.4）。
            默认 False，只监听 127.0.0.1。原实现固定绑定 0.0.0.0 且没有任何
            鉴权，同一局域网内任何人都能静默读取全部幻灯片内容；结合无
            Origin 校验的 WebSocket，演示者本机浏览器中的任意网页也能连上
            广播通道。
        :param host: 显式覆盖监听地址（仅测试用，正常路径请用 allow_lan）。
        """
        self.http_port = http_port
        self.ws_port = ws_port
        self.allow_lan = bool(allow_lan)
        self.host = host or ("0.0.0.0" if self.allow_lan else "127.0.0.1")
        self.html_template_path = html_template_path
        # 一次性访问令牌：HTTP 接口与 WebSocket 握手都要求携带，
        # 只出现在服务端生成并展示给演示者的观众 URL 里。
        self.token = secrets.token_urlsafe(16)
        # 手机遥控回调：收到 {"type":"control","action":...} 时由桌面处理
        self.on_control = None

        # 观众连接列表
        self._viewers: List[ViewerConnection] = []
        self._viewers_lock = threading.Lock()

        # 服务器线程
        self._http_server: Optional[HTTPServer] = None
        self._http_thread: Optional[threading.Thread] = None
        self._ws_server: Optional[socket.socket] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._running = False

        # 演示状态（用于新连接加入时同步）
        self._current_state: Dict[str, Any] = {
            "type": "slide_change",
            "index": 0,
            "total": 0,
        }

        # 幻灯片内容（供 HTTP 服务器读取，任务 4.3 增量）
        self._slides_html: List[str] = []

    # ==================== 启动 / 停止 ====================
    def start(self) -> bool:
        """
        启动服务器。

        :return: 是否成功
        """
        if self._running:
            return True

        try:
            # 1. 启动 HTTP 服务器（提供观众页面）
            self._start_http_server()

            # 2. 启动 WebSocket 服务器（广播通道）
            self._start_ws_server()

            self._running = True
            logging.info(
                f"同步服务器已启动："
                f"HTTP :{self.http_port} / WS :{self.ws_port}"
            )
            return True

        except Exception as e:
            logging.error(f"同步服务器启动失败：{e}")
            self.stop()
            return False

    def stop(self):
        """停止服务器"""
        self._running = False

        # 关闭所有观众连接
        with self._viewers_lock:
            for v in self._viewers:
                v.close()
            self._viewers.clear()

        # 关闭 WebSocket 服务器
        if self._ws_server is not None:
            try:
                self._ws_server.close()
            except Exception:
                pass
            self._ws_server = None

        # 关闭 HTTP 服务器
        if self._http_server is not None:
            try:
                self._http_server.shutdown()
                self._http_server.server_close()
            except Exception:
                pass
            self._http_server = None

        logging.info("同步服务器已停止")

    # ==================== HTTP 服务器 ====================
    def _start_http_server(self):
        """启动 HTTP 服务器（提供观众页面 + 幻灯片内容 API）"""
        template_path = self.html_template_path
        server_self = self

        class ViewerHandler(SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                # 静默日志
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

            def _authorized(self):
                return secrets.compare_digest(
                    self._client_token(), server_self.token
                )

            def _deny(self, code, message):
                body = message.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def do_HEAD(self):
                # 继承的 do_HEAD 会绕过令牌校验，显式拒绝
                self._deny(403, "不支持 HEAD 请求")

            def do_GET(self):
                if not self._authorized():
                    self._deny(
                        403,
                        "缺少或无效的访问令牌。请使用演示端给出的完整地址"
                        "（含 ?t=...）访问。",
                    )
                    return

                path_only = urlparse(self.path).path
                if path_only in ("/", "/sync", "/index.html"):
                    self._serve_viewer_page(template_path)
                elif path_only == "/api/info":
                    self._serve_info()
                elif path_only.startswith("/api/slide/"):
                    # 任务 4.3 增量：幻灯片内容 API
                    self._serve_slide_content()
                else:
                    self.send_error(404)

            def _serve_viewer_page(self, template_path):
                """提供观众页面"""
                try:
                    if template_path and \
                            __import__("os").path.exists(template_path):
                        with open(template_path, "r", encoding="utf-8") as f:
                            html = f.read()
                    else:
                        # 使用内置模板
                        from beeoffice.plugins.beeshow_sync_viewer \
                            import get_viewer_html
                        html = get_viewer_html(
                            server_self.ws_port,
                            server_self.token,
                        )

                    self.send_response(200)
                    self.send_header(
                        "Content-Type", "text/html; charset=utf-8"
                    )
                    # 优化规划 §1.4：不再发送通配 CORS 头——它会让同机浏览器
                    # 中的任意网页跨域读取 /api/info 与 /api/slide/*。
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                except Exception as e:
                    logging.error(f"提供观众页面失败：{e}")
                    self.send_error(500)

            def _serve_info(self):
                """返回服务器信息 JSON"""
                info = {
                    "http_port": server_self.http_port,
                    "ws_port": server_self.ws_port,
                    "viewer_count": len(server_self._viewers),
                    "state": server_self._current_state,
                }
                body = json.dumps(
                    info, ensure_ascii=False
                ).encode("utf-8")
                self.send_response(200)
                self.send_header(
                    "Content-Type", "application/json; charset=utf-8"
                )
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def _serve_slide_content(self):
                """
                提供指定页的 HTML 片段（任务 4.3 增量）。

                URL 形如：/api/slide/3
                返回：第 3 页的 HTML 片段（纯 HTML，非 JSON）
                """
                try:
                    # 注意用 urlparse 去掉查询串（令牌就在查询串里），
                    # 否则 int() 会直接失败
                    raw_idx = urlparse(self.path).path.rsplit("/", 1)[-1]
                    idx = int(raw_idx)
                    slides = server_self.get_slides_html()
                    if 0 <= idx < len(slides):
                        html = slides[idx]
                    else:
                        html = "<p>（无此页）</p>"
                    self.send_response(200)
                    self.send_header(
                        "Content-Type", "text/html; charset=utf-8"
                    )
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    self.wfile.write(html.encode("utf-8"))
                except Exception as e:
                    logging.error(f"提供幻灯片内容失败：{e}")
                    self.send_error(500)

        class ThreadingHTTPServer(
            ThreadingMixIn, HTTPServer
        ):
            daemon_threads = True
            allow_reuse_address = True

        self._http_server = ThreadingHTTPServer(
            (self.host, self.http_port), ViewerHandler
        )
        self._http_thread = threading.Thread(
            target=self._http_server.serve_forever,
            daemon=True,
            name="SyncHTTP",
        )
        self._http_thread.start()

    # ==================== WebSocket 服务器 ====================
    def _start_ws_server(self):
        """启动 WebSocket 服务器（广播通道）"""
        server_sock = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM
        )
        server_sock.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
        )
        server_sock.bind((self.host, self.ws_port))
        server_sock.listen(50)
        server_sock.settimeout(1.0)

        self._ws_server = server_sock
        self._ws_thread = threading.Thread(
            target=self._ws_accept_loop,
            daemon=True,
            name="SyncWS",
        )
        self._ws_thread.start()

    def _ws_accept_loop(self):
        """接受新的 WebSocket 连接"""
        while self._running:
            try:
                client, addr = self._ws_server.accept()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logging.debug(f"accept 失败：{e}")
                break

            # 每个连接一个线程
            t = threading.Thread(
                target=self._handle_viewer,
                args=(client, addr),
                daemon=True,
                name=f"SyncViewer-{addr[0]}",
            )
            t.start()

    @staticmethod
    def decode_text_frame(data: bytes):
        """解码客户端文本帧（browser→server 一定带 mask）。"""
        if len(data) < 2 or (data[0] & 0x0F) != 0x1:
            return None
        length = data[1] & 0x7F
        offset = 2
        if length == 126:
            if len(data) < 4:
                return None
            length = int.from_bytes(data[2:4], "big")
            offset = 4
        elif length == 127:
            if len(data) < 10:
                return None
            length = int.from_bytes(data[2:10], "big")
            offset = 10
        if len(data) < offset + 4 + length:
            return None
        mask = data[offset:offset + 4]
        payload = bytes(
            b ^ mask[i % 4] for i, b in enumerate(
                data[offset + 4:offset + 4 + length]
            )
        )
        try:
            return json.loads(payload.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def _handle_viewer(self, client: socket.socket, addr):
        """处理单个观众连接"""
        try:
            # 1. WebSocket 握手
            if not self._do_handshake(client):
                client.close()
                return

            # 2. 创建连接对象
            viewer = ViewerConnection(client, addr)
            with self._viewers_lock:
                self._viewers.append(viewer)

            logging.info(
                f"观众已连接：{addr}（共 "
                f"{len(self._viewers)} 人）"
            )

            # 3. 发送当前状态
            viewer.send(self._current_state)

            # 4. 读取循环（只处理关闭帧）
            client.settimeout(5.0)
            while self._running:
                try:
                    data = client.recv(1024)
                    if not data:
                        break
                    if WebSocketFrame.decode_close_frame(data):
                        break
                    message = self.decode_text_frame(data)
                    if (message and message.get("type") == "control"
                            and self.on_control is not None):
                        try:
                            self.on_control(str(message.get("action", "")))
                        except Exception as e:  # noqa: BLE001
                            logging.debug(f"遥控回调失败：{e}")
                except socket.timeout:
                    continue
                except Exception:
                    break

        except Exception as e:
            logging.debug(f"处理观众 {addr} 失败：{e}")
        finally:
            # 清理
            with self._viewers_lock:
                self._viewers = [
                    v for v in self._viewers
                    if v.addr != addr
                ]
            try:
                client.close()
            except Exception:
                pass
            logging.info(f"观众已断开：{addr}")

    # ==================== 握手鉴权（优化规划 §1.4） ====================
    def _handshake_allowed(
        self, request_path: str, header_lines: List[str]
    ) -> bool:
        """校验 WebSocket 握手携带的令牌与 Origin。"""
        token = ""
        qs = parse_qs(urlparse(request_path or "").query)
        if qs.get("t"):
            token = qs["t"][0]
        for line in header_lines:
            if line.lower().startswith("authorization:"):
                value = line.split(":", 1)[1].strip()
                if value.lower().startswith("bearer "):
                    token = value[7:].strip()
                break

        if not token or not secrets.compare_digest(token, self.token):
            return False

        for line in header_lines:
            if line.lower().startswith("origin:"):
                origin = line.split(":", 1)[1].strip().lower()
                return self._origin_allowed(origin)
        # 无 Origin 头（非浏览器客户端）在令牌正确时放行
        return True

    def _origin_allowed(self, origin: str) -> bool:
        """只接受来自本服务自身页面的 Origin。"""
        hosts = {"127.0.0.1", "localhost", "[::1]"}
        if self.allow_lan:
            hosts.add(self.get_local_ip().lower())
            hosts.add(self.host.lower())
        return origin in {
            f"http://{h}:{self.http_port}" for h in hosts
        }

    def _do_handshake(self, client: socket.socket) -> bool:
        """
        执行 WebSocket 握手。

        :param client: 客户端 socket
        :return: 是否成功
        """
        try:
            # 读取 HTTP 请求头
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = client.recv(4096)
                if not chunk:
                    return False
                data += chunk
                if len(data) > 8192:
                    return False

            headers = data.decode("utf-8", errors="ignore")
            header_lines = headers.split("\r\n")

            # 优化规划 §1.4：握手必须携带令牌，且 Origin 必须来自本服务页面。
            # 原实现只做 RFC6455 的 Key→Accept 计算，既不校验身份也不校验
            # Origin，因此演示者本机浏览器中的任意网页都能连上广播通道
            # （跨站 WebSocket 劫持），LAN 上任何人也能直接读演示状态。
            request_path = ""
            request_parts = header_lines[0].split(" ") if header_lines else []
            if len(request_parts) >= 2:
                request_path = request_parts[1]
            if not self._handshake_allowed(request_path, header_lines):
                try:
                    client.sendall(
                        b"HTTP/1.1 403 Forbidden\r\n"
                        b"Content-Length: 0\r\n"
                        b"Connection: close\r\n\r\n"
                    )
                except Exception:
                    pass
                return False

            # 提取 Sec-WebSocket-Key
            key = None
            for line in header_lines:
                if line.lower().startswith(
                    "sec-websocket-key:"
                ):
                    key = line.split(":", 1)[1].strip()
                    break

            if not key:
                return False

            # 计算 Sec-WebSocket-Accept
            accept = base64.b64encode(
                hashlib.sha1(
                    (key + WS_MAGIC).encode("utf-8")
                ).digest()
            ).decode("utf-8")

            # 发送握手响应
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                "\r\n"
            )
            client.sendall(response.encode("utf-8"))
            return True

        except Exception as e:
            logging.error(f"WebSocket 握手失败：{e}")
            return False

    # ==================== 广播接口 ====================
    def broadcast(self, message: dict):
        """
        广播消息给所有观众。

        :param message: 消息字典（会自动 JSON 序列化）
        """
        if not self._running:
            return

        # 更新状态（用于新连接加入时同步）
        msg_type = message.get("type", "")
        if msg_type in ("slide_change", "theme_change",
                         "black_screen"):
            self._current_state = message

        # 发送给所有观众
        with self._viewers_lock:
            viewers_copy = list(self._viewers)

        dead_viewers = []
        for viewer in viewers_copy:
            if not viewer.send(message):
                dead_viewers.append(viewer)

        # 清理断开的连接
        if dead_viewers:
            with self._viewers_lock:
                self._viewers = [
                    v for v in self._viewers
                    if v not in dead_viewers
                ]

    def broadcast_slide(self, index: int, total: int):
        """广播翻页"""
        self.broadcast({
            "type": "slide_change",
            "index": index,
            "total": total,
        })

    def broadcast_laser(
        self, x: float, y: float, visible: bool = True
    ):
        """
        广播激光笔位置。

        :param x, y: 归一化坐标（0.0 ~ 1.0）
        :param visible: 是否可见
        """
        self.broadcast({
            "type": "laser",
            "x": round(x, 4),
            "y": round(y, 4),
            "visible": visible,
        })

    def broadcast_draw(
        self, action: str, x: float = 0.0, y: float = 0.0
    ):
        """
        广播画笔事件。

        :param action: "start" / "move" / "end"
        :param x, y: 归一化坐标
        """
        self.broadcast({
            "type": "draw",
            "action": action,
            "x": round(x, 4),
            "y": round(y, 4),
        })

    def broadcast_black_screen(self, visible: bool):
        """广播黑屏"""
        self.broadcast({
            "type": "black_screen",
            "visible": visible,
        })

    def broadcast_theme(self, theme: str):
        """广播主题切换"""
        self.broadcast({
            "type": "theme_change",
            "theme": theme,
        })

    # ==================== 幻灯片内容（任务 4.3 增量） ====================
    def set_slides_html(self, slides_html: list):
        """
        设置幻灯片内容（供 HTTP 服务器读取）。

        :param slides_html: 每页 HTML 片段列表

        用途：
          观众端 JS 通过 `fetch('/api/slide/<idx>')` 获取指定页内容。
          演示者每次进入同步模式时调用本方法设置。
        """
        self._slides_html = list(slides_html)

    def get_slides_html(self) -> list:
        """获取幻灯片内容（供 HTTP Handler 调用）"""
        return list(getattr(self, "_slides_html", []))

    # ==================== 状态查询 ====================
    @property
    def viewer_count(self) -> int:
        """当前观众数"""
        with self._viewers_lock:
            return len(self._viewers)

    @property
    def is_running(self) -> bool:
        return self._running

    def get_local_ip(self) -> str:
        """
        获取本机局域网 IP（供观众访问）。

        通过连接外部地址来探测本机出口 IP。
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def get_viewer_url(self) -> str:
        """
        返回观众访问 URL（含一次性令牌）。

        未开启局域网访问时用回环地址展示——此时只有本机浏览器能打开。
        """
        host = self.get_local_ip() if self.allow_lan else "127.0.0.1"
        return f"http://{host}:{self.http_port}/sync?t={self.token}"