# beeoffice/plugins/beesheet_pivot.py
"""
蜜算数据透视表：**计算语义** + **落盘（可刷新）**。

## 问题（本模块要修的）
原先"数据透视表"只把**结果值**塞进一个新标签页，`config`（行/列/值/聚合/小计）
**当场丢弃** —— 于是：
* 关掉标签页就再也回不去（重算不了）；
* 存成文件后只剩一堆死数字，**看不出这是怎么汇总出来的**，更**无法刷新**。

## 两条路的取舍（先试过再决定，记录下来）
我**先试了写"原生 Excel 数据透视表"**（`openpyxl.pivot` 的
`TableDefinition` + `CacheDefinition`），想让 Excel/WPS 用户能点"刷新"。
两次尝试分别被 openpyxl 拒绝：

    TypeError: TableDefinition.dataCaption should be <class 'str'> ...
    TypeError: PivotField.items ... FieldItem ... expected <class 'FieldItem'>

它的 pivot 对象图**又深又缺文档**，而**半填的 pivot 会让 Excel 弹"修复文件"**
——那比"没有原生透视表"糟得多（本项目最不能接受的就是产出坏文件）。
所以本模块走**规格 + 可刷新**这条路：

1. **隐藏元数据表** `beeoffice_pivot`：写明是哪个版本、透视表在哪个工作表、
   字段配置（JSON），以及**来源文件路径**（如果知道）；
2. **隐藏数据快照表** `beeoffice_pivot_data`：存下当初汇总的那份数据 ——
   这样**即使来源文件不在**，数据透视表也仍是自洽的、可重算的；
3. `refresh_pivot_package()`：按"当前文件里的数据表 → 来源文件 → 快照"
   的顺序取数据，重算并**重写**透视表工作表的数值。

## 已知边界（如实说明）
文件里**没有** Excel 原生的透视表对象（上面已说明原因）；
因此 Excel 里看到的是一张普通表格（值正确、可继续用），
而"刷新"由本应用提供。
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

#: 隐藏元数据表
META_SHEET = "beeoffice_pivot"
#: 隐藏数据快照表
SNAPSHOT_SHEET = "beeoffice_pivot_data"
#: 版本标记（写进元数据表 A1，读的时候用来确认"这是我们写的"）
SPEC_MARKER = "beeoffice-pivot-v1"


def drop_empty_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    丢掉**整行都是空**的行。

    ⚠️ 为什么必须有且只有一份：模型会把数据**补齐到默认行数（1000 行）**，
    尾部全是空串/NaN。若把这份"补齐后的表"直接拿去透视，
    `sum` 会把这些空值也当数据算进来（实测：本该是 1 的求和变成 0）。
    生成路径与刷新路径**必须用同一个过滤**，否则两边结果不一致。
    """
    if df is None or getattr(df, "empty", True):
        return df

    def _row_is_empty(row):
        return all(
            str(v).strip() == "" or (not isinstance(v, str) and pd.isna(v))
            for v in row
        )

    try:
        return df[~df.apply(_row_is_empty, axis=1)]
    except Exception as e:  # noqa: BLE001
        logging.debug(f"[蜜算] 过滤空行失败（用原数据）: {e}")
        return df


