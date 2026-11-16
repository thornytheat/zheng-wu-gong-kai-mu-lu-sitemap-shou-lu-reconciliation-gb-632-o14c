"""运行清单：run_id、输入摘要（sha256）、规则版本、阶段账、耗时。

复算入口：清单里的 resources 给出每个输入地址的状态码、字节数与 sha256，
拿到同样的样例站字节就能重现同一 run_id（run_id 由批次键派生）。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Iterable

from . import config, reasons


def now_utc() -> str:
    return dt.datetime.now(config.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_stamp(utc_text: str | None = None) -> str:
    """UTC 秒级字符串 → 东八区展示串。"""
    if not utc_text:
        return "—"
    try:
        moment = dt.datetime.strptime(utc_text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=config.UTC)
    except ValueError:
        return utc_text
    return moment.astimezone(config.CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def digest_of(resources: Iterable[dict]) -> str:
    """输入摘要：地址 + 状态码 + 响应体 sha256，按地址排序后取 sha256。"""
    lines = sorted(f"{r['url']}\t{r['status']}\t{r['sha256']}" for r in resources)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def batch_key(sites: Iterable[str], digest: str, rule_version: str) -> str:
    """批次键 = 站点集合 + 输入摘要 + 规则版本；相同即同一批次，重跑直接复用。"""
    stem = "|".join([",".join(sorted(sites)), digest, rule_version])
    return hashlib.sha256(stem.encode("utf-8")).hexdigest()


def run_id_for(key: str) -> str:
    return "ra-" + key[:12]


def stage(stage_name: str, in_count: int, out_count: int, quarantine_count: int,
          status: str, elapsed_ms: int, note: str = "") -> dict:
    return {"stage": stage_name,
            "label": config.STAGE_LABELS.get(stage_name, stage_name),
            "in_count": in_count, "out_count": out_count,
            "quarantine_count": quarantine_count, "status": status,
            "elapsed_ms": elapsed_ms, "note": note}


def reason_distribution(rows: Iterable[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for row in rows:
        code = row.get("reason") or "UNKNOWN"
        counts[code] = counts.get(code, 0) + 1
    return [{"code": code, "label": reasons.label(code), "level": reasons.level(code),
             "group": reasons.group_of(code), "count": counts[code]}
            for code in sorted(counts, key=lambda c: (-counts[c], c))]


def build_manifest(run: dict) -> dict:
    """导出的运行清单：只放可复核字段，不放页面用的展示结构。"""
    return {
        "run_id": run["run_id"],
        "batch_key": run["batch_key"],
        "rule_version": run["rule_version"],
        "status": run["status"],
        "sites": run["sites"],
        "input_digest": run["input_digest"],
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "elapsed_ms": run["elapsed_ms"],
        "params": run.get("params", {}),
        "stage_state": run.get("stage_state", {}),
        "stages": run.get("stages", []),
        "resources": [
            {"url": r["url"], "status": r["status"], "bytes": r["bytes"],
             "sha256": r["sha256"]}
            for r in run.get("resources", [])
        ],
        "totals": run.get("totals", {}),
        "reason_counts": run.get("reason_counts", []),
        "replay": run.get("replay", {}),
    }


def manifest_text(run: dict) -> str:
    return json.dumps(build_manifest(run), ensure_ascii=False, indent=2, sort_keys=True)
