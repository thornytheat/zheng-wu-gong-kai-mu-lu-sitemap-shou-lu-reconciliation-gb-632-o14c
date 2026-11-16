"""原因码与缺陷分类的唯一来源。

三处共用同一张表，避免页面、导出、测试各写一份：
- 隔离行原因码（采信阶段：编码、块残缺、重复、越界）；
- 探测原因码（状态码与传输错误）；
- 缺陷分类（三向对账输出的稳定分类）。
分类的判定优先级写在 m3_reach/classify.py，本模块只负责命名与文案。
"""
from __future__ import annotations

LEVEL_LABELS = {"error": "错误", "warn": "警告", "info": "提示"}

# 采信与探测阶段的原因码
CODES: dict[str, dict[str, str]] = {
    "EMPTY_SITEMAP": {"level": "warn", "label": "空 sitemap（仅 urlset）", "note": "0 条 loc，按空态处理"},
    "SITEMAP_HEADER_ONLY": {"level": "warn", "label": "sitemap 仅声明无 url", "note": "只有命名空间声明"},
    "SITEMAP_MISSING": {"level": "error", "label": "sitemap 不存在", "note": "站点未提供 sitemap"},
    "SITEMAP_TRUNCATED": {"level": "error", "label": "sitemap 尾部截断", "note": "缺 </urlset> 或末块未闭合"},
    "SITEMAP_EMPTY_BODY": {"level": "error", "label": "sitemap 空响应", "note": "响应体为 0 字节"},
    "BLOCK_NO_LOC": {"level": "error", "label": "url 块缺 loc", "note": "块内必填 loc 缺失"},
    "BLOCK_NO_LASTMOD": {"level": "info", "label": "url 块缺 lastmod", "note": "允许为空，不计入冲突"},
    "DUP_LOC_SAME": {"level": "info", "label": "重复 loc 且 lastmod 相同", "note": "保留首条"},
    "DUP_LOC_CONFLICT": {"level": "warn", "label": "重复 loc 且 lastmod 冲突", "note": "保留较新 lastmod，另一条入冲突表"},
    "LOC_OFFSITE": {"level": "warn", "label": "loc 跨域", "note": "主机不在站点清单内"},
    "LOC_RELATIVE": {"level": "info", "label": "loc 为相对路径", "note": "按 sitemap 地址补全"},
    "CATALOG_ROW_NO_HREF": {"level": "error", "label": "目录行缺 href", "note": "锚点无地址"},
    "CATALOG_ROW_FRAGMENT": {"level": "info", "label": "目录行仅片段", "note": "href 以 # 开头，不是条目"},
    "CATALOG_ROW_SCRIPT": {"level": "error", "label": "目录行脚本地址", "note": "href 为 javascript:/mailto: 等"},
    "CATALOG_ROW_EMPTY_TEXT": {"level": "warn", "label": "目录行标题为空", "note": "锚点无可读文本"},
    "CATALOG_PAGE_FAILED": {"level": "error", "label": "目录页取数失败", "note": "状态码非 200"},
    "CHARSET_FALLBACK": {"level": "info", "label": "按回退链解码", "note": "声明与实际编码不一致"},
    "CHARSET_UNKNOWN": {"level": "error", "label": "编码无法识别", "note": "回退链全部失败"},
    "TRACKING_PARAM": {"level": "info", "label": "带跟踪参数", "note": "规范化时丢弃"},
    "FRAGMENT_ONLY": {"level": "info", "label": "带片段", "note": "规范化时丢弃"},
    "SCOPE_OFFSITE": {"level": "warn", "label": "超出站点清单", "note": "不参与三向对账"},
    "BAD_URL": {"level": "error", "label": "地址非法", "note": "无法解析为主机+路径"},
    "PROBE_TIMEOUT": {"level": "error", "label": "探测超时", "note": "传输层超时"},
    "PROBE_ERROR": {"level": "error", "label": "探测失败", "note": "连接被拒或协议错误"},
    "PROBE_5XX": {"level": "error", "label": "服务端错误", "note": "5xx 状态码"},
    "PROBE_404": {"level": "error", "label": "页面不存在", "note": "404 状态码"},
    "PROBE_410": {"level": "error", "label": "页面已撤下", "note": "410 状态码"},
    "PROBE_REDIRECT_LOOP": {"level": "error", "label": "跳转成环", "note": "跳转链回到已访问地址"},
    "PROBE_REDIRECT_LIMIT": {"level": "error", "label": "跳转超过上限", "note": "未回到已访问地址但超过跳转上限"},
    "CHAIN_CYCLE": {"level": "error", "label": "跳转成环", "note": "跳转链回到已访问地址，环内地址只计一次"},
    "CHAIN_LIMIT": {"level": "error", "label": "链超过上限", "note": "未成环但超过跳转上限，与环分开记"},
    "BASIS_SHIFT": {"level": "warn", "label": "相对路径基准不同", "note": "同一写法按不同基准补全，不计新增也不计消失"},
    "WATCH_NO_BASE": {"level": "info", "label": "无对比基准", "note": "库里只有本次巡检，没有可比的上次"},
    "WATCH_SAMPLE": {"level": "info", "label": "读样例快照", "note": "库里没有上次，按样例快照对比"},
    "RESUME_NO_STAGE": {"level": "info", "label": "无剩余阶段", "note": "续跑无事可做"},
    "REPLAY_REUSED": {"level": "info", "label": "同输入复用结果", "note": "命中批次键，不新增行"},
    "SCHEMA_LEGACY": {"level": "info", "label": "旧属性映射", "note": "老目录页属性名映射到契约字段"},
}

