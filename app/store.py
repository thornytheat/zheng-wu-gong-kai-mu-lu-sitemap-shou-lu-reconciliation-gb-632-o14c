"""SQLite 持久化：一个 runs 表，payload 存该次巡检的完整证据。

表设计说明：
- batch_key 唯一，用来挡住同一输入的重复入库（幂等重跑的直接依据）；
- run_id 由 batch_key 派生，同输入必然同号，重跑不产生新行；
- 明细（目录行、收录行、探测、缺陷、隔离）整包进 payload，导出与对账同源。
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    batch_key     TEXT NOT NULL UNIQUE,
    status        TEXT NOT NULL,
    input_digest  TEXT NOT NULL,
    rule_version  TEXT NOT NULL,
    sites         TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    elapsed_ms    INTEGER DEFAULT 0,
    findings_total INTEGER DEFAULT 0,
    updated_at    TEXT NOT NULL,
    payload       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
"""

SUMMARY_FIELDS = ("run_id", "batch_key", "status", "input_digest", "rule_version",
                  "started_at", "finished_at", "elapsed_ms", "findings_total")


class Store:
    def __init__(self, path: str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(os.path.dirname(self.path) or ".").mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # -- 写入 ---------------------------------------------------------------
    def save_run(self, run: dict) -> dict:
        payload = json.dumps(run, ensure_ascii=False, sort_keys=True)
        self._conn.execute(
            """INSERT INTO runs (run_id, batch_key, status, input_digest, rule_version,
                                 sites, started_at, finished_at, elapsed_ms,
                                 findings_total, updated_at, payload)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(run_id) DO UPDATE SET
                 status=excluded.status, finished_at=excluded.finished_at,
                 elapsed_ms=excluded.elapsed_ms, findings_total=excluded.findings_total,
                 updated_at=excluded.updated_at, payload=excluded.payload""",
            (run["run_id"], run["batch_key"], run["status"], run["input_digest"],
             run["rule_version"], ",".join(run["sites"]), run["started_at"],
             run.get("finished_at"), int(run.get("elapsed_ms") or 0),
             int(run.get("totals", {}).get("findings_total") or 0),
             run.get("finished_at") or run["started_at"], payload),
        )
        self._conn.commit()
        return run

    # -- 读取 ---------------------------------------------------------------
    def get_run(self, run_id: str) -> dict | None:
        row = self._conn.execute("SELECT payload FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def find_by_batch_key(self, key: str) -> dict | None:
        row = self._conn.execute("SELECT payload FROM runs WHERE batch_key = ?", (key,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def latest_run(self) -> dict | None:
        row = self._conn.execute(
            "SELECT payload FROM runs ORDER BY started_at DESC, run_id DESC LIMIT 1").fetchone()
        return json.loads(row["payload"]) if row else None

    def list_runs(self, limit: int = 30) -> list[dict]:
        rows = self._conn.execute(
            "SELECT run_id, batch_key, status, input_digest, rule_version, started_at,"
            " finished_at, elapsed_ms, findings_total FROM runs"
            " ORDER BY started_at DESC, run_id DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(row) for row in rows]

    def count_runs(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

    def close(self) -> None:
        self._conn.close()
