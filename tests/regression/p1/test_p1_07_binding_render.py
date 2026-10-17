# tests/test_p2_regression/test_p1_07_binding_render.py
"""P1-7 回归：render 第二个返回值有意义"""
import pandas as pd
from beeoffice.plugins.data_binding import (
    DataSourceManager, BindingEngine,
)


def test_render_returns_unresolved():
    mgr = DataSourceManager()
    mgr.register_dataframe("数据", pd.DataFrame({"销售额": [100, 200]}))
    engine = BindingEngine(mgr)
    template = (
        "已绑定：{{ 数据.销售额.-1 }}\n"
        "未绑定：{{ 不存在.字段 }}"
    )
    rendered, unresolved = engine.render(template)
    assert "200" in rendered
    assert len(unresolved) == 1


def test_render_all_resolved():
    mgr = DataSourceManager()
    mgr.register_dataframe("源", pd.DataFrame({"值": [42]}))
    engine = BindingEngine(mgr)
    rendered, unresolved = engine.render("{{ 源.值.-1 }}")
    assert "42" in rendered
    assert unresolved == []
