"""M7 规则一：跳转链与地址基准。

两件事都围绕「地址怎么比」：
1. 301 环：只在 hops 回到已访问地址时判环。自环、双节点环、长环都能给出环内路径；
   一路都是新地址、只是超过跳转上限的，是「链过长」而不是环（TRAP-27）。
   判环用 canonical_input，所以 `/X/` 与 `/x` 的环也能认出来。
2. 相对路径基准：同一段相对写法，按目录页地址补全与按 sitemap 地址补全可能得到
   不同的键；两次巡检各按自己的基准补全后，键不同要先标成「基准不同」，
   不能直接算成一条新增死链加一条消失地址（TRAP-28）。

两个比较键函数都在这里，因为变更对比必须用同一把尺子。
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from ... import config

_DUP_SLASH = re.compile(r"/{2,}")

KIND_DIRECT = "direct"
KIND_CHAIN = "chain"
KIND_CYCLE = "cycle"
KIND_LIMIT = "limit"
KIND_LABELS = {
    KIND_DIRECT: "未跳转",
    KIND_CHAIN: "跳转链",
    KIND_CYCLE: "跳转成环",
    KIND_LIMIT: "链超过上限",
}
BASE_PAGE = "page"
BASE_SITEMAP = "sitemap"
BASE_LABELS = {BASE_PAGE: "目录页地址", BASE_SITEMAP: "sitemap 地址"}


def _trim(path: str) -> str:
    """合并重复斜杠并去尾斜杠（根路径保留）。"""
    cleaned = _DUP_SLASH.sub("/", path or "/")
    if len(cleaned) > 1:
        cleaned = cleaned.rstrip("/") or "/"
    return cleaned


def canonical_input(url: str) -> str:
    """比较两次巡检用的键：小写 + 合并重复斜杠 + 去尾斜杠。

    三步顺序固定，且自身幂等（第二次调用不再改变结果）。
    大小写与尾斜杠同时出现时只算一把键，不产生「新增 + 消失」两条。
    """
    text = (url or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    if not parts.scheme:
        return _trim(text.lower())
    host = (parts.hostname or "").lower()
    port = f":{parts.port}" if parts.port else ""
    path = _trim(parts.path or "/").lower()
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme.lower()}://{host}{port}{path}{query}"


def resolve(raw: str, base_url: str) -> str:
    """相对写法按所在文件地址补全；绝对写法原样返回。"""
    text = (raw or "").strip()
    if not text:
        return ""
    if text.lower().startswith(("http://", "https://")):
        return text
    return urljoin(base_url, text)


def analyze(hops: list[dict] | None, status: int = 0,
            max_hops: int = config.MAX_HOPS) -> dict:
    """看一条跳转链：直接 / 有链 / 成环 / 链过长。"""
    steps = list(hops or [])
    chain = [steps[0]["from"], *(step["to"] for step in steps)] if steps else []
    seen: dict[str, int] = {}
    for index, url in enumerate(chain):
        key = canonical_input(url)
        if key in seen:
            start = seen[key]
            loop = chain[start:index + 1]
            return {"kind": KIND_CYCLE, "label": KIND_LABELS[KIND_CYCLE],
                    "length": len(steps), "loop_path": loop,
                    "entry": chain[start], "reason": "CHAIN_CYCLE",
                    "members": [canonical_input(item) for item in loop]}
        seen[key] = index
    if len(steps) > max_hops:
        return {"kind": KIND_LIMIT, "label": KIND_LABELS[KIND_LIMIT],
                "length": len(steps), "loop_path": [],
                "entry": chain[0] if chain else "", "reason": "CHAIN_LIMIT",
                "members": []}
    if steps:
        return {"kind": KIND_CHAIN, "label": KIND_LABELS[KIND_CHAIN],
                "length": len(steps), "loop_path": [],
                "entry": chain[0], "reason": "",
                "members": []}
    return {"kind": KIND_DIRECT, "label": KIND_LABELS[KIND_DIRECT],
            "length": 0, "loop_path": [], "entry": "", "reason": "", "members": []}


def group_cycles(rows: list[dict]) -> list[dict]:
    """同一个环从多个入口探测会多行；按环内成员集合合并，只报一次。"""
    groups: dict[tuple, dict] = {}
    for row in rows:
        info = row.get("chain") or {}
        if info.get("kind") != KIND_CYCLE:
            continue
        members = tuple(sorted(info.get("members") or []))
        if not members:
            continue
        slot = groups.get(members)
        if slot is None:
            slot = {"members": list(members), "entries": [], "count": 0,
                    "loop_path": info.get("loop_path") or [], "site": row.get("site", "")}
            groups[members] = slot
        slot["count"] += 1
        slot["entries"].append(row.get("key", ""))
    return [groups[key] for key in sorted(groups)]


def raw_index(run: dict) -> dict[str, list[dict]]:
    """每条键的原始写法与它的补全基准：目录行按页面地址，sitemap 按其自身地址。"""
    out: dict[str, list[dict]] = {}
    for slot in run.get("keys") or []:
        key = canonical_input(slot.get("key") or "")
        if not key:
            continue
        raws: list[dict] = []
        seen: set[str] = set()
        for entry in slot.get("catalog") or []:
            raw = (entry.get("raw_href") or "").strip()
            if raw and raw.lower() not in seen:
                seen.add(raw.lower())
                raws.append({"raw": raw, "base_kind": BASE_PAGE,
                             "base": entry.get("page_url") or "", "key": key})
        site = config.SITE_BY_CODE.get(slot.get("site") or "")
        base = f"http://{site.host}{site.sitemap_path}" if site else ""
        for item in slot.get("sitemap") or []:
            raw = (item.get("raw_loc") or "").strip()
            if raw and raw.lower() not in seen:
                seen.add(raw.lower())
                raws.append({"raw": raw, "base_kind": BASE_SITEMAP,
                             "base": base, "key": key})
        out[key] = raws
    return out
