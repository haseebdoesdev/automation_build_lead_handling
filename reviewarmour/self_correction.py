"""Self-correction module.

Calls Claude with a structured review prompt and returns a strict JSON verdict.
Never rewrites the candidate draft itself; it returns directives the
conversation module can use to redraft.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from reviewarmour.errors import ConfigError, LLMResponseError, LLMTransportError
from reviewarmour.prompt_templates import (
    APPROVED_TIMELINE_PARAGRAPHS,
    SELF_CORRECTION_SYSTEM,
)
from reviewarmour.settings import LLMRuntime

logger = logging.getLogger("reviewarmour.self_correction")

# Re-export for callers that want to plumb the same default through.
DEFAULT_MODEL = LLMRuntime().model

_VALID_VERDICTS = frozenset({"pass", "fix", "escalate"})

_HARD_CALENDAR_DATE_DEMAND_RE = re.compile(
    r"(?:"
    r"thehard\s+date|"
    r"\b("
    r"the\s*hard\s+date|"
    r"hard\s+date|exact\s+date|specific\s+date|specifc\s+date|concrete\s+date|"
    r"fixed\s+date|"
    r"calendar\s+date|need\s+a\s+date|give\s+me\s+a\s+date|"
    r"commit\s+to\s+(a\s+)?(day|date)|promise\s+(me\s+)?(a\s+)?(specific\s+)?date|"
    r"guarantee(d)?\s+(by|before|on\b|a\s+date)|"
    r"exact\s+day|specific\s+day|which\s+day\b|by\s+when\b|when\s+exactly\b|"
    r"by\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"by\s+next\s+week|deadline\s+of|firm\s+date"
    r")\b"
    r")",
    re.IGNORECASE,
)


def _latest_lead_message_text(transcript: list[dict[str, Any]]) -> str:
    for turn in reversed(transcript or []):
        role = str(turn.get("role") or "").lower()
        if role in ("lead", "user"):
            return str(turn.get("body") or "")
    return ""


def lead_demands_hard_calendar_date(transcript: list[dict[str, Any]]) -> bool:
    """True when the latest lead turn insists on a fixed day / guaranteed date."""
    return bool(_HARD_CALENDAR_DATE_DEMAND_RE.search(_latest_lead_message_text(transcript)))


def approved_timeline_paragraph_for_review(
    transcript: list[dict[str, Any]],
    timeline_class: str,
) -> tuple[Optional[str], str]:
    """Return (paragraph, framing_key) for timeline_language self-correction.

    Hard-date demands use ``hard_guarantee_asked``; otherwise recency ``timeline_class``.
    """
    if lead_demands_hard_calendar_date(transcript):
        para = APPROVED_TIMELINE_PARAGRAPHS.get("hard_guarantee_asked")
        return para, "hard_guarantee_asked"
    para = APPROVED_TIMELINE_PARAGRAPHS.get(timeline_class)
    return para, timeline_class


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse first JSON object from model output. Strips a single optional code fence.

    Raises:
        LLMResponseError: when no JSON object can be located or the JSON is malformed.
    """
    if not text or not text.strip():
        raise LLMResponseError("Empty model output.")
    t = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)```\s*$", t, re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMResponseError(f"No JSON object in model output: {text[:200]!r}")
    try:
        return json.loads(t[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMResponseError(f"Malformed JSON: {e.msg}: {text[:200]!r}") from e


class MessagesNamespace(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class AnthropicMessagesClient(Protocol):
    @property
    def messages(self) -> MessagesNamespace: ...


@dataclass
class SelfCorrectionVerdict:
    """The structured output from the self-correction Claude call."""

    verdict: str  # "pass" | "fix" | "escalate"
    failed_checks: list[str]
    suggested_fixes: list[str]
    escalation_reason: Optional[str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SelfCorrectionVerdict":
        verdict = str(d.get("verdict", "")).strip().lower()
        if verdict not in _VALID_VERDICTS:
            raise LLMResponseError(
                f"Invalid verdict {verdict!r}; expected one of {sorted(_VALID_VERDICTS)}"
            )
        failed = d.get("failed_checks") or []
        if not isinstance(failed, list):
            raise LLMResponseError("failed_checks must be a list of strings")
        fixes = d.get("suggested_fixes") or []
        if not isinstance(fixes, list):
            raise LLMResponseError("suggested_fixes must be a list of strings")
        escalation_reason = d.get("escalation_reason")
        if escalation_reason is not None and not isinstance(escalation_reason, str):
            raise LLMResponseError("escalation_reason must be string or null")
        return cls(
            verdict=verdict,
            failed_checks=[str(x) for x in failed],
            suggested_fixes=[str(x) for x in fixes],
            escalation_reason=escalation_reason,
        )


def _collapse_whitespace(body: str) -> str:
    return re.sub(r"\s+", " ", (body or "").strip())


def _sanitize_timeline_verdict(
    verdict: SelfCorrectionVerdict,
    *,
    draft_body: str,
    approved_timeline_paragraph: Optional[str],
) -> SelfCorrectionVerdict:
    """Drop spurious timeline_language failures when the approved paragraph is present."""
    para = approved_timeline_paragraph
    if not para:
        return verdict
    if para not in _collapse_whitespace(draft_body):
        return verdict
    timeline_prefix = "timeline_language:"
    failed = [f for f in verdict.failed_checks if not f.startswith(timeline_prefix)]
    if len(failed) == len(verdict.failed_checks):
        return verdict

    if not failed:
        return SelfCorrectionVerdict(
            verdict="pass",
            failed_checks=[],
            suggested_fixes=[],
            escalation_reason=None,
        )

    new_verdict = verdict.verdict
    if new_verdict == "pass":
        new_verdict = "fix"

    return SelfCorrectionVerdict(
        verdict=new_verdict,
        failed_checks=failed,
        suggested_fixes=verdict.suggested_fixes,
        escalation_reason=verdict.escalation_reason,
    )


def _extract_text(msg: Any) -> str:
    """Concatenate text blocks from an Anthropic Messages response."""
    out = ""
    for block in getattr(msg, "content", []) or []:
        if getattr(block, "type", None) == "text":
            out += block.text
    return out


def _call_claude_for_json(
    *,
    client: AnthropicMessagesClient,
    runtime: LLMRuntime,
    system: str,
    user_payload: str,
    max_tokens: int,
) -> dict[str, Any]:
    """Invoke Claude and parse a JSON object from the response.

    Repairs malformed JSON up to ``runtime.json_repair_retries`` times by
    re-prompting with a strict reminder. Wraps SDK transport failures in
    :class:`LLMTransportError` so callers can react uniformly.
    """
    try:
        import anthropic  # noqa: F401  (only imported for the error class on this path)
    except ImportError as e:
        raise ConfigError("anthropic package is required for live calls") from e

    from anthropic import APIConnectionError, APIError, APITimeoutError  # type: ignore

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_payload}]
    last_err: Optional[Exception] = None

    for attempt in range(runtime.json_repair_retries + 1):
        try:
            # temperature=0 — verdicts and structured drafts must be deterministic.
            msg = client.messages.create(  # type: ignore[attr-defined]
                model=runtime.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                timeout=runtime.timeout_s,
                temperature=0,
            )
        except (APITimeoutError, APIConnectionError) as e:
            raise LLMTransportError(f"Anthropic transport error: {e}") from e
        except APIError as e:
            raise LLMTransportError(f"Anthropic API error: {e}") from e

        text = _extract_text(msg)
        try:
            return extract_json_object(text)
        except LLMResponseError as e:
            last_err = e
            logger.warning(
                "JSON repair retry %d/%d for model output: %s",
                attempt + 1,
                runtime.json_repair_retries,
                e,
            )
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous reply was not valid JSON. Reply again with a "
                        "single JSON object only, no prose, no markdown fences."
                    ),
                }
            )

    raise LLMResponseError(
        f"Could not obtain valid JSON after {runtime.json_repair_retries + 1} attempts: {last_err}"
    )


class SelfCorrectionModule:
    """Reviews each outbound draft. Returns a verdict; never rewrites the message."""

    def __init__(
        self,
        client: AnthropicMessagesClient,
        *,
        runtime: Optional[LLMRuntime] = None,
        system_prompt: str = SELF_CORRECTION_SYSTEM,
    ) -> None:
        if client is None:
            raise ConfigError("SelfCorrectionModule requires an Anthropic client")
        self._client = client
        self._runtime = runtime or LLMRuntime()
        self._system = system_prompt

    @property
    def runtime(self) -> LLMRuntime:
        return self._runtime

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
        gbp_inspection: Optional[dict[str, Any]] = None,
    ) -> SelfCorrectionVerdict:
        approved_para, framing_key = approved_timeline_paragraph_for_review(
            transcript, timeline_class
        )
        payload = {
            "draft": {"subject": draft_subject, "body": draft_body, "channel": channel},
            "lead_record": lead_record,
            "conversation_transcript": transcript,
            "commercial_snapshot": commercial_snapshot,
            "timeline_class": timeline_class,
            "timeline_framing_key": framing_key,
            "approved_timeline_paragraph": approved_para,
            "soft_quote_mode": soft_quote_mode,
            "gbp_inspection": gbp_inspection,
        }
        data = _call_claude_for_json(
            client=self._client,
            runtime=self._runtime,
            system=self._system,
            user_payload=json.dumps(payload, ensure_ascii=False),
            max_tokens=self._runtime.review_max_tokens,
        )
        verdict = SelfCorrectionVerdict.from_dict(data)
        return _sanitize_timeline_verdict(
            verdict,
            draft_body=draft_body,
            approved_timeline_paragraph=approved_para,
        )


def make_anthropic_client(
    api_key: Optional[str] = None,
    *,
    max_retries: Optional[int] = None,
) -> Any:
    """Construct a real Anthropic Messages client for production use.

    Reads ``ANTHROPIC_API_KEY`` from the environment when ``api_key`` is omitted.
    Configures the SDK's HTTP retry policy from settings; per-call timeouts are
    applied at each ``messages.create`` site by the modules above.
    """
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise ConfigError("Install the anthropic package: pip install anthropic") from e

    key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ConfigError(
            "Missing Anthropic API key: set ANTHROPIC_API_KEY in the environment "
            "or pass api_key= explicitly."
        )
    runtime = LLMRuntime()
    return anthropic.Anthropic(
        api_key=key,
        max_retries=max_retries if max_retries is not None else runtime.max_retries,
    )
