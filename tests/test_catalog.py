"""M1 目录采信：编码回退、BOM、块残缺、重复 loc、截断、空态三态。

每条断言都用样例站的真实字节，不用构造的理想数据。
"""
from __future__ import annotations

import pathlib

import pytest

from app import manifest
from app.modules.m1_catalog import decode, extract
from app.modules.m1_catalog import service as crawl_service
from fixtures.expected import (
    SITE_A_PAGE1_ENTRIES, SITE_A_PAGE2_ENTRIES, SITE_C_ENTRIES,
    CONFLICT_DROPPED, CONFLICT_KEPT, BLOCK_NO_LOC_ROW, LEADING_ZERO_CODE,
    RESOURCES,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEGENERATE = ROOT / "sample_data" / "degenerate"


def test_bom_stripped_and_line_numbers_kept():
    """TRAP-02：UTF-8 BOM 不剥掉，首行取到的锚点属性会带 \\ufeff。"""
    body = (DEGENERATE / "catalog_bom_crlf.html").read_bytes()
    decoded = decode.decode_body(body, {"content-type": "text/html; charset=utf-8"})
    assert not decoded.text.startswith("\ufeff")
    assert decoded.encoding == "utf-8-sig"
    page = extract.parse_catalog(decoded.text)
    assert len(page.entries) == 2
    assert page.entries[0].line_no == 9
    assert page.entries[0].raw_href == "notice/n-2024-001"


def test_gb18030_fallback_through_wrong_header():
    """TRAP-01：响应头声明 utf-8，字节是 GB18030，必须走回退链。"""
    body = (ROOT / "sample_site" / "site-b" / "catalog.html").read_bytes()
    decoded = decode.decode_body(body, {"content-type": "text/html; charset=utf-8"})
    assert decoded.encoding == "gb18030"
    assert decoded.fallback is True
    assert decoded.declared == "utf-8"
    assert "政务服务" in decoded.text


def test_naive_utf8_decode_fails_on_site_b():
    """反例：朴素实现按声明编码硬解会直接抛错，本项目通过。"""
    body = (ROOT / "sample_site" / "site-b" / "catalog.html").read_bytes()
    with pytest.raises(UnicodeDecodeError):
        body.decode("utf-8")
    decoded = decode.decode_body(body, {"content-type": "text/html; charset=utf-8"})
    assert decoded.text.count("行政许可事项清单") == 2


def test_catalog_region_excludes_navigation(run):
    page = next(p for p in run["pages"] if p["url"].endswith("/site-a/catalog.html"))
    assert page["entries"] == SITE_A_PAGE1_ENTRIES
    hrefs = {row["raw_href"] for row in run["entries"] if row["page_url"] == page["url"]}
    assert "/site-b/catalog.html" not in hrefs      # 导航链接
    assert "catalog_p2.html" not in hrefs           # 下一页链接
    pages = [p for p in run["pages"] if p["site"] == "site-a"]
    assert len(pages) == 2
    assert pages[1]["entries"] == SITE_A_PAGE2_ENTRIES


def test_quarantine_reason_codes(run):
    """TRAP-05：缺 loc 的 url 块、无地址的目录行、脚本地址都要进隔离区。"""
    codes = [row["reason"] for row in run["quarantine"]]
    assert codes.count("BLOCK_NO_LOC") == 1
    assert "CATALOG_ROW_NO_HREF" in codes
    assert "CATALOG_ROW_SCRIPT" in codes
    assert "CATALOG_ROW_FRAGMENT" in codes
    block = next(row for row in run["quarantine"] if row["reason"] == "BLOCK_NO_LOC")
    assert block["row_no"] == BLOCK_NO_LOC_ROW
    assert block["level"] == "error"


def test_truncated_sitemap_keeps_parsed_blocks(run):
    """TRAP-16：site-b 的 sitemap 缺 </urlset>，已解析的块保留并标记截断。"""
    site_b = [row["reason"] for row in run["quarantine"] if row["site"] == "site-b"]
    assert site_b == ["SITEMAP_TRUNCATED"]
    kept = [row for row in run["sitemap"] if row["site"] == "site-b"]
    assert len(kept) == 3
    assert kept[2]["relative"] is True


def test_duplicate_loc_conflict_keeps_newer_lastmod(run):
    """TRAP-14：同一 loc 出现两次且 lastmod 不同，保留较新一条并入冲突表。"""
    assert len(run["conflicts"]) == 1
    conflict = run["conflicts"][0]
    assert conflict["reason"] == "DUP_LOC_CONFLICT"
    assert conflict["kept"] == CONFLICT_KEPT
    assert conflict["dropped"] == CONFLICT_DROPPED
    assert conflict["rule"] == "同址保留较新 lastmod"


@pytest.mark.parametrize("filename,reason", [
    ("sitemap_zero_bytes.xml", "SITEMAP_EMPTY_BODY"),
    ("sitemap_header_only.xml", "SITEMAP_HEADER_ONLY"),
    ("sitemap_empty.xml", "EMPTY_SITEMAP"),
])
def test_empty_sitemap_three_states(stub_cls, settings, filename, reason):
    """TRAP-18：0 字节 / 仅声明 / 有 urlset 无 url 是三种不同结论。"""
    body = (DEGENERATE / filename).read_bytes()
    out = crawl_service.crawl_stage(settings, stub_cls(body), ["site-a"])
    codes = [row["reason"] for row in out["quarantine"]]
    assert reason in codes
    assert out["sitemap"] == []


def test_truncated_degenerate_sample(stub_cls, settings):
    body = (DEGENERATE / "sitemap_truncated.xml").read_bytes()
    out = crawl_service.crawl_stage(settings, stub_cls(body), ["site-a"])
    codes = [row["reason"] for row in out["quarantine"]]
    assert "SITEMAP_TRUNCATED" in codes
    assert len(out["sitemap"]) == 2


def test_resources_and_input_digest(run):
    assert len(run["resources"]) == RESOURCES
    assert all(row["status"] == 200 for row in run["resources"])
    assert all(len(row["sha256"]) == 64 for row in run["resources"])
    assert run["input_digest"] == manifest.digest_of(run["resources"])


def test_leading_zero_entry_code_kept(run):
    """TRAP-08：事项编码含前导零，按字符串保形，禁止过 int()。"""
    codes = [row["entry_code"] for row in run["entries"] if row["site"] == "site-a"]
    assert LEADING_ZERO_CODE in codes
    assert all(isinstance(code, str) for code in codes if code)
    assert next(row for row in run["entries"]
                if row["entry_code"] == LEADING_ZERO_CODE)["dept_code"] == "A01"


def test_site_c_single_page_entries(run):
    page = next(p for p in run["pages"] if p["site"] == "site-c")
    assert page["entries"] == SITE_C_ENTRIES
    assert page["encoding"] == "utf-8"


def test_sitemap_with_only_declaration_is_header_only(stub_cls, settings):
    """边界：只有 XML 声明、没有 urlset 的 sitemap 记「仅声明」，不当作 0 条成功。"""
    out = crawl_service.crawl_stage(
        settings, stub_cls(b"<?xml version='1.0' encoding='UTF-8'?>"), ["site-a"])
    codes = [row["reason"] for row in out["quarantine"]]
    assert "SITEMAP_HEADER_ONLY" in codes
    assert out["sitemap"] == []
