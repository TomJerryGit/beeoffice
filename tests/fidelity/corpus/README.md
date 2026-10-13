# 真实文件语料目录

把**脱敏后的真实** `.docx` / `.xlsx` / `.pptx` 放进这个目录，`tools/fidelity_corpus.py`
会自动扫描并对每个文件做一次往返，报告丢了什么。

```bash
python tools/fidelity_corpus.py                 # 扫 test+files/ 与本目录
python tools/fidelity_corpus.py --dir <目录>     # 指定目录
python tests/fidelity/test_corpus.py -q         # 同样在测试里跑
```

## 为什么需要它

`tests/fidelity/test_ooxml_probe.py` 用的是**合成夹具**（自己造的），
`tools/fidelity_corpus_gen.py` 生成的也是合成的（虽然每个文件专攻一个维度）。
合成文件**必然覆盖不到真实世界的构造** —— 所以"往返零丢失"这个结论
只能靠真实文件来检验。

## 已发现的问题都源自真实语料

压力语料第一次运行就撞出 3 类新的丢失（多分节、嵌套表格、书签），
这些都不是合成夹具能暴露的。见 `docs/fidelity.md`。

## 放文件时的注意

- **体积**：建议单个文件 < 2 MB；大文件会拖慢 CI。
- **隐私**：请先脱敏（替换人名、金额、真实标题等）。
- **不要**放 Office 锁文件（`~$xxx.docx`）—— 扫描时会跳过。
- 扫描器**不会**改动这里：它先在临时目录里做副本再往返。
  （早期版本直接在原地跑，会往语料目录写 `<文件名>_media/`。）
