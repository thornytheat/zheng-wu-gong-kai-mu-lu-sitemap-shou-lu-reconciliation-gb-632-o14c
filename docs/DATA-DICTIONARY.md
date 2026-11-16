# 数据字典 sitemapaudit

字段、单位、精度、可空与边界归属都在这里；页面只显示字段名和数字，不重复这些说明。

## 1 数值与编码

| 项 | 规则 |
|---|---|
| 计数 | 整数，`int`；页面千分位展示，导出原样 |
| 覆盖率 | Decimal，四位小数，`ROUND_HALF_UP`；`0.4706` 表示 47.06% |
| 时间戳 | 入库 UTC 秒级 `YYYY-MM-DDTHH:MM:SSZ`，展示转 Asia/Shanghai |
| `lastmod` | 按 sitemap 原文保留到秒，不补时区；比较用字符串序（ISO 8601 可直接比） |
| 状态码 | `int`，HTTP 原值；`0` 表示传输层失败（连接被拒/超时/越界主机） |
| 字节数 | `int`，响应体长度，不含响应头 |
| sha256 | 小写十六进制 64 位，输入资源与运行清单同源 |
| 事项编码 | 字符串，含前导零（`0070012`），禁止 `int()` |

## 2 地址与规范化

规范化 7 步，顺序固定（`app/modules/m2_url/normalize.py`）：

| 步 | 规则 | 产生痕迹 |
|---|---|---|
| scheme | 只接受 `http`/`https`；`javascript:`/`mailto:` 等进隔离区 | — |
| host | 主机小写、去末尾点、去默认端口（80/443） | `case`、`default_port` |
| relative | 相对地址按所在页面地址补全 | `relative` |
| path | 合并重复斜杠、去尾斜杠（根路径除外）、路径整体小写 | `duplicate_slash`、`trailing_slash`、`case` |
| tracking | 丢弃跟踪参数与空值会话参数（清单见 `config.TRACKING_PARAMS`） | `tracking` |
| query | 保留参数按名称+值排序后重建 | `param_order` |
| fragment | 丢弃片段 | `fragment` |

- **比较键** = 规范化后的完整地址（`scheme://host/path?query`）。
- 样例站大小写不敏感（对标 IIS），所以大小写差异算「地址不规范」，不算死链。
- `relative` 与 `param_order` 是正常写法，不参与「地址不规范」判定；
  其余痕迹任一出现即判 `CANONICAL_MISMATCH`（`classify.MISMATCH_NOTES`）。
- 越界地址（主机不在站点清单）不进 key，记 `SCOPE_OFFSITE` / `LOC_OFFSITE`。

## 3 三向与分类

| 集合 | 定义 |
|---|---|
| 目录集 | 目录页 `data-role="catalog"` 区块内锚点可达的 key |
| 收录集 | 站点 `sitemap.xml` 的 loc 规范化后的 key |
| 可达集 | 对 key 发起逐跳探测的末态（`status`、`final_url`、`hops`） |

分类互斥，优先级由大到小：

| 分类 | 条件 | 严重度 |
|---|---|---|
| `CATALOG_DEAD` | 目录有该 key，末态 4xx/传输失败 | 错误 |
| `ONLY_IN_SITEMAP_DEAD` | 仅收录有，末态 4xx | 错误 |
| `REDIRECT_CHAIN` | 可达但跳转 ≥1 次 | 警告 |
| `DUPLICATE_SLUG` | 同侧多条原始写法折叠到同一 key | 警告 |
| `ONLY_IN_CATALOG` | 目录有、收录无 | 警告 |
| `ONLY_IN_SITEMAP_ALIVE` | 收录有、目录未登记 | 提示 |
| `CANONICAL_MISMATCH` | 双侧都有且 200 无跳转，但原始地址含不规范痕迹 | 提示 |
| `OK` | 双侧都有、200、无跳转、无痕迹 | — |

跳转上限 5 跳；超限或成环记 `PROBE_REDIRECT_LOOP`，状态码按 0 处理（死链）。

## 4 四账

| 账 | 等式 |
|---|---|
| 目录账 | `catalog_keys = both + only_in_catalog` |
| 收录账 | `sitemap_keys = both + only_in_sitemap` |
| 可达账 | `probed = alive_ok + alive_redirect + dead` |
| 缺陷账 | `findings_total = Σ 分类条数 = probed − 对平数` |

覆盖率 = 三向交集 / `catalog_keys`。四账任一不成立，整批状态记 `failed`。

## 5 空态三态

| 输入 | 结论码 | 是否算成功 |
|---|---|---|
| 响应体 0 字节 | `SITEMAP_EMPTY_BODY` | 否 |
| 只有 XML 声明，无 `urlset` | `SITEMAP_HEADER_ONLY` | 否 |
| 有 `urlset` 但 0 条 `url` | `EMPTY_SITEMAP` | 否 |
| 缺 `</urlset>` 或末块未闭合 | `SITEMAP_TRUNCATED` | 部分（已解析块保留） |
| 目录页 404/500 | `CATALOG_PAGE_FAILED` | 否 |

## 6 批次与幂等

| 字段 | 规则 |
|---|---|
| `input_digest` | 对 `url\tstatus\tsha256` 排序后取 sha256 |
| `batch_key` | `sha256(站点排序 + input_digest + 规则版本)` |
| `run_id` | `ra-` + `batch_key` 前 12 位；同输入必然同号 |
| 复用 | 同 `batch_key` 且状态 `done` 时直接返回已入库结果，不新增行 |
| 阶段 | `crawl` / `probe` / `reconcile`，`stop_after` 可停在任一阶段 |

## 7 变更监测

快照 `schema = sitemapaudit/watch/1`，一条比较键一行：

| 字段 | 规则 |
|---|---|
| `key` | 比较键：小写 + 合并重复斜杠 + 去尾斜杠（`chain.canonical_input`） |
| `status` | 探测末态，`0` 表示传输层失败 |
| `hop_count` | 跳转次数；`0` 表示未跳转 |
| `chain.kind` | `direct` / `chain` / `cycle` / `limit` |
| `raws` | 原始写法 + 补全基准（`base_kind` = `page` / `sitemap`） |
| `rows` | 同一比较键出现多行时保留较差的一条 |

三态：`status` 为 0 或 ≥400 记 `dead`；否则 `hop_count` > 0 记 `redirect`，其余 `ok`。

分桶（上次 × 本次，9 格固定表，另加三种独立桶）：

| 上次 | 本次 | 分桶 | 级别 |
|---|---|---|---|
| ok | ok | `unchanged` 未变化 | 提示 |
| ok | redirect | `new_redirect` 新恶化 | 警告 |
| ok | dead | `new_dead` 新增死链 | 错误 |
| redirect | ok | `recovered` 已修复 | 正常 |
| redirect | redirect | `still_redirect` 仍为跳转 | 警告 |
| redirect | dead | `new_dead` 新增死链 | 错误 |
| dead | ok | `recovered` 已修复 | 正常 |
| dead | redirect | `improved` 已改善 | 警告 |
| dead | dead | `still_dead` 仍未修复 | 错误 |
| — | 有 | `added` 新增地址 | 提示 |
| 有 | — | `removed` 消失地址 | 提示 |
| 两侧键不同、写法相同 | — | `basis` 基准不同 | 警告 |

回归清单 = `new_dead` + `new_redirect` + `still_dead` + `improved` + `basis`。
`added` / `removed` 不计入回归；`basis` 需人工确认补全基准后再决定归属。
