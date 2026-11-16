#!/usr/bin/env python3
"""样例政务站：静态文件 + 转发规则 + 已撤下页面，容器与测试共用同一实现。

三条真实站点行为：
1. 路径大小写不敏感（对标 IIS），所以目录里写成大写也能打开，属于地址不规范；
2. 旧路径（/pub/、/old/、不带尾斜杠的目录）返回 301，可以有两跳；
3. 已撤下页面返回 410，而不是 404，巡检要分开记。
另有一处故意配置错误：响应头固定声明 utf-8，site-b 的目录页字节实际是
GB18030（页面 meta 里写对了），采信层必须走编码回退链才能读出中文。
"""
from __future__ import annotations

import argparse
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REDIRECTS = {
    "/site-a/pub/n-2024-001": "/site-a/notice/n-2024-001",
    "/site-a/pub/n-2024-002": "/site-a/notice/n-2024-002",
    "/site-a/pub/legacy/beta": "/site-a/pub/n-2024-002",
    "/site-b/zwgk": "/site-b/catalog.html",
    "/site-c/old/index.html": "/site-c/catalog.html",
}
GONE = {"/site-b/notice/withdrawn-2019"}
DETAIL = re.compile(r"^/site-[abc]/notice/[a-z0-9\-]+$")
MIME = {".html": "text/html", ".xml": "application/xml", ".txt": "text/plain"}


def lookup(root: str, path: str) -> tuple[int, str]:
    """返回（状态码, 目标）。目标对 200 是相对 root 的文件，对 301 是跳转目标。"""
    lowered = path.lower()
    stripped = lowered.rstrip("/") or "/"
    if stripped == "/healthz":
        return 200, ""
    if stripped in GONE:
        return 410, ""
    if stripped in REDIRECTS:
        return 301, REDIRECTS[stripped]
    if DETAIL.match(stripped):
        return 200, "pages/detail.html"
    relative = lowered.lstrip("/")
    if lowered.endswith("/") or relative == "":
        index_rel = os.path.join(relative, "index.html") if relative else "index.html"
        if os.path.isfile(os.path.join(root, index_rel)):
            return 200, index_rel
    if relative and os.path.isfile(os.path.join(root, relative)):
        return 200, relative
    if relative and os.path.isdir(os.path.join(root, relative)):
        return 301, stripped + "/"
    return 404, ""


class Handler(BaseHTTPRequestHandler):
    root = "."
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt: str, *args) -> None:  # noqa: ANN002
        return

    def _respond(self, body: bytes, status: int, content_type: str,
                 extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        status, target = lookup(self.root, path)
        if status == 200 and target == "":
            self._respond(b'{"status":"ok"}', 200, "application/json")
            return
        if status == 301:
            self._respond(b"", 301, "text/plain", {"location": target})
            return
        if status == 410:
            self._respond("页面已撤下".encode("utf-8"), 410, "text/html; charset=utf-8")
            return
        if status == 404:
            self._respond("页面不存在".encode("utf-8"), 404, "text/html; charset=utf-8")
            return
        full = os.path.join(self.root, target)
        try:
            with open(full, "rb") as handle:
                body = handle.read()
        except OSError:
            self._respond("页面不存在".encode("utf-8"), 404, "text/html; charset=utf-8")
            return
        ext = os.path.splitext(target)[1].lower()
        mime = MIME.get(ext, "application/octet-stream")
        self._respond(body, 200, f"{mime}; charset=utf-8")

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()


def serve(root: str, port: int) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"root": root})
    httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
    return httpd


def main() -> None:
    parser = argparse.ArgumentParser(description="样例政务站")
    parser.add_argument("--root", default=os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    httpd = serve(args.root, args.port)
    print(f"sample site on :{args.port} root={args.root}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
