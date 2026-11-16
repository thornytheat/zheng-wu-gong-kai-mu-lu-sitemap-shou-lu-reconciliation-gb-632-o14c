"""M6 缺陷单：把缺陷分类落成可打印、可导出的缺陷行。

缺陷号按分类优先级 + 站点 + 地址排序后连续编号，同一次巡检重跑编号不变
（排序是全序，不依赖落库顺序）。证据列保留原始写法，供编辑直接改页面。
"""
from __future__ import annotations

from ... import reasons


def build_defects(run: dict, settings=None) -> list[dict]:
    probes = [row for row in (run.get("probes") or []) if row["category"] != "OK"]
    probes.sort(key=lambda row: (row.get("priority", 99), row["site"], row["url"]))
    out: list[dict] = []
    for index, row in enumerate(probes, 1):
        evidence = row.get("evidence") or {}
        out.append({
            "defect_no": f"DF-{index:04d}",
            "site": row["site"],
            "category": row["category"],
            "label": reasons.label(row["category"]),
            "url": row["url"],
            "status": row["status"],
            "hop_count": row["hop_count"],
            "reason": row.get("reason", ""),
            "reason_label": row.get("reason_label", ""),
            "in_catalog": evidence.get("in_catalog", row.get("in_catalog", 0)),
            "in_sitemap": evidence.get("in_sitemap", row.get("in_sitemap", 0)),
            "raw_forms": evidence.get("raw_forms", []),
            "notes": evidence.get("notes", []),
            "priority": row.get("priority", 99),
        })
    return out


def severity_of(category: str) -> str:
    if category in ("CATALOG_DEAD", "ONLY_IN_SITEMAP_DEAD"):
        return "错误"
    if category in ("REDIRECT_CHAIN", "DUPLICATE_SLUG", "ONLY_IN_CATALOG"):
        return "警告"
    return "提示"


def summary(defects: list[dict]) -> dict:
    by_category: dict[str, int] = {}
    by_site: dict[str, int] = {}
    for row in defects:
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1
        by_site[row["site"]] = by_site.get(row["site"], 0) + 1
    return {"total": len(defects), "by_category": by_category, "by_site": by_site}
