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


# Spec v2 Section 13 + analysis Bug D: phone-route copy and any pricing copy
# may not hedge with "for a profile like X" — that's the LLM's fall-back
# pattern when SC tells it not to hedge. We strip it deterministically after
# the SC verdict so the redrafter loop can converge instead of looping on the
# same violation across all retries.
# Spec v2 analysis Bug I: tightened from the original to require a clean
# punctuation boundary, exclude newlines, and cap the inner match at 35 chars
# (long enough for a business name + 1-2 words, short enough to never chew
# into the next clause). The original ``[^,.]{1,60}`` greedy class was eating
# benign text in Conv 37, producing broken copy like "...reviews wn, not before".
_HEDGED_INTRO_RE = re.compile(
    r"\bfor\s+(?:a\s+)?(?:profile|business(?:es)?|client(?:s)?|case|practice|"
    r"company|customer)\s+like\s+[^\n,.]{1,35}[,.]\s*",
    re.IGNORECASE,
)


def strip_forbidden_em_dashes(
    draft_body: str,
    *,
    allowed_fragments: tuple[str, ...] = APPROVED_COPY_ALLOWING_EMDASH,
) -> str:
    """Replace em / en dashes with `", "` (comma + space) OUTSIDE approved blocks.

    Spec v2 analysis Bug O: the LLM redrafter consistently re-emits em dashes
    even after SC flags them, causing first-touch and reply drafts to sink to
    human_queue. We strip them deterministically AFTER the drafter run so the
    SC pass sees clean copy and the loop converges. The strip preserves the
    handful of approved verbatim blocks that intentionally contain em dashes
    (success_percentage_asked, pay-anchor) by temporarily masking them.

    Examples:
      "...pay-after-removal basis — no charge..."  -> "...pay-after-removal basis, no charge..."
      "We deliver — and we hold the line."           -> "We deliver, and we hold the line."
    """
    if not draft_body or not _EMDASH_RE.search(draft_body):
        return draft_body
    # Mask approved fragments so their em dashes survive.
    masked = draft_body
    placeholders: list[tuple[str, str]] = []
    for i, fragment in enumerate(allowed_fragments):
        if fragment and fragment in masked:
            token = f"\x00APPROVED_FRAG_{i}\x00"
            masked = masked.replace(fragment, token)
            placeholders.append((token, fragment))
    # Replace em/en dashes outside approved fragments. We collapse surrounding
    # spaces so the comma sits naturally.
    cleaned = re.sub(r"\s*[—–]\s*", ", ", masked)
    # Restore approved fragments verbatim.
    for token, fragment in placeholders:
        cleaned = cleaned.replace(token, fragment)
    return cleaned


def strip_hedged_pricing_intro(draft_body: str) -> str:
    """Remove 'for a profile like X' / 'for a business like Y' hedges in place.

    The LLM tends to re-emit these even after SC flags them. Deterministic
    strip is the only reliable termination for that loop. We do not capitalize
    the next sentence (the redrafter typically already wrote the rest of the
    sentence to flow without the hedge, so dropping just the prefix produces
    natural copy in practice).
    """
    if not draft_body:
        return draft_body
    cleaned = _HEDGED_INTRO_RE.sub("", draft_body)
    # Collapse any double-spaces or leading whitespace introduced by the strip.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n[ \t]+", "\n", cleaned)
    # Re-capitalize the first character of any sentence that now starts with
    # a lowercase letter immediately after a sentence-terminating newline.
    def _cap(m: re.Match[str]) -> str:
        return m.group(1) + m.group(2).upper()
    cleaned = re.sub(r"(^|\n\n)([a-z])", _cap, cleaned)
    return cleaned


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


