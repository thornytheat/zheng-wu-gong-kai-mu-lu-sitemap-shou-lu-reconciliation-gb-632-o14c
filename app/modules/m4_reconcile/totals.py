"""四账与覆盖率：所有对外数字只从这里出。

四账定义（docs/DATA-DICTIONARY.md 同款）：
1. 目录账  catalog_keys = both + only_in_catalog
2. 收录账  sitemap_keys = both + only_in_sitemap
3. 可达账  probed = ok + redirect + dead
4. 缺陷账  findings_total = Σ 各分类条数
覆盖率 = 三向交集 / 目录条目数，四位小数，用 Decimal 算，不用 float。
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from ... import config, reasons


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-config.COVERAGE_QUANT), rounding=ROUND_HALF_UP)


def buckets(probes: list[dict]) -> dict[str, int]:
    ok = dead = redirect = 0
    for row in probes:
        if row["status"] == 0 or row["status"] >= 400:
            dead += 1
        elif row["hop_count"]:
            redirect += 1
        else:
            ok += 1
    return {"ok": ok, "redirect": redirect, "dead": dead}


def category_counts(probes: list[dict]) -> dict[str, int]:
    counts = {code: 0 for code in reasons.DEFECT_CATEGORIES}
    for row in probes:
        if row["category"] in counts:
            counts[row["category"]] += 1
    return counts


def accounts(keys: list[dict], probes: list[dict], catalog_rows: int,
             sitemap_rows: int) -> dict:
    catalog_keys = sum(1 for k in keys if k["catalog"])
    sitemap_keys = sum(1 for k in keys if k["sitemap"])
    both = sum(1 for k in keys if k["catalog"] and k["sitemap"])
    only_catalog = catalog_keys - both
    only_sitemap = sitemap_keys - both
    status_counts = buckets(probes)
    per_category = category_counts(probes)
    findings_total = sum(per_category.values())
    three_way = sum(1 for row in probes
                    if row["in_catalog"] and row["in_sitemap"]
                    and row["status"] == 200 and not row["hop_count"])
    coverage = _q(Decimal(three_way) / Decimal(catalog_keys)) if catalog_keys else Decimal("0.0000")

    checks = {
        "catalog": catalog_keys == both + only_catalog,
        "sitemap": sitemap_keys == both + only_sitemap,
        "probe": len(probes) == status_counts["ok"] + status_counts["redirect"]
        + status_counts["dead"],
        "findings": findings_total == len(probes) - sum(
            1 for row in probes if row["category"] == "OK"),
        "entries": catalog_rows >= catalog_keys and sitemap_rows >= sitemap_keys,
    }
    return {
        "catalog_rows": catalog_rows,
        "catalog_keys": catalog_keys,
        "sitemap_rows": sitemap_rows,
        "sitemap_keys": sitemap_keys,
        "both": both,
        "only_in_catalog": only_catalog,
        "only_in_sitemap": only_sitemap,
        "probed": len(probes),
        "alive_ok": status_counts["ok"],
        "alive_redirect": status_counts["redirect"],
        "dead": status_counts["dead"],
        "three_way": three_way,
        "coverage": str(coverage),
        "findings_total": findings_total,
        "by_category": per_category,
        "category_labels": {code: reasons.label(code) for code in reasons.CATEGORY_ORDER},
        "checks": checks,
        "all_balanced": all(checks.values()),
    }


def coverage_note(totals: dict) -> str:
    return (f"目录 {totals['catalog_keys']} · 收录 {totals['sitemap_keys']} · "
            f"交集 {totals['both']} · 缺陷 {totals['findings_total']}")
