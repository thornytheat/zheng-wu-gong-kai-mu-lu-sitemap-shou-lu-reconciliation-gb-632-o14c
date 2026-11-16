"""逐跳探测：不自动跟随跳转，手工推进并记录每一跳。

两种「走不完」分开记，因为修法不同：
- 成环（回到已访问地址）：改跳转规则，环内其余地址不必再逐条探测；
- 链过长（一路都是新地址，只是超过上限）：加跳转上限或拉直链路，不是环。
朴素实现把两者都叫「跳转成环」，M7 的变更对比会把长链误报成环（TRAP-27）。

状态码 0 表示传输层失败（连接被拒、超时、越界主机），与 4xx/5xx 分开记，
因为前者是运维问题，后者是页面问题。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

from ... import config, reasons

REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})


@dataclass
class Probe:
    key: str
    status: int
    final_url: str
    hops: list[dict] = field(default_factory=list)
    error: str = ""
    reason: str = ""
    elapsed_ms: int = 0

    @property
    def dead(self) -> bool:
        return self.status == 0 or self.status >= 400

    @property
    def hop_count(self) -> int:
        return len(self.hops)


def reason_for(status: int, error: str = "", loop: bool = False,
               limit: bool = False) -> str:
    if loop:
        return "PROBE_REDIRECT_LOOP"
    if limit:
        return "PROBE_REDIRECT_LIMIT"
    if status == 0:
        return "PROBE_TIMEOUT" if "timeout" in error.lower() else "PROBE_ERROR"
    if status == 404:
        return "PROBE_404"
    if status == 410:
        return "PROBE_410"
    if status >= 500:
        return "PROBE_5XX"
    return ""


def probe(fetcher, url: str, max_hops: int = config.MAX_HOPS) -> Probe:
    started = time.monotonic()
    current = url
    hops: list[dict] = []
    seen = {url}
    last = None
    while True:
        last = fetcher.get(current)
        if last.error == "OFFSITE":
            return Probe(key=url, status=0, final_url=current, hops=hops,
                         error="OFFSITE", reason="SCOPE_OFFSITE",
                         elapsed_ms=int((time.monotonic() - started) * 1000))
        if last.status in REDIRECT_CODES and last.location:
            target = urljoin(current, last.location)
            hops.append({"from": current, "to": target, "status": last.status})
            if target in seen:
                return Probe(key=url, status=0, final_url=target, hops=hops,
                             error="跳转成环", reason=reason_for(0, loop=True),
                             elapsed_ms=int((time.monotonic() - started) * 1000))
            if len(hops) > max_hops:
                return Probe(key=url, status=0, final_url=target, hops=hops,
                             error="超过跳转上限", reason=reason_for(0, limit=True),
                             elapsed_ms=int((time.monotonic() - started) * 1000))
            seen.add(target)
            current = target
            continue
        elapsed = int((time.monotonic() - started) * 1000)
        return Probe(key=url, status=last.status, final_url=current, hops=hops,
                     error=last.error or "", reason=reason_for(last.status, last.error or ""),
                     elapsed_ms=elapsed)


def describe(probe_result: Probe) -> str:
    if probe_result.reason:
        return reasons.label(probe_result.reason)
    if probe_result.hop_count:
        return f"跳转 {probe_result.hop_count} 次"
    return f"{probe_result.status}"
