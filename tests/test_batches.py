"""M5 巡检批次：批次键、幂等重跑、停止点与续跑。"""
from __future__ import annotations

import pytest

from app import errors, manifest
from app.modules.m5_batches import service as batch_service, state
from fixtures.expected import FINDINGS, RESOURCES


def test_full_run_records_three_stages(settings, store):
    result = batch_service.run(settings, store)
    run = result["run"]
    assert run["status"] == "done"
    assert run["run_id"].startswith("ra-")
    assert run["stage_state"]["done"] == ["crawl", "probe", "reconcile"]
    assert [stage["stage"] for stage in run["stages"]] == ["crawl", "probe", "reconcile"]
    assert store.count_runs() == 1


def test_rerun_same_input_is_idempotent(settings, store):
    """不变量：同一输入重跑不产生第二行，批次号与数字都不变。"""
    first = batch_service.run(settings, store)["run"]
    second = batch_service.run(settings, store)
    assert second["reused"] is True
    assert second["note"] == "REPLAY_REUSED"
    assert second["run"]["run_id"] == first["run_id"]
    assert second["run"]["totals"]["findings_total"] == FINDINGS
    assert store.count_runs() == 1


def test_stop_after_crawl_keeps_partial(settings, store):
    run = batch_service.run(settings, store, stop_after="crawl")["run"]
    assert run["status"] == "partial"
    assert run["stage_state"]["done"] == ["crawl"]
    assert run["stage_state"]["pending"] == ["probe", "reconcile"]
    assert run["probes"] == []
    assert len(run["entries"]) == 18


def test_resume_finishes_remaining_stages(settings, store):
    partial = batch_service.run(settings, store, stop_after="crawl")["run"]
    plan = state.plan(partial)
    assert plan["next"] == "probe"
    resumed = batch_service.run(settings, store, mode="resume",
                               resume_of=partial["run_id"])["run"]
    assert resumed["status"] == "done"
    assert resumed["stage_state"]["done"] == ["crawl", "probe", "reconcile"]
    assert resumed["totals"]["findings_total"] == FINDINGS
    assert store.count_runs() == 1
    assert resumed["replay"]["of"] == partial["run_id"]


def test_resume_on_finished_run_is_noop(settings, store):
    run = batch_service.run(settings, store)["run"]
    again = batch_service.run(settings, store, mode="resume", resume_of=run["run_id"])
    assert again["reused"] is True
    assert again["note"] == "RESUME_NO_STAGE"
    assert store.count_runs() == 1


def test_bad_stop_stage_rejected(settings, store):
    with pytest.raises(errors.BadRequest):
        batch_service.run(settings, store, stop_after="export")
    with pytest.raises(errors.NotFound):
        batch_service.run(settings, store, mode="resume", resume_of="ra-000000000000")
    with pytest.raises(errors.BadRequest):
        batch_service.run(settings, store, mode="nope")


def test_unknown_site_rejected(settings, store):
    with pytest.raises(errors.BadRequest):
        batch_service.run(settings, store, sites=["site-z"])


def test_stage_state_helpers():
    assert state.validate_stop(None) is None
    assert state.validate_stop("probe") == "probe"
    assert state.pending_after(["crawl", "probe"]) == ["reconcile"]
    assert state.next_stage(["crawl", "probe", "reconcile"]) is None


def test_manifest_is_recomputable(settings, store):
    run = batch_service.run(settings, store)["run"]
    doc = manifest.build_manifest(run)
    assert doc["run_id"] == run["run_id"]
    assert doc["input_digest"] == run["input_digest"]
    assert len(doc["resources"]) == RESOURCES
    assert doc["totals"]["all_balanced"] is True
    assert doc["rule_version"] == run["rule_version"]


def test_batches_api_lists_single_run(client_with_run):
    body = client_with_run.get("/api/batches").json()
    assert body["count"] == 1
    assert body["rows"][0]["findings_total"] == FINDINGS
    detail = client_with_run.get(f"/api/batches/{body['rows'][0]['run_id']}").json()
    assert len(detail["stages"]) == 3
    assert len(detail["resources"]) == RESOURCES
