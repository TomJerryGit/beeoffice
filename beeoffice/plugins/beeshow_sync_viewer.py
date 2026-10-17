# beeoffice/plugins/beeshow_sync_viewer.py
"""
蜜演观众端 HTML 模板（任务 4.3）

职责：
  - 提供观众端 HTML 页面
  - 通过 WebSocket 连接服务器接收广播
  - 实时渲染幻灯片（图片/文字）
  - 显示激光笔位置
  - 支持全屏 / 触屏翻页

设计：
  - 单文件 HTML（内联 CSS + JS）
  - 移动端优先（viewport / 触摸事件）
  - 观众只接收，不发送（除握手）
  - 断线自动重连（指数退避）

依赖：
  - 无（浏览器内置 WebSocket）

用法：
  from beeoffice.plugins.beeshow_sync_viewer import get_viewer_html
  html = get_viewer_html(ws_port=8766)
"""


def get_viewer_html(ws_port: int = 8766, token: str = "") -> str:
    """
    生成观众端 HTML。

    :param ws_port: WebSocket 端口
    :param token: 一次性访问令牌；非空时页面的 WS 连接与 API 请求都会带 ?t=
    :return: HTML 字符串
    """
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1.0,
               maximum-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<title>🐝 蜜蜂办公 · 演示同步</title>
<style>
* {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
html, body {{
    margin: 0; padding: 0;
    width: 100%; height: 100%;
    overflow: hidden;
    background: #1a1a1a;
    color: #fff;
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei",
                 sans-serif;
    user-select: none;
}}

/* 顶部状态栏 */
#status-bar {{
    position: fixed; top: 0; left: 0; right: 0;
    height: 32px;
    background: rgba(0, 0, 0, 0.7);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 12px;
    font-size: 13px;
    z-index: 1000;
    backdrop-filter: blur(8px);
}}

#conn-status {{
    display: flex; align-items: center; gap: 6px;
}}
#conn-dot {{
    width: 8px; height: 8px; border-radius: 50%;
    background: #f44336;
    transition: background 0.3s;
}}
#conn-dot.connected {{ background: #4CAF50; box-shadow: 0 0 8px #4CAF50; }}
#conn-dot.connecting {{ background: #FFC107; }}

#page-info {{ font-variant-numeric: tabular-nums; }}

/* 幻灯片容器 */
#slide-container {{
    position: absolute; top: 32px; left: 0; right: 0; bottom: 0;
    display: flex; align-items: center; justify-content: center;
    overflow: hidden;
    background: #fff;
    transition: background 0.3s;
}}

#slide-content {{
    width: 100%; height: 100%;
    padding: 24px;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
}}

/* 幻灯片内的 HTML 样式（与主题保持一致） */
#slide-content h1 {{ font-size: 2em; color: #FF8F00; margin: 0.3em 0; }}
#slide-content h2 {{ font-size: 1.6em; margin: 0.4em 0; }}
#slide-content h3 {{ font-size: 1.3em; margin: 0.4em 0; }}
#slide-content p, #slide-content li {{ font-size: 1.1em; line-height: 1.7; }}
#slide-content ul, #slide-content ol {{ padding-left: 1.5em; width: 100%; }}
#slide-content img, #slide-content video {{
    max-width: 100%; border-radius: 8px;
}}
#slide-content pre {{
    background: #f5f5f5; padding: 12px; border-radius: 6px;
    overflow-x: auto; width: 100%; font-size: 0.9em;
}}
#slide-content code {{
    background: #f5f5f5; padding: 2px 6px; border-radius: 3px;
}}
#slide-content table {{
    border-collapse: collapse; width: 100%; margin: 12px 0;
}}
#slide-content th, #slide-content td {{
    border: 1px solid #ddd; padding: 8px;
}}

