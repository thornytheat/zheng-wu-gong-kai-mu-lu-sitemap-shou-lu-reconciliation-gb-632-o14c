"""M1 入口：触发巡检、查看单批状态、站点与目录页。

页面只读入库结果，不再取数；触发接口是唯一的取数入口。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ... import errors
from ...web import Ctx, get_ctx, render
from ..m5_batches import history
from ..m5_batches import service as batch_service

router = APIRouter(tags=["M1 目录采信"])


def _crawl_payload(result: dict) -> dict:
    run = result["run"]
    return {"status": run["status"], "run_id": run["run_id"],
            "batch_key": run["batch_key"], "reused": result["reused"],
            "note": result["note"], "stage_state": run.get("stage_state", {}),
            "stages": run.get("stages", []), "totals": run.get("totals", {}),
            "resources": len(run.get("resources", [])),
            "conflicts": len(run.get("conflicts", [])),
            "quarantine": len(run.get("quarantine", []))}


@router.post("/api/crawl")
def api_crawl(payload: dict | None = None, ctx: Ctx = Depends(get_ctx)) -> dict:
    body = payload or {}
    sites = body.get("sites")
    if sites is not None and not isinstance(sites, list):
        raise errors.BadRequest("sites 必须是数组", code="E_BAD_SITE")
    result = batch_service.run(ctx.settings, ctx.store,
                               mode=str(body.get("mode") or "full"),
                               stop_after=body.get("stop_after"),
                               resume_of=body.get("resume_of"),
                               sites=[str(s) for s in sites] if sites else None)
    return _crawl_payload(result)


@router.get("/api/crawl/{run_id}")
def api_crawl_status(run_id: str, ctx: Ctx = Depends(get_ctx)) -> dict:
    run = ctx.store.get_run(run_id)
    if run is None:
        raise errors.NotFound(f"批次 {run_id} 不存在", code="E_NO_RUN")
    return {"run_id": run["run_id"], "status": run["status"],
            "stage_state": run.get("stage_state", {}),
            "stages": history.stage_rows(run),
            "totals": run.get("totals", {}),
            "resources": run.get("resources", []),
            "defect_summary": run.get("defect_summary", {})}


@router.get("/")
def page_run(request: Request):
    ctx: Ctx = get_ctx(request)
    run = ctx.current_run()
    return render(request, "run.html", active="run", run=run,
                  stages=history.stage_rows(run) if run else [],
                  resources=(run or {}).get("resources", []),
                  reason_counts=(run or {}).get("reason_counts", []),
                  batch_list=history.summary(ctx.store))


@router.get("/sites")
def page_sites(request: Request, site: str | None = None):
    ctx: Ctx = get_ctx(request)
    run = ctx.current_run()
    pages = [p for p in (run or {}).get("pages", []) if not site or p["site"] == site]
    entries = [c for c in (run or {}).get("entries", []) if not site or c["site"] == site]
    sitemap = [s for s in (run or {}).get("sitemap", []) if not site or s["site"] == site]
    quarantine = [q for q in (run or {}).get("quarantine", [])
                  if not site or q["site"] == site]
    return render(request, "catalog.html", active="sites", pages=pages,
                  entries=entries[:120], catalog_total=len(entries),
                  sitemap=sitemap, quarantine=quarantine[:60],
                  quarantine_total=len(quarantine),
                  conflicts=(run or {}).get("conflicts", []),
                  notes=(run or {}).get("notes", []),
                  site=site or "")
