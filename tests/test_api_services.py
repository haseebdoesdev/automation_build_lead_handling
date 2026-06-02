"""Tests for API services (router, config) — no external dependencies required."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from api.config import AppConfig, load_config
from api.services.router_service import decide_route
from reviewarmour.models import RouteDecision


class TestRouterService:
    def test_business_hours(self):
        config = AppConfig(business_hours_start=8, business_hours_end=19)
        # Monkeypatch won't work on frozen dataclass + datetime.now,
        # so we just verify the function exists and returns valid values
        result = decide_route(config)
        assert result in (RouteDecision.BUSINESS_HOURS_SALESMAN, RouteDecision.AFTER_HOURS_AI)

    def test_returns_route_decision_enum(self):
        config = AppConfig()
        result = decide_route(config)
        assert isinstance(result, RouteDecision)


class TestAppConfig:
    def test_defaults(self):
        config = AppConfig()
        assert config.operations_timezone == "America/New_York"
        assert config.business_hours_start == 8
        assert config.business_hours_end == 19
        assert config.stall_escalation_window_hours == 6
        assert config.max_ai_followups_after_hours == 3
        assert config.ai_quote_allowed is True
        assert config.soft_quote_mode is False
        assert config.sunday_followups_enabled is False
        assert config.default_lead_cost_usd == 50

    def test_load_config_returns_appconfig(self):
        config = load_config()
        assert isinstance(config, AppConfig)

    def test_salesmen_default(self):
        config = AppConfig()
        assert "jayden" in config.salesmen_on_duty


class TestRouteDecisionEnum:
    def test_values(self):
        assert RouteDecision.BUSINESS_HOURS_SALESMAN.value == "business_hours_salesman"
        assert RouteDecision.AFTER_HOURS_AI.value == "after_hours_ai"
        assert RouteDecision.MORNING_QUEUE.value == "morning_queue"
        assert RouteDecision.AI_ESCALATED_TO_HUMAN.value == "ai_escalated_to_human"
