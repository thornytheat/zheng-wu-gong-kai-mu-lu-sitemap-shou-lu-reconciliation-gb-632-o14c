"""编码探测与回退链：BOM → HTTP 头 → meta 声明 → 严格顺序尝试。

三条真实规则：
1. UTF-8 BOM 必须先剥掉，否则首列名/首个标签带 \\ufeff，后续按名取值全空；
2. 声明可能与实际不符（声明 utf-8、实际 gb18030），声明失败要继续回退；
3. 回退链全部失败要给出明确原因码，不允许用 errors="ignore" 静默吞掉半页。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ... import config, reasons

BOM_UTF8 = b"\xef\xbb\xbf"
BOM_UTF16LE = b"\xff\xfe"
BOM_UTF16BE = b"\xfe\xff"
_META_RE = re.compile(rb"""charset\s*=\s*["']?\s*([a-zA-Z0-9_\-]+)""", re.IGNORECASE)
_XML_DECL_RE = re.compile(rb"""encoding\s*=\s*["']([a-zA-Z0-9_\-]+)["']""", re.IGNORECASE)


@dataclass(frozen=True)
class Decoded:
    text: str
    encoding: str
    declared: str | None
    bom: bool
    fallback: bool
    reason: str | None

    @property
    def stripped_ok(self) -> bool:
        return not self.text.startswith("\ufeff")


def sniff_bom(body: bytes) -> tuple[str, bool]:
    if body.startswith(BOM_UTF8):
        return "utf-8-sig", True
    if body.startswith(BOM_UTF16LE):
        return "utf-16", True
    if body.startswith(BOM_UTF16BE):
        return "utf-16", True
    return "", False


def declared_charset(body: bytes, headers: dict[str, str] | None = None) -> str | None:
    headers = headers or {}
    ctype = headers.get("content-type", "") or ""
    match = re.search(r"charset=([a-zA-Z0-9_\-]+)", ctype, re.IGNORECASE)
    if match:
        return match.group(1)
    head = body[:2048]
    for pattern in (_META_RE, _XML_DECL_RE):
        found = pattern.search(head)
        if found:
            return found.group(1).decode("ascii", "replace")
    return None


def canonical_charset(name: str | None) -> str | None:
    if not name:
        return None
    return config.CHARSET_ALIASES.get(name.strip().lower())


def decode_body(body: bytes, headers: dict[str, str] | None = None) -> Decoded:
    bom_encoding, has_bom = sniff_bom(body)
    declared = declared_charset(body, headers)
    chain: list[str] = []
    if bom_encoding:
        chain.append(bom_encoding)
    mapped = canonical_charset(declared)
    if mapped and mapped not in chain:
        chain.append(mapped)
    for encoding in config.ENCODING_CHAIN:
        if encoding not in chain:
            chain.append(encoding)

    for index, encoding in enumerate(chain):
        try:
            text = body.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        if text.startswith("\ufeff"):
            text = text.lstrip("\ufeff")
        fallback = index > 0 and encoding not in ("utf-8-sig", "utf-8") or (
            declared is not None and canonical_charset(declared) != encoding)
        return Decoded(text=text, encoding=encoding, declared=declared,
                       bom=has_bom or body.startswith(BOM_UTF8),
                       fallback=bool(fallback),
                       reason="CHARSET_FALLBACK" if fallback else None)
    return Decoded(text="", encoding="", declared=declared, bom=has_bom,
                   fallback=False, reason="CHARSET_UNKNOWN")


def decode_or_quarantine(body: bytes, headers: dict[str, str] | None = None) -> Decoded:
    result = decode_body(body, headers)
    if result.reason == "CHARSET_UNKNOWN":
        raise ValueError(reasons.label("CHARSET_UNKNOWN"))
    return result
