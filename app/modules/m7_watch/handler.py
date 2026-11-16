"""M7 入口：变更监测页面、差异 API、回归清单 CSV 与本次快照 JSON。

页面与 API 走同一个 service.watch，筛选只在取数后过滤，不改分桶结论；
导出用完整筛选结果，不受页面单表条数上限影响。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ... import errors, reasons
from ...web import Ctx, get_ctx, render
from . import service

router = APIRouter(tags=["M7 巡检变更监测"])


def _run_or_404(ctx: Ctx, run_id: str | None) -> dict:
    run = ctx.current_run(run_id)
    if run is None:
        raise errors.NotFound("还没有巡检批次，先跑一次巡检", code="E_NO_RUN")
    return run


def _filters(base: str, site: str | None, bucket: str | None) -> dict:
    return {"base": base or "auto", "site": site or "", "bucket": bucket or ""}


@router.get("/api/watch")
def api_watch(base: str = "auto", site: str | None = None, bucket: str | None = None,
              run_id: str | None = None, ctx: Ctx = Depends(get_ctx)) -> dict:
    run = _run_or_404(ctx, run_id)
    return service.watch(ctx.settings, ctx.store, run, base, site, bucket)


@router.get("/api/watch/regressions.csv")
def api_regressions_csv(base: str = "auto", site: str | None = None,
                        bucket: str | None = None, run_id: str | None = None,
                        ctx: Ctx = Depends(get_ctx)) -> Response:
    run = _run_or_404(ctx, run_id)
    result = service.watch(ctx.settings, ctx.store, run, base, site, bucket)
    return Response(content=service.regressions_csv(result),
                    media_type="text/csv; charset=utf-8",
                    headers={"content-disposition":
                             f'attachment; filename="{service.csv_filename(run)}"'})


@router.get("/api/watch/snapshot.json")
def api_snapshot(run_id: str | None = None, ctx: Ctx = Depends(get_ctx)) -> Response:
    run = _run_or_404(ctx, run_id)
    return Response(content=service.snapshot_json(run), media_type="application/json",
                    headers={"content-disposition":
                             f'attachment; filename="{service.snapshot_filename(run)}"'})


@router.get("/watch")
def page_watch(request: Request, base: str = "auto", site: str | None = None,
               bucket: str | None = None, run_id: str | None = None):
    ctx: Ctx = get_ctx(request)
    run = ctx.current_run(run_id)
    data = None
    if run is not None:
        data = service.watch(ctx.settings, ctx.store, run, base, site, bucket)
    chosen = _filters(base, site, bucket)
    return render(request, "watch.html", active="watch", data=data,
                  base=chosen["base"], site=chosen["site"], bucket=chosen["bucket"],
                  buckets=reasons.CHANGE_BUCKETS, sources=service.SOURCES)
