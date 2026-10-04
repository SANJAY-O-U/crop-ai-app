"""
Consistent, frontend-compatible API errors.

Every error body keeps the `detail` STRING the existing frontend reads (frontend/src/cropcast/api.js uses `j.detail`),
and adds a structured `error` object:

    {"detail": "<human message>", "error": {"code": "...", "message": "...", "request_id": "..."}}

  404 not_found                  unknown block / Panchayat / route
  422 invalid_request            invalid query/path parameters (error.fields lists them)
  502 weather_upstream_invalid   the weather provider answered with an unusable response
  503 weather_unavailable        the weather provider could not be reached / timed out (Retry-After set)
  500 internal_error             anything unexpected -- generic message, no stack trace, details only in server logs
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.observability import log_event, request_id_var
from app.weather.errors import WeatherUnavailableError

_CODES = {400: "bad_request", 404: "not_found", 405: "method_not_allowed", 413: "payload_too_large", 422: "invalid_request",
          500: "internal_error", 502: "weather_upstream_invalid", 503: "weather_unavailable"}
_UNREACHABLE_KINDS = {"timeout", "connection", "provider_error", "weather_unavailable"}
RETRY_AFTER_S = "30"


class APIError(Exception):
    """An expected, user-facing failure with its own machine-readable code (e.g. disease models not installed)."""

    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.headers = status, code, message, headers


def body(status: int, message: str, code: str | None = None, **extra) -> dict:
    return {"detail": message, "error": {"code": code or _CODES.get(status, "error"), "message": message,
                                          "request_id": request_id_var.get(), **extra}}


def respond(status: int, message: str, code: str | None = None, headers: dict | None = None, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content=body(status, message, code, **extra), headers=headers)


def register(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return respond(exc.status_code, message, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        fields = [{"field": ".".join(str(p) for p in e["loc"] if p not in ("query", "path", "body")), "problem": e["msg"]} for e in exc.errors()]
        message = "Invalid request: " + "; ".join(f"{f['field'] or 'request'}: {f['problem']}" for f in fields)
        log_event("request_validation_failed", level="warning", path=request.url.path, fields=[f["field"] for f in fields])
        return respond(422, message[:300], fields=fields)

    @app.exception_handler(APIError)
    async def _api_error(request: Request, exc: APIError):
        return respond(exc.status, exc.message, code=exc.code, headers=exc.headers)

    @app.exception_handler(WeatherUnavailableError)
    async def _weather(request: Request, exc: WeatherUnavailableError):
        unreachable = exc.kind in _UNREACHABLE_KINDS
        status = 503 if unreachable else 502
        message = ("Live weather data is temporarily unavailable. Please try again shortly." if unreachable
                   else "The weather provider returned an unusable response. Please try again later.")
        return respond(status, message, headers={"Retry-After": RETRY_AFTER_S} if unreachable else None, upstream_kind=exc.kind)
