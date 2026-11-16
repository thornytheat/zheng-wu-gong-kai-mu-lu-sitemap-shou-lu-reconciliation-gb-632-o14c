"""M3 入口：可达性明细页与 API，支持按站点、分类、死链过滤。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ... import errors, reasons
from ...web import Ctx, get_ctx, render

router = APIRouter(tags=["M3 可达性"])


def _filter(run: dict | None, site: str | None, category: str | None,
            dead_only: bool) -> list[dict]:
    rows = list((run or {}).get("probes", []))
    if site:
        rows = [r for r in rows if r["site"] == site]
    if category:
        rows = [r for r in rows if r["category"] == category]
    if dead_only:
        rows = [r for r in rows if r["status"] == 0 or r["status"] >= 400]
    return rows


@router.get("/api/reachability")
def api_reachability(site: str | None = None, category: str | None = None,
                     dead_only: bool = Query(False),
                     run_id: str | None = None,
                     ctx: Ctx = Depends(get_ctx)) -> dict:
    if category and category not in reasons.CATEGORIES:
        raise errors.BadRequest(f"未知分类 {category}", code="E_BAD_CATEGORY")
    run = ctx.current_run(run_id)
    if run is None:
        raise errors.NotFound("还没有巡检批次", code="E_NO_RUN")
    rows = _filter(run, site, category, dead_only)
    return {"run_id": run["run_id"], "total": len(run.get("probes", [])),
            "count": len(rows), "categories": reasons.CATEGORIES, "rows": rows}


@router.get("/reach")
def page_reach(request: Request, site: str | None = None,
               category: str | None = None, dead_only: bool = False):
    ctx: Ctx = get_ctx(request)
    run = ctx.current_run()
    rows = _filter(run, site, category, dead_only)
    return render(request, "reach.html", active="reach", rows=rows,
                  total=len((run or {}).get("probes", [])),
                  site=site or "", category=category or "",
                  dead_only=dead_only, categories=reasons.CATEGORIES)
