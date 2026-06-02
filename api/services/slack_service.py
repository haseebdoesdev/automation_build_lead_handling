from __future__ import annotations

import json
import logging
from typing import Any

from api.config import AppConfig

logger = logging.getLogger("reviewarmour.api.slack")


async def _post_slack(
    channel: str, text: str, blocks: list[dict] | None, config: AppConfig
) -> dict[str, Any]:
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            payload: dict[str, Any] = {
                "channel": channel,
                "text": text,
            }
            if blocks:
                payload["blocks"] = blocks

            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {config.slack_bot_token}"},
                json=payload,
            )
            data = resp.json()
            if not data.get("ok"):
                logger.error("Slack post failed: %s", data.get("error"))
                return {"ok": False, "error": data.get("error")}
            return {"ok": True, "ts": data.get("ts")}
    except ImportError:
        logger.warning("httpx not installed. Slack message not sent.")
        return {"ok": False, "error": "httpx_not_installed"}
    except Exception as e:
        logger.error("Slack error: %s", e)
        return {"ok": False, "error": str(e)}


async def send_invoice_handoff(
    lead_data: dict[str, Any],
    config: AppConfig,
) -> dict[str, Any]:
    """Quote-to-invoice Slack handoff (Section 13)."""
    text = (
        f"*Invoice Handoff*\n"
        f"Lead: {lead_data['name']} / {lead_data['business']}\n"
        f"Country: {lead_data['country']}\n"
        f"Email: {lead_data['email']} | Phone: {lead_data['phone']}\n"
        f"GBP: {lead_data.get('gbp_link', 'N/A')}\n"
        f"Reviews: {lead_data.get('review_count', 'N/A')}\n"
        f"Quote: ${lead_data['quote_usd']}/review | "
        f"Total: ${lead_data['total_usd']} USD\n"
    )
    if lead_data["country"] == "CA":
        text += "Note: Final invoice in CAD at prevailing rate.\n"
    text += (
        "Pay-after-removal: customer pays only after reviews are confirmed down.\n"
        f"CRM: {lead_data.get('crm_link', 'N/A')}\n"
    )

    result = await _post_slack(config.slack_invoice_channel, text, None, config)

    if not result.get("ok"):
        logger.error("Invoice handoff Slack failed. Paging Jayden via SMS.")
        from api.services.messaging_service import send_sms

        await send_sms(
            config.jayden_phone,
            f"URGENT: Invoice handoff Slack failed for {lead_data['name']} "
            f"({lead_data['business']}). Check manually.",
            "US",
            config,
        )

    return result


async def send_stall_alert(
    lead_data: dict[str, Any],
    config: AppConfig,
    *,
    is_backup: bool = False,
) -> dict[str, Any]:
    """Stall-escalation Slack/SMS alert (Section 14)."""
    label = "BACKUP STALL ALERT" if is_backup else "STALL ALERT"
    text = (
        f"*{label}*\n"
        f"Lead: {lead_data['name']} ({lead_data['business']})\n"
        f"Country: {lead_data['country']}\n"
        f"Phone: {lead_data['phone']} | Email: {lead_data['email']}\n"
        f"Last quote: ${lead_data.get('last_quote', 'N/A')}/review\n"
        f"Last message: {lead_data.get('last_message', 'N/A')}\n"
        f"Silent since: {lead_data.get('silent_since', 'N/A')}\n"
    )

    result = await _post_slack(config.slack_stall_channel, text, None, config)

    from api.services.messaging_service import send_sms

    phone = config.jayden_phone if is_backup else lead_data.get("salesman_phone", config.jayden_phone)
    sms_body = (
        f"{label}: {lead_data['name']} ({lead_data['business']}) "
        f"silent after ${lead_data.get('last_quote', '?')}/review quote. "
        f"Call {lead_data['phone']} ASAP."
    )
    await send_sms(phone, sms_body, "US", config)

    return result


async def send_salesman_dispatch(
    lead_data: dict[str, Any],
    salesman_phone: str,
    config: AppConfig,
) -> dict[str, Any]:
    """Salesman dispatch notification (spec v7 Section 12 + v2 Section 8 pricing)."""
    phone_routed = lead_data.get("phone_call_routed", False)
    header = "*PHONE-CALL LEAD (no quote sent)*" if phone_routed else "*New Lead*"

    text = (
        f"{header}\n"
        f"Name: {lead_data['name']}\n"
        f"Business: {lead_data['business']}\n"
        f"Phone: {lead_data['phone']} | Email: {lead_data['email']}\n"
        f"Country: {lead_data['country']}\n"
        f"GBP: {lead_data.get('gbp_link', 'N/A')}\n"
        f"Urgency: {lead_data.get('urgency', 'N/A')}\n"
        f"Source: {lead_data.get('source', 'N/A')}\n"
    )

    # Spec v2: pricing context for the salesman.
    tier = lead_data.get("pricing_tier", "N/A")
    if tier != "N/A":
        text += (
            f"\n*Pricing Context*\n"
            f"Tier: {tier} | Category: {lead_data.get('gbp_category', 'N/A')}\n"
            f"Volume bracket: {lead_data.get('volume_bracket', 'N/A')} "
            f"({lead_data.get('review_count', '?')} reviews)\n"
            f"Recommended range: {lead_data.get('recommended_range', 'N/A')}\n"
            f"Recommended opening: {lead_data.get('recommended_opening', 'N/A')}\n"
            f"Total deal value: {lead_data.get('total_deal_value', 'N/A')}\n"
            f"Review breakdown: {lead_data.get('review_breakdown', 'N/A')}\n"
        )
        rs = lead_data.get("reasoning_summary", "N/A")
        if rs and rs != "N/A":
            text += f"Reasoning: {rs}\n"

    result = await _post_slack(config.slack_salesman_channel, text, None, config)

    from api.services.messaging_service import send_sms

    rec_open = lead_data.get("recommended_opening", "")
    sms_pricing = f" Quote: {rec_open}" if rec_open and rec_open != "N/A" else ""
    label = "PHONE-CALL LEAD" if phone_routed else "NEW LEAD"
    sms_body = (
        f"{label}: {lead_data['name']} / {lead_data['business']} "
        f"({lead_data['country']}).{sms_pricing} "
        f"Call {lead_data['phone']}. Reply ACK to confirm."
    )
    await send_sms(salesman_phone, sms_body, "US", config)

    return result
