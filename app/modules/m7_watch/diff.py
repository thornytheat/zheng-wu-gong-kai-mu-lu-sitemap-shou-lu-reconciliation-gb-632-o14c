"""M7 规则二：两批次差异、回归清单与站点趋势。

三条规则都能单测，不依赖 HTTP，也不读库：

1. 变化分桶：上次状态 × 本次状态共 9 种组合，每种一个固定归属（TRANSITIONS）。
   上次死链、本次能打开但要跳转的记「已改善」——地址能打开了，不能记成仍未修复。
2. 基准不同（TRAP-28）：只在单侧出现的地址，若两侧原始写法相同、补全基准不同
   （目录页地址 vs sitemap 地址），先配成「基准不同」，不能算成一条新增加一条消失。
   绝对写法按原样解析，不受基准影响，所以不参与配对。
3. 跳转环（TRAP-27）：环按环内成员集合合并，多个入口只报一次；一路都是新地址、
   只是超过跳转上限的记「链过长」，不是环（判定在 chain.analyze）。
"""
from __future__ import annotations

from ... import reasons
from . import chain

SNAPSHOT_SCHEMA = "sitemapaudit/watch/1"

STATE_OK = "ok"
STATE_REDIRECT = "redirect"
STATE_DEAD = "dead"
STATES = (STATE_OK, STATE_REDIRECT, STATE_DEAD)
STATE_LABELS = {STATE_OK: "可达", STATE_REDIRECT: "跳转", STATE_DEAD: "死链"}
STATE_RANK = {STATE_OK: 0, STATE_REDIRECT: 1, STATE_DEAD: 2}

# 上次状态 × 本次状态 → 分桶。9 格全在表里，没有默认值，新增状态就必须补表。
TRANSITIONS: dict[tuple[str, str], str] = {
    (STATE_OK, STATE_OK): "unchanged",
    (STATE_OK, STATE_REDIRECT): "new_redirect",
    (STATE_OK, STATE_DEAD): "new_dead",
    (STATE_REDIRECT, STATE_OK): "recovered",
    (STATE_REDIRECT, STATE_REDIRECT): "still_redirect",
    (STATE_REDIRECT, STATE_DEAD): "new_dead",
    (STATE_DEAD, STATE_OK): "recovered",
    (STATE_DEAD, STATE_REDIRECT): "improved",
    (STATE_DEAD, STATE_DEAD): "still_dead",
}

# 缺陷/变更标签的 CSS 类名：error 用 bad，warn 用 warn，ok 用 ok
LEVEL_CLASS = {"error": "bad", "warn": "warn", "ok": "ok", "info": "info"}


def state_of(row: dict) -> str:
    """一条探测结果归入三态：状态码 0 与 4xx/5xx 都是死链，其余看有没有跳转。"""
    status = int(row.get("status") or 0)
    if status == 0 or status >= 400:
        return STATE_DEAD
    return STATE_REDIRECT if int(row.get("hop_count") or 0) > 0 else STATE_OK


def bucket_of(prev_state: str, cur_state: str) -> str:
    try:
        return TRANSITIONS[(prev_state, cur_state)]
    except KeyError as exc:
        raise ValueError(f"未登记的状态组合 {prev_state} → {cur_state}") from exc


def _chain_brief(info: dict) -> dict:
    return {"kind": info.get("kind", ""), "label": info.get("label", ""),
            "length": int(info.get("length") or 0),
            "members": list(info.get("members") or []),
            "loop_path": list(info.get("loop_path") or [])}


