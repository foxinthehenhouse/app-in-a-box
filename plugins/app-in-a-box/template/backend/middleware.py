"""Request id + security headers, as one pure-ASGI middleware.

Pure ASGI (not BaseHTTPMiddleware) so it adds no per-request task and doesn't break
streaming responses. Headers:

- `X-Request-ID`: echoed or generated (see observability.new_request_id).
- `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Cross-Origin-Resource-Policy`: cheap defaults every JSON API should send.
- `Content-Security-Policy: default-src 'none'`: this API serves JSON, never pages.
  Skipped on the interactive docs, which load Swagger UI from a CDN.
- `Strict-Transport-Security`: production only (Railway terminates TLS).
- `Cache-Control: no-store` on `/api/`: per-user data must never sit in a shared cache.
"""

from __future__ import annotations

from typing import Any

from backend.observability import new_request_id, request_id_var, tag_request

_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
_BASE_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-resource-policy", b"same-site"),
)


class RequestContextMiddleware:
    def __init__(self, app: Any, *, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = None
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        rid = new_request_id(incoming)
        request_id_var.set(rid)  # task-local; read by logs, Sentry and the error handler
        tag_request(rid)
        path: str = scope.get("path", "")

        async def send_with_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                extra = [(b"x-request-id", rid.encode("latin-1")), *_BASE_HEADERS]
                if not path.startswith(_DOCS_PATHS):
                    extra.append(
                        (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
                    )
                if self.hsts:
                    extra.append((b"strict-transport-security", b"max-age=63072000"))
                if path.startswith("/api/"):
                    extra.append((b"cache-control", b"no-store"))
                headers.extend((k, v) for k, v in extra if k not in present)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
