"""M1 编排：按站点取 sitemap 与目录页，逐条目留行号，坏块进隔离区。

采信阶段的四条硬规则（都在 tests/test_catalog.py 里钉死）：
1. 编码按回退链解，声明失真时继续回退，不允许静默吞半页；
2. url 块缺 loc 一律不进条目，进隔离区并给行号；
3. 同一 sitemap 里 loc 完全重复时，lastmod 相同保留首条；lastmod 不同入冲突表，
   保留较新一条（字符串比较到秒，ISO 8601 可直接比）；
4. sitemap 尾部缺 </urlset> 判截断：已解析的块保留，但整站标记不完整。
"""
from __future__ import annotations

import time
from urllib.parse import urljoin

from ... import config, manifest, reasons
from . import decode, extract, fetch


def _site_url(site: config.Site, path: str) -> str:
    return f"http://{site.host}{path}"


def _record(resources: list[dict], fetched: fetch.Fetched) -> None:
    resources.append({"url": fetched.url, "status": fetched.status,
                      "bytes": fetched.size,
                      "sha256": manifest.sha256_bytes(fetched.body),
                      "error": fetched.error or ""})


def _quarantine(rows: list[dict], site_code: str, source: str, row_no: int,
                reason: str, excerpt: str) -> None:
    rows.append({"site": site_code, "source": source, "row_no": row_no,
                 "reason": reason, "excerpt": excerpt[:100],
                 "level": reasons.level(reason), "label": reasons.label(reason)})


def _read_sitemap(settings: config.Settings, fetcher, site: config.Site,
                  out: dict) -> None:
    url = _site_url(site, site.sitemap_path)
    fetched = fetcher.get(url)
    _record(out["resources"], fetched)
    if fetched.status == 0:
        _quarantine(out["quarantine"], site.code, "sitemap", 0, "PROBE_ERROR",
                    fetched.error or "")
        return
    if fetched.status != 200:
        _quarantine(out["quarantine"], site.code, "sitemap", 0, "SITEMAP_MISSING",
                    f"{url} → {fetched.status}")
        return
    if not fetched.body:
        _quarantine(out["quarantine"], site.code, "sitemap", 0, "SITEMAP_EMPTY_BODY", url)
        return
    decoded = decode.decode_body(fetched.body, fetched.headers)
    if decoded.reason == "CHARSET_UNKNOWN":
        _quarantine(out["quarantine"], site.code, "sitemap", 0, "CHARSET_UNKNOWN", url)
        return
    if decoded.fallback:
        out["notes"].append({"site": site.code, "code": "CHARSET_FALLBACK",
                             "detail": f"sitemap {decoded.encoding}"})
    doc = extract.parse_sitemap(decoded.text)
    if not doc.has_urlset:
        _quarantine(out["quarantine"], site.code, "sitemap", 0,
                    "SITEMAP_HEADER_ONLY" if doc.total_blocks == 0 else "SITEMAP_TRUNCATED",
                    url)
        if doc.total_blocks == 0:
            return
    if doc.has_urlset and doc.closed and doc.total_blocks == 0:
        _quarantine(out["quarantine"], site.code, "sitemap", 0, "EMPTY_SITEMAP", url)
        return
    if doc.truncated:
        _quarantine(out["quarantine"], site.code, "sitemap", 0, "SITEMAP_TRUNCATED",
                    f"{url} 块数 {doc.total_blocks}")

    for dropped in doc.dropped:
        _quarantine(out["quarantine"], site.code, "sitemap", dropped["row_no"],
                    dropped["reason"], dropped["excerpt"])

    seen: dict[str, dict] = {}
    for block in doc.blocks:
        lastmod = block.lastmod
        kept = seen.get(block.loc)
        if kept is not None:
            if lastmod and kept["raw_lastmod"] and lastmod != kept["raw_lastmod"]:
                newer = max(lastmod, kept["raw_lastmod"])
                older = min(lastmod, kept["raw_lastmod"])
                out["conflicts"].append({
                    "site": site.code, "field": "lastmod", "raw_loc": block.loc,
                    "kept": newer, "dropped": older, "reason": "DUP_LOC_CONFLICT",
                    "label": reasons.label("DUP_LOC_CONFLICT"),
                    "rule": "同址保留较新 lastmod",
                })
                if newer != kept["raw_lastmod"]:
                    kept["raw_lastmod"] = newer
                    kept["row_no"] = block.row_no
            else:
                out["notes"].append({"site": site.code, "code": "DUP_LOC_SAME",
                                     "detail": block.loc})
            continue
        row = {"site": site.code, "source_url": url, "row_no": block.row_no,
               "raw_loc": block.loc, "raw_lastmod": lastmod,
               "relative": not block.loc.lower().startswith(("http://", "https://"))}
        seen[block.loc] = row
        out["sitemap"].append(row)