# 规范化改写痕迹 → 页面文案
NORMALIZE_NOTES: dict[str, str] = {
    "scheme": "协议改写",
    "relative": "补全相对地址",
    "case": "大小写统一",
    "trailing_slash": "去尾斜杠",
    "duplicate_slash": "合并斜杠",
    "default_port": "去默认端口",
    "tracking": "去跟踪参数",
    "param_order": "参数排序",
    "fragment": "去片段",
}

# 缺陷分类：三向对账的稳定输出，页面与导出直接引用
CATEGORIES: dict[str, str] = {
    "CATALOG_DEAD": "目录死链",
    "ONLY_IN_SITEMAP_DEAD": "仅收录且死链",
    "REDIRECT_CHAIN": "跳转链",
    "DUPLICATE_SLUG": "重复条目",
    "ONLY_IN_CATALOG": "漏收录",
    "ONLY_IN_SITEMAP_ALIVE": "目录未登记",
    "CANONICAL_MISMATCH": "地址不规范",
    "OK": "已对平",
}
CATEGORY_ORDER = tuple(CATEGORIES)
DEFECT_CATEGORIES = tuple(c for c in CATEGORY_ORDER if c != "OK")

# M7 变更分桶：两次巡检同一地址的走向。互斥且穷尽，另有新增/消失/基准不同三个独立桶。
CHANGE_BUCKETS: dict[str, dict[str, str]] = {
    "new_dead": {"level": "error", "label": "新增死链", "note": "上次可达，本次死链"},
    "new_redirect": {"level": "warn", "label": "新恶化", "note": "上次 200，本次要跳转"},
    "recovered": {"level": "ok", "label": "已修复", "note": "上次死链，本次可达"},
    "improved": {"level": "warn", "label": "已改善", "note": "上次死链，本次能打开但要跳转"},
    "still_dead": {"level": "error", "label": "仍未修复", "note": "上次死链，本次还是死链"},
    "still_redirect": {"level": "warn", "label": "仍为跳转", "note": "两次都要跳转"},
    "unchanged": {"level": "ok", "label": "未变化", "note": "两次状态相同"},
    "added": {"level": "info", "label": "新增地址", "note": "本次新出现的地址"},
    "removed": {"level": "info", "label": "消失地址", "note": "上次有、本次没有"},
    "basis": {"level": "warn", "label": "基准不同", "note": "同一写法按不同基准补全，需人工确认"},
}
CHANGE_ORDER = tuple(CHANGE_BUCKETS)
ACTIONABLE_BUCKETS = ("new_dead", "new_redirect", "still_dead", "improved", "basis")
# 分桶优先级给页面排序用：越靠前越要先看
CHANGE_RANK = {bucket: index for index, bucket in enumerate(CHANGE_ORDER)}


def change_label(bucket: str) -> str:
    return CHANGE_BUCKETS.get(bucket, {}).get("label", bucket)


def change_level(bucket: str) -> str:
    return CHANGE_BUCKETS.get(bucket, {}).get("level", "info")


def change_note(bucket: str) -> str:
    return CHANGE_BUCKETS.get(bucket, {}).get("note", "")


def change_rank(bucket: str) -> int:
    return CHANGE_RANK.get(bucket, len(CHANGE_RANK))



def label(code: str) -> str:
    if code in CATEGORIES:
        return CATEGORIES[code]
    return CODES.get(code, {}).get("label", code)


def level(code: str) -> str:
    return CODES.get(code, {}).get("level", "info")


def describe(code: str) -> dict[str, str]:
    entry = CODES.get(code) or {"level": "info", "label": CATEGORIES.get(code, code),
                                "note": code}
    return {"code": code, "label": entry["label"], "level": entry["level"],
            "note": entry["note"]}


def note_label(code: str) -> str:
    return NORMALIZE_NOTES.get(code, label(code))


def group_of(code: str) -> str:
    """原因码分组：采信 / 规范化 / 探测 / 变更 / 批次。"""
    if code.startswith(("SITEMAP_", "BLOCK_", "DUP_LOC", "CATALOG_ROW", "CHARSET")):
        return "采信"
    if code.startswith(("TRACKING", "FRAGMENT", "SCOPE", "BAD_URL")):
        return "规范化"
    if code in NORMALIZE_NOTES:
        return "规范化"
    if code.startswith("PROBE_"):
        return "探测"
    if code.startswith(("CHAIN_", "BASIS_", "WATCH_")):
        return "变更"
    return "批次"
