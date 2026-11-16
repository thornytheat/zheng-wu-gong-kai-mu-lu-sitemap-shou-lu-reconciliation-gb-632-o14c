"""M5 入口：批次历史、单批详情、续跑。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ... import errors
from ...web import Ctx, get_ctx, render
from . import history, service

router = APIRouter(tags=["M5 巡检批次"])


def _run_or_404(ctx: Ctx, run_id: str) -> dict:
    run = ctx.store.get_run(run_id)
    if run is None:
        raise errors.NotFound(f"批次 {run_id} 不存在", code="E_NO_RUN")
    return run


@router.get("/api/batches")
def api_batches(ctx: Ctx = Depends(get_ctx)) -> dict:
    return history.summary(ctx.store)


@router.get("/api/batches/{run_id}")
def api_batch_detail(run_id: str, ctx: Ctx = Depends(get_ctx)) -> dict:
    return history.detail(_run_or_404(ctx, run_id))


@router.post("/api/batches/{run_id}/resume")
def api_resume(run_id: str, payload: dict | None = None,
               ctx: Ctx = Depends(get_ctx)) -> dict:
    _run_or_404(ctx, run_id)
    body = payload or {}
    result = service.run(ctx.settings, ctx.store, mode="resume", resume_of=run_id,
                         stop_after=body.get("stop_after"))
    return {"run_id": result["run_id"], "status": result["status"],
            "note": result["note"], "stage_state": result["stage_state"],
            "totals": result["totals"]}


@router.get("/batches")
def page_batches(request: Request, run_id: str | None = None):
    ctx: Ctx = get_ctx(request)
    data = history.summary(ctx.store)
    detail = None
    run = ctx.current_run(run_id)
    if run is not None:
        detail = history.detail(run)
    return render(request, "batches.html", active="batches", batches=data,
                  detail=detail, selected=run_id or ((run or {}).get("run_id")))
