# 样例数据

## 在线样例站 `sample_site/`

三站目录页 + sitemap，由 `sample_site/serve.py` 提供（容器内 `sample-site` 服务，
测试里由 conftest 起同一份实现）。真实缺陷分布见 `docs/DEPTH.md` 的陷阱表。

- `site-a/`：主站，当前属性写法；sitemap 带 UTF-8 BOM、CRLF、相对 loc、
  `lastmod` 冲突、大写主机、跨域 loc、缺 loc 的 url 块。
- `site-b/`：目录页字节为 GB18030（响应头错标 utf-8），锚点用旧属性
  `data-bh/data-bm/data-bt`；sitemap 尾部缺 `</urlset>`。
- `site-c/`：干净站，只有跟踪参数与旧入口两条脏点。

## 退化样例 `sample_data/degenerate/`

采信层空态与截断的三种结论分开验证，各一个文件：

| 文件 | 结论 |
|---|---|
| `sitemap_zero_bytes.xml` | `SITEMAP_EMPTY_BODY`（响应体 0 字节） |
| `sitemap_header_only.xml` | `SITEMAP_HEADER_ONLY`（只有声明，无 urlset） |
| `sitemap_empty.xml` | `EMPTY_SITEMAP`（有 urlset，0 条 url） |
| `sitemap_truncated.xml` | `SITEMAP_TRUNCATED`（缺 `</urlset>`，已解析块保留） |
| `catalog_bom_crlf.html` | BOM 剥离 + CRLF 不影响条目行号 |