def _read_catalog(settings: config.Settings, fetcher, site: config.Site,
                  out: dict) -> None:
    page_url = _site_url(site, site.catalog_path)
    pages_seen = 0
    while page_url and pages_seen < config.MAX_CATALOG_PAGES:
        fetched = fetcher.get(page_url)
        _record(out["resources"], fetched)
        if fetched.status != 200:
            _quarantine(out["quarantine"], site.code, "catalog", 0, "CATALOG_PAGE_FAILED",
                        f"{page_url} → {fetched.status}")
            return
        decoded = decode.decode_body(fetched.body, fetched.headers)
        if decoded.reason == "CHARSET_UNKNOWN":
            _quarantine(out["quarantine"], site.code, "catalog", 0, "CHARSET_UNKNOWN", page_url)
            return
        if decoded.fallback:
            out["notes"].append({"site": site.code, "code": "CHARSET_FALLBACK",
                                 "detail": f"目录页 {decoded.encoding}"})
        page = extract.parse_catalog(decoded.text)
        pages_seen += 1
        out["pages"].append({"site": site.code, "url": page_url,
                             "entries": len(page.entries), "title": page.title,
                             "encoding": decoded.encoding,
                             "declared_rows": page.declared_rows})
        for entry in page.entries:
            href = entry.raw_href.strip()
            if not href:
                _quarantine(out["quarantine"], site.code, "catalog", entry.line_no,
                            "CATALOG_ROW_NO_HREF", entry.raw_text)
                continue
            lowered = href.lower()
            if lowered.startswith(config.SCRIPT_SCHEMES):
                _quarantine(out["quarantine"], site.code, "catalog", entry.line_no,
                            "CATALOG_ROW_SCRIPT", href[:80])
                continue
            if href.startswith("#"):
                _quarantine(out["quarantine"], site.code, "catalog", entry.line_no,
                            "CATALOG_ROW_FRAGMENT", href[:80])
                continue
            if not entry.raw_text:
                out["notes"].append({"site": site.code, "code": "CATALOG_ROW_EMPTY_TEXT",
                                     "detail": f"行 {entry.line_no} {href[:60]}"})
            out["catalog"].append({
                "site": site.code, "page_url": page_url, "page_no": pages_seen,
                "line_no": entry.line_no, "raw_href": href,
                "raw_text": entry.raw_text, "attrs": entry.attrs,
            })
        page_url = urljoin(page_url, page.next_href) if page.next_href else None


def crawl_stage(settings: config.Settings, fetcher, sites: list[str] | None = None) -> dict:
    started = time.monotonic()
    site_codes = sites or list(config.SITE_CODES)
    out = {"resources": [], "catalog": [], "sitemap": [], "quarantine": [],
           "conflicts": [], "notes": [], "pages": [], "sites": site_codes}
    for code in site_codes:
        site = config.SITE_BY_CODE[code]
        _read_sitemap(settings, fetcher, site, out)
        _read_catalog(settings, fetcher, site, out)
    elapsed = int((time.monotonic() - started) * 1000)
    kept = len(out["catalog"]) + len(out["sitemap"])
    out["stage"] = manifest.stage("crawl", len(out["resources"]), kept,
                                  len(out["quarantine"]), "done", elapsed,
                                  f"{len(site_codes)} 站 · {len(out['resources'])} 资源")
    return out
