"""M3 可达性：逐跳记录、状态码语义、分类优先级。"""
from __future__ import annotations

import pytest

from app.modules.m1_catalog import fetch
from app.modules.m3_reach import classify, probe
from fixtures.expected import GONE_URL, TWO_HOP_URL


def test_two_hop_chain_recorded(fetcher):
    result = probe.probe(fetcher, TWO_HOP_URL)
    assert result.status == 200
    assert result.hop_count == 2
    assert [hop["status"] for hop in result.hops] == [301, 301]
    assert result.final_url.endswith("/site-a/notice/n-2024-002")
    assert result.dead is False


def test_410_and_404_distinguished(fetcher):
    gone = probe.probe(fetcher, GONE_URL)
    assert gone.status == 410
    assert gone.reason == "PROBE_410"
    missing = probe.probe(fetcher, "http://www.hz.gov.cn/site-a/attach/2026/report.pdf")
    assert missing.status == 404
    assert missing.reason == "PROBE_404"


def test_redirect_loop_stopped():
    class Loop:
        def get(self, url: str) -> fetch.Fetched:
            return fetch.Fetched(url=url, status=301,
                                 headers={"location": "/site-a/loop"})

    result = probe.probe(Loop(), "http://www.hz.gov.cn/site-a/loop")
    assert result.status == 0
    assert result.reason == "PROBE_REDIRECT_LOOP"
    assert result.hop_count == 1


def make(in_catalog=1, in_sitemap=1, status=200, hops=0, notes=(), raw=("a",)):
    return classify.Observation(key="k", site="site-a",
                                url="http://www.hz.gov.cn/site-a/x",
                                in_catalog=in_catalog, in_sitemap=in_sitemap,
                                status=status, hops=hops, raw_forms=list(raw),
                                notes=list(notes))


def test_dead_beats_redirect_and_missing(): 
    """TRAP-19：多条规则同时命中时按固定优先级，死链优先。"""
    assert classify.classify(make(status=404, hops=2))[0] == "CATALOG_DEAD"
    assert classify.classify(make(in_catalog=0, status=410))[0] == "ONLY_IN_SITEMAP_DEAD"


def test_rule_order_does_not_change_result():
    """TRAP-19：把规则表整体倒序，结论不变。"""
    observations = [make(), make(in_catalog=0), make(notes=["tracking"]),
                    make(in_catalog=2), make(status=404), make(hops=1)]
    baseline = [classify.classify(obs)[0] for obs in observations]
    for rules in (tuple(reversed(classify.RULES)),
                  tuple(sorted(classify.RULES, key=lambda item: item[1]))):
        assert [classify.classify(obs, rules)[0] for obs in observations] == baseline


def test_only_in_catalog_and_sitemap_paths():
    assert classify.classify(make(in_sitemap=0))[0] == "ONLY_IN_CATALOG"
    assert classify.classify(make(in_catalog=0))[0] == "ONLY_IN_SITEMAP_ALIVE"
    assert classify.classify(make(hops=1))[0] == "REDIRECT_CHAIN"


def test_canonical_mismatch_needs_a_mismatch_note():
    assert classify.classify(make(notes=["relative"]))[0] == "OK"
    assert classify.classify(make(notes=["relative", "case"]))[0] == "CANONICAL_MISMATCH"
    assert classify.Observation(key="k", site="site-a", url="u", in_catalog=1,
                                in_sitemap=1, status=200, hops=0).changed is False


def test_duplicate_comes_from_one_side_only():
    cross = make(in_catalog=1, in_sitemap=1, notes=["case"])
    assert cross.duplicate is False
    assert classify.classify(cross)[0] == "CANONICAL_MISMATCH"
    assert classify.classify(make(in_catalog=2))[0] == "DUPLICATE_SLUG"
    assert classify.classify(make(in_sitemap=2))[0] == "DUPLICATE_SLUG"


def test_reachability_api_filters(client_with_run):
    body = client_with_run.get("/api/reachability?category=CATALOG_DEAD").json()
    assert body["count"] == 3
    assert body["total"] == 23
    assert all(row["category"] == "CATALOG_DEAD" for row in body["rows"])
    dead = client_with_run.get("/api/reachability?dead_only=true").json()
    assert dead["count"] == 4


def test_reachability_rejects_unknown_category(client_with_run):
    response = client_with_run.get("/api/reachability?category=NOPE")
    assert response.status_code == 400
    assert response.json()["error"] == "E_BAD_CATEGORY"


def test_self_loop_is_cycle_not_hop_limit():
    """反例：一跳回到自己算成环，不是链过长；两者修法不同。"""
    class SelfLoop:
        def get(self, url):
            return fetch.Fetched(url=url, status=301, body=b"",
                                 headers={"location": url})

    result = probe.probe(SelfLoop(), "http://www.hz.gov.cn/site-a/loop")
    assert result.status == 0
    assert result.reason == "PROBE_REDIRECT_LOOP"
    assert result.hop_count == 1
