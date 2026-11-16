"""领域异常到 HTTP 的映射：所有对外错误都带稳定错误码。"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = 500
    code = "E_INTERNAL"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code

    def payload(self) -> dict:
        return {"error": self.code, "message": self.message}


class BadRequest(AppError):
    status_code = 400
    code = "E_BAD_REQUEST"


class NotFound(AppError):
    status_code = 404
    code = "E_NOT_FOUND"


class Conflict(AppError):
    status_code = 409
    code = "E_CONFLICT"


class UpstreamError(AppError):
    status_code = 502
    code = "E_UPSTREAM"


def install_handlers(app) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):  # noqa: ANN001
        return JSONResponse(status_code=exc.status_code, content=exc.payload())

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError):  # noqa: ANN001
        return JSONResponse(status_code=400,
                            content={"error": "E_BAD_REQUEST", "message": str(exc)})
