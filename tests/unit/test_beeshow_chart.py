"""P1：PPT 图表渲染/表格入口。"""
from beeoffice.plugins.beeshow_chart import parse_chart_data, render_chart_png


def test_parse_chart_data():
    labels, values = parse_chart_data("一月,10\n二月,20")
    assert labels == ["一月", "二月"]
    assert values == [10.0, 20.0]


def test_render_chart_png(tmp_path):
    out = render_chart_png("A,1\nB,2\nC,3", "bar", str(tmp_path / "chart.png"))
    assert (tmp_path / "chart.png").exists()
    assert out.endswith("chart.png")


def test_chart_and_table_support(qtbot):
    from beeoffice.plugins.beeshow import BeeShowView
    s = BeeShowView(); qtbot.addWidget(s); s.show()
    assert hasattr(s, "_show_chart_dialog")
    assert hasattr(s, "_show_table_editor")
