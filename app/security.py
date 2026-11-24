import os
import secrets
from urllib.parse import urlsplit
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse


class SecurityMiddleware:
    def __init__(self, app, requests_per_minute: int = 30) -> None:
        self.app = app
        self.limit = max(5, requests_per_minute)
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope, receive: Callable[..., Awaitable], send: Callable[..., Awaitable]) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        path = request.url.path
        if path.startswith("/api/"):
            origin = request.headers.get("origin")
            if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and urlsplit(origin).netloc != request.url.netloc:
                await JSONResponse({"detail": "不允许跨站修改请求"}, status_code=403)(scope, receive, send)
                return
            ip = request.client.host if request.client else "unknown"
            now = time.monotonic()
            if len(self.hits) > 1024:
                self.hits = defaultdict(deque, {key: hits for key, hits in self.hits.items() if hits and hits[-1] >= now - 60})
            bucket = self.hits[ip]
            while bucket and bucket[0] < now - 60:
                bucket.popleft()
            if len(bucket) >= self.limit:
                await JSONResponse({"detail": "请求过于频繁，请稍后再试"}, status_code=429)(scope, receive, send)
                return
            bucket.append(now)
            expected = os.getenv("APP_ACCESS_TOKEN", "").strip()
            supplied = request.headers.get("authorization", "").removeprefix("Bearer ") or request.cookies.get("job_agent_session", "")
            if expected and path != "/api/session" and not secrets.compare_digest(supplied.encode(), expected.encode()):
                await JSONResponse({"detail": "访问令牌无效"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)
