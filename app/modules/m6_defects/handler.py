"""M6 入口：缺陷单页面、缺陷 API、CSV 与运行清单导出。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ... import errors, reasons
from ...web import Ctx, get_ctx, render
from . import service

router = APIRouter(tags=["M6 缺陷单"])


def _run(ctx: Ctx, run_id: str | None) -> dict:
    run = ctx.current_run(run_id)
    if run is None:
        raise errors.NotFound("还没有巡检批次", code="E_NO_RUN")
    return run


@router.get("/api/defects")
def api_defects(run_id: str | None = None, site: str | None = None,
                category: str | None = None,
                ctx: Ctx = Depends(get_ctx)) -> dict:
    return service.list_defects(_run(ctx, run_id), site, category)


@router.get("/api/defects.csv")
def api_defects_csv(run_id: str | None = None, site: str | None = None,
                    category: str | None = None,
                    ctx: Ctx = Depends(get_ctx)) -> Response:
    run = _run(ctx, run_id)
    body = service.defects_csv(run, site, category)
    return Response(content=body, media_type="text/csv; charset=utf-8",
                    headers={"content-disposition":
                             f'attachment; filename="{service.defects_filename(run)}"'})


@router.get("/api/quarantine.csv")
def api_quarantine_csv(run_id: str | None = None, site: str | None = None,
                       ctx: Ctx = Depends(get_ctx)) -> Response:
    run = _run(ctx, run_id)
    return Response(content=service.quarantine_csv(run, site),
                    media_type="text/csv; charset=utf-8",
                    headers={"content-disposition":
                             f'attachment; filename="{service.quarantine_filename(run)}"'})


@router.get("/api/export/manifest.json")
def api_manifest(run_id: str | None = None, ctx: Ctx = Depends(get_ctx)) -> Response:
    run = _run(ctx, run_id)
    return Response(content=service.manifest_json(run), media_type="application/json",
                    headers={"content-disposition":
                             f'attachment; filename="{service.manifest_filename(run)}"'})


@router.get("/defects")
def page_defects(request: Request, run_id: str | None = None, site: str | None = None,
                 category: str | None = None):
    ctx: Ctx = get_ctx(request)
    run = ctx.current_run(run_id)
    data = {"rows": [], "count": 0, "total": 0,
            "summary": {"total": 0, "by_category": {}, "by_site": {}},
            "categories": reasons.CATEGORIES, "explain": {}}
    if run is not None:
        data = service.list_defects(run, site, category)
    return render(request, "defects.html", active="defects", data=data,
                  rows=data["rows"], site=site or "", category=category or "",
                  categories=reasons.CATEGORIES, explain=data["explain"],
                  summary=data["summary"])
