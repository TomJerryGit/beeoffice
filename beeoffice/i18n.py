# beeoffice/i18n.py
import json
import logging
from pathlib import Path


class I18nManager:
    """国际化管理器（单例）"""
    _instance = None
    _current_lang = "zh_CN"
    _translations = {}
    _default_translations = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_translations()
        return cls._instance

    def _load_translations(self):
        """从 locales 目录加载所有 JSON 语言文件"""
        locales_dir = Path(__file__).parent / "locales"
        if not locales_dir.exists():
            logging.warning(f"语言目录不存在: {locales_dir}")
            return

        for lang_file in locales_dir.glob("*.json"):
            lang_code = lang_file.stem
            try:
                with open(lang_file, "r", encoding="utf-8") as f:
                    self._translations[lang_code] = json.load(f)
                logging.info(f"已加载语言包: {lang_code}")
            except Exception as e:
                logging.error(f"加载语言包 {lang_file} 失败: {e}")
                self._translations[lang_code] = {}

        # 默认回退语言为 en_US（如果存在）
        self._default_translations = self._translations.get("en_US", {})
        if not self._default_translations:
            logging.warning("未找到 en_US 语言包，回退翻译将不可用")

    def set_language(self, lang_code: str) -> bool:
        """设置当前语言，成功返回 True"""
        if lang_code in self._translations:
            self._current_lang = lang_code
            logging.info(f"语言已切换为: {lang_code}")
            return True
        logging.warning(f"不支持的语言代码: {lang_code}")
        return False

    def get(self, key: str, default: str = None) -> str:
        """
        获取翻译文本。

        回退顺序（v5.3 修正）：
            当前语言 → **调用方给的默认值** → en_US → 键名

        为什么不能先回退 en_US：
            本项目的中文默认值写在代码里（`tr("k", "中文")`），
            zh_CN.json 只覆盖少数需要改写的条目。
            若先回退 en_US，中文用户会在绝大多数新增文案上看到英文——
            方向完全反了。英文用户因为 en_US 是全量的，不受影响。
        """
        value = self._translations.get(self._current_lang, {}).get(key)
        if value:
            return value
        if default is not None:
            return default
        value = self._default_translations.get(key)
        return value if value else key

    @property
    def current_language(self) -> str:
        return self._current_lang


# ---------- 模块级便捷函数 ----------
def tr(key: str, default: str = None) -> str:
    """翻译函数，等价于 I18nManager().get()"""
    return I18nManager().get(key, default)


def set_language(lang: str) -> bool:
    """设置语言"""
    return I18nManager().set_language(lang)