import logging
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from portfolio_analytics_api.core.logging import bind_request_id, reset_request_id

logger = logging.getLogger(__name__)
REQUEST_ID_HEADER = "X-Request-ID"


class RequestObservabilityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _request_id_from_scope(scope)
        token = bind_request_id(request_id)
        started_at = perf_counter()
        status_code = 500
        logger.info(
            "http request started",
            extra={
                "event": "http.request.started",
                "request_id": request_id,
                "http_method": scope["method"],
            },
        )

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append(
                    (
                        REQUEST_ID_HEADER.lower().encode("ascii"),
                        request_id.encode("ascii"),
                    )
                )
                message = {**message, "headers": headers}
            await send(message)

        try:
            try:
                await self._app(scope, receive, send_with_request_id)
            except Exception as error:
                status_code = 500
                logger.error(
                    "unhandled request error",
                    extra={
                        "event": "http.request.failed",
                        "request_id": request_id,
                        "http_method": scope["method"],
                        "http_route": _route_template(scope),
                        "status_code": status_code,
                        "error_category": "internal_error",
                        "error_type": type(error).__name__,
                    },
                )
                response = JSONResponse(
                    status_code=status_code,
                    content={
                        "error": {
                            "code": "internal_error",
                            "message": "an unexpected error occurred",
                        }
                    },
                )
                await response(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 3)
            logger.info(
                "http request completed",
                extra={
                    "event": "http.request.completed",
                    "request_id": request_id,
                    "http_method": scope["method"],
                    "http_route": _route_template(scope),
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "outcome": _http_outcome(status_code),
                },
            )
            reset_request_id(token)


def _request_id_from_scope(scope: Scope) -> str:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() != REQUEST_ID_HEADER.lower().encode("ascii"):
            continue
        try:
            return str(UUID(raw_value.decode("ascii")))
        except (UnicodeDecodeError, ValueError):
            break
    return str(uuid4())


def _route_template(scope: Scope) -> str:
    route: Any = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def _http_outcome(status_code: int) -> str:
    if status_code >= 500:
        return "server_error"
    if status_code >= 400:
        return "client_error"
    return "success"
