# tests/test_export_pdf.py
"""
PDF 导出测试

覆盖：
  - 页面设置注入 HTML
  - 水印注入
  - 页码注入
"""
import pytest


class TestPageSettingsInjection:
    """页面设置注入 HTML"""

    def test_page_size_injected(self, beewrite_editor):
        """A4 尺寸应注入到 CSS"""
        content = "<html><head></head><body>test</body></html>"
        settings = {
            "paper": "A4",
            "orientation": "portrait",
            "margin_top": 25.4,
            "margin_bottom": 25.4,
            "margin_left": 31.7,
            "margin_right": 31.7,
        }
        result = beewrite_editor._apply_page_settings_to_content(
            content, settings
        )
        assert "210mm" in result, "A4 宽度未注入"
        assert "297mm" in result, "A4 高度未注入"

    def test_landscape_injected(self, beewrite_editor):
        """横向时宽高应互换"""
        content = "<html><head></head><body>test</body></html>"
        settings = {
            "paper": "A4",
            "orientation": "landscape",
            "margin_top": 25.4,
            "margin_bottom": 25.4,
            "margin_left": 31.7,
            "margin_right": 31.7,
        }
        result = beewrite_editor._apply_page_settings_to_content(
            content, settings
        )
        assert "297mm" in result
        assert "210mm" in result


class TestWatermarkInjection:
    """水印注入"""

    def test_watermark_enabled(self, beewrite_editor):
        """开启水印后应注入水印 HTML"""
        beewrite_editor._watermark_config = {
            "text": "内部资料",
            "fontsize": 80,
            "color": "#CCCCCC",
            "opacity": 0.15,
            "angle": -45,
            "tile": False,
        }
        extras = beewrite_editor._build_export_extras()
        assert "内部资料" in extras


class TestPageNumberInjection:
    """页码注入"""

    def test_page_number_enabled(self, beewrite_editor):
        """开启页码后应注入页码 CSS"""
        beewrite_editor._page_number_config = {
            "enabled": True,
            "position": "底部居中",
            "format": "第 1 页 / 共 N 页",
            "start": 1,
            "fontsize": 10,
        }
        extras = beewrite_editor._build_export_extras()
        assert "counter(page)" in extras