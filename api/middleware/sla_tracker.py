from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("reviewarmour.api.sla")

SLA_THRESHOLD_MS = 60_000


class SLATrackerMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path == "/api/inbound/form":
            start = time.monotonic()
            response = await call_next(request)
            elapsed_ms = (time.monotonic() - start) * 1000

            if elapsed_ms > SLA_THRESHOLD_MS:
                logger.warning(
                    "SLA BREACH: /api/inbound/form took %.0fms (limit %dms)",
                    elapsed_ms,
                    SLA_THRESHOLD_MS,
                )
            else:
                logger.info(
                    "SLA OK: /api/inbound/form responded in %.0fms", elapsed_ms
                )
            return response

        return await call_next(request)
