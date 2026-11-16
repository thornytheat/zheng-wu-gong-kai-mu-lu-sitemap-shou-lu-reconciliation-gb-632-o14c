"""缺陷分类：显式优先级 + 谓词表，结果与规则书写顺序无关。

七条规则同时可能命中同一个地址（比如「只在目录里 + 死链 + 有跳转」），
朴素写法按 if 顺序覆盖，改一次代码结论就变。这里每条规则带固定优先级，
classify() 先按优先级排序再判，所以传进来的规则序列顺序不影响结果
（tests/test_reach.py::test_rule_order_does_not_matter 钉死）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ... import reasons

# 触发「地址不规范」的改写痕迹：相对地址与参数排序是正常写法，不算缺陷
MISMATCH_NOTES = frozenset({"tracking", "fragment", "case", "trailing_slash",
                            "duplicate_slash", "default_port", "scheme"})


@dataclass
class Observation:
    key: str
    site: str
    url: str
    in_catalog: int
    in_sitemap: int
    status: int
    hops: int
    raw_forms: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def dead(self) -> bool:
        return self.status == 0 or self.status >= 400

    @property
    def distinct_raw(self) -> int:
        return len({form.strip().lower() for form in self.raw_forms})

    @property
    def duplicate(self) -> bool:
        """同侧出现多条原始写法：目录登记两次，或 sitemap 收录两种写法。

        目录写一次、sitemap 写一次但拼法不同不算重复条目，那是地址不规范。
        """
        return self.in_catalog > 1 or self.in_sitemap > 1

    @property
    def changed(self) -> bool:
        return any(note in MISMATCH_NOTES for note in self.notes)


RULES: tuple[tuple[int, str, str], ...] = (
    (10, "CATALOG_DEAD", "目录有条目，探测末态 4xx/传输失败"),
    (20, "ONLY_IN_SITEMAP_DEAD", "仅 sitemap 收录，探测末态 4xx"),
    (30, "REDIRECT_CHAIN", "可达但经过跳转"),
    (40, "DUPLICATE_SLUG", "多条原始条目规范化后同址"),
    (50, "ONLY_IN_CATALOG", "目录有条目，sitemap 未收录"),
    (60, "ONLY_IN_SITEMAP_ALIVE", "sitemap 收录，目录未登记"),
    (70, "CANONICAL_MISMATCH", "双侧都有但原始地址不是规范地址"),
)


def _hit(code: str, obs: Observation) -> bool:
    if code == "CATALOG_DEAD":
        return obs.dead and obs.in_catalog > 0
    if code == "ONLY_IN_SITEMAP_DEAD":
        return obs.dead and obs.in_catalog == 0 and obs.in_sitemap > 0
    if code == "REDIRECT_CHAIN":
        return not obs.dead and obs.hops > 0
    if code == "DUPLICATE_SLUG":
        return obs.duplicate
    if code == "ONLY_IN_CATALOG":
        return obs.in_catalog > 0 and obs.in_sitemap == 0
    if code == "ONLY_IN_SITEMAP_ALIVE":
        return obs.in_sitemap > 0 and obs.in_catalog == 0
    if code == "CANONICAL_MISMATCH":
        return obs.in_catalog > 0 and obs.in_sitemap > 0 and obs.changed
    return False


def ordered(rules=RULES) -> list[tuple[int, str, str]]:
    return sorted(rules, key=lambda item: (item[0], item[1]))


def classify(obs: Observation, rules=RULES) -> tuple[str, int]:
    for priority, code, _note in ordered(rules):
        if _hit(code, obs):
            return code, priority
    return "OK", 100


def category_label(code: str) -> str:
    return reasons.CATEGORIES.get(code, code)


def evidence(obs: Observation) -> dict:
    return {"in_catalog": obs.in_catalog, "in_sitemap": obs.in_sitemap,
            "status": obs.status, "hops": obs.hops,
            "raw_forms": list(obs.raw_forms)[:6],
            "notes": list(obs.notes),
            "duplicate": obs.duplicate}
