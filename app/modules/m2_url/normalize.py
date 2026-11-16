"""地址规范化：7 步固定顺序，输出可比较的 key 与「改写过」标记。

顺序本身是规则的一部分（先补全相对地址才能取主机，先丢跟踪参数才能排序），
所以 normalize() 里每一步都写成显式函数并按固定次序调用，不允许按 dict 遍历顺序拼。
改写痕迹存进 notes，缺陷分类的 CANONICAL_MISMATCH 依据就是它非空。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from ... import config

_DUP_SLASH_RE = re.compile(r"/{2,}")


@dataclass(frozen=True)
class Normalized:
    raw: str
    url: str
    scheme: str
    host: str
    path: str
    query: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def key(self) -> str:
        return self.url

    @property
    def changed(self) -> bool:
        return bool(self.notes)


def _strip_scheme(text: str) -> str:
    lowered = text.lower()
    if lowered.startswith(config.SCRIPT_SCHEMES):
        raise ValueError("地址不是网页地址")
    if text.startswith("//"):
        return "http:" + text
    return text


def _clean_query(query: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    if not query:
        return "", notes
    pairs = parse_qsl(query, keep_blank_values=True)
    kept = []
    dropped_tracking = False
    for name, value in pairs:
        if name.lower() in config.TRACKING_PARAMS:
            dropped_tracking = True
            continue
        kept.append((name, value))
    if dropped_tracking:
        notes.append("tracking")
    if [p[0] for p in kept] != sorted(p[0] for p in kept):
        notes.append("param_order")
    kept.sort()
    if len(kept) != len(pairs) and not dropped_tracking:
        notes.append("tracking")
    return urlencode(kept), notes


def normalize(raw: str, base_url: str | None = None) -> Normalized:
    text = (raw or "").strip()
    if not text:
        raise ValueError("地址为空")
    notes: list[str] = []
    text = _strip_scheme(text)
    parts = urlsplit(text)
    if not parts.scheme:
        if not base_url:
            raise ValueError("地址缺少协议且没有基地址")
        text = urljoin(base_url, text)
        notes.append("relative")
        parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme not in config.ALLOWED_SCHEMES:
        raise ValueError(f"不接受的协议 {scheme}")
    if scheme != parts.scheme:
        notes.append("scheme")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("地址缺少主机")
    raw_host = parts.netloc.rsplit("@", 1)[-1].split(":")[0]
    if raw_host != host:
        notes.append("case")
    port = parts.port
    port_text = ""
    if port is not None:
        if config.DEFAULT_PORTS.get(scheme) == port:
            notes.append("default_port")
        else:
            port_text = f":{port}"
    path = parts.path or "/"
    if _DUP_SLASH_RE.search(path):
        path = _DUP_SLASH_RE.sub("/", path)
        notes.append("duplicate_slash")
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
        notes.append("trailing_slash")
    lowered_path = path.lower()
    if lowered_path != path:
        notes.append("case")
    path = lowered_path
    query, query_notes = _clean_query(parts.query)
    notes.extend(query_notes)
    if parts.fragment:
        notes.append("fragment")
    url = f"{scheme}://{host}{port_text}{path}" + (f"?{query}" if query else "")
    seen: list[str] = []
    for note in notes:
        if note not in seen:
            seen.append(note)
    return Normalized(raw=raw, url=url, scheme=scheme, host=host, path=path,
                      query=query, notes=tuple(seen))


def safe_normalize(raw: str, base_url: str | None = None) -> Normalized | None:
    try:
        return normalize(raw, base_url)
    except ValueError:
        return None
