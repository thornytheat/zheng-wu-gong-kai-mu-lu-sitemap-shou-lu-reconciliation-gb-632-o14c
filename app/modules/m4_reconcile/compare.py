"""三向交叉表：目录/收录 × 可达三态，九格；每格给出计数与示例地址。

交叉表是给人看差异用的：任一格不为 0 都能点进去看明细，
所以每格带前 3 条 key 作为线索，而不是只给一个数字。
"""
from __future__ import annotations

from ... import reasons

SIDE_LABELS = (("catalog", "仅在目录"), ("both", "双侧都有"), ("sitemap", "仅在收录"))
STATE_LABELS = (("ok", "200 无跳转"), ("redirect", "跳转"), ("dead", "死链"))


def side_of(row: dict) -> str:
    has_catalog = bool(row["in_catalog"])
    has_sitemap = bool(row["in_sitemap"])
    if has_catalog and has_sitemap:
        return "both"
    return "catalog" if has_catalog else "sitemap"


def state_of(row: dict) -> str:
    if row["status"] == 0 or row["status"] >= 400:
        return "dead"
    return "redirect" if row["hop_count"] else "ok"


def crosstab(probes: list[dict]) -> dict:
    cells = {side: {state: {"count": 0, "samples": []} for state, _ in STATE_LABELS}
             for side, _ in SIDE_LABELS}
    for row in probes:
        cell = cells[side_of(row)][state_of(row)]
        cell["count"] += 1
        if len(cell["samples"]) < 3:
            cell["samples"].append(row["url"])
    return {
        "sides": [{"key": key, "label": label} for key, label in SIDE_LABELS],
        "states": [{"key": key, "label": label} for key, label in STATE_LABELS],
        "cells": cells,
        "total": sum(cell["count"] for side in cells.values() for cell in side.values()),
    }


def category_explain() -> list[dict]:
    """缺陷分类的含义（页面表头用一行说明，不写成段落）。"""
    return [
        {"code": "CATALOG_DEAD", "label": reasons.label("CATALOG_DEAD"),
         "rule": "目录有条目且探测末态 4xx 或传输失败"},
        {"code": "ONLY_IN_SITEMAP_DEAD", "label": reasons.label("ONLY_IN_SITEMAP_DEAD"),
         "rule": "仅 sitemap 收录且探测末态 4xx"},
        {"code": "REDIRECT_CHAIN", "label": reasons.label("REDIRECT_CHAIN"),
         "rule": "可达但经过至少一次跳转"},
        {"code": "DUPLICATE_SLUG", "label": reasons.label("DUPLICATE_SLUG"),
         "rule": "同站多条原始条目规范化后同址"},
        {"code": "ONLY_IN_CATALOG", "label": reasons.label("ONLY_IN_CATALOG"),
         "rule": "目录有条目但 sitemap 未收录"},
        {"code": "ONLY_IN_SITEMAP_ALIVE", "label": reasons.label("ONLY_IN_SITEMAP_ALIVE"),
         "rule": "sitemap 收录但目录未登记"},
        {"code": "CANONICAL_MISMATCH", "label": reasons.label("CANONICAL_MISMATCH"),
         "rule": "双侧都有且可达，但原始地址含跟踪参数、片段或大小写差异"},
    ]


def site_breakdown(probes: list[dict]) -> list[dict]:
    sites: dict[str, dict] = {}
    for row in probes:
        slot = sites.setdefault(row["site"], {"site": row["site"], "total": 0,
                                             "ok": 0, "findings": 0, "dead": 0})
        slot["total"] += 1
        slot["findings"] += 0 if row["category"] == "OK" else 1
        slot["dead"] += 1 if state_of(row) == "dead" else 0
        slot["ok"] += 1 if row["category"] == "OK" else 0
    return [sites[key] for key in sorted(sites)]
