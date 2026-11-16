"""M2 URL 规则：规范化 7 步、旧属性映射、越界过滤。"""
from __future__ import annotations

import pytest

from app.modules.m2_url import contract, normalize, scope
from app.modules.m2_url import service as url_service
from fixtures.expected import (CASE_TRACKING_URL, LEGACY_CODE, LEGACY_ATTR_SCHEME,
                               UNION_KEYS)


def test_all_rewrites_together():
    norm = normalize.normalize(
        "HTTP://WWW.HZ.GOV.CN:80/site-a/Notice/N-2024-003/"
        "?utm_source=weixin&sessionid=x#top")
    assert norm.url == "http://www.hz.gov.cn/site-a/notice/n-2024-003"
    assert set(norm.notes) == {"case", "default_port", "trailing_slash",
                              "tracking", "fragment"}
    assert norm.changed is True


def test_query_parameters_sorted():
    norm = normalize.normalize("http://www.hz.gov.cn/site-a/x?b=2&a=1")
    assert norm.url == "http://www.hz.gov.cn/site-a/x?a=1&b=2"
    assert "param_order" in norm.notes


def test_relative_path_resolved_against_page():
    norm = normalize.normalize("notice/n-2024-001",
                              "http://www.hz.gov.cn/site-a/catalog.html")
    assert norm.url == "http://www.hz.gov.cn/site-a/notice/n-2024-001"
    assert norm.notes == ("relative",)


def test_script_scheme_rejected():
    with pytest.raises(ValueError):
        normalize.normalize("javascript:void(0)")
    with pytest.raises(ValueError):
        normalize.normalize("mailto:edit@hz.gov.cn")


def test_normalize_is_idempotent():
    first = normalize.normalize("HTTP://WWW.HZ.GOV.CN/site-a/Notice/X/?utm_source=a#f")
    second = normalize.normalize(first.url)
    assert second.url == first.url
    assert second.notes == ()


def test_legacy_attributes_mapped():
    """TRAP-17：老目录页属性名映射到契约字段，旧站不迁移也能采信。"""
    fields, scheme = contract.map_attrs({"data-bh": "0081001", "data-bm": "B01",
                                        "data-bt": "清单"})
    assert scheme == "legacy"
    assert fields == {"entry_code": "0081001", "dept_code": "B01", "title": "清单"}
    current, scheme2 = contract.map_attrs({"data-code": "0070012", "data-dept": "A01"})
    assert scheme2 == "current"
    assert current["entry_code"] == "0070012"
    assert contract.map_attrs({"class": "x"})[1] == "none"


def test_legacy_scheme_reaches_entries(run):
    entry = next(row for row in run["entries"] if row["site"] == "site-b")
    assert entry["attr_scheme"] == LEGACY_ATTR_SCHEME
    assert entry["entry_code"] == LEGACY_CODE
    assert entry["page_url"].endswith("/site-b/catalog.html")


def test_scope_uses_host_list():
    assert scope.site_of("http://www.hz.gov.cn/site-a/x") == "site-a"
    assert scope.site_of("http://fgw.hz.gov.cn/site-c/x") == "site-c"
    assert scope.in_scope("https://zwfw.hz.gov.cn/site-b/x") is True
    assert scope.in_scope("http://zwfw.other.gov.cn/site-b/x") is False


def test_offsite_rows_quarantined(run):
    codes = [row["reason"] for row in run["quarantine"]]
    assert "SCOPE_OFFSITE" in codes
    assert "LOC_OFFSITE" in codes
    offsite = next(row for row in run["quarantine"] if row["reason"] == "SCOPE_OFFSITE")
    assert offsite["source"] == "catalog"
    assert "other.gov.cn" in offsite["excerpt"]


def test_raw_forms_merged_into_one_key(run):
    slot = next(row for row in run["keys"] if row["key"] == CASE_TRACKING_URL)
    assert len(slot["catalog"]) == 1
    assert slot["catalog"][0]["raw_href"].endswith("?utm_source=weixin&sessionid=abc123")
    assert "case" in slot["notes"] and "tracking" in slot["notes"]
    assert slot["site"] == "site-a"


def test_prepare_keeps_both_sides(run):
    prepared = url_service.prepare(run["catalog"], run["sitemap"])
    both = [row for row in prepared["keys"] if row["catalog"] and row["sitemap"]]
    assert len(both) == 8
    assert prepared["key_count"] == UNION_KEYS


def test_empty_query_value_kept_unless_tracking():
    """边界：空值参数保留，只有跟踪参数名才丢；空值不等于跟踪参数。"""
    kept = normalize.normalize("http://www.hz.gov.cn/site-a/x?keep=")
    assert kept.url == "http://www.hz.gov.cn/site-a/x?keep="
    assert "tracking" not in kept.notes
    dropped = normalize.normalize("http://www.hz.gov.cn/site-a/x?utm_source=&keep=")
    assert dropped.url == "http://www.hz.gov.cn/site-a/x?keep="
    assert "tracking" in dropped.notes
