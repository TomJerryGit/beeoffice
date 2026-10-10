# beeoffice/settings.py
"""
应用设置管理，支持版本迁移与敏感信息编码

v5.0.1 修复（P1-5）：
  - 旧版 webdav_pass 迁移到 cloud_config.password 时，原实现存在双重解码风险：
      _migrate 把 base64 值塞进 cloud_config.password，
      load() 又统一 _decode() 一次，边缘情况下（明文恰好是合法 base64）会出错。
  - 修复方案：
      1) _migrate 显式解码后写入 cloud_config.password
      2) 用 __decoded__ 标记已解码字段，load() 遇到此标记跳过二次解码
      3) save() 过滤 __decoded__ 标记，不写入磁盘

v5.1.0 新增：
  - 任务 1.1：AI 服务配置（ai_api_key / ai_api_base / ai_model）
  - 任务 4.2：用户信息（user_name，用于评论作者名）
  - 任务 1.3：图库 API 配置（unsplash_api_key / pexels_api_key）
"""
import json
import base64
import logging
from pathlib import Path


class AppSettings:
    """应用设置管理，支持版本迁移与敏感信息编码"""

    VERSION = 1  # 当前设置文件版本，升级时递增

    def __init__(self):
        # 配置文件路径
        self.path = Path(str(Path.home() / ".beeoffice_settings.json"))

        # 默认值
        self.window_size = (1024, 680)
        self.recent_files = []
        self.open_tabs = []
        self.theme = "light"
        self.accent_color = "amber"
        self.language = "zh_CN"
        self.has_completed_onboarding = False
        self.recent_commands = []

        # WebDAV 旧字段（保留以兼容旧版本）
        self.webdav_url = ""
        self.webdav_user = ""
        self.webdav_pass = ""
        self.webdav_enabled = False
        self.webdav_auto_sync = False

        # Git 字段
        self.git_repo_path = ""
        self.git_enabled = False

        # 云存储（新）
        self.cloud_type = "webdav"
        self.cloud_config = {}
        self.cloud_enabled = False
        self.cloud_auto_sync = False

        # AI 服务（任务 1.1）
        self.ai_api_key = ""
        self.ai_api_base = "https://api.deepseek.com/v1"
        self.ai_model = "deepseek-chat"

        # 用户信息（任务 4.2）
        self.user_name = ""

        # 图库 API（任务 1.3，可选）
        self.unsplash_api_key = ""
        self.pexels_api_key = ""

        # 加载设置
        self.load()

    # ---------- 编码/解码 ----------
    def _encode(self, s):
        """Base64 编码敏感信息"""
        if not s:
            return s
        try:
            return base64.b64encode(s.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logging.error(f"编码失败: {e}")
            return s

    def _decode(self, s):
        """Base64 解码敏感信息"""
        if not s:
            return s
        try:
            return base64.b64decode(s.encode("utf-8")).decode("utf-8")
        except Exception:
            # 兼容未编码的旧数据
            return s

    # ---------- 加载 ----------
    def load(self):
        """从文件加载设置"""
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logging.error(f"加载设置文件失败: {e}")
            return

        # 处理版本迁移
        version = data.get("version", 0)
        if version < self.VERSION:
            data = self._migrate(version, data)

        # 基础设置
        self.window_size = tuple(data.get("window_size", self.window_size))
        self.recent_files = data.get("recent_files", [])
        self.open_tabs = data.get("open_tabs", [])
        self.theme = data.get("theme", "light")
        self.accent_color = data.get("accent_color", "amber")
        self.language = data.get("language", "zh_CN")
        self.has_completed_onboarding = data.get("has_completed_onboarding", False)
        self.recent_commands = data.get("recent_commands", [])

        # WebDAV 旧字段（解码密码）
        self.webdav_url = data.get("webdav_url", "")
        self.webdav_user = data.get("webdav_user", "")
        self.webdav_pass = self._decode(data.get("webdav_pass", ""))
        self.webdav_enabled = data.get("webdav_enabled", False)
        self.webdav_auto_sync = data.get("webdav_auto_sync", False)

        # Git
        self.git_repo_path = data.get("git_repo_path", "")
        self.git_enabled = data.get("git_enabled", False)

        # 云存储（新）
        self.cloud_type = data.get("cloud_type", "webdav")
        self.cloud_config = data.get("cloud_config", {})
        # P1-5：迁移时已解码的字段用 __decoded__ 标记，跳过二次解码
        if isinstance(self.cloud_config, dict):
            already_decoded = self.cloud_config.pop("__decoded__", [])
            if not isinstance(already_decoded, list):
                already_decoded = []
            for key in ("password", "access_token"):
                if (key in self.cloud_config
                        and self.cloud_config[key]
                        and key not in already_decoded):
                    self.cloud_config[key] = self._decode(
                        self.cloud_config[key]
                    )
        self.cloud_enabled = data.get("cloud_enabled", False)
        self.cloud_auto_sync = data.get("cloud_auto_sync", False)

        # AI 服务（任务 1.1）
        self.ai_api_key = self._decode(data.get("ai_api_key", ""))
        self.ai_api_base = data.get(
            "ai_api_base", "https://api.deepseek.com/v1"
        )
        self.ai_model = data.get("ai_model", "deepseek-chat")

        # 用户信息（任务 4.2）
        self.user_name = data.get("user_name", "")

        # 图库 API（任务 1.3）
        self.unsplash_api_key = self._decode(
            data.get("unsplash_api_key", "")
        )
        self.pexels_api_key = self._decode(
            data.get("pexels_api_key", "")
        )

    def _migrate(self, old_version, data):
        """从旧版本迁移设置到新版本"""
        # 版本 0 -> 1：将 webdav_* 迁移到 cloud_config
        if old_version < 1:
            if data.get("webdav_url"):
                # P1-5：先把 webdav_pass 解码为明文，再放进 cloud_config，
                # 并用 __decoded__ 标记，避免 load() 二次解码
                raw_pass = data.get("webdav_pass", "")
                plain_pass = self._decode(raw_pass) if raw_pass else ""

                data.setdefault("cloud_config", {})
                data["cloud_config"].setdefault(
                    "url", data.get("webdav_url", "")
                )
                data["cloud_config"].setdefault(
                    "username", data.get("webdav_user", "")
                )
                data["cloud_config"]["password"] = plain_pass

                # 标记：password 已是明文，load() 不再解码
                decoded = data["cloud_config"].setdefault("__decoded__", [])
                if "password" not in decoded:
                    decoded.append("password")

                data.setdefault("cloud_type", "webdav")
                data.setdefault(
                    "cloud_enabled", data.get("webdav_enabled", False)
                )
                data.setdefault(
                    "cloud_auto_sync", data.get("webdav_auto_sync", False)
                )

        # 更新版本号
        data["version"] = self.VERSION
        return data

    # ---------- 保存 ----------
    def save(self):
        """保存设置到文件"""
        # 编码云配置中的敏感信息
        cloud_config_encoded = {}
        if isinstance(self.cloud_config, dict):
            for k, v in self.cloud_config.items():
                # P1-5：跳过内部标记，不写入磁盘
                if k == "__decoded__":
                    continue
                if k in ("password", "access_token") and v:
                    cloud_config_encoded[k] = self._encode(v)
                else:
                    cloud_config_encoded[k] = v

        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({
                    "version": self.VERSION,
                    "window_size": list(self.window_size),
                    "recent_files": self.recent_files,
                    "open_tabs": self.open_tabs,
                    "theme": self.theme,
                    "accent_color": self.accent_color,
                    "language": self.language,
                    "has_completed_onboarding": self.has_completed_onboarding,
                    "recent_commands": self.recent_commands,
                    # 旧 WebDAV 字段（兼容）
                    "webdav_url": self.webdav_url,
                    "webdav_user": self.webdav_user,
                    "webdav_pass": self._encode(self.webdav_pass),
                    "webdav_enabled": self.webdav_enabled,
                    "webdav_auto_sync": self.webdav_auto_sync,
                    # Git
                    "git_repo_path": self.git_repo_path,
                    "git_enabled": self.git_enabled,
                    # 新云存储
                    "cloud_type": self.cloud_type,
                    "cloud_config": cloud_config_encoded,
                    "cloud_enabled": self.cloud_enabled,
                    "cloud_auto_sync": self.cloud_auto_sync,
                    # AI 服务（任务 1.1）
                    "ai_api_key": self._encode(self.ai_api_key),
                    "ai_api_base": self.ai_api_base,
                    "ai_model": self.ai_model,
                    # 用户信息（任务 4.2）
                    "user_name": self.user_name,
                    # 图库 API（任务 1.3）
                    "unsplash_api_key": self._encode(
                        self.unsplash_api_key
                    ),
                    "pexels_api_key": self._encode(
                        self.pexels_api_key
                    ),
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"保存设置文件失败: {e}")

    # ---------- 便捷方法 ----------
    def add_recent_file(self, filepath):
        """添加文件到最近列表"""
        filepath = str(filepath)
        if filepath in self.recent_files:
            self.recent_files.remove(filepath)
        self.recent_files.insert(0, filepath)
        self.recent_files = self.recent_files[:10]
        self.save()

    def clear_recent_files(self):
        """清空最近文件列表"""
        self.recent_files = []
        self.save()