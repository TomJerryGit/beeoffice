# beeoffice/plugins/beeshow_html.py
"""
蜜演幻灯片 HTML 骨架的统一拼装（优化规划 §3.3 消重）

背景
----
"幻灯片 HTML 骨架"原先在 **6 处**各写了一遍，每处都在重复同一套
`<!DOCTYPE html><html><head><meta charset>…<style>{主题}{版式}body{背景}</style>
</head><body><div class="slide">…</div>…</body></html>`，只有额外内容不同：

  | 调用点 | 用途 | 额外内容 |
  |---|---|---|
  | `beeshow_export_mixin._export_pdf`    | PDF  | `@page{size:A4 landscape;margin:0}` + 每页 page-break |
  | `beeshow_export_mixin._export_html`   | HTML | `body{margin:0}` + 动态数字 JS |
  | `beeshow_export_mixin._export_images` | PNG  | 无 |
  | `beeshow_play_mixin._show_play_slide` | 播放 | 动画 CSS + 控制条 + 形变 JS |
  | `beeshow_slide_mixin._show_slide`     | 预览 | 页码 + 各类编辑 JS |
  | `beeshow_pptx_engine._wrap_html`      | PPTX | `<base href>` + 固定 1280×960 画布 |

任何骨架级调整（charset、`.slide` 容器、CSS 顺序）原先都要改 6 遍，极易漂移。

本模块**不依赖 Qt**，因此可以直接用纯字符串断言测试；
各处调用点的产物级行为则由
`tests/regression/v5/test_v505_slide_html_scaffold.py` 覆盖。
"""


def render_slide_html(
    inner_html: str,
    *,
    theme_css: str = "",
    layout_css: str = "",
    bg: str = "",
    extra_css: str = "",
    head_extra: str = "",
    body_extra: str = "",
    wrap_slide: bool = True,
    slide_style: str = "",
) -> str:
    """
    拼装一份完整的幻灯片 HTML。

    :param inner_html: 幻灯片内容（或**已包好 `.slide`** 的多页内容，
        此时传 `wrap_slide=False`）
    :param theme_css: 主题 CSS
    :param layout_css: 版式 CSS（PPTX 引擎不用）
    :param bg: 背景色；为空则不加 `body{background:...}` 规则
    :param extra_css: 追加到 `<style>` 末尾的额外 CSS
    :param head_extra: 插在 `<head>` 里、`<style>` **之前**的内容
        （例如 PPTX 需要的 `<base href>`）
    :param body_extra: 插在 `.slide` 容器**之后**、`</body>` 之前的内容
        （页码、控制条、各类 JS）
    :param wrap_slide: 是否用 `<div class="slide">…</div>` 包住 `inner_html`
    :param slide_style: 给 `.slide` 容器追加的 `style="..."`（含引号）
    :return: 完整 HTML 字符串

    取舍说明：
      - `theme_css` 与 `layout_css` 之间**不加分隔符**，保持与改动前一致的拼接；
        其余片段（`body{...}`、`extra_css`）前面加一个空格。CSS 对空白不敏感，
        但这样可确保 `…}{…}` 不会因为缺少分隔而被误解析成同一个选择器。
      - 不在这里注入任何"默认样式"：各处原有的差异（`@page`、`body{margin:0}`、
        固定画布尺寸）继续由调用方显式传入，避免"统一"顺手改掉某一条路径的版式。
    """
    style_parts = [theme_css, layout_css]
    if bg:
        style_parts.append(f" body{{background:{bg};}}")
    if extra_css:
        style_parts.append(f" {extra_css}")
    style = "".join(style_parts)

    if wrap_slide:
        open_slide = f'<div class="slide"{slide_style}>'
        close_slide = "</div>"
    else:
        open_slide = close_slide = ""

    return (
        f'<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'{head_extra}'
        f'<style>{style}</style></head>'
        f'<body>{open_slide}{inner_html}{close_slide}{body_extra}</body></html>'
    )
