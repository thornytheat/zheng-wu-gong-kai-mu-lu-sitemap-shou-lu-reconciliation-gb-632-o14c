"""字段契约与旧版属性映射（schema 演进）。

样例站三站由不同年代建站：老目录页的锚点用 `data-bm`（部门）、`data-bh`（编号）、
`data-bt`（标题），新目录页改成 `data-dept` / `data-code` / `data-title`。
契约把两套写法映射到同一组字段，旧站不迁移也能采信；未登记的属性一律忽略。
"""
from __future__ import annotations

from ... import config, reasons

CURRENT_ATTRS = {
    "data-code": "entry_code",
    "data-dept": "dept_code",
    "data-title": "title",
}

LEGACY_ATTRS = {
    "data-bh": "entry_code",
    "data-bm": "dept_code",
    "data-bt": "title",
    "data-bmname": "dept_name",
}

FIELD_CONTRACT = (
    {"name": "site", "type": "string", "unit": "—", "nullable": False,
     "note": "站点代号，取值固定为 site-a/b/c"},
    {"name": "raw_href", "type": "string", "unit": "—", "nullable": False,
     "note": "目录页原始地址，逐字保留"},
    {"name": "raw_loc", "type": "string", "unit": "—", "nullable": False,
     "note": "sitemap 原始 loc，逐字保留（可能相对路径）"},
    {"name": "url", "type": "string", "unit": "—", "nullable": False,
     "note": "规范化地址，比较与探测都用它"},
    {"name": "entry_code", "type": "string", "unit": "—", "nullable": True,
     "note": "事项编码，含前导零，按字符串保形"},
    {"name": "dept_code", "type": "string", "unit": "—", "nullable": True,
     "note": "部门编码，新旧属性映射到同一字段"},
    {"name": "lastmod", "type": "string", "unit": "UTC", "nullable": True,
     "note": "sitemap 声明时间，原样保留到秒"},
    {"name": "status", "type": "int", "unit": "HTTP", "nullable": False,
     "note": "探测末态状态码，0 表示传输层失败"},
    {"name": "hops", "type": "int", "unit": "次", "nullable": False,
     "note": "跳转次数，上限 5"},
    {"name": "category", "type": "enum", "unit": "—", "nullable": False,
     "note": "缺陷分类，见 /api/contract 的 categories"},
    {"name": "coverage", "type": "decimal", "unit": "—", "nullable": False,
     "note": "三向交集 / 目录条目数，保留 4 位小数"},
)

NORMALIZE_STEPS = (
    {"step": "scheme", "note": "只接受 http/https，其余进隔离区"},
    {"step": "host", "note": "主机小写，去掉末尾点与默认端口"},
    {"step": "relative", "note": "相对地址按所在页面地址补全"},
    {"step": "path", "note": "合并重复斜杠，去掉尾斜杠（根路径除外），路径整体小写"},
    {"step": "tracking", "note": "丢弃跟踪参数与空值会话参数"},
    {"step": "fragment", "note": "丢弃片段"},
    {"step": "param_order", "note": "保留参数按名称+值排序后重建"},
)


def map_attrs(attrs: dict[str, str]) -> tuple[dict[str, str], str]:
    """返回（规范字段, 属性代别）。代别取值 current / legacy / none。"""
    fields: dict[str, str] = {}
    scheme = "none"
    for key, value in attrs.items():
        if key in CURRENT_ATTRS and value:
            fields[CURRENT_ATTRS[key]] = value.strip()
            scheme = "current"
    if scheme == "none":
        for key, value in attrs.items():
            if key in LEGACY_ATTRS and value:
                fields[LEGACY_ATTRS[key]] = value.strip()
                scheme = "legacy"
    return fields, scheme


def contract_payload() -> dict:
    return {
        "rule_version": config.RULE_VERSION,
        "fields": list(FIELD_CONTRACT),
        "normalize_steps": list(NORMALIZE_STEPS),
        "current_attrs": CURRENT_ATTRS,
        "legacy_attrs": LEGACY_ATTRS,
        "categories": reasons.CATEGORIES,
    }
