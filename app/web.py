"""模板渲染与共享视图上下文。

页面只读 store，不做业务计算；数字格式化统一在这里，避免每页各写一套。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from . import config, manifest, reasons

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

NAV = (
    ("/", "巡检运行", "run"),
    ("/sites", "站点与目录", "sites"),
    ("/reach", "可达性明细", "reach"),
    ("/reconcile", "对账缺陷", "reconcile"),
    ("/batches", "批次历史", "batches"),
    ("/defects", "缺陷单", "defects"),
    ("/watch", "变更监测", "watch"),
)
RUN_STATUS = {"done": "完成", "partial": "部分完成", "failed": "失败", "running": "运行中"}


@dataclass
class Ctx:
    settings: config.Settings
    store: object

    def current_run(self, run_id: str | None = None) -> dict | None:
        if run_id:
            return self.store.get_run(run_id)
        return self.store.latest_run()


def get_ctx(request: Request) -> Ctx:
    return request.app.state.ctx


def fmt_num(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, Decimal)):
        return f"{int(value):,}" if isinstance(value, int) else f"{value:,}"
    return str(value)


def fmt_pct(value) -> str:
    if value in (None, ""):
        return "—"
    return f"{Decimal(str(value)) * 100:.2f}%"


def fmt_bytes(value) -> str:
    if not value:
        return "0 B"
    size = float(value)
    for unit in ("B", "KB", "MB"):
        if size < 1024 or unit == "MB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} MB"


def setup(app) -> None:
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    env = templates.env
    env.filters["num"] = fmt_num
    env.filters["pct"] = fmt_pct
    env.filters["bytes"] = fmt_bytes
    env.filters["localts"] = manifest.local_stamp
    env.filters["reason"] = reasons.label
    env.filters["category"] = reasons.label
    env.filters["level"] = lambda code: reasons.LEVEL_LABELS.get(reasons.level(code), "提示")
    env.filters["group"] = reasons.group_of
    env.filters["note_label"] = reasons.note_label
    env.filters["attr"] = lambda code: {"current": "新属性", "legacy": "旧属性"}.get(code, "未登记")
    env.filters["runstatus"] = lambda s: RUN_STATUS.get(s, s or "—")
    env.filters["short"] = lambda text, n=42: (text if len(str(text)) <= n else str(text)[:n] + "…")
    env.globals["NAV"] = NAV
    env.globals["SITES"] = config.SITES
    env.globals["RULE_VERSION"] = config.RULE_VERSION
    env.globals["STAGE_FLOW"] = config.STAGE_FLOW
    app.state.templates = templates


def render(request: Request, name: str, **context) -> object:
    ctx: Ctx = request.app.state.ctx
    run_id = context.pop("run_id", None)
    run = ctx.current_run(run_id)
    active = context.pop("active", "")
    label = dict((key, text) for _href, text, key in NAV).get(active, "")
    base = {
        "request": request,
        "nav": NAV,
        "active": active,
        "page_label": label,
        "sites": config.SITES,
        "run": run,
        "run_id": (run or {}).get("run_id"),
        "eval_date": ctx.settings.eval_date,
        "rule_version": config.RULE_VERSION,
        "stage_flow": config.STAGE_FLOW,
        "runs": ctx.store.list_runs(8),
    }
    base.update(context)
    return request.app.state.templates.TemplateResponse(name, base)
