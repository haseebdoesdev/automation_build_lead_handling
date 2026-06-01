"""Pytest hooks for live-flow artifact capture and report generation.

When ``tests/test_live_flows.py`` runs with ``ANTHROPIC_API_KEY`` set, pipeline /
self-correction / commercial outputs are recorded per test and written to
``tests/TEST_RESULTS_REPORT.md`` and ``tests_log.md`` after the session.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = REPO_ROOT / "tests" / "TEST_RESULTS_REPORT.md"
LOG_PATH = REPO_ROOT / "tests_log.md"

_thread = threading.local()
_session: dict[str, Any] = {
    "enabled": False,
    "artifacts": {},
    "results": {},
    "started_at": None,
    "finished_at": None,
}


def _current_nodeid() -> Optional[str]:
    return getattr(_thread, "nodeid", None)


def _artifact_bucket(nodeid: str) -> dict[str, Any]:
    bucket = _session["artifacts"].setdefault(
        nodeid,
        {"outputs": [], "class_doc": "", "test_doc": ""},
    )
    return bucket


def _append_output(nodeid: str, entry: dict[str, Any]) -> None:
    if not _session["enabled"]:
        return
    _artifact_bucket(nodeid)["outputs"].append(entry)


def _serialize_pipeline_result(result: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    draft = result.draft
    commercial = result.commercial
    sc_logs = []
    for log in result.self_correction_logs or []:
        sc_logs.append(
            {
                "attempt": log.attempt,
                "verdict": log.verdict,
                "failed_checks": list(log.failed_checks),
            }
        )
    entry: dict[str, Any] = {
        "type": "pipeline",
        "outcome": result.outcome,
        "inbound_message": kwargs.get("inbound_message"),
        "wants_price": kwargs.get("wants_price"),
        "quoted_previously": kwargs.get("quoted_previously"),
        "sequence_stage": kwargs.get("sequence_stage"),
        "channel": getattr(kwargs.get("channel"), "value", kwargs.get("channel")),
        "draft_action": getattr(draft, "action", None) if draft else None,
        "draft_subject": getattr(draft, "subject", None) if draft else None,
        "draft_body": getattr(draft, "body", None) if draft else None,
        "draft_reason": getattr(draft, "reason", None) if draft else None,
        "state_updates": dict(result.state_updates or {}),
        "handoff_payload": result.handoff_payload,
        "human_queue_payload": result.human_queue_payload,
        "self_correction_logs": sc_logs,
    }
    if commercial is not None:
        entry["commercial"] = {
            "tier_id": commercial.tier_id,
            "authorized_quote_usd_per_review": commercial.authorized_quote_usd_per_review,
            "negotiation_step": commercial.negotiation_step,
            "can_quote": commercial.can_quote,
            "escalate": commercial.escalate,
            "escalation_reason": commercial.escalation_reason,
            "request_gbp_first": commercial.request_gbp_first,
        }
    return entry


def _serialize_sc_verdict(verdict: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "self_correction",
        "input_draft_body": kwargs.get("draft_body"),
        "input_draft_subject": kwargs.get("draft_subject"),
        "verdict": verdict.verdict,
        "failed_checks": list(verdict.failed_checks),
        "suggested_fixes": list(verdict.suggested_fixes),
        "escalation_reason": verdict.escalation_reason,
    }


def _serialize_commercial(result: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "commercial",
        "wants_price": kwargs.get("wants_price"),
        "tier_id": result.tier_id,
        "authorized_quote_usd_per_review": result.authorized_quote_usd_per_review,
        "negotiation_step": result.negotiation_step,
        "can_quote": result.can_quote,
        "escalate": result.escalate,
        "escalation_reason": result.escalation_reason,
        "request_gbp_first": result.request_gbp_first,
    }


def _serialize_review_draft(draft: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "review_request_draft",
        "touch_number": kwargs.get("touch_number"),
        "channel": getattr(kwargs.get("channel"), "value", kwargs.get("channel")),
        "action": draft.action,
        "subject": draft.subject,
        "body": draft.body,
        "reason": draft.reason,
    }


def _install_capture_patches() -> None:
    from reviewarmour.commercial import CommercialEngine
    from reviewarmour.conversation import CustomerReviewRequestModule, OutboundPipeline
    from reviewarmour.self_correction import SelfCorrectionModule

    if getattr(_install_capture_patches, "_done", False):
        return

    _orig_run = OutboundPipeline.run
    _orig_review = SelfCorrectionModule.review
    _orig_eval = CommercialEngine.evaluate_pricing
    _orig_review_draft = CustomerReviewRequestModule.draft

    def patched_run(self, **kwargs):
        result = _orig_run(self, **kwargs)
        nodeid = _current_nodeid()
        if nodeid:
            _append_output(nodeid, _serialize_pipeline_result(result, kwargs))
        return result

    def patched_review(self, **kwargs):
        verdict = _orig_review(self, **kwargs)
        nodeid = _current_nodeid()
        if nodeid:
            _append_output(nodeid, _serialize_sc_verdict(verdict, kwargs))
        return verdict

    def patched_eval(self, lead, **kwargs):
        result = _orig_eval(self, lead, **kwargs)
        nodeid = _current_nodeid()
        if nodeid:
            _append_output(nodeid, _serialize_commercial(result, kwargs))
        return result

    def patched_review_draft(self, **kwargs):
        draft = _orig_review_draft(self, **kwargs)
        nodeid = _current_nodeid()
        if nodeid:
            _append_output(nodeid, _serialize_review_draft(draft, kwargs))
        return draft

    OutboundPipeline.run = patched_run  # type: ignore[method-assign]
    SelfCorrectionModule.review = patched_review  # type: ignore[method-assign]
    CommercialEngine.evaluate_pricing = patched_eval  # type: ignore[method-assign]
    CustomerReviewRequestModule.draft = patched_review_draft  # type: ignore[method-assign]
    _install_capture_patches._done = True  # type: ignore[attr-defined]


def _output_verdict_summary(outputs: list[dict[str, Any]]) -> str:
    if not outputs:
        return "No API output captured (deterministic assertion only)."

    parts: list[str] = []
    for idx, out in enumerate(outputs, start=1):
        prefix = f"Output {idx}"
        kind = out.get("type")
        if kind == "pipeline":
            parts.append(
                f"{prefix} [pipeline]: outcome={out.get('outcome')!r}; "
                f"draft_action={out.get('draft_action')!r}; "
                f"authorized_quote={out.get('commercial', {}).get('authorized_quote_usd_per_review') if out.get('commercial') else 'n/a'}; "
                f"SC attempts={len(out.get('self_correction_logs') or [])}"
            )
            if out.get("inbound_message"):
                parts.append(f"  inbound: {out['inbound_message']!r}")
            body = out.get("draft_body") or ""
            if body:
                snippet = body.replace("\n", " ")[:280]
                parts.append(f"  draft: {snippet}{'…' if len(body) > 280 else ''}")
            sc_logs = out.get("self_correction_logs") or []
            for log in sc_logs:
                parts.append(
                    f"  SC attempt {log['attempt']}: verdict={log['verdict']!r}; "
                    f"failed={log.get('failed_checks')}"
                )
        elif kind == "self_correction":
            parts.append(
                f"{prefix} [self_correction]: verdict={out.get('verdict')!r}; "
                f"failed_checks={out.get('failed_checks')}"
            )
            if out.get("input_draft_body"):
                snippet = str(out["input_draft_body"]).replace("\n", " ")[:200]
                parts.append(f"  input draft: {snippet}")
        elif kind == "commercial":
            parts.append(
                f"{prefix} [commercial]: tier={out.get('tier_id')!r}; "
                f"quote={out.get('authorized_quote_usd_per_review')}; "
                f"step={out.get('negotiation_step')}; escalate={out.get('escalate')}"
            )
        elif kind == "review_request_draft":
            parts.append(
                f"{prefix} [review_request]: action={out.get('action')!r}; "
                f"touch={out.get('touch_number')}; channel={out.get('channel')!r}"
            )
            body = out.get("body") or ""
            if body:
                parts.append(f"  body: {body[:200]}{'…' if len(body) > 200 else ''}")
    return "\n".join(parts)


def _format_output_block(outputs: list[dict[str, Any]]) -> str:
    if not outputs:
        return "_No pipeline/SC/commercial output captured._\n"
    lines = ["```json",]
    import json

    lines.append(json.dumps(outputs, indent=2, ensure_ascii=False, default=str))
    lines.append("```")
    return "\n".join(lines) + "\n"


def _write_reports() -> None:
    results: dict[str, dict[str, Any]] = _session["results"]
    artifacts: dict[str, dict[str, Any]] = _session["artifacts"]
    nodeids = sorted(set(results) | set(artifacts))

    passed = sum(1 for r in results.values() if r.get("outcome") == "passed")
    failed = sum(1 for r in results.values() if r.get("outcome") == "failed")
    skipped = sum(1 for r in results.values() if r.get("outcome") == "skipped")
    xfailed = sum(1 for r in results.values() if r.get("outcome") == "xfailed")
    api_blocked = sum(
        1
        for r in results.values()
        if r.get("outcome") == "failed"
        and r.get("failure")
        and "credit balance is too low" in str(r.get("failure")).lower()
    )
    real_failed = failed - api_blocked
    total = len(nodeids)

    api_credit_failures = api_blocked
    real_failures = real_failed

    started = _session.get("started_at") or datetime.now(timezone.utc)
    finished = _session.get("finished_at") or datetime.now(timezone.utc)
    duration = (finished - started).total_seconds()

    # Section grouping from class name prefix
    sections: dict[str, list[str]] = {}
    for nodeid in nodeids:
        class_name = nodeid.split("::")[-2] if "::" in nodeid else "Other"
        letter = class_name[4] if class_name.startswith("Test") and len(class_name) > 4 else "?"
        sections.setdefault(letter, []).append(nodeid)

    report_lines = [
        "# ReviewArmour Live Integration Test Results",
        "",
        f"**Generated:** {finished.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "**Test file:** `tests/test_live_flows.py`",
        f"**Total:** {total} | **Passed:** {passed} | **Failed:** {failed} | "
        f"**Skipped:** {skipped} | **XFailed:** {xfailed}",
        f"**Runtime:** {duration:.1f}s ({duration / 60:.1f} min)",
        "",
    ]
    if api_credit_failures:
        report_lines.extend(
            [
                "> **API billing block:** "
                f"{api_credit_failures} failure(s) were caused by exhausted Anthropic "
                "API credits (`credit balance is too low`), not by application logic. "
                f"Likely real failures this run: **{real_failures}**.",
                "",
            ]
        )
    report_lines.extend(["---", "", "## Summary", ""])
    report_lines.extend(
        [
            "| Section | Tests | Passed | Failed |",
            "|---------|-------|--------|--------|",
        ]
    )

    for letter in sorted(sections):
        ids = sections[letter]
        sec_pass = sum(1 for nid in ids if results.get(nid, {}).get("outcome") == "passed")
        sec_fail = sum(1 for nid in ids if results.get(nid, {}).get("outcome") == "failed")
        report_lines.append(f"| {letter} | {len(ids)} | {sec_pass} | {sec_fail} |")

    report_lines.extend(["", "---", "", "## Per-Test Results", ""])

    for nodeid in nodeids:
        meta = results.get(nodeid, {})
        art = artifacts.get(nodeid, {})
        outcome = meta.get("outcome", "unknown").upper()
        test_name = nodeid.split("::")[-1]
        class_name = nodeid.split("::")[-2] if "::" in nodeid else ""
        doc = (art.get("test_doc") or art.get("class_doc") or "").strip()

        report_lines.append(f"### `{test_name}`")
        report_lines.append("")
        report_lines.append(f"- **Class:** `{class_name}`")
        if doc:
            report_lines.append(f"- **Intent:** {doc}")
        report_lines.append(f"- **Verdict:** **{outcome}**")
        failure_text = meta.get("failure") or ""
        if failure_text and "credit balance is too low" in failure_text:
            report_lines.append("- **Failure type:** API credits exhausted (not a logic failure)")
        if meta.get("duration") is not None:
            report_lines.append(f"- **Duration:** {meta['duration']:.2f}s")
        if meta.get("failure"):
            report_lines.append(f"- **Failure:** `{meta['failure']}`")

        outputs = art.get("outputs") or []
        report_lines.append("")
        report_lines.append("#### Output produced")
        report_lines.append("")
        report_lines.append(_format_output_block(outputs))
        report_lines.append("#### Verdict on output")
        report_lines.append("")
        if outcome == "PASSED":
            report_lines.append(
                "Test assertions passed against the captured output(s) above."
            )
        elif outcome == "FAILED":
            report_lines.append(
                "Test assertions **failed** against the captured output(s) above."
            )
        else:
            report_lines.append(f"Test ended with status: {outcome}.")
        report_lines.append("")
        report_lines.append("```text")
        report_lines.append(_output_verdict_summary(outputs))
        report_lines.append("```")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")

    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")

    log_lines = [
        f"Live flow test run — {finished.isoformat()}",
        f"Results: {passed} passed, {failed} failed, {skipped} skipped, {xfailed} xfailed / {total} total",
        f"Duration: {duration:.1f}s",
    ]
    if api_credit_failures:
        log_lines.append(
            f"API credit blocks: {api_credit_failures} (likely real failures: {real_failures})"
        )
    log_lines.extend(
        [
            f"Detailed report: tests/TEST_RESULTS_REPORT.md",
            "",
            "## Quick listing",
            "",
        ]
    )
    for nodeid in nodeids:
        outcome = results.get(nodeid, {}).get("outcome", "?")
        log_lines.append(f"{nodeid} {outcome.upper()}")
    if failed:
        log_lines.extend(["", "## Failures", ""])
        for nodeid in nodeids:
            meta = results.get(nodeid, {})
            if meta.get("outcome") == "failed" and meta.get("failure"):
                log_lines.append(f"- `{nodeid}`: {meta['failure']}")
    LOG_PATH.write_text("\n".join(log_lines), encoding="utf-8")


def pytest_collection_modifyitems(session, config, items):
    live_items = [i for i in items if i.path.name == "test_live_flows.py"]
    if live_items and os.environ.get("ANTHROPIC_API_KEY"):
        _session["enabled"] = True
        _session["started_at"] = datetime.now(timezone.utc)
        _install_capture_patches()


def pytest_runtest_setup(item):
    if _session["enabled"]:
        _thread.nodeid = item.nodeid
        bucket = _artifact_bucket(item.nodeid)
        bucket["class_doc"] = (item.cls.__doc__ or "") if item.cls else ""
        bucket["test_doc"] = (item.obj.__doc__ or "") if callable(item.obj) else ""


def pytest_runtest_makereport(item, call):
    if not _session["enabled"] or call.when != "call":
        return
    outcome = call.excinfo is None and "passed" or "failed"
    if call.excinfo is not None and call.excinfo.typename == "Skipped":
        outcome = "skipped"
    failure = None
    if call.excinfo is not None and outcome == "failed":
        failure = str(call.excinfo.value)
    _session["results"][item.nodeid] = {
        "outcome": outcome,
        "duration": call.duration,
        "failure": failure,
    }


def pytest_sessionfinish(session, exitstatus):
    if _session["enabled"]:
        _session["finished_at"] = datetime.now(timezone.utc)
        _write_reports()
