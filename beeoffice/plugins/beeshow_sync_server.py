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
import socket
import struct
import threading
import time
import uuid
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import List, Optional, Dict, Any


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
        host: str = "0.0.0.0",
        html_template_path: Optional[str] = None,
        token: str = "",
    ):
        self.http_port = http_port
        self.ws_port = ws_port
        self.host = host
        self.html_template_path = html_template_path
        # 安全（P0）：一次性访问令牌。
        # 服务绑定 0.0.0.0 是同步演示的功能需要（观众手机要能连），
        # 但原实现无任何鉴权，同一网段任何人都能拉走整份讲稿。
        # 现在所有 HTTP 端点与 WebSocket 握手都必须携带 ?t=<token>。
        self.token = token or uuid.uuid4().hex[:12]

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

        # 竞态修复（P0）：_running 必须在启动任何线程之前置位。
        # 原实现先 _start_ws_server()（内部立刻起 accept 线程），
        # 之后才 self._running = True；accept 循环 while self._running
        # 很可能在置位前就判断为 False 并退出，表现为"启动成功但 WS 从不监听"。
        self._running = True

        try:
            # 1. 启动 HTTP 服务器（提供观众页面）
            self._start_http_server()

            # 2. 启动 WebSocket 服务器（广播通道）
            self._start_ws_server()

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

            def _path_only(self):
                """去掉查询串后的路径（?t=... 不能影响路由匹配）。"""
                from urllib.parse import urlparse
                return urlparse(self.path).path

            def _token_ok(self):
                """校验一次性访问令牌（?t=xxx）。"""
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                return qs.get("t", [""])[0] == server_self.token

            def _forbidden(self):
                body = b"403 Forbidden: invalid or missing token"
                self.send_response(403)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                # 安全（P0）：所有端点都必须带令牌。
                # 原实现默认绑定 0.0.0.0、无鉴权、且返回 CORS 通配头，
                # 同一网段或任意网页都能读取整份演示文稿。
                if not self._token_ok():
                    self._forbidden()
                    return
                path = self._path_only()
                if path in ("/", "/sync", "/index.html"):
                    self._serve_viewer_page(template_path)
                elif path == "/api/info":
                    self._serve_info()
                elif path.startswith("/api/slide/"):
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
                            token=server_self.token,
                        )

                    self.send_response(200)
                    self.send_header(
                        "Content-Type", "text/html; charset=utf-8"
                    )
                    # 安全：不再返回 Access-Control-Allow-Origin: *
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
                self.end_headers()
                self.wfile.write(body)

            def _serve_slide_content(self):
                """
                提供指定页的 HTML 片段（任务 4.3 增量）。

                URL 形如：/api/slide/3
                返回：第 3 页的 HTML 片段（纯 HTML，非 JSON）
                """
                try:
                    idx = int(self._path_only().rsplit("/", 1)[-1])
                    slides = server_self.get_slides_html()
                    if 0 <= idx < len(slides):
                        html = slides[idx]
                    else:
                        html = "<p>（无此页）</p>"
                    self.send_response(200)
                    self.send_header(
                        "Content-Type", "text/html; charset=utf-8"
                    )
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

    def _ws_token_ok(self, headers_text: str) -> bool:
        """从 WebSocket 握手请求行里取出 ?t= 并校验。"""
        from urllib.parse import urlparse, parse_qs
        try:
            request_line = headers_text.split("\r\n", 1)[0]
            parts = request_line.split(" ")
            if len(parts) < 2:
                return False
            qs = parse_qs(urlparse(parts[1]).query)
            return qs.get("t", [""])[0] == self.token
        except Exception:
            return False

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

            # 安全（P0）：WebSocket 也必须校验令牌，
            # 否则观众端能连上广播通道收走所有翻页与讲稿内容。
            if not self._ws_token_ok(headers):
                try:
                    client.sendall(
                        b"HTTP/1.1 403 Forbidden\r\n"
                        b"Content-Length: 0\r\nConnection: close\r\n\r\n"
                    )
                except Exception:
                    pass
                return False

            # 提取 Sec-WebSocket-Key
            key = None
            for line in headers.split("\r\n"):
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
        """返回观众访问 URL（含一次性令牌，请勿外传）"""
        return (
            f"http://{self.get_local_ip()}:{self.http_port}/sync"
            f"?t={self.token}"
        )