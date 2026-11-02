"""数据工具箱增强：图表推荐 + 一键清洗。"""
import pandas as pd

from beeoffice.plugins.data_insights import clean_table, recommend_charts


def test_recommend_line_for_datetime_and_numeric():
    df = pd.DataFrame({
        "日期": pd.date_range("2026-01-01", periods=5),
        "金额": [1, 2, 3, 4, 5],
    })
    recs = recommend_charts(df)
    assert recs and recs[0]["type"] == "line"


def test_recommend_bar_for_category():
    df = pd.DataFrame({"部门": ["A", "B", "A"], "金额": [1, 2, 3]})
    assert recommend_charts(df)[0]["type"] == "bar"


def test_clean_table_removes_empty_and_dupes():
    df = pd.DataFrame({
        "名称": [" 甲 ", "乙", "乙", "", None],
        "金额": ["1", "2", "2", "", None],
        "空列": [None, None, None, None, None],
    })
    out, report = clean_table(df)
    assert len(out) == 2
    assert "空列" not in out.columns
    assert out["名称"].tolist() == ["甲", "乙"]
    assert report["dropped_duplicates"] >= 1
    assert report["trimmed_cells"] >= 1
    assert "金额" in report["numeric_cols"]
