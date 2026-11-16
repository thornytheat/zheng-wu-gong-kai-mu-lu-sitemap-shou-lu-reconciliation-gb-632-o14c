"""测试固定装置：本地样例站、临时库、固定评估日。

样例站用 sample_site/serve.py 起真实 HTTP 服务（随机端口），
和容器里跑的是同一份实现，所以跳到/410/编码错标这些行为在测试里也是真的。
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import threading

import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import config                                    # noqa: E402
from app.main import create_app                           # noqa: E402
from app.modules.m1_catalog import fetch as fetch_mod     # noqa: E402
from app.modules.m5_batches import service as batch_service  # noqa: E402
from app.store import Store                               # noqa: E402

EVAL_DATE = "2026-11-15"
DEGENERATE = ROOT / "sample_data" / "degenerate"

MINIMAL_CATALOG = (b"<!DOCTYPE html><html><head><meta charset='utf-8'></head><body>"
                   b"<ol data-role='catalog'></ol></body></html>")


@pytest.fixture(scope="session")
def site_base() -> str:
    spec = importlib.util.spec_from_file_location("gb632_sample_site",
                                                 ROOT / "sample_site" / "serve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    httpd = module.serve(str(ROOT / "sample_site"), 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture()
def settings(tmp_path, site_base) -> config.Settings:
    return config.Settings(db_path=str(tmp_path / "sitemapaudit.sqlite"),
                           sample_site_base=site_base,
                           sample_site_dir=str(ROOT / "sample_site"),
                           eval_date=EVAL_DATE)


@pytest.fixture()
def store(settings) -> Store:
    return Store(settings.db_path)


@pytest.fixture()
def fetcher(settings) -> fetch_mod.MirrorFetcher:
    return fetch_mod.make_fetcher(settings)


@pytest.fixture()
def run(settings, store) -> dict:
    return batch_service.run(settings, store)["run"]


@pytest.fixture()
def partial_run(settings, store) -> dict:
    return batch_service.run(settings, store, stop_after="crawl")["run"]


@pytest.fixture()
def client(settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture()
def client_with_run(client) -> TestClient:
    response = client.post("/api/crawl", json={})
    assert response.status_code == 200
    return client


class StubFetcher:
    """只回放给定字节的取数桩：用来喂退化 sitemap（空/仅声明/截断）。"""

    def __init__(self, sitemap_body: bytes, catalog_body: bytes = MINIMAL_CATALOG,
                 status: int = 200):
        self.sitemap_body = sitemap_body
        self.catalog_body = catalog_body
        self.status = status
        self.calls: list[str] = []

    def resolve(self, url: str):
        return url

    def get(self, url: str) -> fetch_mod.Fetched:
        self.calls.append(url)
        if url.endswith("/sitemap.xml"):
            return fetch_mod.Fetched(url=url, status=self.status, body=self.sitemap_body,
                                     headers={"content-type": "application/xml; charset=utf-8"})
        if url.endswith("/catalog.html"):
            return fetch_mod.Fetched(url=url, status=200, body=self.catalog_body,
                                     headers={"content-type": "text/html; charset=utf-8"})
        return fetch_mod.Fetched(url=url, status=404, error="状态码 404")

    def resource_row(self, fetched, digest):
        return {"url": fetched.url, "status": fetched.status, "bytes": fetched.size,
                "sha256": digest, "error": fetched.error or ""}


class CountingFetcher:
    """统计取数次数的包装：用来证明续跑没有重新采信。"""

    def __init__(self, inner):
        self.inner = inner
        self.calls: list[str] = []

    def resolve(self, url):
        return self.inner.resolve(url)

    def get(self, url):
        self.calls.append(url)
        return self.inner.get(url)

    def resource_row(self, fetched, digest):
        return self.inner.resource_row(fetched, digest)


@pytest.fixture()
def stub_cls():
    return StubFetcher


@pytest.fixture()
def counting_cls():
    return CountingFetcher