/* 等待界面 */
#waiting {{
    position: absolute; top: 32px; left: 0; right: 0; bottom: 0;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    background: #1a1a1a;
    color: #fff;
    text-align: center;
    padding: 24px;
    z-index: 500;
}}
#waiting h1 {{ font-size: 3em; margin: 0.2em; }}
#waiting p {{ color: #999; line-height: 1.8; }}

/* 激光笔 */
#laser {{
    position: fixed;
    width: 28px; height: 28px;
    border-radius: 50%;
    background: radial-gradient(circle,
        rgba(255, 0, 0, 1) 0%,
        rgba(255, 0, 0, 0.6) 40%,
        rgba(255, 0, 0, 0) 70%);
    pointer-events: none;
    z-index: 900;
    transform: translate(-50%, -50%);
    display: none;
    filter: drop-shadow(0 0 8px rgba(255, 0, 0, 0.9));
    transition: opacity 0.15s;
}}

/* 画布（画笔） */
#drawing-canvas {{
    position: fixed; top: 32px; left: 0;
    width: 100%; height: calc(100% - 32px);
    pointer-events: none;
    z-index: 800;
    display: none;
}}

/* 黑屏 */
#black-screen {{
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: #000;
    z-index: 950;
    display: none;
}}

/* 底部提示 */
#hint {{
    position: fixed; bottom: 8px; left: 0; right: 0;
    text-align: center;
    color: rgba(255, 255, 255, 0.4);
    font-size: 11px;
    pointer-events: none;
    z-index: 1000;
}}
</style>
</head>
<body>

<!-- 状态栏 -->
<div id="status-bar">
    <div id="conn-status">
        <div id="conn-dot"></div>
        <span id="conn-text">连接中...</span>
    </div>
    <div id="page-info">- / -</div>
</div>

<!-- 等待界面 -->
<div id="waiting">
    <h1>🐝</h1>
    <p>等待演示开始...</p>
    <p style="font-size: 12px; color: #666; margin-top: 20px;">
        请让演示者开启「📱 同步演示」
    </p>
</div>

<!-- 幻灯片容器 -->
<div id="slide-container">
    <div id="slide-content"></div>
</div>

<!-- 激光笔 -->
<div id="laser"></div>

<!-- 画布 -->
<canvas id="drawing-canvas"></canvas>

<!-- 黑屏 -->
<div id="black-screen"></div>

<!-- 底部提示 -->
<div id="hint">双指缩放 · 双击全屏</div>

