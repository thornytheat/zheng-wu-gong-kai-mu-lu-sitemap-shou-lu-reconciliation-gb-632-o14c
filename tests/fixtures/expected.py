"""期望值集中一处：断言里出现的具体数字全从这里取，避免散落魔数。

数值来自 sample_site 三站的真实字节，改样例站就要同步改这里。
"""

# 采信阶段
SITE_A_PAGE1_ENTRIES = 12          # 目录区域内锚点数（含待隔离的 3 行）
SITE_A_PAGE2_ENTRIES = 3
SITE_B_ENTRIES = 3
SITE_C_ENTRIES = 4
CATALOG_PAGES = 4
RESOURCES = 7                      # 3 站 sitemap + 3 站目录页 + site-a 的第 2 页
UNION_KEYS = 23                    # 目录 17 + 收录 14 - 双侧 8
CONFLICT_KEPT = "2026-10-11T09:30:00Z"
CONFLICT_DROPPED = "2026-09-02T08:00:00Z"
BLOCK_NO_LOC_ROW = 11

# 三向对账
CATALOG_ROWS = 18
CATALOG_KEYS = 17
SITEMAP_ROWS = 15
SITEMAP_KEYS = 14
BOTH = 8
ONLY_IN_CATALOG = 9
ONLY_IN_SITEMAP = 6
PROBED = 23
ALIVE_OK = 15
ALIVE_REDIRECT = 4
DEAD = 4
THREE_WAY = 8
COVERAGE = "0.4706"
FINDINGS = 21

BY_CATEGORY = {
    "CATALOG_DEAD": 3,
    "ONLY_IN_SITEMAP_DEAD": 1,
    "REDIRECT_CHAIN": 4,
    "DUPLICATE_SLUG": 2,
    "ONLY_IN_CATALOG": 2,
    "ONLY_IN_SITEMAP_ALIVE": 5,
    "CANONICAL_MISMATCH": 4,
}

# 具体地址
LEADING_ZERO_CODE = "0070012"
LEGACY_CODE = "0081001"
LEGACY_ATTR_SCHEME = "legacy"
CASE_TRACKING_URL = "http://www.hz.gov.cn/site-a/notice/n-2024-003"
TWO_HOP_URL = "http://www.hz.gov.cn/site-a/pub/legacy/beta"
GONE_URL = "http://zwfw.hz.gov.cn/site-b/notice/withdrawn-2019"
CLEAN_KEY = "http://fgw.hz.gov.cn/site-c/notice/n-c-001"
SEVEN_HUNDRED = "0070014"
