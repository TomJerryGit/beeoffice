# diagnose_image.py
"""图片往返问题诊断脚本"""
import sys
import tempfile
import zipfile
from pathlib import Path

print("=" * 60)
print("  图片往返问题诊断")
print("=" * 60)
print()

# ==================== 1. 检查目标 DOCX ====================
docx_path = Path(r"D:\beeofficeV\test+files\Test永遇乐·京口北固亭怀古.docx")
print(f"【1】目标 DOCX: {docx_path}")
if docx_path.exists():
    print(f"     ✅ 存在，大小: {docx_path.stat().st_size} bytes")
else:
    print(f"     ❌ 不存在")
    sys.exit(1)
print()

# ==================== 2. DOCX 内部的 word/media/ ====================
print(f"【2】DOCX 内部 word/media/ 目录（检查图片是否真被嵌入）")
with zipfile.ZipFile(docx_path, 'r') as z:
    media_files = [n for n in z.namelist() if 'media' in n.lower()]
    if media_files:
        print(f"     ✅ 找到 {len(media_files)} 个 media 文件:")
        for f in media_files:
            info = z.getinfo(f)
            print(f"        {f}  ({info.file_size} bytes)")
    else:
        print(f"     ❌ DOCX 内部没有 media 目录或图片")
        print(f"        → 说明保存时图片未成功嵌入 DOCX！")
print()

# ==================== 3. 同目录 _media 文件夹 ====================
media_dir = docx_path.parent / (docx_path.stem + "_media")
print(f"【3】同目录 _media 文件夹（检查导入时提取的图片）")
print(f"     路径: {media_dir}")
if media_dir.exists():
    files = list(media_dir.glob("*"))
    if files:
        print(f"     ✅ 找到 {len(files)} 个文件:")
        for f in files:
            print(f"        {f.name}  ({f.stat().st_size} bytes)")
    else:
        print(f"     ⚠️ 目录存在但为空")
else:
    print(f"     ❌ 目录不存在")
print()

# ==================== 4. %TEMP%/beeoffice_images/ ====================
temp_dir = Path(tempfile.gettempdir()) / "beeoffice_images"
print(f"【4】临时目录 beeoffice_images（工具栏插图的原始保存位置）")
print(f"     路径: {temp_dir}")
if temp_dir.exists():
    files = list(temp_dir.glob("*"))
    if files:
        print(f"     ✅ 找到 {len(files)} 个文件:")
        # 只显示最近 5 个
        sorted_files = sorted(
            files, key=lambda f: f.stat().st_mtime, reverse=True
        )
        for f in sorted_files[:5]:
            print(f"        {f.name}  ({f.stat().st_size} bytes)")
        if len(files) > 5:
            print(f"        ... 还有 {len(files) - 5} 个")
    else:
        print(f"     ⚠️ 目录存在但为空")
else:
    print(f"     ❌ 目录不存在")
print()

# ==================== 5. 解析 DOCX 内部 XML 结构 ====================
print(f"【5】DOCX 内部 XML 关键标签统计")
try:
    with zipfile.ZipFile(docx_path, 'r') as z:
        # document.xml
        with z.open("word/document.xml") as f:
            xml_content = f.read().decode("utf-8")

        ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
        ns_v = "urn:schemas-microsoft-com:vml"
        ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

        blip_count = xml_content.count("blip")
        imagedata_count = xml_content.count("imagedata")
        txbx_count = xml_content.count("txbxContent")
        drawing_count = xml_content.count("w:drawing")

        print(f"     blip（DrawingML 图片）:     {blip_count}")
        print(f"     imagedata（VML 图片）:      {imagedata_count}")
        print(f"     txbxContent（文本框）:      {txbx_count}")
        print(f"     w:drawing（图形对象）:      {drawing_count}")

        # 列出所有 rId 关系
        try:
            with z.open("word/_rels/document.xml.rels") as f:
                rels = f.read().decode("utf-8")
            image_rels = rels.count("relationships/image")
            print(f"     image 关系数量:             {image_rels}")
        except Exception as e:
            print(f"     读取 rels 失败: {e}")
except Exception as e:
    print(f"     ❌ 解析失败: {e}")
print()

# ==================== 6. 结论 ====================
print("=" * 60)
print("  结论")
print("=" * 60)
print()
print("根据以上 5 项检查：")
print("  · 若【2】显示有图片，说明保存时图片已嵌入 DOCX")
print("    → 问题在【3】提取阶段，或插入阶段路径解析")
print("  · 若【2】显示无图片，说明保存时图片未嵌入 DOCX")
print("    → 问题在【4】%TEMP% 里的图片文件丢失（被系统清理）")
print("    → 或 _insert_picture_to_para 路径解析失败")
print()