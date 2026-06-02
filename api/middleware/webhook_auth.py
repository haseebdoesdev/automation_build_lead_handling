from __future__ import annotations

import hashlib
import hmac
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("reviewarmour.api.webhook_auth")

PROTECTED_PREFIXES = ("/api/inbound/form", "/api/inbound/email")


class WebhookAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        config = getattr(request.app.state, "config", None)
        secret = getattr(config, "webhook_secret", "") if config else ""

        if not secret:
            return await call_next(request)

        path = request.url.path
        if not any(path.startswith(p) for p in PROTECTED_PREFIXES):
            return await call_next(request)

        sig_header = request.headers.get("X-Webhook-Signature", "")
        if not sig_header:
            logger.warning("Missing X-Webhook-Signature for %s", path)
            return JSONResponse({"error": "missing signature"}, status_code=401)

        body = await request.body()
        expected = hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(sig_header, expected):
            logger.warning("Invalid webhook signature for %s", path)
            return JSONResponse({"error": "invalid signature"}, status_code=401)

        return await call_next(request)
