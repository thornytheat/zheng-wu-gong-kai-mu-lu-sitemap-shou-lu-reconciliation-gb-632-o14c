"""M4 编排：把四账、交叉表、站点分布合成一份对账结果。

对账不重算规则，只汇总 M2 的 key 与 M3 的分类；四账不平时整批标为失败，
不允许「数字对不上但页面照常」。
"""
from __future__ import annotations

import time

from ... import manifest
from . import compare, totals


def accounts_only(keys: list[dict], probes: list[dict]) -> dict:
    """只算四账，不做交叉表：部分完成（停在探测阶段）时也给出可核对的数字。"""
    catalog_rows = sum(len(k["catalog"]) for k in keys)
    sitemap_rows = sum(len(k["sitemap"]) for k in keys)
    return totals.accounts(keys, probes, catalog_rows, sitemap_rows)


def reconcile_stage(keys: list[dict], probes: list[dict], crawl: dict) -> dict:
    started = time.monotonic()
    accounts = accounts_only(keys, probes)
    table = compare.crosstab(probes)
    sites = compare.site_breakdown(probes)
    elapsed = int((time.monotonic() - started) * 1000)
    status = "done" if accounts["all_balanced"] else "failed"
    note = totals.coverage_note(accounts)
    stage = manifest.stage("reconcile", accounts["probed"], accounts["findings_total"],
                           accounts["dead"], status, elapsed, note)
    return {"accounts": accounts, "crosstab": table, "by_site": sites,
            "explain": compare.category_explain(), "stage": stage,
            "note": note, "all_balanced": accounts["all_balanced"]}
