"""缺陷单导出：CSV 带 BOM，Excel 直接能开；列顺序固定，便于按列复核。

CSV 里保留原始写法与状态码：编辑拿到表就能回到目录页对应行，
不需要再点一遍页面。字段顺序是契约的一部分（tests/test_defects.py 断言表头）。
"""
from __future__ import annotations

import csv
import io

COLUMNS = ("缺陷号", "站点", "分类", "严重度", "地址", "状态码", "跳转次数",
           "目录出现", "收录出现", "原因码", "原始写法")

QUARANTINE_COLUMNS = ("站点", "来源", "行号", "原因码", "原因", "级别", "原文")

BOM = "\ufeff"


def defects_csv(defects: list[dict], severity_of) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for row in defects:
        writer.writerow([
            row["defect_no"], row["site"], row["label"],
            severity_of(row["category"]), row["url"], row["status"],
            row["hop_count"], row["in_catalog"], row["in_sitemap"],
            row["reason"] or "—",
            " | ".join(row["raw_forms"]),
        ])
    return BOM + buffer.getvalue()


def quarantine_csv(rows: list[dict]) -> str:
    """隔离区导出：给编辑一份可以直接拿去改页面的清单。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(QUARANTINE_COLUMNS)
    for row in rows:
        writer.writerow([row["site"], row["source"], row["row_no"], row["reason"],
                         row.get("label", ""), row.get("level", ""), row["excerpt"]])
    return BOM + buffer.getvalue()


def filename(run_id: str) -> str:
    return f"defects-{run_id}.csv"


def quarantine_filename(run_id: str) -> str:
    return f"quarantine-{run_id}.csv"
