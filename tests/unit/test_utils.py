"""utils.py 纯函数补测。"""
import json
from pathlib import Path

import beeoffice.utils as u


def test_safe_filename():
    assert u.safe_filename("") == "untitled"
    assert u.safe_filename("a<b>c:d/e\\f|g?h*i") == "a_b_c_d_e_f_g_h_i"
    assert u.safe_filename("  name.  ") == "name"
    assert u.safe_filename("x" * 300) == "x" * 200


def test_human_readable_size():
    assert u.human_readable_size(-1) == "未知"
    assert u.human_readable_size(0) == "0.0 B"
    assert u.human_readable_size(1024) == "1.0 KB"
    assert u.human_readable_size(1024 * 1024) == "1.0 MB"


def test_normalize_path_and_ensure_dir(tmp_path):
    assert u.normalize_path("") == ""
    assert u.normalize_path("abc") == "abc"
    assert u.ensure_dir(tmp_path / "a" / "b") is True
    assert (tmp_path / "a" / "b").is_dir()


def test_atomic_write_text_and_json(tmp_path):
    p = tmp_path / "a.txt"
    assert u.atomic_write_text(p, "hello") is True
    assert p.read_text(encoding="utf-8") == "hello"
    j = tmp_path / "a.json"
    assert u.atomic_write_json(j, {"x": 1}) is True
    assert json.loads(j.read_text(encoding="utf-8")) == {"x": 1}
    # 不可序列化
    assert u.atomic_write_json(tmp_path / "bad.json", {1, 2}) is False


def test_resource_and_frozen():
    assert u.is_frozen() is False
    assert u.get_resource_path("a.txt")


def test_memory_usage():
    val = u.get_memory_usage()
    assert val == -1 or val > 0
    u.print_memory("test")
