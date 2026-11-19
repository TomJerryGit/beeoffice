"""`.beshow` 持久化源 PPTX 路径。"""
from beeoffice.plugins import beeshow_doc


def test_source_path_roundtrip(tmp_path):
    src = tmp_path / "source.pptx"
    src.write_bytes(b"fake")
    deck = tmp_path / "deck.beshow"
    assert beeshow_doc.save_deck(deck, "# 标题\n\n正文", pptx_source=str(src))
    assert beeshow_doc.load_pptx_source(deck) == str(src)
    content = beeshow_doc.load_deck(deck)
    assert content.startswith("# 标题")
    assert "beeshow-pptx-source" not in content


def test_source_path_replaced_on_save(tmp_path):
    deck = tmp_path / "deck.beshow"
    assert beeshow_doc.save_deck(deck, "A", pptx_source="D:/a.pptx")
    assert beeshow_doc.save_deck(deck, "B", pptx_source="D:/b.pptx")
    assert beeshow_doc.load_pptx_source(deck) == "D:/b.pptx"
    assert beeshow_doc.load_deck(deck).strip() == "B"
