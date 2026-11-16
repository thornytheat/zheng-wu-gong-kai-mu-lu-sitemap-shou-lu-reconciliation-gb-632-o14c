"""M5 编排：采信 → 探测 → 对账三阶段串起来，管批次键、幂等与续跑。

幂等的依据是批次键：站点集合 + 输入摘要 + 规则版本。同键同 run_id，
重跑直接返回已入库的那份，不新增行；换了样例站字节就换键，成为新批次。
"""
from __future__ import annotations

import time

from ... import config, errors, manifest
from ..m1_catalog import fetch as fetch_mod
from ..m1_catalog import service as crawl_service
from ..m2_url import service as url_service
from ..m3_reach import service as reach_service
from ..m4_reconcile import service as reconcile_service
from ..m6_defects import service as defect_service
from . import history, state


def _payload(run: dict, reused: bool, note: str = "") -> dict:
    return {"run": run, "reused": reused, "note": note,
            "run_id": run["run_id"], "status": run["status"],
            "stage_state": run.get("stage_state", {}),
            "totals": run.get("totals", {})}


def run(settings, store, mode: str = "full", stop_after: str | None = None,
        resume_of: str | None = None, sites: list[str] | None = None) -> dict:
    if mode not in ("full", "resume"):
        raise errors.BadRequest("mode 只支持 full / resume", code="E_BAD_MODE")
    stop = state.validate_stop(stop_after)
    if sites:
        unknown = [code for code in sites if code not in config.SITE_BY_CODE]
        if unknown:
            raise errors.BadRequest(f"未知站点 {', '.join(unknown)}", code="E_BAD_SITE")
    if mode == "resume":
        return resume(settings, store, resume_of, stop)
    return full(settings, store, stop, sites)


def full(settings, store, stop: str | None, sites: list[str] | None) -> dict:
    started_at = manifest.now_utc()
    clock = time.monotonic()
    fetcher = fetch_mod.make_fetcher(settings)
    crawl = crawl_service.crawl_stage(settings, fetcher, sites)
    digest = manifest.digest_of(crawl["resources"])
    key = manifest.batch_key(crawl["sites"], digest, settings.rule_version)
    run_id = manifest.run_id_for(key)

    existing = store.find_by_batch_key(key)
    if existing is not None and existing.get("status") == "done" and stop is None:
        return _payload(existing, reused=True, note="REPLAY_REUSED")

    prepared = url_service.prepare(crawl["catalog"], crawl["sitemap"])
    stages = [crawl["stage"]]
    probes: list[dict] = []
    reconciled: dict = {}
    if stop == "crawl":
        done = ["crawl"]
        status = "partial"
    else:
        probed = reach_service.probe_stage(settings, fetcher, prepared)
        probes = probed["rows"]
        stages.append(probed["stage"])
        if stop == "probe":
            done = ["crawl", "probe"]
            status = "partial"
        else:
            reconciled = reconcile_service.reconcile_stage(prepared["keys"], probes, crawl)
            stages.append(reconciled["stage"])
            done = list(config.STAGES)
            status = "done" if reconciled["all_balanced"] else "failed"

    accounts = reconciled.get("accounts") or reconcile_service.accounts_only(
        prepared["keys"], probes)
    result = {
        "run_id": run_id,
        "batch_key": key,
        "status": status,
        "sites": list(crawl["sites"]),
        "input_digest": digest,
        "rule_version": settings.rule_version,
        "started_at": started_at,
        "finished_at": manifest.now_utc(),
        "elapsed_ms": int((time.monotonic() - clock) * 1000),
        "params": {"mode": "full", "stop_after": stop or "all",
                   "sites": list(crawl["sites"]), "max_hops": settings.max_hops,
                   "eval_date": settings.eval_date},
        "stage_state": state.state(done, status),
        "stages": stages,
        "resources": crawl["resources"],
        "pages": crawl["pages"],
        "catalog": crawl["catalog"],
        "sitemap": crawl["sitemap"],
        "keys": prepared["keys"],
        "entries": prepared["entries"],
        "probes": probes,
        "quarantine": crawl["quarantine"] + prepared["quarantine"],
        "notes": crawl["notes"] + prepared["notes"],
        "conflicts": crawl["conflicts"],
        "accounts": accounts,
        "totals": accounts,
        "crosstab": reconciled.get("crosstab", {}),
        "by_site": reconciled.get("by_site", []),
        "explain": reconciled.get("explain", []),
        "replay": {"reused": False, "at": started_at, "of": None},
    }
    _finish(result)
    store.save_run(result)
    return _payload(result, reused=False)


def resume(settings, store, resume_of: str | None, stop: str | None) -> dict:
    if not resume_of:
        raise errors.BadRequest("续跑需要 resume_of", code="E_RESUME_TARGET")
    result = store.get_run(resume_of)
    if result is None:
        raise errors.NotFound(f"批次 {resume_of} 不存在", code="E_NO_RUN")
    plan = state.plan(result)
    if not plan["pending"]:
        return _payload(result, reused=True, note="RESUME_NO_STAGE")

    clock = time.monotonic()
    done = list(plan["done"])
    stages = [s for s in result["stages"] if s["stage"] in done]
    prepared = url_service.prepare(result["catalog"], result["sitemap"])
    probes = list(result.get("probes") or [])
    reconciled: dict = {}
    fetcher = fetch_mod.make_fetcher(settings)

    if "probe" not in done:
        probed = reach_service.probe_stage(settings, fetcher, prepared)
        probes = probed["rows"]
        stages.append(probed["stage"])
        done.append("probe")
        if stop == "probe":
            result.update({"status": "partial", "stage_state": state.state(done, "partial")})
            result["probes"] = probes
            result["stages"] = stages
            result["elapsed_ms"] = int((time.monotonic() - clock) * 1000)
            _finish(result)
            store.save_run(result)
            return _payload(result, reused=False, note="RESUME_STOPPED")

    if "reconcile" not in done:
        reconciled = reconcile_service.reconcile_stage(prepared["keys"], probes,
                                                       {"pages": result["pages"]})
        stages.append(reconciled["stage"])
        done.append("reconcile")

    accounts = reconciled.get("accounts") or reconcile_service.accounts_only(
        prepared["keys"], probes)
    status = "done" if accounts["all_balanced"] else "failed"
    result.update({
        "status": status,
        "finished_at": manifest.now_utc(),
        "elapsed_ms": int((time.monotonic() - clock) * 1000),
        "stage_state": state.state(done, status, resume_of=resume_of),
        "stages": stages,
        "keys": prepared["keys"],
        "entries": prepared["entries"],
        "probes": probes,
        "quarantine": result["quarantine"] + prepared["quarantine"],
        "accounts": accounts,
        "totals": accounts,
        "crosstab": reconciled.get("crosstab", result.get("crosstab", {})),
        "by_site": reconciled.get("by_site", result.get("by_site", [])),
        "explain": reconciled.get("explain", result.get("explain", [])),
        "replay": {"reused": False, "at": manifest.now_utc(), "of": resume_of},
    })
    _finish(result)
    store.save_run(result)
    return _payload(result, reused=False, note="RESUME_DONE")


def _finish(result: dict) -> None:
    result["defects"] = defect_service.build_defects(result)
    result["reason_counts"] = manifest.reason_distribution(
        list(result["quarantine"]) + [
            {"reason": row["reason"]} for row in result.get("probes") or []
            if row.get("reason")])
    result["defect_summary"] = defect_service.summarize(result["defects"])


def list_batches(store) -> dict:
    return history.summary(store)