def snapshot(run: dict, note: str = "") -> dict:
    """把一次巡检压成可比对的快照：一条 key 一行，三态 + 跳转链摘要 + 原始写法。"""
    raws = chain.raw_index(run)
    merged: dict[str, dict] = {}
    for probe_row in run.get("probes") or []:
        key = chain.canonical_input(probe_row.get("key") or probe_row.get("url") or "")
        if not key:
            continue
        item = {
            "key": key,
            "url": probe_row.get("url") or key,
            "site": probe_row.get("site") or "",
            "status": int(probe_row.get("status") or 0),
            "hop_count": int(probe_row.get("hop_count") or 0),
            "category": probe_row.get("category") or "",
            "final_url": probe_row.get("final_url") or "",
            "chain": _chain_brief(chain.analyze(probe_row.get("hops"),
                                                probe_row.get("status") or 0)),
            "raws": list(raws.get(key) or []),
        }
        kept = merged.get(key)
        if kept is None or STATE_RANK[state_of(item)] > STATE_RANK[state_of(kept)]:
            merged[key] = item
    rows = [merged[key] for key in sorted(merged)]
    return {
        "schema": SNAPSHOT_SCHEMA,
        "run_id": run.get("run_id", ""),
        "started_at": run.get("started_at", ""),
        "finished_at": run.get("finished_at", ""),
        "rule_version": run.get("rule_version", ""),
        "sites": list(run.get("sites") or []),
        "note": note,
        "row_count": len(rows),
        "rows": rows,
    }


def index(snapshot_doc: dict) -> dict[str, dict]:
    """按比较键建索引；导入的快照写法不统一时也先归一再配对，重复键留较差的那条。"""
    out: dict[str, dict] = {}
    for row in snapshot_doc.get("rows") or []:
        key = chain.canonical_input(row.get("key") or row.get("url") or "")
        if not key:
            continue
        item = dict(row)
        item["key"] = key
        kept = out.get(key)
        if kept is None or STATE_RANK[state_of(item)] > STATE_RANK[state_of(kept)]:
            out[key] = item
    return out


def _raw_index(rows: dict[str, dict], keys) -> dict[str, list[tuple[str, dict]]]:
    out: dict[str, list[tuple[str, dict]]] = {}
    for key in keys:
        for item in rows[key].get("raws") or []:
            raw = (item.get("raw") or "").strip()
            if raw:
                out.setdefault(raw.lower(), []).append((key, item))
    return out


def _is_relative(raw: str) -> bool:
    text = (raw or "").strip().lower()
    return bool(text) and not text.startswith(("http://", "https://"))


def _base_differs(left: dict, right: dict) -> bool:
    return ((left.get("base_kind") or "") != (right.get("base_kind") or "")
            or (left.get("base") or "") != (right.get("base") or ""))


def basis_pairs(prev_index: dict[str, dict], cur_index: dict[str, dict],
                removed: list[str], added: list[str]) -> tuple[list[dict], list[str], list[str]]:
    """把「同写法、不同补全基准」的消失/新增配成一对，剩下的才计入增删。"""
    cur_raws = _raw_index(cur_index, added)
    used_prev: set[str] = set()
    used_cur: set[str] = set()
    pairs: list[dict] = []
    for key in sorted(removed):
        for item in prev_index[key].get("raws") or []:
            raw = (item.get("raw") or "").strip()
            if not _is_relative(raw):
                continue
            matched = False
            for other_key, other in cur_raws.get(raw.lower(), []):
                if other_key in used_cur or not _base_differs(item, other):
                    continue
                used_prev.add(key)
                used_cur.add(other_key)
                pairs.append({"prev_key": key, "cur_key": other_key,
                              "raw": raw, "prev_base": item.get("base") or "",
                              "cur_base": other.get("base") or ""})
                matched = True
                break
            if matched:
                break
    left_removed = [key for key in removed if key not in used_prev]
    left_added = [key for key in added if key not in used_cur]
    return pairs, left_removed, left_added


def _row(key: str, bucket: str, prev: dict | None, cur: dict | None,
         prev_state: str, cur_state: str) -> dict:
    source = cur or prev or {}
    return {
        "key": key,
        "bucket": bucket,
        "bucket_label": reasons.change_label(bucket),
        "level": LEVEL_CLASS.get(reasons.change_level(bucket), "info"),
        "note": reasons.change_note(bucket),
        "site": source.get("site") or "",
        "url": source.get("url") or key,
        "status_prev": (prev or {}).get("status", "—") if prev else "—",
        "status_cur": (cur or {}).get("status", "—") if cur else "—",
        "prev_state": prev_state,
        "cur_state": cur_state,
        "prev_state_label": STATE_LABELS.get(prev_state, "—"),
        "cur_state_label": STATE_LABELS.get(cur_state, "—"),
        "chain": (cur or prev or {}).get("chain") or {},
    }


