# beeoffice/resources/template_manager.py
"""
模板管理器：内置模板 + 用户模板 + 在线模板

优化要点：
  1. 用 logging 替代裸 except，避免吞掉 KeyboardInterrupt / SystemExit 等
  2. 文件名安全化，避免非法字符 / 路径穿越 / 长度超限
  3. 补齐 save_user_template 别名（beeoffice/templates.py 已在调用此方法）
  4. 索引文件损坏 / 类型不对时自动重建
  5. 用户模板文件丢失时自动从索引中清理
  6. OnlineTemplateFetcher 信号改名 templates_ready，
     避免覆盖 QThread 内置的 finished 信号（PySide6 已知坑）
  7. 常量提取为模块级 + 类属性，便于测试与配置
  8. 新增 delete_template / rename_template / get_user_templates /
     get_builtin_templates 等便捷方法，不破坏原有接口
  9. save_as_template 使用微秒级时间戳，避免同一秒并发保存冲突
 10. 所有 IO 操作补齐异常日志，返回 bool 表示成功与否
"""
import re
import json
import logging
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from beeoffice.resources.templates import TEMPLATES


# ==================== 常量 ====================
# 在线模板仓库 API
TEMPLATE_REPO_API = (
    "https://api.github.com/repos/TomJerryGit/beeoffice-templates"
    "/contents/templates"
)

# 用户模板目录
USER_TEMPLATE_DIR = Path.home() / ".beeoffice_templates"

# 索引文件名
INDEX_FILENAME = "index.json"

# 模板分类关键字映射
CATEGORY_KEYWORDS = {
    "工作": ["周报", "日报", "月报", "工作", "报告", "汇报"],
    "会议": ["会议", "纪要", "记录"],
    "项目": ["项目", "计划", "进度", "需求", "验收"],
    "数据": ["数据", "分析", "报表", "统计"],
    "财务": ["财务", "预算", "报销", "发票", "成本"],
    "餐饮": ["餐饮", "食材", "餐厅", "日报表"],
    "电商": ["电商", "GMV", "库存"],
    "教培": ["学员", "续费", "课程"],
}

# 非法文件名字符（含控制字符）
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# 文件名片段最大长度
_MAX_FILENAME_LEN = 100


# ==================== 工具函数 ====================
def _safe_filename(name: str) -> str:
    """
    将模板名称转为安全的文件名片段：
    - 替换非法字符为下划线
    - 去除首尾空白与末尾点号
    - 限制长度
    """
    if not name:
        return "untitled"
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("_", name).strip().rstrip(".")
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:_MAX_FILENAME_LEN]


