"""Domain error types for the ReviewArmour AI layer.

These let callers (CRM, sender service, alerting) discriminate between
upstream failures (Anthropic, network), data violations (schema), and
business-logic outcomes (escalate, human queue).
"""

from __future__ import annotations


class ReviewArmourError(Exception):
    """Base class."""


class ConfigError(ReviewArmourError):
    """Misconfiguration — missing API key, bad model id, etc."""


class LLMResponseError(ReviewArmourError):
    """Claude returned an unparseable or schema-invalid response after retries."""


class LLMTransportError(ReviewArmourError):
    """Network / HTTP layer failure after retries."""


class CommercialPolicyError(ReviewArmourError):
    """Caller asked the engine to do something forbidden by policy
    (e.g. quote when ai_quote_allowed is False at a layer that should not see it)."""
