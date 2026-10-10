# tests/test_p2_regression/test_p1_05_decoded_marker.py
"""
P1-5 扩展回归：__decoded__ 标记不应写入磁盘。

背景：
  P1-5 修复旧版 webdav_pass → cloud_config.password 的双重解码问题，
  用 __decoded__ 列表标记"已解码的字段"，load() 遇到则跳过二次解码。

  但 save() 必须过滤掉这个内部标记，否则：
    - 磁盘上会出现 "cloud_config": {"password": "x", "__decoded__": ["password"]}
    - 下次 load() 读到残留的 __decoded__，会误以为 password 已是明文

测试策略：
  1. 构造 cloud_config 含 __decoded__ 的状态
  2. save() 落盘
  3. 读回原始 JSON
  4. 断言 __decoded__ 不在磁盘文件里

本次调整（优化规划 §1.2）：原实现用一份手工复制的 AppSettings.__init__
字段清单来重定向配置路径；v5.1 新增字段后清单失效，save() 抛 AttributeError
被静默吞掉，设置文件被截断成空文件，这两个用例因此长期失败。现已改为
AppSettings(path=...) 参数注入。
"""
import json


def test_decoded_marker_not_written_to_disk(tmp_path):
    """P1-5：save() 应过滤 cloud_config 里的 __decoded__ 键。"""
    from beeoffice.settings import AppSettings

    settings_path = tmp_path / ".beeoffice_settings.json"
    s = AppSettings(path=settings_path)

    # 模拟迁移后的状态：cloud_config 含 __decoded__ 标记
    s.cloud_config = {
        "url": "https://example.com/webdav",
        "username": "alice",
        "password": "secret123",
        "__decoded__": ["password"],
    }

    assert s.save() is True, "保存应成功"

    # 读回磁盘上的 JSON
    with open(settings_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cloud_config = data.get("cloud_config", {})
    assert "__decoded__" not in cloud_config, (
        f"P1-5：__decoded__ 是内部标记，不应写入磁盘。"
        f"实际 cloud_config={cloud_config}"
    )
    # 密码应被 Base64 编码
    assert cloud_config.get("password") != "secret123", (
        "P1-5：密码应被编码后再落盘"
    )
    # 其他字段正常保留
    assert cloud_config.get("url") == "https://example.com/webdav"
    assert cloud_config.get("username") == "alice"


def test_load_after_save_roundtrip(tmp_path):
    """P1-5：save → load 往返后密码应还原。"""
    from beeoffice.settings import AppSettings

    settings_path = tmp_path / ".beeoffice_settings.json"

    s1 = AppSettings(path=settings_path)
    s1.cloud_config = {
        "url": "https://example.com/webdav",
        "username": "alice",
        "password": "my_secret_pwd",
    }
    s1.cloud_enabled = True
    assert s1.save() is True

    s2 = AppSettings(path=settings_path)
    assert s2.cloud_config.get("password") == "my_secret_pwd", (
        f"P1-5：密码往返应还原。实际: {s2.cloud_config}"
    )
