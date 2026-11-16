"""sitemapaudit 全局配置：站点清单、编码回退链、跟踪参数、探测上限。

规则唯一来源，其他模块只读不写：
- 地址一律先规范化再比较，规范化步骤见 m2_url/normalize.py；
- 原始地址按字符串保形，标称事项编码含前导零，禁止过 int()；
- 时间入库为 UTC 秒级字符串，展示按 Asia/Shanghai；
- 样例站大小写不敏感（对标 IIS），大小写差异算地址不规范，不算死链。
"""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHINA_TZ = dt.timezone(dt.timedelta(hours=8), "Asia/Shanghai")
UTC = dt.timezone.utc

RULE_VERSION = "sitemapaudit/1.0.0"
EVAL_DATE_DEFAULT = "2026-11-15"

STAGES = ("crawl", "probe", "reconcile")
STAGE_LABELS = {"crawl": "采信", "probe": "探测", "reconcile": "对账"}
STAGE_FLOW = "采信 → 探测 → 对账"

# 编码回退链：先按 HTTP 头 / meta 声明，再按严格顺序逐个尝试
ENCODING_CHAIN = ("utf-8-sig", "utf-8", "gb18030")
CHARSET_ALIASES = {
    "utf8": "utf-8", "utf-8": "utf-8", "utf-8-sig": "utf-8-sig",
    "gb2312": "gb18030", "gbk": "gb18030", "gb18030": "gb18030", "gb-2312": "gb18030",
    "big5": "big5",
}

# 跟踪参数：规范化时整条丢弃，参数名不区分大小写
TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "spm", "from", "sessionid", "jsessionid", "phpsessid", "_ga", "fbclid",
    "share_token", "share_from",
})

DEFAULT_PORTS = {"http": 80, "https": 443}
ALLOWED_SCHEMES = ("http", "https")
SCRIPT_SCHEMES = ("javascript:", "mailto:", "tel:", "data:", "file:")

MAX_HOPS = 5
PROBE_TIMEOUT = 5.0
MAX_CATALOG_PAGES = 6
SMALL_BODY_LIMIT = 4 * 1024 * 1024

# M7 变更监测：样例基线是上一季度用 /api/watch/snapshot.json 导出的快照，
# 只在 base=sample 时读取；库内有更早的巡检时优先用库内的那次。
BASELINE_PATH = PROJECT_ROOT / "sample_data" / "watch" / "baseline.json"
WATCH_HISTORY = 8      # 历史趋势最多回看的批次
WATCH_PAGE_ROWS = 60   # 页面单表最多展示的变化行

# 目录页里被当成条目的锚点行号上限，用于防止把导航链接算成目录条目
COVERAGE_QUANT = 4  # 覆盖率保留 4 位小数


@dataclass(frozen=True)
class Site:
    code: str
    name: str
    host: str
    path: str

    @property
    def sitemap_path(self) -> str:
        return f"{self.path}/sitemap.xml"

    @property
    def catalog_path(self) -> str:
        return f"{self.path}/catalog.html"


SITES = (
    Site("site-a", "河州市人民政府", "www.hz.gov.cn", "/site-a"),
    Site("site-b", "河州市政务服务局", "zwfw.hz.gov.cn", "/site-b"),
    Site("site-c", "河州市发展改革委", "fgw.hz.gov.cn", "/site-c"),
)
SITE_CODES = tuple(s.code for s in SITES)
SITE_BY_CODE = {s.code: s for s in SITES}
SITE_BY_HOST = {s.host: s for s in SITES}


@dataclass(frozen=True)
class Settings:
    db_path: str
    sample_site_base: str
    sample_site_dir: str
    eval_date: str
    rule_version: str = RULE_VERSION
    max_hops: int = MAX_HOPS
    probe_timeout: float = PROBE_TIMEOUT
    baseline_path: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=os.environ.get("SITEMAPAUDIT_DB", str(PROJECT_ROOT / "data" / "sitemapaudit.sqlite")),
            sample_site_base=os.environ.get("SAMPLE_SITE_BASE", "http://sample-site:8000").rstrip("/"),
            sample_site_dir=os.environ.get("SAMPLE_SITE_DIR", str(PROJECT_ROOT / "sample_site")),
            eval_date=os.environ.get("EVAL_DATE", EVAL_DATE_DEFAULT),
            rule_version=os.environ.get("RULE_VERSION", RULE_VERSION),
            baseline_path=os.environ.get("SITEMAPAUDIT_BASELINE", str(BASELINE_PATH)),
        )

    @property
    def watch_baseline_path(self) -> str:
        return self.baseline_path or str(BASELINE_PATH)

    @property
    def sites(self) -> tuple[Site, ...]:
        return SITES

    def site(self, code: str) -> Site:
        if code not in SITE_BY_CODE:
            raise KeyError(code)
        return SITE_BY_CODE[code]