def build_pivot(df: pd.DataFrame, config: Dict[str, Any]
                ) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    按配置生成数据透视表（**与对话框同一套语义**，避免两处漂移）。

    :param config: {"rows": [...], "cols": [...], "values": [...],
                    "aggfunc": "sum"/"mean"/"count"/"max"/"min",
                    "margins": bool}
    :return: (透视结果, 错误信息) —— 其中一个为 None
    """
    if df is None:
        return None, "没有数据"
    rows = list(config.get("rows") or [])
    cols = list(config.get("cols") or [])
    values = list(config.get("values") or [])
    if not rows and not cols:
        return None, "必须至少指定行字段或列字段"
    if not values:
        return None, "必须指定值字段"
    try:
        pivot = pd.pivot_table(
            df,
            index=rows if rows else None,
            columns=cols if cols else None,
            values=values,
            aggfunc=config.get("aggfunc", "sum"),
            margins=bool(config.get("margins", False)),
        )
        # 展平多级列索引（与对话框一致：`a_b` 形式）
        if isinstance(pivot.columns, pd.MultiIndex):
            pivot.columns = [
                "_".join(str(x) for x in col if x) for col in pivot.columns
            ]
        # ⚠️ **有行字段就必须把索引转成列** —— 原先只对 `MultiIndex` 做，
        # 于是"只有一个行字段"时（最常见的情况！）`reset_index(drop=True)`
        # 会把行标签**整个丢掉**，透视表只剩一堆数字，看不出每行是谁：
        #     修前：列 = ['销量_1月','销量_2月']，索引 = [0,1]  ← 产品 A/B 消失
        #     修后：列 = ['产品','销量_1月','销量_2月']
        # 这是从对话框原样搬过来的老 bug，落盘时被端到端测试暴露出来。
        if rows:
            pivot = pivot.reset_index()
        pivot = pivot.reset_index(drop=True)
        pivot = pivot.fillna(0)
        return pivot, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


# ==================== 落盘 ====================

def _clear_sheet(sheet):
    """
    清空一张表。

    ⚠️ 必须**删行**而不是只把值置 None：`append()` 是"追加到最后一行之后"，
    只清值会让 `max_row` 停在原处、`append` 写到很下面（我第一版就是这样：
    刷新后透视表第一行是空的，数据跑到了几百行以下）。
    """
    try:
        if sheet.max_row and sheet.max_row > 0:
            sheet.delete_rows(1, sheet.max_row)
    except Exception as e:  # noqa: BLE001
        logging.debug(f"[蜜算] 清空工作表失败: {e}")


def _ensure_sheet(workbook, title: str, state: str = "hidden"):
    """取（或建）一张工作表，并设置其可见性。"""
    if title in workbook.sheetnames:
        sheet = workbook[title]
    else:
        sheet = workbook.create_sheet(title)
    try:
        if sheet.sheet_state != state:
            sheet.sheet_state = state
    except Exception as e:  # noqa: BLE001
        logging.debug(f"[蜜算] 设置工作表可见性失败 {title}: {e}")
    return sheet


def write_pivot_package(path, *, pivot_sheet: str, spec: Dict[str, Any],
                        source_df: Optional[pd.DataFrame] = None) -> Dict[str, int]:
    """
    把"透视表规格 + 数据快照"写进已存在的 xlsx（就地更新）。

    :return: 计数（如实：失败返回 0 并记日志，不抛异常 —— 数据已经写好了）
    """
    result = {"meta": 0, "snapshot": 0}
    try:
        from openpyxl import load_workbook
    except ImportError:
        return result
    target = Path(path)
    if not target.is_file():
        return result
    try:
        workbook = load_workbook(str(target))
    except Exception as e:  # noqa: BLE001
        logging.warning(f"[蜜算] 写透视表元数据失败（打不开文件）: {e}")
        return result

    try:
        meta = _ensure_sheet(workbook, META_SHEET)
        _clear_sheet(meta)                      # 重复保存不能叠加
        meta["A1"] = SPEC_MARKER
        meta["A2"] = "pivot_sheet"
        meta["B2"] = str(pivot_sheet)
        meta["A3"] = "spec"
        import json as _json

        meta["B3"] = _json.dumps(spec or {}, ensure_ascii=False)
        meta.column_dimensions["A"].width = 18
        meta.column_dimensions["B"].width = 80
        result["meta"] = 1

        if source_df is not None and not getattr(source_df, "empty", True):
            snapshot = _ensure_sheet(workbook, SNAPSHOT_SHEET)
            _clear_sheet(snapshot)
            snapshot.append([str(c) for c in source_df.columns])
            for _, row in source_df.iterrows():
                snapshot.append([_json_safe(v) for v in row.tolist()])
            result["snapshot"] = 1

        workbook.save(str(target))
    except Exception as e:  # noqa: BLE001
        logging.warning(f"[蜜算] 写透视表元数据失败: {e}")
    finally:
        try:
            workbook.close()
        except Exception:  # noqa: BLE001
            pass
    return result


def _json_safe(value):
    """把 pandas/numpy 值变成能写进单元格的东西。"""
    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def read_pivot_package(path) -> Optional[Dict[str, Any]]:
    """
    读回透视表规格与快照。

    :return: {"spec": {...}, "pivot_sheet": str, "snapshot": DataFrame|None}；
             不是本应用写的（或读不到）时返回 None —— **不猜**。
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        return None
    target = Path(path)
    if not target.is_file():
        return None
    try:
        workbook = load_workbook(str(target), data_only=True)
    except Exception as e:  # noqa: BLE001
        logging.debug(f"[蜜算] 读取透视表元数据失败: {e}")
        return None

    try:
        if META_SHEET not in workbook.sheetnames:
            return None
        meta = workbook[META_SHEET]
        if str(meta["A1"].value or "") != SPEC_MARKER:
            return None
        pivot_sheet = str(meta["B2"].value or "")
        try:
            spec = json.loads(str(meta["B3"].value or "{}"))
        except (TypeError, ValueError):
            spec = {}

        snapshot = None
        if SNAPSHOT_SHEET in workbook.sheetnames:
            snap = workbook[SNAPSHOT_SHEET]
            rows = [[c.value for c in r] for r in snap.iter_rows()]
            if rows:
                header, body = rows[0], rows[1:]
                snapshot = pd.DataFrame(body, columns=header)
        return {"spec": spec, "pivot_sheet": pivot_sheet, "snapshot": snapshot}
    except Exception as e:  # noqa: BLE001
        logging.debug(f"[蜜算] 解析透视表元数据失败: {e}")
        return None
    finally:
        try:
            workbook.close()
        except Exception:  # noqa: BLE001
            pass


