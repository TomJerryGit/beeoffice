# 真实文档语料库

目标：30–50 份真实/脱敏样本，覆盖四模块复杂场景。

## 目录

```text
tests/corpus/
  README.md
  manifest.json
  raw/          # 本地样本，不入库（含隐私）
  reports/      # 往返差异报告
```

## 采集要求

- 来源合法、已脱敏；
- 覆盖政府/企业/论文/财务/教学；
- 不提交含个人信息的原始文件；
- manifest 记录哈希、类型、复杂度标签。

## 往返矩阵

```text
导入 → 编辑 → 导出 → WPS 打开 → MS Office 打开 → 差异断言
```

## 样本状态

- pending：待采集
- ready：可跑
- blocked：缺依赖
- pass/fail：最近结果
