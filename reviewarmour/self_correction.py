from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol

from reviewarmour.prompt_templates import SELF_CORRECTION_SYSTEM

DEFAULT_MODEL = "claude-sonnet-4-20250514"


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse first JSON object from model output; strip optional markdown fences."""
    t = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)```\s*$", t, re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No valid JSON object in model output: {text[:200]!r}")
    return json.loads(t[start : end + 1])


class MessagesClient(Protocol):
    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict[str, Any]],
    ) -> Any: ...


@dataclass
class SelfCorrectionVerdict:
    verdict: str  # pass | fix | escalate
    failed_checks: list[str]
    suggested_fixes: list[str]
    escalation_reason: Optional[str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SelfCorrectionVerdict":
        return cls(
            verdict=str(d.get("verdict", "escalate")),
            failed_checks=list(d.get("failed_checks") or []),
            suggested_fixes=list(d.get("suggested_fixes") or []),
            escalation_reason=d.get("escalation_reason"),
        )


class SelfCorrectionModule:
    """
    Calls Claude to review drafts. Does not rewrite messages.
    """

    def __init__(
        self,
        client: Optional[MessagesClient] = None,
        *,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 1200,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def review(
        self,
        *,
        draft_subject: Optional[str],
        draft_body: str,
        channel: str,
        lead_record: dict[str, Any],
        transcript: list[dict[str, Any]],
        commercial_snapshot: Optional[dict[str, Any]],
        timeline_class: str,
        soft_quote_mode: bool,
    ) -> SelfCorrectionVerdict:
        if self._client is None:
            raise RuntimeError("Anthropic client not configured for SelfCorrectionModule.review")

        payload = {
            "draft": {"subject": draft_subject, "body": draft_body, "channel": channel},
            "lead_record": lead_record,
            "conversation_transcript": transcript,
            "commercial_snapshot": commercial_snapshot,
            "timeline_class": timeline_class,
            "soft_quote_mode": soft_quote_mode,
        }
        user = json.dumps(payload, ensure_ascii=False)
        msg = self._client.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=SELF_CORRECTION_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = ""
        for block in getattr(msg, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text += block.text
        data = extract_json_object(text)
        return SelfCorrectionVerdict.from_dict(data)


def make_anthropic_client(api_key: Optional[str] = None) -> Any:
    """Construct real Anthropic Messages API client when key is available."""
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Install anthropic package") from e

    return anthropic.Anthropic(api_key=api_key)