<script>
(function() {{
    'use strict';

    // ==================== 配置 ====================
    const WS_PORT = {ws_port};
    // 安全：一次性访问令牌，由服务端注入；WS 与 API 请求都要带上
    const TOKEN = "{token}";
    const RECONNECT_BASE = 1000;   // 重连基础间隔（毫秒）
    const RECONNECT_MAX = 30000;   // 最大重连间隔

    // ==================== 状态 ====================
    let ws = null;
    let reconnectDelay = RECONNECT_BASE;
    let currentSlide = 0;
    let totalSlides = 0;
    let isConnected = false;
    let drawingActive = false;

    // ==================== DOM 引用 ====================
    const connDot = document.getElementById('conn-dot');
    const connText = document.getElementById('conn-text');
    const pageInfo = document.getElementById('page-info');
    const waiting = document.getElementById('waiting');
    const slideContent = document.getElementById('slide-content');
    const laser = document.getElementById('laser');
    const blackScreen = document.getElementById('black-screen');
    const canvas = document.getElementById('drawing-canvas');
    const ctx = canvas.getContext('2d');

    // ==================== WebSocket 连接 ====================
    function connect() {{
        const url = `ws://${{location.hostname}}:${{WS_PORT}}/?t=${{encodeURIComponent(TOKEN)}}`;
        connDot.className = 'connecting';
        connText.textContent = '连接中...';

        try {{
            ws = new WebSocket(url);
        }} catch (e) {{
            console.error('WebSocket 创建失败：', e);
            scheduleReconnect();
            return;
        }}

        ws.onopen = function() {{
            console.log('已连接');
            isConnected = true;
            connDot.className = 'connected';
            connText.textContent = '已连接';
            reconnectDelay = RECONNECT_BASE;
        }};

        ws.onmessage = function(event) {{
            try {{
                const msg = JSON.parse(event.data);
                handleMessage(msg);
            }} catch (e) {{
                console.error('解析消息失败：', e);
            }}
        }};

        ws.onclose = function() {{
            console.log('连接已断开');
            isConnected = false;
            connDot.className = '';
            connText.textContent = '重连中...';
            scheduleReconnect();
        }};

        ws.onerror = function(e) {{
            console.error('WebSocket 错误：', e);
        }};
    }}

    function scheduleReconnect() {{
        setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(
            reconnectDelay * 1.5, RECONNECT_MAX
        );
    }}

    // ==================== 消息处理 ====================
    function handleMessage(msg) {{
        switch (msg.type) {{
            case 'slide_change':
                handleSlideChange(msg);
                break;
            case 'laser':
                handleLaser(msg);
                break;
            case 'draw':
                handleDraw(msg);
                break;
            case 'black_screen':
                handleBlackScreen(msg);
                break;
            case 'theme_change':
                handleThemeChange(msg);
                break;
            default:
                console.log('未知消息类型：', msg.type);
        }}
    }}

    function handleSlideChange(msg) {{
        currentSlide = msg.index || 0;
        totalSlides = msg.total || 0;
        pageInfo.textContent = `${{currentSlide + 1}} / ${{totalSlides}}`;

        // 隐藏等待界面
        waiting.style.display = 'none';

        // 请求幻灯片内容（通过 HTTP API）
        fetch(`/api/slide/${{currentSlide}}?t=${{encodeURIComponent(TOKEN)}}`)
            .then(r => r.text())
            .then(html => {{
                slideContent.innerHTML = html;
                // 应用动态数字动画
                if (window.replayDynamicNumbers) {{
                    window.replayDynamicNumbers();
                }}
            }})
            .catch(e => {{
                console.error('加载幻灯片失败：', e);
            }});
    }}

    function handleLaser(msg) {{
        if (!msg.visible) {{
            laser.style.display = 'none';
            return;
        }}
        const x = msg.x * window.innerWidth;
        const y = msg.y * (window.innerHeight - 32) + 32;
        laser.style.left = x + 'px';
        laser.style.top = y + 'px';
        laser.style.display = 'block';
    }}

    function handleDraw(msg) {{
        if (msg.action === 'start') {{
            canvas.style.display = 'block';
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight - 32;
            drawingActive = true;
            ctx.beginPath();
            ctx.moveTo(
                msg.x * window.innerWidth,
                msg.y * (window.innerHeight - 32)
            );
        }} else if (msg.action === 'move' && drawingActive) {{
            ctx.lineTo(
                msg.x * window.innerWidth,
                msg.y * (window.innerHeight - 32)
            );
            ctx.strokeStyle = '#FF0000';
            ctx.lineWidth = 3;
            ctx.lineCap = 'round';
            ctx.stroke();
        }} else if (msg.action === 'end') {{
            drawingActive = false;
        }}
    }}

    function handleBlackScreen(msg) {{
        blackScreen.style.display = msg.visible ? 'block' : 'none';
    }}

    function handleThemeChange(msg) {{
        console.log('主题切换：', msg.theme);
        // 可扩展：动态加载主题 CSS
    }}

    // ==================== 交互 ====================
    // 双击全屏
    document.addEventListener('dblclick', function() {{
        if (!document.fullscreenElement) {{
            document.documentElement.requestFullscreen?.();
        }} else {{
            document.exitFullscreen?.();
        }}
    }});

    // 窗口变化时重绘
    window.addEventListener('resize', function() {{
        if (canvas.style.display === 'block') {{
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight - 32;
        }}
    }});

    // ==================== 启动 ====================
    connect();

}})();
</script>
</body>
</html>"""