def resolve_source_data(package: Dict[str, Any],
                        data_df: Optional[pd.DataFrame] = None
                        ) -> Tuple[Optional[pd.DataFrame], str]:
    """
    按"当前文件里的数据表 → 快照"顺序取用于重算的数据。

    :return: (数据, 来源说明) —— 供界面**如实**告诉用户用的是哪一份
    """
    if data_df is not None and not getattr(data_df, "empty", True):
        return data_df, "当前表格"
    snapshot = package.get("snapshot")
    if snapshot is not None and not getattr(snapshot, "empty", True):
        return snapshot, "文件内的数据快照"
    return None, "没有可用的数据"


def refresh_pivot_package(path, data_df: Optional[pd.DataFrame] = None
                          ) -> Tuple[bool, str, Optional[pd.DataFrame]]:
    """
    按已保存的规格**重算**透视表，并把结果写回透视表工作表。

    :param data_df: 用这份数据重算（通常是"当前文件里的数据表"）；
                    None 时用文件内的快照
    :return: (成功?, 说明文字, 新的透视结果)
    """
    package = read_pivot_package(path)
    if not package:
        return False, "这个文件里没有保存过透视表配置", None

    data, source_desc = resolve_source_data(package, data_df)
    if data is None:
        return False, "找不到可用于重算的数据（快照也不在）", None

    pivot, error = build_pivot(data, package.get("spec") or {})
    if pivot is None:
        return False, f"重算失败：{error}", None

    if not _write_pivot_values(path, package.get("pivot_sheet") or "", pivot):
        return False, "重算成功，但写入工作表失败", pivot
    return True, f"已按「{source_desc}」重算（{len(pivot)} 行）", pivot


def _write_pivot_values(path, sheet_name: str, pivot: pd.DataFrame) -> bool:
    """把透视结果写回指定工作表（**先清空**原区域，避免旧行残留）。"""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return False
    try:
        workbook = load_workbook(str(path))
    except Exception as e:  # noqa: BLE001
        logging.warning(f"[蜜算] 刷新透视表打不开文件: {e}")
        return False
    try:
        if not sheet_name or sheet_name not in workbook.sheetnames:
            sheet_name = workbook.sheetnames[0]
        sheet = workbook[sheet_name]
        _clear_sheet(sheet)
        sheet.append([str(c) for c in pivot.columns])
        for _, row in pivot.iterrows():
            sheet.append([_json_safe(v) for v in row.tolist()])
        workbook.save(str(path))
        return True
    except Exception as e:  # noqa: BLE001
        logging.warning(f"[蜜算] 刷新透视表写入失败: {e}")
        return False
    finally:
        try:
            workbook.close()
        except Exception:  # noqa: BLE001
            pass
