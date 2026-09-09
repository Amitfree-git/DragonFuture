from __future__ import annotations

import os
import re
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

PUBLIC_PATHS = {
    "/api/v1/futures/health",
    "/api/v1/futures/ready",
    "/docs",
    "/openapi.json",
    "/redoc",
}
SECRET_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+|TUSHARE_TOKEN=\S+", re.I)


def api_token() -> str | None:
    value = os.getenv("DRAGONBOAT_FUTURES_API_TOKEN")
    return value.strip() if value else None


def redact(text: str) -> str:
    return SECRET_PATTERN.sub(lambda match: (match.group(1) + "***") if match.group(1) else "TUSHARE_TOKEN=***", text)


class ReadOnlyAccessMiddleware(BaseHTTPMiddleware):
    """Optional bearer auth and a process-local rate limit. Disabled when no token is set."""

    def __init__(self, app, *, max_per_minute: int = 60) -> None:
        super().__init__(app)
        self.max_per_minute = max_per_minute
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        token = api_token()
        if token:
            header = request.headers.get("authorization", "")
            presented = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
            if presented != token:
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = [stamp for stamp in self._hits[key] if now - stamp < 60.0]
        if len(window) >= self.max_per_minute:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
        window.append(now)
        self._hits[key] = window
        return await call_next(request)
