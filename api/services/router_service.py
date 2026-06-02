from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from reviewarmour.models import RouteDecision

from api.config import AppConfig


def decide_route(config: AppConfig) -> RouteDecision:
    """Time-based routing: business hours → salesman, after hours → AI."""
    tz = ZoneInfo(config.operations_timezone)
    now_local = datetime.now(tz)
    hour = now_local.hour

    if config.business_hours_start <= hour < config.business_hours_end:
        return RouteDecision.BUSINESS_HOURS_SALESMAN

    return RouteDecision.AFTER_HOURS_AI
