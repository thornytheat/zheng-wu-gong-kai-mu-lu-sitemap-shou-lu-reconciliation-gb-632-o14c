"""M6 编排：缺陷筛选、缺陷单 CSV、运行清单 JSON。

三种导出都从同一份已入库 run 取数，页面、CSV、manifest 的数字必须一致
（tests/test_defects.py::test_export_matches_page 钉死）。
"""
from __future__ import annotations

from ... import errors, manifest, reasons
from ..m4_reconcile import compare as reconcile_compare
from . import csv_out, defect


def list_defects(run: dict, site: str | None = None,
                 category: str | None = None) -> dict:
    if category and category not in reasons.CATEGORIES:
        raise errors.BadRequest(f"未知分类 {category}", code="E_BAD_CATEGORY")
    rows = list(run.get("defects") or [])
    if site:
        rows = [row for row in rows if row["site"] == site]
    if category:
        rows = [row for row in rows if row["category"] == category]
    return {"run_id": run["run_id"], "total": len(run.get("defects") or []),
            "count": len(rows), "rows": rows,
            "summary": defect.summary(rows),
            "categories": reasons.CATEGORIES,
            "explain": {row["code"]: row["rule"]
                        for row in reconcile_compare.category_explain()}}


def build_defects(run: dict, settings=None) -> list[dict]:
    return defect.build_defects(run, settings)


def summarize(defects: list[dict]) -> dict:
    return defect.summary(defects)


def defects_csv(run: dict, site: str | None = None, category: str | None = None) -> str:
    rows = list_defects(run, site, category)["rows"]
    return csv_out.defects_csv(rows, defect.severity_of)


def quarantine_rows(run: dict, site: str | None = None) -> list[dict]:
    rows = list(run.get("quarantine") or [])
    if site:
        rows = [row for row in rows if row["site"] == site]
    return rows


def quarantine_csv(run: dict, site: str | None = None) -> str:
    return csv_out.quarantine_csv(quarantine_rows(run, site))


def quarantine_filename(run: dict) -> str:
    return csv_out.quarantine_filename(run["run_id"])


def defects_filename(run: dict) -> str:
    return csv_out.filename(run["run_id"])


def manifest_json(run: dict) -> str:
    """运行清单导出：直接复用平台层的清单构造，不再单开一个转发模块。"""
    return manifest.manifest_text(run)


def manifest_filename(run: dict) -> str:
    return f"manifest-{run['run_id']}.json"
