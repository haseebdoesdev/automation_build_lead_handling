from __future__ import annotations

import logging
from typing import Any

from api.config import AppConfig

logger = logging.getLogger("reviewarmour.api.messaging")


async def send_sms(
    to_phone: str,
    body: str,
    country: str,
    config: AppConfig,
) -> dict[str, Any]:
    """Send SMS via Twilio. Returns Twilio message SID and status."""
    from_phone = config.twilio_us_phone if country == "US" else config.twilio_ca_phone

    try:
        from twilio.rest import Client

        client = Client(config.twilio_account_sid, config.twilio_auth_token)
        message = client.messages.create(
            body=body,
            from_=from_phone,
            to=to_phone,
        )
        logger.info("SMS sent to %s: SID=%s", to_phone, message.sid)
        return {"sid": message.sid, "status": message.status}
    except ImportError:
        logger.warning("Twilio SDK not installed. SMS to %s not sent.", to_phone)
        return {"sid": "mock_no_twilio", "status": "mock"}
    except Exception as e:
        logger.error("SMS send failed to %s: %s", to_phone, e)
        return {"sid": None, "status": "failed", "error": str(e)}


async def send_whatsapp(
    to_phone: str,
    body: str,
    country: str,
    config: AppConfig,
) -> dict[str, Any]:
    """Send WhatsApp message via Twilio. to_phone is a bare E.164 number (no whatsapp: prefix)."""
    from_phone = config.twilio_wa_us_phone if country == "US" else config.twilio_wa_ca_phone
    if not from_phone:
        logger.warning("WhatsApp send skipped for %s: no WA number configured for %s", to_phone, country)
        return {"sid": None, "status": "skipped_no_wa_number"}

    try:
        from twilio.rest import Client

        client = Client(config.twilio_account_sid, config.twilio_auth_token)
        message = client.messages.create(
            body=body,
            from_=from_phone,
            to=f"whatsapp:{to_phone}",
        )
        logger.info("WhatsApp sent to %s: SID=%s", to_phone, message.sid)
        return {"sid": message.sid, "status": message.status}
    except ImportError:
        logger.warning("Twilio SDK not installed. WhatsApp to %s not sent.", to_phone)
        return {"sid": "mock_no_twilio", "status": "mock"}
    except Exception as e:
        logger.error("WhatsApp send failed to %s: %s", to_phone, e)
        return {"sid": None, "status": "failed", "error": str(e)}


async def send_email(
    to_email: str,
    subject: str,
    body: str,
    country: str,
    config: AppConfig,
) -> dict[str, Any]:
    """Send email via Amazon SES. Returns SES message ID."""
    sender = (
        config.ses_sender_email_us if country == "US" else config.ses_sender_email_ca
    )
    sender_formatted = f"{config.ses_sender_name} <{sender}>"

    try:
        import boto3

        ses = boto3.client("ses", region_name=config.ses_region)
        response = ses.send_email(
            Source=sender_formatted,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
        message_id = response["MessageId"]
        logger.info("Email sent to %s: MessageId=%s", to_email, message_id)
        return {"message_id": message_id, "status": "sent"}
    except ImportError:
        logger.warning("boto3 not installed. Email to %s not sent.", to_email)
        return {"message_id": "mock_no_boto3", "status": "mock"}
    except Exception as e:
        logger.error("Email send failed to %s: %s", to_email, e)
        return {"message_id": None, "status": "failed", "error": str(e)}
