"""M4 三向对账：四账、交叉表、双向引用、空态。"""
from __future__ import annotations

import pytest

from app.modules.m4_reconcile import totals
from fixtures.expected import (
    ALIVE_OK, ALIVE_REDIRECT, BOTH, BY_CATEGORY, CATALOG_KEYS, CATALOG_ROWS,
    COVERAGE, DEAD, FINDINGS, ONLY_IN_CATALOG, ONLY_IN_SITEMAP, PROBED,
    SITEMAP_KEYS, SITEMAP_ROWS, THREE_WAY,
)


def test_four_accounts_match_sample_site(run):
    accounts = run["totals"]
    assert accounts["catalog_rows"] == CATALOG_ROWS
    assert accounts["catalog_keys"] == CATALOG_KEYS
    assert accounts["sitemap_rows"] == SITEMAP_ROWS
    assert accounts["sitemap_keys"] == SITEMAP_KEYS
    assert accounts["probed"] == PROBED
    assert accounts["findings_total"] == FINDINGS
    assert accounts["coverage"] == COVERAGE
    assert accounts["all_balanced"] is True


def test_category_partition_is_exhaustive(run):
    """不变量：各分类之和 = 缺陷总数，且分类表里的站点真实存在。"""
    accounts = run["totals"]
    assert accounts["by_category"] == BY_CATEGORY
    assert sum(accounts["by_category"].values()) == accounts["findings_total"]
    assert accounts["findings_total"] == len(run["defects"])


def test_status_partition_covers_all_probes(run):
    accounts = run["totals"]
    assert accounts["alive_ok"] == ALIVE_OK
    assert accounts["alive_redirect"] == ALIVE_REDIRECT
    assert accounts["dead"] == DEAD
    assert accounts["alive_ok"] + accounts["alive_redirect"] + accounts["dead"] == PROBED


def test_catalog_sitemap_split(run):
    accounts = run["totals"]
    assert accounts["both"] == BOTH
    assert accounts["only_in_catalog"] == ONLY_IN_CATALOG
    assert accounts["only_in_sitemap"] == ONLY_IN_SITEMAP
    assert accounts["catalog_keys"] == accounts["both"] + accounts["only_in_catalog"]
    assert accounts["sitemap_keys"] == accounts["both"] + accounts["only_in_sitemap"]


def test_both_directions_reported(run):
    """TRAP-21：只查单向会漏半边，漏收录与仅收录死链必须同时出现。"""
    by_category = run["totals"]["by_category"]
    assert by_category["ONLY_IN_CATALOG"] == 2
    assert by_category["ONLY_IN_SITEMAP_DEAD"] == 1
    assert by_category["ONLY_IN_SITEMAP_ALIVE"] == 5


def test_crosstab_sums_to_probes(run):
    table = run["crosstab"]
    assert table["total"] == PROBED
    cell_sum = sum(cell["count"] for side in table["cells"].values() for cell in side.values())
    assert cell_sum == PROBED
    assert table["cells"]["both"]["ok"]["count"] == THREE_WAY
    assert table["cells"]["catalog"]["dead"]["count"] == 3
    assert table["cells"]["sitemap"]["dead"]["count"] == 1


def test_accounts_without_probes_stay_zero():
    accounts = totals.accounts([], [], 0, 0)
    assert accounts["coverage"] == "0.0000"
    assert accounts["findings_total"] == 0
    assert accounts["probed"] == 0
    assert accounts["all_balanced"] is True


def test_site_breakdown_covers_three_sites(run):
    rows = run["by_site"]
    assert {row["site"] for row in rows} == {"site-a", "site-b", "site-c"}
    assert sum(row["total"] for row in rows) == PROBED
    assert sum(row["findings"] for row in rows) == FINDINGS


def test_reconcile_api_payload(client_with_run):
    body = client_with_run.get("/api/reconcile").json()
    assert body["status"] == "done"
    assert body["accounts"]["all_balanced"] is True
    assert body["crosstab"]["total"] == PROBED
    assert len(body["explain"]) == 7
    assert body["defects"]
