from __future__ import annotations

from typing import Any, Dict
from starlette.types import ASGIApp, Receive, Scope, Send
from uvicorn.protocols.utils import get_path_with_query_string

from .sender import LogCenterSender


class LogCenterAuditMiddleware:
    def __init__(self, app: ASGIApp, sender: LogCenterSender):
        self.app = app
        self.sender = sender

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        info: Dict[str, Any] = {}

        async def inner_send(message: dict):
            if message.get("type") == "http.response.start":
                info["status_code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, inner_send)

        except Exception as exc:
            info["status_code"] = 500
            path_qs = str(get_path_with_query_string(scope))
            method = scope.get("method")
            await self.sender.send(
                "ERROR",
                "Unhandled exception in request",
                data={
                    "path": path_qs,
                    "method": method,
                    "exception_class": exc.__class__.__name__,
                },
                status="ERROR",
            )
            raise

        finally:
            status = int(info.get("status_code", 200))
            if status >= 500:
                path_qs = str(get_path_with_query_string(scope))
                method = scope.get("method")
                await self.sender.send(
                    "ERROR",
                    "HTTP 5xx response",
                    data={"path": path_qs, "method": method, "status": status},
                    status="ERROR",
                )
