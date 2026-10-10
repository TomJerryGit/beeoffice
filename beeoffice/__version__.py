# beeoffice/__version__.py
"""
蜜蜂办公 BeeOffice 版本信息

版本号遵循语义化版本（SemVer）：
  - 主版本号（Major）：不兼容的 API 变更
  - 次版本号（Minor）：向后兼容的功能新增
  - 修订号（Patch）：向后兼容的问题修复

版本历史：
  v5.0.7（2026-10-10）：
    - 安全与数据完整性修复，详见 CHANGELOG.md 的 [5.0.7] 条目与
      《BeeOffice-优化规划.md》阶段 0 / 1
    - 注意：源码内相关注释按优化规划章节写作「v5.0.5 修复」，指同一批改动

  v5.0.4（2026-09-16）：
    - 蜜写：图片段落导出为 DOCX 时居中对齐 + 段前段后各 12pt
    - 蜜写：图片宽度上限从 600px 提升到 720px
    - 蜜写：图片插入后所在段落自动居中

  v5.0.3（2026-09-16）：
    - 修复打开含图片的 DOCX 时图片丢失：
      _open_docx_file.on_result 调用顺序调整
      （set_current_file_path 提前到 set_content / _switch_mode 之前）

  v5.0.2（2026-09-16）：
    - 修复图片在富文本 ↔ Markdown 往返中丢失
    - 修复 DOCX 导入时内嵌图片提取
    - 修复粘贴图片保存位置

  v5.0.1（2026-09-16）：
    - 累积修复 14 个 P0 + 18 个 P1 问题
    - 详见 CHANGELOG.md
"""

__version__ = "5.0.7"
__author__ = "TomJerryGit"
__email__ = "1265338136@qq.com"
__slogan__ = "百花寻觅，酿得甜蜜。"

# 兼容旧代码引用
__all__ = ["__version__", "__author__", "__email__", "__slogan__"]