# 深度登记 sitemapaudit

- 规模：中型（文件 81，Python 48，7 个功能模块，测试函数 85，用例 87）
- 核心规则：canonical 规范化 7 步 → 逐跳探测 → 三向分类（7 类 + 对平），四账守恒；两次巡检按同一把比较键做变更分桶
- 使用者与工作流：政务公开办网站编辑，季度巡检 3 站 2.4 万条目录；样例站 → 采信 → 规范化 → 可达性 → 三向对账 → 缺陷单导出 → 与上季度对比出回归清单

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 目录采信 | 触发巡检，看目录页与隔离行 | POST /api/crawl | `app/modules/m1_catalog/service.py` `app/modules/m1_catalog/decode.py` `app/modules/m1_catalog/extract.py` `app/modules/m1_catalog/fetch.py` | `tests/test_catalog.py` |
| M2 URL 规则 | 查契约、试算地址规范化 | GET /api/contract | `app/modules/m2_url/normalize.py` `app/modules/m2_url/contract.py` `app/modules/m2_url/scope.py` | `tests/test_url.py` |
| M3 可达性 | 看逐地址状态码、跳转链与分类 | GET /api/reachability | `app/modules/m3_reach/probe.py` `app/modules/m3_reach/classify.py` | `tests/test_reach.py` |
| M4 三向对账 | 核对四账、交叉表与分类合计 | GET /api/reconcile | `app/modules/m4_reconcile/totals.py` `app/modules/m4_reconcile/compare.py` | `tests/test_reconcile.py` |
| M5 巡检批次 | 查历史、停在中间、续跑 | GET /api/batches | `app/modules/m5_batches/service.py` `app/modules/m5_batches/state.py` `app/modules/m5_batches/history.py` | `tests/test_batches.py` |
| M6 缺陷单 | 按分类筛缺陷、导出 CSV 与清单 | GET /api/defects | `app/modules/m6_defects/defect.py` `app/modules/m6_defects/csv_out.py` `app/modules/m6_defects/service.py` | `tests/test_defects.py` |
| M7 变更监测 | 与上次对比、按站点看趋势、导回归清单 | GET /api/watch | `app/modules/m7_watch/diff.py` `app/modules/m7_watch/chain.py` `app/modules/m7_watch/service.py` | `tests/test_watch.py` |

阶段编排在 `app/modules/m5_batches/service.py`：采信（M1）→ 规范化与探测（M2+M3）→ 对账（M4）→ 缺陷（M6）。
停止点 `stop_after=crawl|probe` 可让每个阶段单独跑；`POST /api/batches/{run_id}/resume` 从剩余阶段接着跑，
已采信的字节不再取一次。

变更对比在 `app/modules/m7_watch/service.py`：挑基准（库内更早批次 → 样例快照）→ 两次快照按比较键配对
（`diff.py`）→ 分桶与回归清单 → 页面与导出同源。跳转环与补全基准的判定在 `chain.py`。

## 陷阱登记

| TRAP | 现象 | 朴素实现会怎样 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | site-b 目录页字节是 GB18030，响应头写 utf-8 | `decode("utf-8")` 直接抛错，或 errors="ignore" 吞成乱码 | 声明 → 回退链 `utf-8-sig/utf-8/gb18030`，失败记 `CHARSET_UNKNOWN` | `app/modules/m1_catalog/decode.py` | `tests/test_catalog.py::test_gb18030_fallback_through_wrong_header` |
| TRAP-02 | sitemap 与目录页带 UTF-8 BOM | 首个标签/属性带 `\ufeff`，规范化后地址多字符 | 解码时 `lstrip("\ufeff")`，行号照原页 | `app/modules/m1_catalog/decode.py` | `tests/test_catalog.py::test_bom_stripped_and_line_numbers_kept` |
| TRAP-05 | url 块缺 loc、目录行缺 href | 静默补空串，条目错位 | 严格块校验，进隔离区并带行号 | `app/modules/m1_catalog/extract.py` | `tests/test_catalog.py::test_quarantine_reason_codes` |
| TRAP-08 | 事项编码 `0070012` 含前导零 | `int()` 后丢零，与 sitemap 对不上 | 全列按字符串保形，禁止 `int()` | `app/modules/m2_url/contract.py` | `tests/test_catalog.py::test_leading_zero_entry_code_kept` |
| TRAP-14 | 同一 loc 出现两次，lastmod 不同 | 后写覆盖，留下较旧的时间 | 冲突表 + 保留较新 lastmod，另一条可导出 | `app/modules/m1_catalog/service.py` | `tests/test_catalog.py::test_duplicate_loc_conflict_keeps_newer_lastmod` |
| TRAP-16 | site-b sitemap 尾部缺 `</urlset>` | 半截 XML 整体报废，或照单全收 | 已解析块保留，整站标记 `SITEMAP_TRUNCATED` | `app/modules/m1_catalog/extract.py` | `tests/test_catalog.py::test_truncated_sitemap_keeps_parsed_blocks` |
| TRAP-17 | 老目录页用 `data-bh/data-bm/data-bt` | `KeyError` 或字段全空 | 契约映射旧属性 → 规范字段，记录属性代别 | `app/modules/m2_url/contract.py` | `tests/test_url.py::test_legacy_attributes_mapped` |
| TRAP-18 | sitemap 0 字节 / 仅声明 / 有 urlset 无 url | 三种都返回"成功 0 条" | 三个稳定原因码分开 | `app/modules/m1_catalog/service.py` | `tests/test_catalog.py::test_empty_sitemap_three_states` |
| TRAP-19 | 一个地址同时是漏收录 + 死链 + 跳转 | 按 if 顺序覆盖，改行代码结论就变 | 规则表带固定优先级，排序后判定；倒序规则表结论不变 | `app/modules/m3_reach/classify.py` | `tests/test_reach.py::test_rule_order_does_not_change_result` |
| TRAP-21 | 只查 sitemap→目录 一个方向 | 漏掉「目录有、sitemap 无」那一半 | 双向核验：ONLY_IN_CATALOG 与 ONLY_IN_SITEMAP_DEAD 同时输出 | `app/modules/m4_reconcile/totals.py` | `tests/test_reconcile.py::test_both_directions_reported` |
| TRAP-27 | 301 环与「超过上限的长链」混为一谈 | 都记跳转成环；同一环从多个入口探测各报一次，清单里同环出现多行 | 未回到已访问地址的超限链记 `CHAIN_LIMIT`；环按环内成员集合合并，多入口只报一次 | `app/modules/m7_watch/chain.py` | `tests/test_watch.py::test_trap27_cycle_grouped_once_and_long_chain_is_not_cycle` |
| TRAP-28 | 同一相对写法分别按目录页地址与 sitemap 地址补全，得到两个键 | 算成一条新增死链加一条消失地址，回归清单出现假新增 | 两侧原始写法相同、补全基准不同的先配成 `BASIS_SHIFT`「基准不同」，不进增删 | `app/modules/m7_watch/diff.py` | `tests/test_watch.py::test_trap28_relative_base_shift_is_basis_not_add_and_remove` |

