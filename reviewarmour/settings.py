"""Runtime configuration for the ReviewArmour AI layer.

Values are read from environment variables at process start. None of these
contain secrets except ``ANTHROPIC_API_KEY``, which is consumed by
``make_anthropic_client`` and never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Default: Claude Sonnet 4 (alias ID served by the Anthropic API). Override
# with ``ANTHROPIC_MODEL`` if your workspace exposes a different snapshot
# (e.g. ``claude-sonnet-4-5-20250929``).
DEFAULT_MODEL: str = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Hard ceiling on Anthropic call latency (seconds). Above this we surface a
# transport error instead of holding up the sender pipeline.
DEFAULT_REQUEST_TIMEOUT_S: float = float(os.environ.get("ANTHROPIC_TIMEOUT_S", "45"))

# How many times the Anthropic SDK retries 5xx / connection errors per call.
DEFAULT_MAX_RETRIES: int = int(os.environ.get("ANTHROPIC_MAX_RETRIES", "2"))

# How many times we re-prompt Claude when its JSON is unparseable or fails
# our schema. Independent from the SDK's HTTP retry.
DEFAULT_JSON_REPAIR_RETRIES: int = int(os.environ.get("LLM_JSON_REPAIR_RETRIES", "1"))

# Token budget for each Claude call. Conversation drafts can be a bit larger
# because they include subject + body; self-correction is short.
DEFAULT_DRAFT_MAX_TOKENS: int = int(os.environ.get("DRAFT_MAX_TOKENS", "1800"))
DEFAULT_REVIEW_MAX_TOKENS: int = int(os.environ.get("REVIEW_MAX_TOKENS", "1200"))

# A/B/C variation for the first-touch outbound. Default per spec is "A".
FIRST_TOUCH_VARIATION: str = os.environ.get("REVIEWARMOUR_FIRST_TOUCH_VARIATION", "A").upper()


@dataclass(frozen=True)
class LLMRuntime:
    """Bundle of per-call runtime knobs passed into ConversationModule / SelfCorrectionModule.

    Construct one explicitly when the env-driven defaults are not desired
    (tests, alternate deployments).
    """

    model: str = DEFAULT_MODEL
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S
    max_retries: int = DEFAULT_MAX_RETRIES
    json_repair_retries: int = DEFAULT_JSON_REPAIR_RETRIES
    draft_max_tokens: int = DEFAULT_DRAFT_MAX_TOKENS
    review_max_tokens: int = DEFAULT_REVIEW_MAX_TOKENS
