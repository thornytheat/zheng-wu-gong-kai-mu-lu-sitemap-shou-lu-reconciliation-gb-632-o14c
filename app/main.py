"""应用装配：配置 → 存储 → 模板 → 七个功能模块路由。

用工厂函数而不是模块级 app，测试可以给每个用例一个临时库和一个本地样例站。
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, errors, web
from .modules.m1_catalog import handler as m1_handler
from .modules.m2_url import handler as m2_handler
from .modules.m3_reach import handler as m3_handler
from .modules.m4_reconcile import handler as m4_handler
from .modules.m5_batches import handler as m5_handler
from .modules.m6_defects import handler as m6_handler
from .modules.m7_watch import handler as m7_handler
from .store import Store

MODULES = (m1_handler, m2_handler, m3_handler, m4_handler, m5_handler, m6_handler,
           m7_handler)
PAGE_PATHS = ("/", "/sites", "/reach", "/reconcile", "/batches", "/defects", "/watch",
              "/healthz")


def create_app(settings: config.Settings | None = None) -> FastAPI:
    settings = settings or config.Settings.from_env()
    app = FastAPI(
        title="sitemapaudit 政务公开目录与收录对账",
        description="采信三站目录与 sitemap → 地址规范化 → 可达性探测 → 三向对账 → 缺陷单",
        version=settings.rule_version,
    )
    app.state.settings = settings
    app.state.store = Store(settings.db_path)
    app.state.ctx = web.Ctx(settings=settings, store=app.state.store)
    web.setup(app)
    app.mount("/static", StaticFiles(directory=str(web.STATIC_DIR)), name="static")
    for module in MODULES:
        app.include_router(module.router)
    errors.install_handlers(app)

    # 运维习惯用 curl -I 探活，页面路径支持 HEAD，只回头部不渲染模板
    def _head_ok() -> Response:
        return Response(status_code=200, media_type="text/html; charset=utf-8")

    for path in PAGE_PATHS:
        app.add_api_route(path, _head_ok, methods=["HEAD"], include_in_schema=False)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict:
        return {"status": "ok", "rule_version": settings.rule_version,
                "eval_date": settings.eval_date, "sites": list(config.SITE_CODES)}

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError):  # noqa: ANN001
        return JSONResponse(status_code=400,
                            content={"error": "E_BAD_REQUEST", "message": str(exc)})

    return app
