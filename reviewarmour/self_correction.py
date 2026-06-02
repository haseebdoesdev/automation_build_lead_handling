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
    APPROVED_COPY_ALLOWING_EMDASH,
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

_EMDASH_RE = re.compile(r"[\u2014\u2013]")


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


# Spec v2 Section 13 — deterministic SC pre-checks
# ------------------------------------------------------------------------

# Matches any USD figure: $400, $1,200, 425 USD, 400 dollars
_USD_FIGURE_RE = re.compile(
    r"(?:\$\s?\d[\d,]*(?:\.\d+)?|"
    r"\b\d{2,4}\s*(?:USD|usd|dollars?)\b|"
    r"\b\d{2,4}\s*(?:per\s+review|/review|/per\s+review))",
    re.IGNORECASE,
)

# Spec v2 Section 13: banned ROI/CLV/lifetime-value language in any AI message.
_ROI_CLV_PATTERNS = (
    re.compile(r"\broi\b", re.IGNORECASE),
    re.compile(r"\breturn on investment\b", re.IGNORECASE),
    re.compile(r"\bclv\b", re.IGNORECASE),
    re.compile(r"\bcustomer lifetime value\b", re.IGNORECASE),
    re.compile(r"\blifetime value\b", re.IGNORECASE),
    re.compile(r"\bvalue per customer\b", re.IGNORECASE),
    re.compile(r"\brevenue per customer\b", re.IGNORECASE),
)

# Internal financial data the AI must never put in customer messages.
_HIDDEN_COST_PATTERNS = (
    re.compile(r"\bcost\s+(?:to\s+remove|of\s+removal|per\s+removal)\b", re.IGNORECASE),
    re.compile(r"\blead\s+(?:cost|acquisition\s+cost)\b", re.IGNORECASE),
    re.compile(r"\bour\s+margin\b", re.IGNORECASE),
    re.compile(r"\bmargin\s+(?:percentage|percent|%|floor|minimum)\b", re.IGNORECASE),
    re.compile(r"\bour\s+cost\b", re.IGNORECASE),
)


def _draft_dollar_figures(draft_body: str) -> list[str]:
    """Return raw USD figure substrings appearing in the draft."""
    return _USD_FIGURE_RE.findall(draft_body or "")


def _phone_call_threshold_violation_check(
    verdict: SelfCorrectionVerdict,
    *,
    draft_body: str,
    commercial_snapshot: Optional[dict[str, Any]],
) -> SelfCorrectionVerdict:
    """Spec v2 Section 4 + 13: If phone_call_threshold_triggered=True the draft
    must NOT contain any specific dollar quote. Verdict → fix on violation.
    """
    if not commercial_snapshot:
        return verdict
    if not commercial_snapshot.get("phone_call_threshold_triggered"):
        return verdict

    figures = _draft_dollar_figures(draft_body)
    if not figures:
        return verdict

    failed = list(verdict.failed_checks)
    failed.append(
        "phone_call_threshold: draft contains a dollar figure but quote must "
        "be routed to phone call"
    )
    fixes = list(verdict.suggested_fixes)
    fixes.append(
        "Remove any specific dollar amount. Tell the lead their specialist will "
        "walk them through pricing on a quick call."
    )
    new_verdict = "fix" if verdict.verdict == "pass" else verdict.verdict
    return SelfCorrectionVerdict(
        verdict=new_verdict,
        failed_checks=failed,
        suggested_fixes=fixes,
        escalation_reason=verdict.escalation_reason,
    )


def _roi_clv_language_check(
    verdict: SelfCorrectionVerdict,
    *,
    draft_body: str,
) -> SelfCorrectionVerdict:
    """Spec v2 Section 13: ROI / CLV / lifetime-value language is forbidden in
    every AI message. Verdict → fix.
    """
    body = draft_body or ""
    hits = [p.pattern for p in _ROI_CLV_PATTERNS if p.search(body)]
    if not hits:
        return verdict
    failed = list(verdict.failed_checks)
    failed.append(f"roi_clv_language: matched patterns {hits}")
    fixes = list(verdict.suggested_fixes)
    fixes.append(
        "Remove ROI / lifetime-value / return-on-investment framing. Speak to "
        "the immediate review-removal outcome only."
    )
    new_verdict = "fix" if verdict.verdict == "pass" else verdict.verdict
    return SelfCorrectionVerdict(
        verdict=new_verdict,
        failed_checks=failed,
        suggested_fixes=fixes,
        escalation_reason=verdict.escalation_reason,
    )


