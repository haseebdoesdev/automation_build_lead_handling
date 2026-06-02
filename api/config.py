from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AppConfig:
    """All environment-driven configuration for the integration layer."""

    # --- Anthropic ---
    anthropic_api_key: str = ""

    # --- PostgreSQL ---
    database_url: str = "postgresql+asyncpg://localhost:5432/reviewarmour"

    # --- Twilio ---
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_us_phone: str = ""
    twilio_ca_phone: str = ""

    # --- Amazon SES ---
    ses_region: str = "us-east-1"
    ses_sender_email_us: str = ""
    ses_sender_email_ca: str = ""
    ses_sender_name: str = "ReviewArmour"

    # --- Slack ---
    slack_bot_token: str = ""
    slack_invoice_channel: str = ""
    slack_stall_channel: str = ""
    slack_salesman_channel: str = ""

    # --- Operations ---
    operations_timezone: str = "America/New_York"
    business_hours_start: int = 8
    business_hours_end: int = 19
    morning_queue_release_hour: int = 8
    salesman_ack_window_minutes: int = 5
    salesman_call_sla_minutes: int = 15
    stall_escalation_window_hours: int = 6
    max_ai_followups_after_hours: int = 3
    ai_followup_interval_minutes: int = 30
    default_lead_cost_usd: int = 50

    # --- GBP scraper ---
    gbp_auth_state: str = "patchright_maps_auth.json"

    # --- Feature flags ---
    ai_quote_allowed: bool = True
    soft_quote_mode: bool = False
    sunday_followups_enabled: bool = False
    human_approval_before_send: bool = False

    # --- Salesman rotation ---
    salesmen_on_duty: list[str] = field(default_factory=lambda: ["jayden"])
    jayden_phone: str = ""
    jayden_slack_id: str = ""

    # --- Webhook secrets ---
    webhook_secret: str = ""


def load_config() -> AppConfig:
    return AppConfig(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://localhost:5432/reviewarmour",
        ),
        twilio_account_sid=os.environ.get("TWILIO_ACCOUNT_SID", ""),
        twilio_auth_token=os.environ.get("TWILIO_AUTH_TOKEN", ""),
        twilio_us_phone=os.environ.get("TWILIO_US_PHONE", ""),
        twilio_ca_phone=os.environ.get("TWILIO_CA_PHONE", ""),
        ses_region=os.environ.get("SES_REGION", "us-east-1"),
        ses_sender_email_us=os.environ.get("SES_SENDER_EMAIL_US", ""),
        ses_sender_email_ca=os.environ.get("SES_SENDER_EMAIL_CA", ""),
        ses_sender_name=os.environ.get("SES_SENDER_NAME", "ReviewArmour"),
        slack_bot_token=os.environ.get("SLACK_BOT_TOKEN", ""),
        slack_invoice_channel=os.environ.get("SLACK_INVOICE_CHANNEL", ""),
        slack_stall_channel=os.environ.get("SLACK_STALL_CHANNEL", ""),
        slack_salesman_channel=os.environ.get("SLACK_SALESMAN_CHANNEL", ""),
        operations_timezone=os.environ.get("OPS_TIMEZONE", "America/New_York"),
        business_hours_start=int(os.environ.get("BIZ_HOURS_START", "8")),
        business_hours_end=int(os.environ.get("BIZ_HOURS_END", "19")),
        morning_queue_release_hour=int(os.environ.get("MORNING_QUEUE_HOUR", "8")),
        salesman_ack_window_minutes=int(os.environ.get("SALESMAN_ACK_WINDOW_MIN", "5")),
        salesman_call_sla_minutes=int(os.environ.get("SALESMAN_CALL_SLA_MIN", "15")),
        stall_escalation_window_hours=int(
            os.environ.get("STALL_WINDOW_HOURS", "6")
        ),
        max_ai_followups_after_hours=int(
            os.environ.get("MAX_AI_FOLLOWUPS", "3")
        ),
        ai_followup_interval_minutes=int(
            os.environ.get("AI_FOLLOWUP_INTERVAL_MIN", "30")
        ),
        default_lead_cost_usd=int(os.environ.get("DEFAULT_LEAD_COST_USD", "50")),
        ai_quote_allowed=os.environ.get("AI_QUOTE_ALLOWED", "true").lower() == "true",
        soft_quote_mode=os.environ.get("SOFT_QUOTE_MODE", "false").lower() == "true",
        sunday_followups_enabled=os.environ.get("SUNDAY_FOLLOWUPS", "false").lower()
        == "true",
        human_approval_before_send=os.environ.get(
            "HUMAN_APPROVAL_BEFORE_SEND", "false"
        ).lower()
        == "true",
        salesmen_on_duty=[
            s.strip()
            for s in os.environ.get("SALESMEN_ON_DUTY", "jayden").split(",")
            if s.strip()
        ],
        jayden_phone=os.environ.get("JAYDEN_PHONE", ""),
        jayden_slack_id=os.environ.get("JAYDEN_SLACK_ID", ""),
        webhook_secret=os.environ.get("WEBHOOK_SECRET", ""),
        gbp_auth_state=os.environ.get(
            "GBP_AUTH_STATE", "patchright_maps_auth.json"
        ),
    )