补充的不变量与端到端：

- 幂等：`tests/test_batches.py::test_rerun_same_input_is_idempotent`（同输入同 run_id，库内只有一行）
- 守恒：`tests/test_reconcile.py::test_status_partition_covers_all_probes`（可达三态之和 = 探测数）
- 分桶：`tests/test_watch.py::test_bucket_table_covers_all_nine_combinations`（9 种状态组合都有归属，新增状态必须补表）
- 不变量：`tests/test_defects.py::test_summary_totals_match_defect_rows`（分类合计 = 站点合计 = 缺陷条数）
- 边界：`tests/test_catalog.py::test_sitemap_with_only_declaration_is_header_only`（只有声明记仅声明）
- 边界：`tests/test_url.py::test_empty_query_value_kept_unless_tracking`（空值参数保留，只丢跟踪参数名）
- 反例：`tests/test_reach.py::test_self_loop_is_cycle_not_hop_limit`（自环算成环，不算链过长）
- 反例：`tests/test_catalog.py::test_naive_utf8_decode_fails_on_site_b`（朴素 utf-8 硬解直接抛错）
- 端到端：`tests/test_e2e.py::test_end_to_end_from_sample_site`（样例站 → 缺陷 CSV → 运行清单）

## 对账规则

- 目录账：`catalog_keys = both + only_in_catalog`
- 收录账：`sitemap_keys = both + only_in_sitemap`
- 可达账：`probed = alive_ok + alive_redirect + dead`（三态互斥：先判死链，再判跳转）
- 缺陷账：`findings_total = Σ 各分类条数`，且 `findings_total = probed − 对平数`
- 覆盖率 = 三向交集（双侧都有 + 200 + 无跳转）/ `catalog_keys`，Decimal 四位小数

## 变更对比规则

- 比较键 = `chain.canonical_input`：小写 + 合并重复斜杠 + 去尾斜杠，三步固定且幂等。
- 分桶 = 上次三态 × 本次三态（9 格固定表）+ 新增 / 消失 / 基准不同。
- 上次死链、本次能打开但要跳转，记「已改善」，与「仍未修复」分开。
- 回归清单 = 新增死链 + 新恶化 + 仍未修复 + 已改善 + 基准不同；已修复与未变化不进。
- 跳转环按环内成员集合合并；样例站当前没有环，判定逻辑由测试喂跳转链覆盖。
- 基准优先级：库内更早的批次 → `sample_data/watch/baseline.json` → 提示无基准。

## 已知不覆盖

- 不解析 `sitemapindex` 索引文件；样例站只有单层 `urlset`。
- 不改写页面：canonical 只做判定与证据，不生成整改后的 HTML。
- 不抓取目录页的详情页正文，可达性只看状态码与跳转链，不做内容比对。
- 变更对比只看三态与跳转链，不比 `lastmod`、标题与正文。
- 趋势只回看 8 批，依赖库里保留的 run payload；删库后趋势从下一批重新累计。
- 并发探测未做：23 个地址串行，2.4 万条真实规模需要加并发与限速（当前未实现，写在这里而不是假装支持）。
