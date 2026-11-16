"""M2 入口：契约查询与规范化试算。

试算接口是给编辑用的：贴一个地址，立刻看到规范化结果与改写痕迹，
不必先跑整批巡检。非法地址返回 400，不做部分成功。
"""
from __future__ import annotations

from fastapi import APIRouter

from ... import errors, reasons
from . import contract, normalize, scope

router = APIRouter(tags=["M2 URL 规则"])


@router.get("/api/contract")
def api_contract() -> dict:
    return contract.contract_payload()


@router.post("/api/url/normalize")
def api_normalize(payload: dict | None = None) -> dict:
    body = payload or {}
    raw = body.get("url")
    if not isinstance(raw, str) or not raw.strip():
        raise errors.BadRequest("url 必填", code="E_BAD_URL")
    base = body.get("base")
    if base is not None and not isinstance(base, str):
        raise errors.BadRequest("base 必须是字符串", code="E_BAD_URL")
    try:
        result = normalize.normalize(raw, base)
    except ValueError as exc:
        raise errors.BadRequest(str(exc), code="E_BAD_URL") from exc
    return {
        "raw": result.raw,
        "url": result.url,
        "key": result.key,
        "host": result.host,
        "path": result.path,
        "query": result.query,
        "changed": result.changed,
        "notes": [{"code": n, "label": reasons.note_label(n)} for n in result.notes],
        "site": scope.site_of(result.url),
        "in_scope": scope.in_scope(result.url),
    }
