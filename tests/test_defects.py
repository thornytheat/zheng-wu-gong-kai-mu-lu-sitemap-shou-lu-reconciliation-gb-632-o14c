"""M6 缺陷单：编号、排序、CSV、清单导出与筛选。"""
from __future__ import annotations

import json

import pytest

from app import errors
from app.modules.m6_defects import service as defect_service
from fixtures.expected import BY_CATEGORY, FINDINGS


def test_defect_numbers_are_sequential(run):
    defects = run["defects"]
    assert len(defects) == FINDINGS
    assert [row["defect_no"] for row in defects] == [
        f"DF-{index:04d}" for index in range(1, FINDINGS + 1)]


def test_defects_sorted_by_priority(run):
    defects = run["defects"]
    priorities = [row["priority"] for row in defects]
    assert priorities == sorted(priorities)
    assert defects[0]["category"] == "CATALOG_DEAD"
    assert defects[0]["in_catalog"] == 1


def test_csv_header_and_bom(run):
    text = defect_service.defects_csv(run)
    assert text.startswith("\ufeff")
    header = text.lstrip("\ufeff").splitlines()[0]
    assert header.split(",")[:4] == ["缺陷号", "站点", "分类", "严重度"]
    assert header.split(",")[-1] == "原始写法"


def test_csv_rows_follow_filter(run):
    text = defect_service.defects_csv(run, category="CATALOG_DEAD")
    lines = text.lstrip("\ufeff").splitlines()
    assert len(lines) == 1 + BY_CATEGORY["CATALOG_DEAD"]
    assert "目录死链" in lines[1]


def test_csv_matches_defect_list(run):
    text = defect_service.defects_csv(run)
    lines = text.lstrip("\ufeff").splitlines()
    assert len(lines) == 1 + FINDINGS
    assert run["defects"][0]["defect_no"] in lines[1]


def test_filter_by_category_and_site(run):
    by_category = defect_service.list_defects(run, category="REDIRECT_CHAIN")
    assert by_category["count"] == 4
    assert by_category["summary"]["by_category"] == {"REDIRECT_CHAIN": 4}
    by_site = defect_service.list_defects(run, site="site-b")
    assert by_site["count"] == 4
    both = defect_service.list_defects(run, site="site-a", category="CATALOG_DEAD")
    assert both["count"] == 2


def test_unknown_category_rejected(run):
    with pytest.raises(errors.BadRequest):
        defect_service.list_defects(run, category="NOPE")


def test_manifest_export_fields(run):
    doc = json.loads(defect_service.manifest_json(run))
    assert doc["run_id"] == run["run_id"]
    assert doc["rule_version"] == "sitemapaudit/1.0.0"
    assert doc["totals"]["findings_total"] == FINDINGS
    assert doc["stage_state"]["done"] == ["crawl", "probe", "reconcile"]


def test_defects_api_and_csv_download(client_with_run):
    body = client_with_run.get("/api/defects").json()
    assert body["count"] == FINDINGS
    assert body["categories"]["CATALOG_DEAD"] == "目录死链"
    csv_response = client_with_run.get("/api/defects.csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert csv_response.text.count("\r\n") == 1 + FINDINGS
    assert "attachment" in csv_response.headers["content-disposition"]


def test_quarantine_csv_export(client_with_run):
    response = client_with_run.get("/api/quarantine.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.lstrip("\ufeff").splitlines()
    assert lines[0].split(",") == ["站点", "来源", "行号", "原因码", "原因", "级别", "原文"]
    assert any("BLOCK_NO_LOC" in line for line in lines[1:])
    only_site_b = client_with_run.get("/api/quarantine.csv?site=site-b")
    assert len(only_site_b.text.lstrip("\ufeff").splitlines()) == 2


def test_defect_page_and_manifest_download(client_with_run):
    page = client_with_run.get("/defects")
    assert page.status_code == 200
    assert "DF-0001" in page.text
    manifest_response = client_with_run.get("/api/export/manifest.json")
    assert manifest_response.status_code == 200
    assert manifest_response.json()["totals"]["findings_total"] == FINDINGS


def test_summary_totals_match_defect_rows(run):
    """不变量：分类合计 = 站点合计 = 缺陷条数，页面、CSV、清单读数一致。"""
    summary = defect_service.summarize(run["defects"])
    assert summary["total"] == FINDINGS
    assert sum(summary["by_category"].values()) == FINDINGS
    assert sum(summary["by_site"].values()) == FINDINGS
    assert summary["by_category"] == BY_CATEGORY
