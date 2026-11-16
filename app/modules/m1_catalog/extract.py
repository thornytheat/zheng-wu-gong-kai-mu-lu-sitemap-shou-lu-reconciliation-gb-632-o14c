"""结构解析：目录页锚点（带原始行号）与 sitemap 的 url 块。

只做结构，不做业务归一（规范化是 M2 的事）：
- 目录条目只取 `data-role="catalog"` 区块内的锚点，导航/页脚链接不算条目；
- 锚点的行号来自 HTMLParser.getpos()，导出时能回到原页行；
- sitemap 按 `<url>` 块切，缺 loc 的块进隔离区，尾部未闭合视为截断。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

_WS_RE = re.compile(r"[\s\u00a0\u3000]+")
_URL_BLOCK_RE = re.compile(r"<url>(.*?)</url>", re.S | re.I)
_LOC_RE = re.compile(r"<loc>(.*?)</loc>", re.S | re.I)
_LASTMOD_RE = re.compile(r"<lastmod>(.*?)</lastmod>", re.S | re.I)
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)


def collapse(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


@dataclass
class CatalogEntry:
    line_no: int
    raw_href: str
    raw_text: str
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class CatalogPage:
    entries: list[CatalogEntry]
    next_href: str | None
    title: str
    catalog_region: bool
    declared_rows: int | None


class _CatalogParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[CatalogEntry] = []
        self.next_href: str | None = None
        self.title = ""
        self.catalog_region = False
        self.declared_rows: int | None = None
        self._depth_in_region = 0
        self._anchor: dict | None = None
        self._text_buf: list[str] = []
        self._in_title = False
        self._title_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        amap = {k.lower(): (v or "") for k, v in attrs}
        if amap.get("data-role") == "catalog":
            self.catalog_region = True
            self._depth_in_region = 0
        if self.catalog_region:
            self._depth_in_region += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            classes = amap.get("class", "")
            if "next" in classes.split() and self.next_href is None:
                self.next_href = amap.get("href") or None
            if self.catalog_region:
                self._anchor = {"attrs": amap, "line": self.getpos()[0]}
                self._text_buf = []
        if amap.get("data-declared-rows"):
            digits = re.sub(r"\D", "", amap["data-declared-rows"])
            self.declared_rows = int(digits) if digits else None

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor is not None:
            self.entries.append(CatalogEntry(
                line_no=int(self._anchor["line"]),
                raw_href=self._anchor["attrs"].get("href", ""),
                raw_text=collapse("".join(self._text_buf)),
                attrs=self._anchor["attrs"],
            ))
            self._anchor = None
            self._text_buf = []
        if tag == "title":
            self._in_title = False
            self.title = collapse("".join(self._title_buf))
        if self.catalog_region:
            self._depth_in_region -= 1
            if self._depth_in_region <= 0:
                self.catalog_region = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_buf.append(data)
        if self._anchor is not None:
            self._text_buf.append(data)


def parse_catalog(text: str) -> CatalogPage:
    parser = _CatalogParser()
    parser.feed(text)
    parser.close()
    title = parser.title
    if not title:
        match = _TITLE_RE.search(text)
        title = collapse(match.group(1)) if match else ""
    return CatalogPage(entries=parser.entries, next_href=parser.next_href,
                       title=title, catalog_region=parser.catalog_region,
                       declared_rows=parser.declared_rows)


@dataclass
class SitemapBlock:
    row_no: int
    loc: str
    lastmod: str


@dataclass
class SitemapDoc:
    blocks: list[SitemapBlock]
    dropped: list[dict]
    truncated: bool
    has_urlset: bool
    closed: bool
    total_blocks: int


def parse_sitemap(text: str) -> SitemapDoc:
    total = len(_URL_BLOCK_RE.findall(text))
    truncated = False
    has_urlset = "<urlset" in text.lower()
    closed = "</urlset>" in text.lower()
    if has_urlset and not closed:
        truncated = True
    # 尾部未闭合的 <url> 块：有开头没有结尾
    tail_parts = text.lower().rsplit("<url>", 1)
    if len(tail_parts) == 2 and "</url>" not in tail_parts[1]:
        truncated = True
    blocks: list[SitemapBlock] = []
    dropped: list[dict] = []
    for index, body in enumerate(_URL_BLOCK_RE.findall(text), 1):
        loc_match = _LOC_RE.search(body)
        lastmod_match = _LASTMOD_RE.search(body)
        lastmod = collapse(lastmod_match.group(1)) if lastmod_match else ""
        if not loc_match:
            dropped.append({"row_no": index, "reason": "BLOCK_NO_LOC",
                            "excerpt": collapse(body)[:80]})
            continue
        loc = collapse(loc_match.group(1))
        if not loc:
            dropped.append({"row_no": index, "reason": "BLOCK_NO_LOC",
                            "excerpt": collapse(body)[:80]})
            continue
        blocks.append(SitemapBlock(row_no=index, loc=loc, lastmod=lastmod))
    return SitemapDoc(blocks=blocks, dropped=dropped, truncated=truncated,
                      has_urlset=has_urlset, closed=closed, total_blocks=total)
