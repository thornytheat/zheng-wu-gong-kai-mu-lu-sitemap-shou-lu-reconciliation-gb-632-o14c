"""批次历史：巡查记录列表与单批摘要。

只读 store，不重算规则；页面上的每个数字都能在 manifest 导出里找到同名字段。
"""
from __future__ import annotations

from ... import config, manifest


def summary(store) -> dict:
    runs = store.list_runs(30)
    rows = []
    for run in runs:
        rows.append({
            "run_id": run["run_id"],
            "batch_key": run["batch_key"],
            "status": run["status"],
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
            "elapsed_ms": run["elapsed_ms"],
            "input_digest": run["input_digest"],
            "digest_short": run["input_digest"][:12],
            "findings_total": run["findings_total"],
            "sites": (run.get("sites") or "").split(",") if run.get("sites") else [],
        })
    return {"count": len(rows), "rows": rows, "stages": list(config.STAGES),
            "flow": config.STAGE_FLOW}


def stage_rows(run: dict) -> list[dict]:
    rows = list(run.get("stages") or [])
    for stage in rows:
        stage["label"] = config.STAGE_LABELS.get(stage["stage"], stage["stage"])
    return rows


def detail(run: dict) -> dict:
    return {
        "run_id": run["run_id"],
        "batch_key": run["batch_key"],
        "status": run["status"],
        "sites": run["sites"],
        "input_digest": run["input_digest"],
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "elapsed_ms": run["elapsed_ms"],
        "stage_state": run.get("stage_state", {}),
        "stages": stage_rows(run),
        "params": run.get("params", {}),
        "resources": [{"url": r["url"], "status": r["status"], "bytes": r["bytes"],
                       "sha256": r["sha256"], "digest_short": r["sha256"][:12]}
                      for r in run.get("resources", [])],
        "totals": run.get("totals", {}),
        "defect_summary": run.get("defect_summary", {}),
        "reason_counts": run.get("reason_counts", []),
        "replay": run.get("replay", {}),
        "manifest_meta": {"rule_version": manifest.build_manifest(run)["rule_version"]},
    }