# Spec v2 analysis Bug G: when the lead's latest inbound asks about timing
# / hard guarantee and an approved timeline paragraph is set, the draft body
# MUST contain that paragraph verbatim. The LLM SC sometimes accepts a
# paraphrase; this deterministic pre-check downgrades pass->fix in that case.
_TIMING_TOPIC_PATTERNS = (
    re.compile(r"\bhow\s+(?:fast|quickly|long|soon)\b", re.IGNORECASE),
    re.compile(r"\bwhen\s+(?:can|will|do)\b", re.IGNORECASE),
    re.compile(r"\btimeline\b", re.IGNORECASE),
    re.compile(r"\bcommit\s+to\b", re.IGNORECASE),
    re.compile(r"\bguarantee\b", re.IGNORECASE),
    re.compile(r"\bby\s+(?:next|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE),
    re.compile(r"\bexpect\s+them\s+down\b", re.IGNORECASE),
    re.compile(r"\bcome\s+down\b", re.IGNORECASE),
)


def _inbound_asks_timing(transcript: list[dict[str, Any]]) -> bool:
    """True if the latest lead turn raises a timing / guarantee topic."""
    for turn in reversed(transcript):
        if turn.get("role") not in ("lead", "user"):
            continue
        body = turn.get("body") or turn.get("content") or ""
        return any(p.search(body) for p in _TIMING_TOPIC_PATTERNS)
    return False


def _enforce_verbatim_timeline_paragraph(
    verdict: SelfCorrectionVerdict,
    *,
    draft_body: str,
    transcript: list[dict[str, Any]],
    approved_timeline_paragraph: Optional[str],
) -> SelfCorrectionVerdict:
    """Spec v2 analysis Bug G: if the lead asked a timing question and an
    approved paragraph was passed in, the draft body MUST contain it verbatim.
    Otherwise we downgrade pass->fix so the redrafter pulls the verbatim string.
    """
    if not approved_timeline_paragraph:
        return verdict
    if not _inbound_asks_timing(transcript):
        return verdict
    body_norm = _collapse_whitespace(draft_body)
    if approved_timeline_paragraph in body_norm:
        return verdict
    failed = list(verdict.failed_checks)
    failed.append(
        "timeline_language: lead asked timing/guarantee but draft does not "
        "contain the verbatim approved_timeline_paragraph"
    )
    fixes = list(verdict.suggested_fixes)
    fixes.append(
        "Paste the approved_timeline_paragraph for the current timeline_framing_key "
        "into the draft verbatim — no paraphrase."
    )
    new_verdict = "fix" if verdict.verdict == "pass" else verdict.verdict
    return SelfCorrectionVerdict(
        verdict=new_verdict,
        failed_checks=failed,
        suggested_fixes=fixes,
        escalation_reason=verdict.escalation_reason,
    )


def _sanitize_methodology_verdict(
    verdict: SelfCorrectionVerdict,
    *,
    draft_body: str,
    approved_methodology_paragraphs: dict[str, str],
) -> SelfCorrectionVerdict:
    """Spec v2 analysis Bug J + L: drop scope / methodology_language failures
    when the draft contains a verbatim approved METHODOLOGY paragraph.

    The LLM SC sometimes flags the verbatim ``"...which is why our success
    rate holds where it does"`` tail as an invented success claim, even though
    it's part of the canonical METHODOLOGY general string.
    """
    if not approved_methodology_paragraphs:
        return verdict
    body_norm = _collapse_whitespace(draft_body)
    present = any(
        para and para in body_norm
        for para in approved_methodology_paragraphs.values()
    )
    if not present:
        return verdict
    drop_prefixes = ("methodology_language:", "scope:", "success_rate:")
    failed = [
        f
        for f in verdict.failed_checks
        if not (
            any(f.startswith(p) for p in drop_prefixes)
            and (
                "methodolog" in f.lower()
                or "operational detail" in f.lower()
                or "success rate" in f.lower()
                or "policy violation" in f.lower()
            )
        )
    ]
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
    new_reason = verdict.escalation_reason
    if new_verdict == "escalate" and not any(
        f.startswith("hidden_cost_leak") or f.startswith("floor_breach")
        for f in failed
    ):
        new_verdict = "fix"
        new_reason = None
    return SelfCorrectionVerdict(
        verdict=new_verdict,
        failed_checks=failed,
        suggested_fixes=verdict.suggested_fixes,
        escalation_reason=new_reason,
    )


def _sanitize_docusign_verdict(
    verdict: SelfCorrectionVerdict,
    *,
    draft_body: str,
    approved_docusign_line: str,
) -> SelfCorrectionVerdict:
    """Spec v2 analysis Bug K: drop scope failures that flag DocuSign /
    contract-detail expansion when the approved one-liner is the substring.

    The drafter tends to elaborate ("we send the removal brief via DocuSign,
    you sign there") which triggers ``scope: contract beyond DocuSign line``
    in SC. The expansion is fine as long as the approved one-liner is present
    AND the word "contract" doesn't appear (the prompt already bans that).
    """
    if not approved_docusign_line:
        return verdict
    body_norm = _collapse_whitespace(draft_body)
    if approved_docusign_line not in body_norm:
        return verdict
    # If the draft uses the banned word "contract" we leave the scope failure.
    if re.search(r"\bcontract\b", draft_body, re.IGNORECASE):
        return verdict
    drop_prefixes = ("scope:",)
    failed = [
        f
        for f in verdict.failed_checks
        if not (
            any(f.startswith(p) for p in drop_prefixes)
            and (
                "docusign" in f.lower()
                or "contract" in f.lower()
                or "agreement" in f.lower()
                or "removal brief" in f.lower()
            )
        )
    ]
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
    new_reason = verdict.escalation_reason
    if new_verdict == "escalate" and not any(
        f.startswith("hidden_cost_leak") or f.startswith("floor_breach")
        for f in failed
    ):
        new_verdict = "fix"
        new_reason = None
    return SelfCorrectionVerdict(
        verdict=new_verdict,
        failed_checks=failed,
        suggested_fixes=verdict.suggested_fixes,
        escalation_reason=new_reason,
    )


def _sanitize_success_verdict(
    verdict: SelfCorrectionVerdict,
    *,
    draft_body: str,
    approved_success_paragraphs: dict[str, str],
) -> SelfCorrectionVerdict:
    """Drop spurious success_rate / scope failures when an approved SUCCESS
    paragraph is present verbatim in the draft (spec v2 analysis Bug H).

    The LLM SC sometimes flags 'high success rate' as an invented qualitative
    claim even when the exact APPROVED_SUCCESS_GENERAL string is present. We
    detect the verbatim substring and clear those failure kinds.
    """
    if not approved_success_paragraphs:
        return verdict
    body_norm = _collapse_whitespace(draft_body)
    present = any(
        para and para in body_norm for para in approved_success_paragraphs.values()
    )
    if not present:
        return verdict
    success_drop_prefixes = ("success_rate:", "scope:")
    failed = [
        f
        for f in verdict.failed_checks
        if not (
            any(f.startswith(p) for p in success_drop_prefixes)
            and ("success" in f.lower() or "high success rate" in f.lower())
        )
    ]
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
    # If we dropped enough to remove the escalation reason, demote escalate→fix.
    new_reason = verdict.escalation_reason
    if new_verdict == "escalate" and not any(
        f.startswith("hidden_cost_leak") or f.startswith("floor_breach")
        or f.startswith("scope:") for f in failed
    ):
        new_verdict = "fix"
        new_reason = None
    return SelfCorrectionVerdict(
        verdict=new_verdict,
        failed_checks=failed,
        suggested_fixes=verdict.suggested_fixes,
        escalation_reason=new_reason,
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
        # Spec v2 analysis Bug H + J + L + K: also surface the approved SUCCESS,
        # METHODOLOGY, and DocuSign strings so SC can recognize them as
        # verbatim allowlist when present.
        from reviewarmour.prompt_templates import (
            APPROVED_DOCUSIGN_LINE,
            APPROVED_METHODOLOGY_PARAGRAPHS,
            APPROVED_SUCCESS_PARAGRAPHS,
        )
        payload = {
            "draft": {"subject": draft_subject, "body": draft_body, "channel": channel},
            "lead_record": lead_record,
            "conversation_transcript": transcript,
            "commercial_snapshot": commercial_snapshot,
            "timeline_class": timeline_class,
            "timeline_framing_key": framing_key,
            "approved_timeline_paragraph": approved_para,
            "approved_success_paragraphs": APPROVED_SUCCESS_PARAGRAPHS,
            "approved_methodology_paragraphs": APPROVED_METHODOLOGY_PARAGRAPHS,
            "approved_docusign_line": APPROVED_DOCUSIGN_LINE,
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
        verdict = _enforce_verbatim_timeline_paragraph(
            verdict,
            draft_body=draft_body,
            transcript=transcript,
            approved_timeline_paragraph=approved_para,
        )
        verdict = _sanitize_success_verdict(
            verdict,
            draft_body=draft_body,
            approved_success_paragraphs=APPROVED_SUCCESS_PARAGRAPHS,
        )
        verdict = _sanitize_methodology_verdict(
            verdict,
            draft_body=draft_body,
            approved_methodology_paragraphs=APPROVED_METHODOLOGY_PARAGRAPHS,
        )
        verdict = _sanitize_docusign_verdict(
            verdict,
            draft_body=draft_body,
            approved_docusign_line=APPROVED_DOCUSIGN_LINE,
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