def compare(prev_snapshot: dict, cur_snapshot: dict) -> dict:
    """两次快照按规范化键配对，输出逐条变化与分桶合计。"""
    prev_index = index(prev_snapshot)
    cur_index = index(cur_snapshot)
    removed = [key for key in prev_index if key not in cur_index]
    added = [key for key in cur_index if key not in prev_index]
    pairs, removed, added = basis_pairs(prev_index, cur_index, removed, added)
    used = {pair["prev_key"] for pair in pairs} | {pair["cur_key"] for pair in pairs}

    rows: list[dict] = []
    for key in sorted(set(prev_index) | set(cur_index)):
        if key in used:
            continue
        prev = prev_index.get(key)
        cur = cur_index.get(key)
        if prev is not None and cur is not None:
            prev_state, cur_state = state_of(prev), state_of(cur)
            bucket = bucket_of(prev_state, cur_state)
        elif prev is not None:
            prev_state, cur_state = state_of(prev), ""
            bucket = "removed"
        else:
            prev_state, cur_state = "", state_of(cur)
            bucket = "added"
        rows.append(_row(key, bucket, prev, cur, prev_state, cur_state))

    for pair in pairs:
        prev = prev_index[pair["prev_key"]]
        cur = cur_index[pair["cur_key"]]
        row = _row(pair["cur_key"], "basis", prev, cur, state_of(prev), state_of(cur))
        row.update({"raw": pair["raw"], "prev_key": pair["prev_key"],
                    "prev_url": prev.get("url") or pair["prev_key"],
                    "prev_base": pair["prev_base"], "cur_base": pair["cur_base"]})
        rows.append(row)

    rows.sort(key=lambda row: (reasons.change_rank(row["bucket"]),
                               row.get("site") or "", row["key"]))
    return {"rows": rows, "summary": summarize(rows),
            "prev_run_id": prev_snapshot.get("run_id", ""),
            "cur_run_id": cur_snapshot.get("run_id", "")}


def regressions(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["bucket"] in reasons.ACTIONABLE_BUCKETS]


def summarize(rows: list[dict]) -> dict:
    counts = {bucket: 0 for bucket in reasons.CHANGE_ORDER}
    by_site: dict[str, dict] = {}
    for row in rows:
        counts[row["bucket"]] = counts.get(row["bucket"], 0) + 1
        site = row.get("site") or "—"
        slot = by_site.setdefault(site, {"site": site, "total": 0})
        slot["total"] += 1
        slot[row["bucket"]] = slot.get(row["bucket"], 0) + 1
    buckets = [{"key": bucket, "label": reasons.change_label(bucket),
                "level": LEVEL_CLASS.get(reasons.change_level(bucket), "info"),
                "count": counts[bucket]} for bucket in reasons.CHANGE_ORDER]
    return {"total": len(rows), "bucket_counts": counts, "buckets": buckets,
            "actionable": len(regressions(rows)),
            "by_site": [by_site[key] for key in sorted(by_site)]}


def trend(runs: list[dict]) -> dict:
    """按站点看三态计数随批次的变化；runs 按时间升序传入。"""
    rows: list[dict] = []
    sites: set[str] = set()
    for run in runs:
        doc = snapshot(run)
        counts: dict[str, dict[str, int]] = {}
        for row in doc["rows"]:
            site = row.get("site") or "—"
            sites.add(site)
            slot = counts.setdefault(site, {STATE_OK: 0, STATE_REDIRECT: 0, STATE_DEAD: 0})
            slot[state_of(row)] += 1
        rows.append({"run_id": doc["run_id"], "started_at": doc["started_at"],
                     "total": doc["row_count"], "sites": counts})
    return {"runs": rows, "sites": sorted(sites),
            "states": list(STATES), "state_labels": dict(STATE_LABELS)}
