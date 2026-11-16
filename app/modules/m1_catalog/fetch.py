"""采信层取数：样例站镜像、地址映射、状态码保真（不自动跟随跳转）。

镜像规则：地址里的主机必须在站点清单内，路径原样发给样例站；不在清单里的
主机返回 OFFSITE，由 M2 判为超出范围，不进三向对账。

跳转不在这里跟随：可达性要逐跳记录跳转链，所以取数一律
follow_redirects=False，链路由 m3_reach/probe.py 推进。容器与测试都走同一个
HTTP 样例站（sample_site/serve.py），不保留第二套离线取数实现。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from ... import config


@dataclass(frozen=True)
class Fetched:
    url: str
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.status == 200 and not self.error

    @property
    def size(self) -> int:
        return len(self.body)

    @property
    def location(self) -> str | None:
        return self.headers.get("location")


class MirrorFetcher:
    """把公网风格的地址映射到样例站，状态码与响应体照原样返回。"""

    def __init__(self, base: str, timeout: float = config.PROBE_TIMEOUT):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def resolve(self, url: str) -> str | None:
        parts = urlsplit(url)
        if parts.scheme not in config.ALLOWED_SCHEMES:
            return None
        if parts.hostname not in config.SITE_BY_HOST:
            return None
        path = parts.path or "/"
        query = f"?{parts.query}" if parts.query else ""
        return f"{self.base}{path}{query}"

    def get(self, url: str) -> Fetched:
        target = self.resolve(url)
        if target is None:
            return Fetched(url=url, status=0, error="OFFSITE")
        try:
            resp = httpx.get(target, timeout=self.timeout, follow_redirects=False)
        except httpx.HTTPError as exc:
            return Fetched(url=url, status=0, error=f"{type(exc).__name__}: {exc}")
        return Fetched(url=url, status=resp.status_code, body=resp.content,
                       headers={k.lower(): v for k, v in resp.headers.items()})

    def resource_row(self, fetched: Fetched, digest: str) -> dict:
        return {"url": fetched.url, "status": fetched.status, "bytes": fetched.size,
                "sha256": digest, "error": fetched.error or ""}


def make_fetcher(settings: config.Settings) -> MirrorFetcher:
    return MirrorFetcher(settings.sample_site_base, timeout=settings.probe_timeout)
