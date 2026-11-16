"""M4 入口：对账结果页与 API（四账 + 交叉表 + 分类含义）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ... import errors
from ...web import Ctx, get_ctx, render

router = APIRouter(tags=["M4 三向对账"])


def _payload(ctx: Ctx, run_id: str | None) -> dict:
    run = ctx.current_run(run_id)
    if run is None:
        raise errors.NotFound("还没有巡检批次", code="E_NO_RUN")
    return {"run_id": run["run_id"], "status": run["status"],
            "accounts": run.get("accounts", {}),
            "crosstab": run.get("crosstab", {}),
            "by_site": run.get("by_site", []),
            "explain": run.get("explain", []),
            "defects": run.get("defects", [])}


@router.get("/api/reconcile")
def api_reconcile(run_id: str | None = None, ctx: Ctx = Depends(get_ctx)) -> dict:
    return _payload(ctx, run_id)


@router.get("/reconcile")
def page_reconcile(request: Request, run_id: str | None = None):
    ctx: Ctx = get_ctx(request)
    data = _payload(ctx, run_id)
    return render(request, "reconcile.html", active="reconcile", data=data,
                  accounts=data["accounts"], crosstab=data["crosstab"],
                  by_site=data["by_site"], explain=data["explain"])
