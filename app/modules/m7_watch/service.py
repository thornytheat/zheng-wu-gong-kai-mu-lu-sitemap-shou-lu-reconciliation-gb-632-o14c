"""M7 编排：挑基准、算差异、出趋势、导快照与回归清单。

基准优先级固定：库内更早的批次（同一份样例站字节可复算）→ 样例快照文件。
两者都没有时返回 WATCH_NO_BASE，页面照常打开并提示先跑一次巡检，
不拿空数据假装「没有变化」。

变更对比只读已入库的 run，不重新探测，所以页面刷新不会改变结论。
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from ... import config, errors, reasons
from . import chain, diff

BOM = "\ufeff"
SOURCES = {"auto": "自动", "store": "库内上次", "sample": "样例快照"}
BASE_LABELS = {"store": "库内上次", "sample": "样例快照", "none": "无基准"}
CSV_COLUMNS = ("批次", "变化", "站点", "上次", "本次", "上次状态码", "本次状态码",
               "地址", "说明")


def _read_json(path: str) -> dict | None:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        doc = json.loads(text)
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


def load_sample(settings) -> dict | None:
    """样例快照：结构对得上 schema 才用，坏文件当没有基准。"""
    doc = _read_json(settings.watch_baseline_path)
    if not doc or doc.get("schema") != diff.SNAPSHOT_SCHEMA:
        return None
    if not isinstance(doc.get("rows"), list):
        return None
    return doc


def previous_run(store, current: dict) -> dict | None:
    """库内上一次：开始时间不晚于本次、批次号不同的最近一条。"""
    started = current.get("started_at") or ""
    for row in store.list_runs(config.WATCH_HISTORY + 1):
        if row["run_id"] == current.get("run_id"):
            continue
        if (row.get("started_at") or "") <= started:
            payload = store.get_run(row["run_id"])
            if payload is not None:
                return payload
    return None


def baseline(settings, store, current: dict, source: str = "auto") -> dict:
    if source not in SOURCES:
        raise errors.BadRequest(f"base 只支持 {', '.join(SOURCES)}", code="E_BAD_BASE")
    if source in ("auto", "store"):
        prev = previous_run(store, current)
        if prev is not None:
            return {"snapshot": diff.snapshot(prev), "source": "store",
                    "label": f"库内上次 {prev['run_id']}", "code": ""}
        if source == "store":
            return {"snapshot": None, "source": "store", "label": "库内没有上次",
                    "code": "WATCH_NO_BASE"}
    doc = load_sample(settings)
    if doc is not None:
        return {"snapshot": doc, "source": "sample",
                "label": doc.get("note") or "样例快照", "code": "WATCH_SAMPLE"}
    return {"snapshot": None, "source": "none", "label": "没有对比基准",
            "code": "WATCH_NO_BASE"}


def _history(store) -> list[dict]:
    runs: list[dict] = []
    for row in store.list_runs(config.WATCH_HISTORY):
        payload = store.get_run(row["run_id"])
        if payload is not None:
            runs.append(payload)
    return list(reversed(runs))  # 页面按时间从左到右看


def watch(settings, store, current: dict, source: str = "auto",
          site: str | None = None, bucket: str | None = None) -> dict:
    if source not in SOURCES:
        raise errors.BadRequest(f"base 只支持 {', '.join(SOURCES)}", code="E_BAD_BASE")
    if bucket and bucket not in reasons.CHANGE_BUCKETS:
        raise errors.BadRequest(f"未知变化 {bucket}", code="E_BAD_BUCKET")
    if site and site not in config.SITE_BY_CODE:
        raise errors.BadRequest(f"未知站点 {site}", code="E_BAD_SITE")

    base = baseline(settings, store, current, source)
    current_doc = diff.snapshot(current)
    result = {
        "status": "no_base" if base["snapshot"] is None else "ok",
        "code": base["code"],
        "base": {"source": base["source"],
                 "source_label": BASE_LABELS.get(base["source"], base["source"]),
                 "run_id": (base["snapshot"] or {}).get("run_id", ""),
                 "started_at": (base["snapshot"] or {}).get("started_at", ""),
                 "label": base["label"]},
        "current": {"run_id": current.get("run_id", ""),
                    "started_at": current.get("started_at", ""),
                    "rows": current_doc["row_count"]},
        "source": source,
        "site": site or "",
        "bucket": bucket or "",
        "buckets": [{"key": bucket_key, "label": reasons.change_label(bucket_key),
                     "level": diff.LEVEL_CLASS.get(reasons.change_level(bucket_key), "info"),
                     "count": 0} for bucket_key in reasons.CHANGE_ORDER],
        "summary": diff.summarize([]),
        "rows": [],
        "shown": 0,
        "regressions": [],
        "cycles": chain.group_cycles(current_doc["rows"]),
        "trend": diff.trend(_history(store)),
    }
    if base["snapshot"] is None:
        return result

    compared = diff.compare(base["snapshot"], current_doc)
    rows = compared["rows"]
    if site:
        rows = [row for row in rows if row["site"] == site]
    if bucket:
        rows = [row for row in rows if row["bucket"] == bucket]
    result.update({
        "summary": compared["summary"],
        "buckets": compared["summary"]["buckets"],
        "regressions": diff.regressions(rows),
        "shown": len(rows),
        "rows": rows[:config.WATCH_PAGE_ROWS],
    })
    return result


def regressions_csv(result: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    run_id = result.get("current", {}).get("run_id", "")
    for row in result.get("regressions") or []:
        writer.writerow([run_id, row["bucket_label"], row["site"],
                         row["prev_state_label"], row["cur_state_label"],
                         row.get("status_prev", "—"), row.get("status_cur", "—"),
                         row["url"], row["note"]])
    return BOM + buffer.getvalue()


def snapshot_json(run: dict) -> str:
    """本次快照：下次巡检把它当基准，字段与样例快照一致。"""
    doc = diff.snapshot(run, note="本次巡检快照，可作为下次对比基准")
    return json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True)


def snapshot_filename(run: dict) -> str:
    return f"watch-{run.get('run_id', 'run')}.json"


def csv_filename(run: dict) -> str:
    return f"regressions-{run.get('run_id', 'run')}.csv"