def _hidden_cost_language_check(
    verdict: SelfCorrectionVerdict,
    *,
    draft_body: str,
) -> SelfCorrectionVerdict:
    """Spec v2 Section 11: internal financial data ('our margin', 'cost to
    remove', 'lead cost', etc.) in a draft is an immediate escalation.
    """
    body = draft_body or ""
    hits = [p.pattern for p in _HIDDEN_COST_PATTERNS if p.search(body)]
    if not hits:
        return verdict
    failed = list(verdict.failed_checks)
    failed.append(f"hidden_cost_leak: matched patterns {hits}")
    fixes = list(verdict.suggested_fixes)
    fixes.append("Remove all internal cost / margin language.")
    return SelfCorrectionVerdict(
        verdict="escalate",
        failed_checks=failed,
        suggested_fixes=fixes,
        escalation_reason="hidden_cost_leak",
    )


def _floor_breach_check(
    verdict: SelfCorrectionVerdict,
    *,
    draft_body: str,
    commercial_snapshot: Optional[dict[str, Any]],
) -> SelfCorrectionVerdict:
    """Spec v2 Section 1: tier floors are absolute. If the draft quotes a
    per-review price below the tier floor, escalate.
    """
    if not commercial_snapshot:
        return verdict
    floor = commercial_snapshot.get("floor_usd") or commercial_snapshot.get("floor")
    if not floor:
        return verdict
    body = draft_body or ""
    # Look for the dollar-USD figures and extract the integer.
    matches = re.findall(r"\$\s?(\d[\d,]*)(?:\.\d+)?", body)
    for m in matches:
        try:
            val = int(m.replace(",", ""))
        except ValueError:
            continue
        # Per-review prices live in $100–$999; ignore $1000+ (total-deal mentions).
        if 100 <= val <= 999 and val < floor:
            failed = list(verdict.failed_checks) + [
                f"floor_breach: quoted ${val} < tier floor ${floor}"
            ]
            fixes = list(verdict.suggested_fixes) + [
                f"Do not quote below ${floor}/review. Escalate to human."
            ]
            return SelfCorrectionVerdict(
                verdict="escalate",
                failed_checks=failed,
                suggested_fixes=fixes,
                escalation_reason="floor_breach",
            )
    return verdict


def draft_has_forbidden_em_dash(
    draft_body: str,
    *,
    allowed_fragments: tuple[str, ...] = APPROVED_COPY_ALLOWING_EMDASH,
) -> bool:
    """True when the draft contains em/en dashes outside approved verbatim blocks."""
    body = draft_body or ""
    if not _EMDASH_RE.search(body):
        return False
    stripped = body
    for fragment in allowed_fragments:
        stripped = stripped.replace(fragment, "")
    return bool(_EMDASH_RE.search(stripped))


def _enforce_em_dash_verdict(
    verdict: SelfCorrectionVerdict,
    *,
    draft_body: str,
) -> SelfCorrectionVerdict:
    """Deterministic copy_rules gate: fail drafts with forbidden em dashes."""
    if not draft_has_forbidden_em_dash(draft_body):
        return verdict

    reason = "copy_rules: em dash present"
    failed = list(verdict.failed_checks)
    if not any("em dash" in f.lower() for f in failed):
        failed.append(reason)

    fixes = list(verdict.suggested_fixes)
    if not fixes:
        fixes = ["Replace em dashes with a comma or hyphen"]

    if verdict.verdict == "escalate":
        return verdict

    return SelfCorrectionVerdict(
        verdict="fix",
        failed_checks=failed,
        suggested_fixes=fixes,
        escalation_reason=verdict.escalation_reason,
    )


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
        verdict = _sanitize_timeline_verdict(
            verdict,
            draft_body=draft_body,
            approved_timeline_paragraph=approved_para,
        )
        verdict = _enforce_em_dash_verdict(verdict, draft_body=draft_body)

        # Spec v2 deterministic post-checks. Order matters: hidden-cost and
        # floor-breach escalate immediately; phone-call-threshold and ROI/CLV
        # downgrade pass→fix.
        verdict = _hidden_cost_language_check(verdict, draft_body=draft_body)
        verdict = _floor_breach_check(
            verdict,
            draft_body=draft_body,
            commercial_snapshot=commercial_snapshot,
        )
        verdict = _phone_call_threshold_violation_check(
            verdict,
            draft_body=draft_body,
            commercial_snapshot=commercial_snapshot,
        )
        verdict = _roi_clv_language_check(verdict, draft_body=draft_body)
        return verdict


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
