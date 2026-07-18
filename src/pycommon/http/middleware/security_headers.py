"""OWASP baseline security headers middleware (pure ASGI)."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """Attach standard secure response headers."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        hsts: bool = True,
        hsts_max_age: int = 31536000,
        frame_options: str = "DENY",
        content_type_options: str = "nosniff",
        referrer_policy: str = "strict-origin-when-cross-origin",
        permissions_policy: str = "geolocation=(), microphone=(), camera=()",
    ) -> None:
        self.app = app
        self.hsts = hsts
        self.hsts_max_age = hsts_max_age
        self.frame_options = frame_options
        self.content_type_options = content_type_options
        self.referrer_policy = referrer_policy
        self.permissions_policy = permissions_policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        include_hsts = self.hsts and scope.get("scheme") == "https"

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = self.content_type_options
                headers["X-Frame-Options"] = self.frame_options
                headers["Referrer-Policy"] = self.referrer_policy
                headers["Permissions-Policy"] = self.permissions_policy
                if include_hsts:
                    headers["Strict-Transport-Security"] = (
                        f"max-age={self.hsts_max_age}; includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)
