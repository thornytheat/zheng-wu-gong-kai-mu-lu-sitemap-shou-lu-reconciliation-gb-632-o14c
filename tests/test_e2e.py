"""端到端：从样例站一路走到缺陷导出；以及失败输入的错误码。"""
from __future__ import annotations

from fixtures.expected import FINDINGS, PROBED


def test_end_to_end_from_sample_site(client):
    crawl = client.post("/api/crawl", json={})
    assert crawl.status_code == 200
    body = crawl.json()
    assert body["status"] == "done"
    assert body["reused"] is False
    run_id = body["run_id"]

    detail = client.get(f"/api/crawl/{run_id}").json()
    assert detail["status"] == "done"
    assert len(detail["resources"]) == 7

    reconcile = client.get("/api/reconcile").json()
    assert reconcile["accounts"]["findings_total"] == FINDINGS
    assert reconcile["accounts"]["coverage"] == "0.4706"
    assert reconcile["crosstab"]["total"] == PROBED

    defects = client.get("/api/defects").json()
    assert defects["total"] == FINDINGS
    assert defects["rows"][0]["defect_no"] == "DF-0001"

    csv_response = client.get("/api/defects.csv")
    assert "DF-0001" in csv_response.text
    manifest = client.get("/api/export/manifest.json").json()
    assert manifest["run_id"] == run_id


def test_all_pages_render(client_with_run):
    for path in ("/", "/sites", "/reach", "/reconcile", "/batches", "/defects"):
        response = client_with_run.get(path)
        assert response.status_code == 200, path
        assert "河州市政务公开办" in response.text
        assert "制表" in response.text


def test_failure_inputs_return_4xx(client):
    bad_url = client.post("/api/url/normalize", json={"url": "javascript:alert(1)"})
    assert bad_url.status_code == 400
    assert bad_url.json()["error"] == "E_BAD_URL"

    empty_url = client.post("/api/url/normalize", json={"url": "   "})
    assert empty_url.status_code == 400

    no_run = client.get("/api/reconcile")
    assert no_run.status_code == 404
    assert no_run.json()["error"] == "E_NO_RUN"

    bad_mode = client.post("/api/crawl", json={"mode": "nope"})
    assert bad_mode.status_code == 400
    assert bad_mode.json()["error"] == "E_BAD_MODE"

    missing = client.get("/api/crawl/ra-not-exist")
    assert missing.status_code == 404


def test_rerun_keeps_run_id_and_digest(client):
    first = client.post("/api/crawl", json={}).json()
    manifest_first = client.get("/api/export/manifest.json").json()
    second = client.post("/api/crawl", json={}).json()
    manifest_second = client.get("/api/export/manifest.json").json()
    assert second["reused"] is True
    assert second["run_id"] == first["run_id"]
    assert manifest_first["input_digest"] == manifest_second["input_digest"]
    assert manifest_first["run_id"] == manifest_second["run_id"]
