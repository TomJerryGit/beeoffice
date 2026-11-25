# Phase B：Excel 组合图与 venv 构建

日期：2026-11-25

## 组合图

- 类型：柱状图 + 折线图；
- 折线使用次坐标轴；
- 支持标题/图例/样式/坐标轴/宽高；
- 测试检查 XML 同时含 barChart 与 lineChart。

## 隔离 venv

```text
D:\beeofficeV\_ptmp\ci-env
```

脚本优先使用：

```text
BEEOFFICE_VENV
..\ci-env
.venv
```

新增：

```text
build_local.bat
tools/package_release.py
```

## 验证

```text
全量：1711 passed
```

## 已知边界

- 组合图目前固定“第一数据列柱状、第二数据列折线”；
- 更多系列/双柱组合未做；
- 现有组合图导入读取仍不完整。
