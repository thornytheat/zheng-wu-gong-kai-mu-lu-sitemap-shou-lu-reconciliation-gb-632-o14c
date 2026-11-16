"""阶段状态与续跑计划：已完成的阶段、剩余阶段、停止点校验。

阶段只有三个（采信 → 探测 → 对账），停止点只能是其中之一；
非法停止点直接 400，不做猜测性纠正。

续跑只复用同一批次里已入库的采信结果（目录行、收录行、资源摘要），
探测与对账重新执行——这两步不改变输入摘要，所以 run_id 不变，
批次键也不变，重跑不会产生第二行。
"""
from __future__ import annotations

from ... import config, errors


def validate_stop(stop_after: str | None) -> str | None:
    if stop_after in (None, "", "all"):
        return None
    if stop_after not in config.STAGES:
        raise errors.BadRequest(
            f"stop_after 只支持 {', '.join(config.STAGES)}", code="E_BAD_STAGE")
    return stop_after


def pending_after(done: list[str]) -> list[str]:
    return [stage for stage in config.STAGES if stage not in done]


def next_stage(done: list[str]) -> str | None:
    remaining = pending_after(done)
    return remaining[0] if remaining else None


def state(done: list[str], status: str, resume_of: str | None = None) -> dict:
    return {"done": list(done), "pending": pending_after(done), "status": status,
            "resume_of": resume_of,
            "flow": config.STAGE_FLOW}


def stages_done(run: dict) -> list[str]:
    return list((run.get("stage_state") or {}).get("done") or [])


def plan(run: dict) -> dict:
    if run is None:
        raise errors.NotFound("批次不存在", code="E_NO_RUN")
    done = stages_done(run)
    pending = pending_after(done)
    return {"run_id": run["run_id"], "status": run["status"], "done": done,
            "pending": pending, "next": next_stage(done),
            "resume_hint": (f"从 {config.STAGE_LABELS[pending[0]]} 继续" if pending
                            else "已完成，无需续跑")}


def can_resume(run: dict) -> bool:
    return bool(pending_after(stages_done(run)))
