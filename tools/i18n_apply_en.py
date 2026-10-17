# -*- coding: utf-8 -*-
"""
把「中文 → 英文」映射批量应用到 locales/en_US.json。

为什么需要它：
    i18n_migrate.py 生成的 key 是文本哈希（auto.<module>.<hash>），
    手写 JSON 容易抄错 key。本工具按"中文原文"匹配，自动查出对应 key。

用法：
    python tools/i18n_apply_en.py --keys docs/i18n-dialogs.json --map docs/en-dialogs.json

参数：
    --keys  i18n_migrate.py --json 导出的 {key: 中文}
    --map   {中文: English}

退出码：
    0 全部覆盖；1 存在未翻译项（会打印出来）
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EN_PATH = ROOT / "beeoffice" / "locales" / "en_US.json"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    keys = json.loads(Path(args.keys).read_text(encoding="utf-8"))
    mapping = json.loads(Path(args.map).read_text(encoding="utf-8"))
    en = json.loads(EN_PATH.read_text(encoding="utf-8"))

    applied = 0
    missing = []
    for key, zh in keys.items():
        english = mapping.get(zh)
        if english is None:
            missing.append(zh)
            continue
        en[key] = english
        applied += 1

    print(f"映射条目 : {len(mapping)}")
    print(f"已应用   : {applied} / {len(keys)}")
    if missing:
        print(f"未翻译   : {len(missing)}")
        for text in missing[:10]:
            print(f"  · {text}")

    if args.dry_run:
        print("\n（预演，未写盘）")
        return 0 if not missing else 1

    EN_PATH.write_text(
        json.dumps(en, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n✓ 已写入 {EN_PATH.relative_to(ROOT)}（共 {len(en)} 个 key）")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
