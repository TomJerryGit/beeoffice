# tests/test_p2_regression/test_p1_17_mobile_temp.py
"""P1-17 回归：多 MobileServer 实例使用独立临时目录"""
from beeoffice.mobile import MobileServer


class _FakeParent:
    pass


def test_two_instances_different_temp_dirs(qapp):
    s1 = MobileServer(_FakeParent())
    s2 = MobileServer(_FakeParent())
    assert s1.temp_dir != s2.temp_dir


def test_temp_dir_unique_on_recreate(qapp):
    dirs = {MobileServer(_FakeParent()).temp_dir for _ in range(3)}
    assert len(dirs) == 3
