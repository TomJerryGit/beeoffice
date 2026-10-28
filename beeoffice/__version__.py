# beeoffice/__version__.py
"""
蜜蜂办公 BeeOffice 版本信息

**本文件是版本号的唯一来源**（优化规划 §4.3）。
README 的版本徽章与 CHANGELOG 的最新条目由 `tools/sync_version.py` 与之核对，
不一致时该工具以退出码 1 报错（CI 会拦住）。

版本号遵循语义化版本（SemVer）：
  - 主版本号（Major）：不兼容的 API 变更
  - 次版本号（Minor）：向后兼容的功能新增
  - 修订号（Patch）：向后兼容的问题修复

变更历史**不写在这里**：请查阅 CHANGELOG.md。
（§4.3 要求源码 docstring 只写"为什么这样写"，历史交给 CHANGELOG 与 git。
本文件原先内嵌了 v5.0.1~v5.0.7 的补丁说明，与 CHANGELOG 重复、且必然漏更新。）
"""

__version__ = "5.0.30"
__author__ = "TomJerryGit"
__email__ = "1265338136@qq.com"
__slogan__ = "百花寻觅，酿得甜蜜。"

# 兼容旧代码引用
__all__ = ["__version__", "__author__", "__email__", "__slogan__"]