# ==================== 在线模板拉取线程 ====================
class OnlineTemplateFetcher(QThread):
    """
    从 GitHub 仓库拉取在线模板列表。

    注意：信号名用 templates_ready，不要叫 finished。
    QThread 本身有 finished 信号，子类若定义同名信号会覆盖它，
    在 PySide6 中会导致 Qt 内部 emit 时参数不匹配，行为未定义。
    """

    templates_ready = Signal(list)
    error = Signal(str)

    def __init__(self, api_url: str = TEMPLATE_REPO_API, parent=None):
        super().__init__(parent)
        self._api_url = api_url

    def run(self):
        try:
            req = urllib.request.Request(
                self._api_url,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                raw = response.read().decode("utf-8")
            data = json.loads(raw)

            templates = []
            if isinstance(data, list):
                for item in data:
                    if (
                        isinstance(item, dict)
                        and item.get("type") == "file"
                        and str(item.get("name", "")).endswith(".md")
                    ):
                        templates.append({
                            # 去掉末尾 .md
                            "name": item["name"][:-3],
                            "download_url": item.get("download_url", ""),
                            "size": item.get("size", 0),
                        })
            self.templates_ready.emit(templates)
        except Exception as e:
            logging.error(f"拉取在线模板失败: {e}")
            self.error.emit(str(e))


# ==================== 模板管理器 ====================
class TemplateManager:
    """模板管理器：内置 + 用户 + 在线"""

    # 类属性，便于测试时覆盖
    REPO_API = TEMPLATE_REPO_API
    USER_DIR = USER_TEMPLATE_DIR
    INDEX_FILE = INDEX_FILENAME

    def __init__(self, user_dir: Path = None, repo_api: str = None):
        """
        :param user_dir: 用户模板目录（默认 ~/.beeoffice_templates）
        :param repo_api: 在线模板 API 地址
        """
        self._user_template_dir = Path(user_dir or self.USER_DIR)
        try:
            self._user_template_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logging.error(
                f"创建用户模板目录失败 {self._user_template_dir}: {e}"
            )

        self._template_index_path = self._user_template_dir / self.INDEX_FILE
        self._repo_api = repo_api or self.REPO_API
        self._index = {"user_templates": []}
        self._load_index()

    # ==================== 索引读写 ====================
    def _load_index(self):
        """加载索引文件，损坏 / 类型异常时自动重建"""
        if not self._template_index_path.exists():
            self._index = {"user_templates": []}
            return

        try:
            with open(self._template_index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logging.error(f"读取模板索引失败，将重建: {e}")
            self._index = {"user_templates": []}
            return

        # 结构校验
        if not isinstance(data, dict):
            logging.warning("模板索引结构异常，将重建")
            self._index = {"user_templates": []}
            return

        user_templates = data.get("user_templates", [])
        if not isinstance(user_templates, list):
            logging.warning("user_templates 字段不是列表，将重置")
            user_templates = []

        # 清洗条目：只保留含 filename 且 name 的 dict
        cleaned = []
        for tpl in user_templates:
            if (
                isinstance(tpl, dict)
                and tpl.get("filename")
                and tpl.get("name")
            ):
                cleaned.append(tpl)
            else:
                logging.warning(f"跳过无效模板索引条目: {tpl}")

        self._index = {"user_templates": cleaned}

    def _save_index(self) -> bool:
        """保存索引文件，返回是否成功"""
        try:
            with open(self._template_index_path, "w", encoding="utf-8") as f:
                json.dump(self._index, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logging.error(f"保存模板索引失败: {e}")
            return False

    # ==================== 查询 ====================
    def get_all_templates(self):
        """
        返回所有模板：
        [{name, content, source, category, created?}, ...]
        """
        templates = []

        # 1. 内置模板
        for name, content in TEMPLATES.items():
            templates.append({
                "name": name,
                "content": content,
                "source": "builtin",
                "category": self._categorize(name),
            })

        # 2. 用户模板
        stale_entries = []
        for tpl in self._index.get("user_templates", []):
            filepath = self._user_template_dir / tpl["filename"]
            if not filepath.exists():
                stale_entries.append(tpl)
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                templates.append({
                    "name": tpl["name"],
                    "content": content,
                    "source": "user",
                    "category": tpl.get("category", "其他"),
                    "created": tpl.get("created", ""),
                })
            except Exception as e:
                logging.error(f"读取用户模板失败 {filepath}: {e}")

        # 清理索引中文件已丢失的条目
        if stale_entries:
            for tpl in stale_entries:
                try:
                    self._index["user_templates"].remove(tpl)
                except ValueError:
                    pass
            self._save_index()

        return templates

    def get_user_templates(self):
        """仅返回用户模板"""
        return [t for t in self.get_all_templates() if t["source"] == "user"]

    def get_builtin_templates(self):
        """仅返回内置模板"""
        return [t for t in self.get_all_templates() if t["source"] == "builtin"]

    # ==================== 保存 ====================
    def save_as_template(self, name, content, category="其他") -> bool:
        """
        保存为模板
        :param name: 模板名称（不能为空）
        :param content: 模板内容
        :param category: 分类（默认「其他」）
        :return: 是否成功
        """
        name = (name or "").strip()
        if not name:
            logging.warning("模板名称为空，已忽略")
            return False

        if content is None:
            content = ""

        # 生成文件名：微秒级时间戳 + 安全名，避免并发冲突
        safe_name = _safe_filename(name)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        filename = f"{timestamp}_{safe_name}.md"
        filepath = self._user_template_dir / filename

        # 写入文件
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            logging.error(f"写入模板文件失败 {filepath}: {e}")
            return False

        # 更新索引
        self._index.setdefault("user_templates", []).append({
            "name": name,
            "filename": filename,
            "category": category or "其他",
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        return self._save_index()

    def save_user_template(self, name, content, category="其他") -> bool:
        """
        保存为模板（beeoffice/templates.py 调用的别名）
        与 save_as_template 等价。
        """
        return self.save_as_template(name, content, category)

    # ==================== 删除 / 重命名 ====================
    def delete_template(self, name: str) -> bool:
        """
        按名称删除用户模板（删除所有同名条目）
        :return: 是否删除了至少一条
        """
        name = (name or "").strip()
        if not name:
            return False

        removed = False
        remaining = []
        for tpl in self._index.get("user_templates", []):
            if tpl.get("name") == name:
                filepath = self._user_template_dir / tpl["filename"]
                try:
                    if filepath.exists():
                        filepath.unlink()
                except Exception as e:
                    logging.error(f"删除模板文件失败 {filepath}: {e}")
                removed = True
            else:
                remaining.append(tpl)

        if removed:
            self._index["user_templates"] = remaining
            self._save_index()
        return removed

    def rename_template(self, old_name: str, new_name: str) -> bool:
        """
        重命名用户模板（仅修改索引中的显示名，不改文件名）
        :return: 是否重命名成功
        """
        old_name = (old_name or "").strip()
        new_name = (new_name or "").strip()
        if not old_name or not new_name:
            return False

        renamed = False
        for tpl in self._index.get("user_templates", []):
            if tpl.get("name") == old_name:
                tpl["name"] = new_name
                renamed = True

        if renamed:
            self._save_index()
        return renamed

    # ==================== 在线模板 ====================
    def fetch_online_templates(self) -> OnlineTemplateFetcher:
        """
        返回在线模板拉取线程（异步）。
        调用方需连接 templates_ready / error 信号并 start()。

        用法：
            fetcher = tm.fetch_online_templates()
            fetcher.templates_ready.connect(self._on_templates_ready)
            fetcher.error.connect(self._on_fetch_error)
            fetcher.start()
        """
        return OnlineTemplateFetcher(self._repo_api)

    def download_online_template(self, download_url, name) -> bool:
        """
        同步下载在线模板并保存为用户模板。
        注意：会阻塞当前线程，建议在后台线程调用。
        """
        if not download_url:
            logging.warning("下载地址为空")
            return False

        try:
            req = urllib.request.Request(download_url)
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode("utf-8")
        except Exception as e:
            logging.error(f"下载在线模板失败 {download_url}: {e}")
            return False

        return self.save_as_template(name, content, category="在线")

    # ==================== 分类 ====================
    @staticmethod
    def _categorize(name: str) -> str:
        """根据模板名称推测分类"""
        if not name:
            return "其他"
        for cat, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in name:
                    return cat
        return "其他"


# ==================== 模块级便捷函数 ====================
def get_template_manager() -> TemplateManager:
    """获取默认的模板管理器实例"""
    return TemplateManager()