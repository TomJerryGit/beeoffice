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

from beeoffice.utils import atomic_write_json


class AppSettings:
    """应用设置管理，支持版本迁移与敏感信息编码"""

    VERSION = 1  # 当前设置文件版本，升级时递增

    # 保存失败时的提示回调，由 UI 层注册（app.py）。
    # 之所以做成可选的类级钩子而不是直接弹 QMessageBox，是为了让本模块不依赖
    # Qt —— 否则在无 GUI 环境与测试里会弹出模态框把测试挂死。
    on_save_error = None

    def __init__(self, path=None):
        # 配置文件路径。允许注入：测试应通过 path 参数或本参数隔离，
        # 而不是复制本类的字段列表（那样字段一旦增减测试就会掩盖真实缺陷）。
        self.path = (
            Path(path)
            if path is not None
            else Path(str(Path.home() / ".beeoffice_settings.json"))
        )

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
        # 同步目录（P1 修复）：原先"立即同步"上传的是 `~/.beeoffice_data`
        # —— 那个目录**全仓没有写入方**，所以永远是空的（同步等于没事做）。
        # 现在改为**可配置**目录，空值表示用默认 `~/BeeOffice云同步`。
        self.cloud_sync_dir = ""

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
        # i18n 决策（2026-10-20）：中文优先 —— 固定 zh_CN，忽略旧配置里的其他语言。
        # 字段保留是为了配置向后兼容（以及未来 tr 化后重新启用）。
        self.language = "zh_CN"
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
        self.cloud_sync_dir = data.get("cloud_sync_dir", "") or ""
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
    def save(self) -> bool:
        """
        保存设置到文件（原子写）。

        v5.0.5 修复（优化规划 §1.2）：
          原实现先以 "w" 模式打开文件——这会**立即截断**它——然后在
          json.dump 的参数位置构造字典。于是任何构造期异常（例如字段缺失，
          实测由 v5.1 新增字段未同步到测试 fixture 触发）都会把用户的设置
          文件留成 0 字节空文件，而异常被 except 静默吞掉。

          现在分两步：先在内存构造完整 payload（此步失败时磁盘未被触碰），
          再交给 atomic_write_json 做 “同目录临时文件 + fsync + os.replace”
          的原子替换。目标文件要么保持旧的完整内容，要么是新的完整内容。

        :return: 是否保存成功
        """
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

        # 关键：payload 在打开目标文件之前完整构造
        try:
            payload = {
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
                "cloud_sync_dir": self.cloud_sync_dir,
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
            }
        except Exception as e:
            logging.error(f"构建设置数据失败（原文件未改动）: {e}")
            self._notify_save_error(f"设置保存失败，原有设置未被改动：{e}")
            return False

        ok = atomic_write_json(self.path, payload)
        if not ok:
            self._notify_save_error(
                f"设置保存失败，原有设置未被改动：{self.path}"
            )
        return ok

    def _notify_save_error(self, message: str) -> None:
        """把保存失败告知用户。UI 层未注册回调时只记日志，绝不静默。"""
        logging.error(message)
        callback = type(self).on_save_error
        if callback is None:
            return
        try:
            callback(message)
        except Exception:
            logging.exception("设置保存失败回调本身出错")

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