"""站点范围：主机决定归属，不在清单内的地址不进三向对账。

政务站常见的越界有三种：友情链接指向别的厅局站、把站内地址写成外部域名、
附件地址跳到文件服务器。三者都按原因码 SCOPE_OFFSITE 记一条，可导出复核，
但既不进目录账，也不进缺陷账，避免把别人的站算成本站缺失。
"""
from __future__ import annotations

from urllib.parse import urlsplit

from ... import config


def site_of(url: str) -> str | None:
    host = (urlsplit(url).hostname or "").lower()
    for site in config.SITES:
        if host == site.host:
            return site.code
    return None


def in_scope(url: str) -> bool:
    return site_of(url) is not None


def detail(url: str) -> dict:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return {"host": host, "path": parts.path or "/",
            "site": site_of(url), "in_scope": site_of(url) is not None,
            "reason": None if site_of(url) else "SCOPE_OFFSITE"}
