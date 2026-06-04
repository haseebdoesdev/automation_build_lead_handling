"""
ReviewArmour interactive pipeline tester (GUI).

Run from repo root:

    pip install -e ".[tester]"
    pip install -e ".[gbp]"   # optional: GBP Maps scrape (Playwright)

Then ``playwright install chromium`` once if using GBP inspect.

    python -m reviewarmour_tester.app

Requires ANTHROPIC_API_KEY for full pipeline runs. Inbound trigger highlighting
works without it when using "Triggers only (no LLM)". Virtual clock on the Lead tab
controls timestamps for pipeline runs, activity log lines, stall evaluation,
and Flow 18 nurture emails (T+30m / +60m / +24h after the first simulated ``send``).
"""

from __future__ import annotations

import json
import os
import re
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from nicegui import run, ui

from reviewarmour.conversation import (
    Channel,
    ConversationModule,
    CustomerReviewRequestModule,
    OutboundPipeline,
    SelfCorrectionModule,
    evaluate_post_quote_stall,
    extract_gbp_url,
)
from reviewarmour.followup_cadence import schedule_nurture_follow_ups
from reviewarmour.gbp import inspection_dict_to_lead_field_updates, run_inspect_gbp_sync
from reviewarmour.gbp.inference import map_text_to_gbp_category
from reviewarmour.models import (
    Country,
    GBPCategory,
    LeadRecord,
    RecencyProfile,
)
from reviewarmour.self_correction import make_anthropic_client
from reviewarmour_tester.inspect import describe_result, inspect_inbound, inspect_pipeline_result
from reviewarmour_tester.session import TesterSession, pipeline_result_to_dict


# -----------------------------------------------------------------------------
# Per-client session + lazy LLM clients
# -----------------------------------------------------------------------------

_sessions: dict[str, TesterSession] = {}
_pipeline: Optional[OutboundPipeline] = None
_sc_module: Optional[SelfCorrectionModule] = None
_review_module: Optional[CustomerReviewRequestModule] = None


def _client_id() -> str:
    try:
        from nicegui import context

        return context.client.id
    except Exception:
        return "default"


def get_session() -> TesterSession:
    cid = _client_id()
    if cid not in _sessions:
        _sessions[cid] = TesterSession()
        _sessions[cid].log("Session initialized.")
    return _sessions[cid]


def get_llm_stack() -> tuple[OutboundPipeline, SelfCorrectionModule]:
    global _pipeline, _sc_module, _review_module
    if _pipeline is None:
        client = make_anthropic_client()
        conv = ConversationModule(client)
        _sc_module = SelfCorrectionModule(client)
        _review_module = CustomerReviewRequestModule(client)
        _pipeline = OutboundPipeline(conversation=conv, self_correction=_sc_module)
    assert _sc_module is not None
    return _pipeline, _sc_module


def get_review_module() -> CustomerReviewRequestModule:
    get_llm_stack()
    assert _review_module is not None
    return _review_module


def _derive_recency_flags(recency_value: str, review_count: int) -> list[bool]:
    """Derive per-review under-1-month flags from the lead's recency_profile.

    Spec v2: the adaptive selector + T1 written exception depend on per-review
    timing flags. Without them the engine cannot identify the exception path.
    """
    n = max(review_count, 1)
    rv = (recency_value or "").lower()
    if rv == RecencyProfile.ALL_UNDER_1_MONTH.value:
        return [True] * n
    if rv == RecencyProfile.ALL_OVER_1_MONTH.value:
        return [False] * n
    if rv == RecencyProfile.MOSTLY_UNDER_1_MONTH.value:
        # Roughly 70% recent.
        return [i < (n * 7 + 9) // 10 for i in range(n)]
    if rv == RecencyProfile.MOSTLY_OVER_1_MONTH.value:
        return [i < n // 3 for i in range(n)]
    if rv == RecencyProfile.MIXED.value:
        return [i % 2 == 0 for i in range(n)]
    # UNCERTAIN -> conservative all-over.
    return [False] * n


def _derive_gbp_category(form: dict[str, Any]) -> GBPCategory | None:
    """Spec v2 — auto-pick a GBPCategory enum value from the form.

    Priority: explicit ``gbp_category`` field (enum value as string) > mapping
    of ``business_category`` text > mapping of ``business_name`` text > None.
    """
    explicit = (form.get("gbp_category") or "").strip()
    if explicit:
        try:
            return GBPCategory(explicit)
        except ValueError:
            pass
    for source_field in ("business_category", "business_name"):
        text = (form.get(source_field) or "").strip()
        if not text:
            continue
        mapped = map_text_to_gbp_category(text)
        if mapped:
            try:
                return GBPCategory(mapped)
            except ValueError:
                continue
    return None


def build_lead_from_bindings(form: dict[str, Any]) -> LeadRecord:
    rc = form.get("review_count", 2)
    if isinstance(rc, float):
        rc = int(rc)
    rc_int = int(rc or 2)
    ns = form.get("negotiation_step", 0)
    if isinstance(ns, float):
        ns = int(ns)
    recency_value = form.get("recency") or RecencyProfile.ALL_UNDER_1_MONTH.value
    has_image_reviews = bool(form.get("has_image_reviews"))
    return LeadRecord(
        lead_id=str(form.get("lead_id") or "test-lead"),
        first_name=str(form.get("first_name") or "Sam"),
        last_name=str(form.get("last_name") or "Lee"),
        business_name=str(form.get("business_name") or "Acme Plumbing"),
        country=Country(form.get("country") or Country.US.value),
        phone=str(form.get("phone") or "+15550001111"),
        email=str(form.get("email") or "sam@example.com"),
        gbp_link=(str(form.get("gbp_link") or "").strip() or None),
        review_count=rc_int,
        recency_profile=RecencyProfile(recency_value),
        business_category=str(form.get("business_category") or "plumber"),
        is_price_sensitive_bulk=bool(form.get("is_price_sensitive_bulk")),
        negotiation_step=int(ns or 0),
        ai_quote_allowed=bool(form.get("ai_quote_allowed")),
        soft_quote_mode=bool(form.get("soft_quote_mode")),
        lead_source=str(form.get("lead_source") or "tester"),
        urgency_flag=(str(form.get("urgency_flag") or "").strip() or None),
        # Spec v2: derive industry-pricing fields so the commercial engine can
        # actually quote instead of returning request_category_first=True.
        gbp_category=_derive_gbp_category(form),
        reviews_image_content=[has_image_reviews] * rc_int,
        reviews_under_one_month=_derive_recency_flags(recency_value, rc_int),
    )


def apply_inspection_dict_to_form(form: dict[str, Any], raw: dict[str, Any]) -> list[str]:
    """Merge a successful ``inspect_maps_place`` result into tester lead form fields.

    Spec v2 also imports gbp_category and per-review image/recency flags.
    """
    if raw.get("status") != "success":
        return []
    applied: list[str] = []
    updates = inspection_dict_to_lead_field_updates(raw)
    if "recency_profile" in updates:
        form["recency"] = updates["recency_profile"]
        applied.append("recency")
    if "review_count" in updates:
        form["review_count"] = updates["review_count"]
        applied.append("review_count")
    if "business_category" in updates:
        form["business_category"] = updates["business_category"]
        applied.append("business_category")
    if "gbp_category" in updates:
        form["gbp_category"] = updates["gbp_category"]
        applied.append("gbp_category")
    if raw.get("any_review_has_images") is True:
        form["has_image_reviews"] = True
        applied.append("has_image_reviews")
    if raw.get("business_name_extracted"):
        form["business_name"] = raw["business_name_extracted"]
        applied.append("business_name")
    if raw.get("url"):
        form["gbp_link"] = raw["url"]
        applied.append("gbp_link")
    return applied


@ui.page("/")
def index() -> None:
    ui.page_title("ReviewArmour pipeline tester")
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    form_state: dict[str, Any] = {
        "lead_id": "test-1",
        "first_name": "Sam",
        "last_name": "Lee",
        "business_name": "Lee Plumbing Co",
        "country": Country.US.value,
        "phone": "+15551110001",
        "email": "sam@example.com",
        "gbp_link": "https://g.page/lee-plumbing",
        "review_count": 2,
        "recency": RecencyProfile.ALL_UNDER_1_MONTH.value,
        "business_category": "plumber",
        # Spec v2: GBP industry category enum + per-review image hint.
        "gbp_category": GBPCategory.PLUMBER.value,
        "has_image_reviews": False,
        "is_price_sensitive_bulk": False,
        "negotiation_step": 0,
        "ai_quote_allowed": True,
        "soft_quote_mode": False,
        "lead_source": "tester",
        "urgency_flag": "",
        "channel": Channel.EMAIL.value,
        "send_channel": Channel.EMAIL.value,
        "sequence_stage": "main",
        "wants_price": False,
        "post_payment_context": False,
        "quoted_previously": False,
        "meaningful_progress_mode": "auto",
        "lead_requested_price_below_floor": False,
        "auto_inspect_gbp": True,
    }

    # Slots filled inside tab panels before first refresh
    slots: dict[str, Any] = {}
    _stall_eval_hook: list[Any] = []

    def meaningful_progress_param():
        """None = auto (Section 8 heuristic); CRM overrides yes/no."""
        m = form_state.get("meaningful_progress_mode", "auto")
        if m == "auto":
            return None
        return m == "yes"

    def refresh_virtual_clock_label() -> None:
        lbl = slots.get("clock_label")
        if lbl is not None:
            lbl.text = f"Virtual now (UTC): {get_session().virtual_now.isoformat()}"

    @ui.refreshable
    def refresh_logs() -> None:
        sess = get_session()
        log_el = slots.get("log")
        if not log_el:
            return
        log_el.clear()
        with log_el:
            body = "\n".join(sess.activity[-800:])
            ui.code(body).classes("w-full max-h-[480px] overflow-auto text-xs")

    @ui.refreshable
    def render_inbound_bar() -> None:
        el = slots.get("inbound")
        if not el:
            return
        el.clear()
        sess = get_session()
        d = sess.last_inbound_inspection
        with el:
            ui.label("Inbound pattern detectors").classes("font-bold w-full")
            with ui.row(wrap=True).classes("gap-2"):
                chips = [
                    ("inbound asks price → commercial engine", d.get("inbound_asks_for_price")),
                    ("acceptance signal", d.get("acceptance_signal")),
                    ("auto: in-scope engagement (Section 8)", d.get("meaningful_engagement_auto")),
                    ("escalate regex hit", d.get("escalate_match")),
                    ("legal keywords", d.get("legal_keywords")),
                    ("post_pay / cancel*", d.get("post_pay_keywords")),
                    ("regulator keywords", d.get("regulator_keywords")),
                    ("owner/manager phrase", d.get("owner_manager_keywords")),
                ]
                for label, on in chips:
                    ui.badge(label, color="positive" if on else "grey")
                if d.get("escalate_reason"):
                    ui.badge(f"reason: {d['escalate_reason']}", color="warning")
                ui.badge(
                    f"no-progress count (session): {sess.conversation_state.consecutive_no_progress_turns}",
                    color="warning"
                    if sess.conversation_state.consecutive_no_progress_turns
                    else "grey",
                )

    @ui.refreshable
    def render_action_bar() -> None:
        el = slots.get("action")
        if not el:
            return
        el.clear()
        sess = get_session()
        d = sess.last_pipeline_inspection
        with el:
            ui.label("Last pipeline / AI outcome").classes("font-bold w-full")
            with ui.row(wrap=True).classes("gap-2"):
                items = [
                    ("outcome: send", d.get("outcome_send")),
                    ("outcome: escalate", d.get("outcome_escalate")),
                    ("outcome: human_queue", d.get("outcome_human_queue")),
                    ("handoff quote→invoice", d.get("handoff_quote_to_invoice")),
                    ("state quote_accepted", d.get("state_quote_accepted")),
                    ("commercial turn clock set", d.get("commercial_turn_timestamp_set")),
                    ("stall_eval_hit", d.get("stall_eval_hit")),
                    ("draft escalate (model)", d.get("draft_escalate_from_model")),
                    ("commercial escalated", d.get("commercial_escalated")),
                ]
                for label, on in items:
                    ui.badge(label, color="positive" if on else "grey")
                attempts = d.get("self_correction_attempts")
                verdicts = d.get("last_sc_verdicts")
                if attempts is not None:
                    ui.badge(f"SC attempts={attempts} verdicts={verdicts}", color="info")

    def _turn_belongs_channel(turn: dict[str, Any], target: str) -> bool:
        ch = (turn.get("channel") or "").lower()
        role = turn.get("role", "")
        if role == "system":
            return False
        if ch == target:
            return True
        # Legacy rows without channel: treat as email-only so SMS stays clean.
        if not ch and target == Channel.EMAIL.value:
            return True
        return False

    @ui.refreshable
    def render_chat_system() -> None:
        el = slots.get("chat_sys")
        if not el:
            return
        el.clear()
        sess = get_session()
        sys_turns = [t for t in sess.transcript if t.get("role") == "system"]
        with el:
            if not sys_turns:
                ui.label("No system / escalate rows.").classes("text-grey text-xs")
                return
            ui.label("System / escalate").classes("text-bold text-xs w-full")
            for turn in sys_turns:
                ui.markdown(f"**system**\n\n{turn.get('body', '')}")

    @ui.refreshable
    def render_chat_email() -> None:
        el = slots.get("chat_email")
        if not el:
            return
        el.clear()
        sess = get_session()
        turns = [
            t
            for t in sess.transcript
            if t.get("role") != "system" and _turn_belongs_channel(t, Channel.EMAIL.value)
        ]
        with el:
            ui.label("Email thread").classes("font-bold border-b w-full pb-1 mb-2")
            if not turns:
                ui.label("No email messages yet.").classes("text-grey text-sm")
            for turn in turns:
                role = turn.get("role", "?")
                body = turn.get("body", "")
                sub = turn.get("subject")
                meta = f"{role}"
                if sub:
                    meta += f" · subj: {sub}"
                ui.markdown(f"**{meta}**\n\n{body}")

    @ui.refreshable
    def render_chat_sms() -> None:
        el = slots.get("chat_sms")
        if not el:
            return
        el.clear()
        sess = get_session()
        turns = [
            t
            for t in sess.transcript
            if t.get("role") != "system" and _turn_belongs_channel(t, Channel.SMS.value)
        ]
        with el:
            ui.label("SMS thread").classes("font-bold border-b w-full pb-1 mb-2")
            if not turns:
                ui.label("No SMS messages yet.").classes("text-grey text-sm")
            for turn in turns:
                role = turn.get("role", "?")
                body = turn.get("body", "")
                meta = f"{role}"
                ui.markdown(f"**{meta}**\n\n{body}")

    def _run_nurture_followups_due(from_clock_tick: bool) -> None:
        """Fire scheduled nurture touches when virtual_now has reached fire_at_utc."""
        sess = get_session()
        if not sess.nurture_follow_ups:
            return
        now_u = sess.virtual_now.astimezone(timezone.utc)
        fired: list[int] = []
        for fu in sess.nurture_follow_ups:
            if fu.index in sess.nurture_follow_up_fired:
                continue
            at = fu.fire_at_utc
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            else:
                at = at.astimezone(timezone.utc)
            if at <= now_u:
                sess.nurture_follow_up_fired.add(fu.index)
                row: dict[str, Any] = {
                    "role": "assistant",
                    "channel": fu.channel.value,
                    "body": fu.body,
                }
                if fu.subject:
                    row["subject"] = fu.subject
                sess.transcript.append(row)
                sess.merge_state_updates(fu.state_updates)
                sess.log(
                    f"NURTURE follow-up #{fu.index} fired (due {at.isoformat()}, "
                    f"virtual_now={now_u.isoformat()})"
                )
                fired.append(fu.index)
        if not fired:
            return
        render_chat_email.refresh()
        render_chat_sms.refresh()
        render_action_bar.refresh()
        refresh_logs.refresh()
        if from_clock_tick:
            ch0 = sess.nurture_follow_ups[0].channel
            where = "Email" if ch0 == Channel.EMAIL else "SMS"
            ui.notify(
                f"Nurture follow-up(s) {', '.join(f'#{i}' for i in fired)} — see {where} thread",
                type="positive",
            )

    async def handle_pipeline_result(result: Any) -> None:
        sess = get_session()
        sess.last_pipeline_inspection = inspect_pipeline_result(result)
        sess.last_pipeline_result_dict = pipeline_result_to_dict(result)
        if result.human_queue_payload:
            sess.last_human_queue = result.human_queue_payload
        sess.merge_state_updates(result.state_updates or {})
        ns = (result.state_updates or {}).get("negotiation_step")
        if ns is not None:
            form_state["negotiation_step"] = int(ns)
        if result.commercial and result.commercial.authorized_quote_usd_per_review:
            sess.last_quote_usd = result.commercial.authorized_quote_usd_per_review
        sess.log(describe_result(result))

        if result.outcome == "send" and result.draft and result.draft.action == "send":
            body_out = result.draft.body or ""
            if re.search(r"\$\s*\d", body_out):
                form_state["quoted_previously"] = True
            sess.transcript.append(
                {
                    "role": "assistant",
                    "channel": (
                        result.draft.channel.value
                        if result.draft.channel
                        else form_state.get("send_channel") or form_state["channel"]
                    ),
                    "subject": result.draft.subject,
                    "body": body_out,
                }
            )
            if not sess.nurture_follow_ups:
                out_ch = (
                    result.draft.channel
                    if result.draft.channel is not None
                    else Channel(
                        str(
                            form_state.get("send_channel")
                            or form_state.get("channel")
                            or "email"
                        )
                    )
                )
                lead = build_lead_from_bindings(form_state)
                sess.nurture_follow_ups = schedule_nurture_follow_ups(
                    sess.virtual_now, lead, channel=out_ch
                )
                sched = ", ".join(
                    f"F{fu.index}@{fu.fire_at_utc.isoformat()}" for fu in sess.nurture_follow_ups
                )
                sess.log(f"Scheduled nurture follow-ups: {sched}")
        elif result.outcome == "escalate":
            esc_reason = "unknown"
            if result.draft and result.draft.reason:
                esc_reason = result.draft.reason
            elif (result.state_updates or {}).get("escalation_reason"):
                esc_reason = str(result.state_updates["escalation_reason"])
            sess.transcript.append(
                {
                    "role": "system",
                    "body": f"[ESCALATE] {esc_reason}",
                }
            )
        elif result.outcome == "human_queue":
            sess.transcript.append(
                {
                    "role": "system",
                    "body": "[HUMAN QUEUE] Draft failed SC after retries — see Human reviewer tab.",
                }
            )

        render_action_bar.refresh()
        render_chat_system.refresh()
        render_chat_email.refresh()
        render_chat_sms.refresh()
        refresh_logs.refresh()
        hq = slots.get("hq_text")
        if hq is not None:
            hq.value = json.dumps(sess.last_human_queue or {}, indent=2)

        _run_nurture_followups_due(False)

    # --- header ---
    with ui.header().classes("items-center justify-between flex-wrap gap-2"):
        ui.label("ReviewArmour pipeline tester").classes("text-h5")
        with ui.row().classes("items-center gap-2"):
            ui.badge("API key OK", color="positive" if has_key else "warning")
            if not has_key:
                ui.label("Set ANTHROPIC_API_KEY for LLM runs").classes("text-warning text-sm")

            def new_conversation():
                s = get_session()
                s.reset()
                # Fresh thread: stale negotiation / quote flags produce wrong $ from CommercialEngine.
                form_state["negotiation_step"] = 0
                form_state["quoted_previously"] = False
                s.last_inbound_inspection = {}
                s.last_pipeline_inspection = {}
                render_inbound_bar.refresh()
                render_action_bar.refresh()
                render_chat_system.refresh()
                render_chat_email.refresh()
                render_chat_sms.refresh()
                refresh_logs.refresh()
                hq = slots.get("hq_text")
                if hq is not None:
                    hq.value = "{}"
                refresh_virtual_clock_label()
                ui.notify("New conversation", type="positive")

            ui.button("New conversation", on_click=new_conversation, color="secondary")

    with ui.tabs().classes("w-full") as tabs:
        t_lead = ui.tab("Lead & pipeline")
        t_conv = ui.tab("Conversation")
        t_gbp = ui.tab("GBP inspect")
        t_log = ui.tab("Activity log")
        t_human = ui.tab("Human reviewer")
        t_review = ui.tab("Review request")

    with ui.tab_panels(tabs, value=t_lead).classes("w-full"):
        # ----- Lead -----
        with ui.tab_panel(t_lead):
            with ui.row(wrap=True).classes("w-full gap-4"):
                with ui.card().classes("flex-grow min-w-[260px]"):
                    ui.label("Virtual clock").classes("text-bold")
                    ui.label(
                        "After the first pipeline outcome ``send``, nurture emails are scheduled "
                        "at T+30m, +60m, +24h (UTC anchor = virtual now at send time), "
                        "on the same channel as that send (email or SMS). "
                        "Use +hours / Apply ISO to fire them into the matching thread."
                    ).classes("text-xs text-grey w-full max-w-md")
                    slots["clock_label"] = ui.label()
                    refresh_virtual_clock_label()
                    iso_clock = ui.input(
                        "Set virtual now (ISO 8601)",
                        value="2026-05-11T12:00:00+00:00",
                    ).classes("w-full")

                    def apply_virtual_iso() -> None:
                        try:
                            raw = (iso_clock.value or "").strip()
                            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                            get_session().set_virtual_now(dt)
                            refresh_virtual_clock_label()
                            ui.notify("Virtual clock updated", type="positive")
                            if _stall_eval_hook:
                                _stall_eval_hook[0](True)
                        except Exception as e:
                            ui.notify(f"Invalid ISO: {e}", type="negative")

                    ui.button("Apply ISO time", on_click=apply_virtual_iso)
                    adv_h = ui.number("Advance hours", format="%.1f", value=6.0)

                    def advance_hours() -> None:
                        h = float(adv_h.value or 0.0)
                        get_session().advance_virtual_now(timedelta(hours=h))
                        refresh_virtual_clock_label()
                        ui.notify(f"+{h}h — re-running post-quote stall check", type="info")
                        if _stall_eval_hook:
                            _stall_eval_hook[0](True)

                    ui.button("+ hours", on_click=advance_hours)
                    adv_d = ui.number("Advance days", format="%.1f", value=1.0)

                    def advance_days() -> None:
                        d = float(adv_d.value or 0.0)
                        get_session().advance_virtual_now(timedelta(days=d))
                        refresh_virtual_clock_label()
                        ui.notify(f"+{d}d — re-running post-quote stall check", type="info")
                        if _stall_eval_hook:
                            _stall_eval_hook[0](True)

                with ui.card().classes("flex-grow min-w-[280px]"):
                    ui.label("Lead record").classes("text-bold")
                    ui.input("Lead ID").bind_value(form_state, "lead_id")
                    ui.input("First name").bind_value(form_state, "first_name")
                    ui.input("Last name").bind_value(form_state, "last_name")
                    ui.input("Business").bind_value(form_state, "business_name")
                    ui.select(
                        {c.value: c.value for c in Country},
                        label="Country",
                        value=form_state["country"],
                    ).bind_value(form_state, "country")
                    ui.input("Phone").bind_value(form_state, "phone")
                    ui.input("Email").bind_value(form_state, "email")
                    ui.input("GBP link (empty = missing)").bind_value(form_state, "gbp_link")
                    ui.number("Review count", format="%.0f", value=2).bind_value(
                        form_state, "review_count"
                    )
                    ui.select(
                        {r.value: r.value for r in RecencyProfile},
                        label="Recency profile",
                        value=form_state["recency"],
                    ).bind_value(form_state, "recency")
                    ui.input("Business category").bind_value(form_state, "business_category")
                    # Spec v2 — industry pricing matrix needs an explicit GBPCategory
                    ui.select(
                        {c.value: c.value for c in GBPCategory},
                        label="GBP category (spec v2)",
                        value=form_state["gbp_category"],
                    ).bind_value(form_state, "gbp_category")
                    ui.checkbox(
                        "Any image reviews? (spec v2 T1 exception input)",
                        value=False,
                    ).bind_value(form_state, "has_image_reviews")
                    ui.number("Negotiation step", format="%.0f", value=0).bind_value(
                        form_state, "negotiation_step"
                    )
                    ui.checkbox("Price-sensitive bulk (5+ mixed)", value=False).bind_value(
                        form_state, "is_price_sensitive_bulk"
                    )
                    ui.checkbox("AI quote allowed", value=True).bind_value(
                        form_state, "ai_quote_allowed"
                    )
                    ui.checkbox("Soft quote mode", value=False).bind_value(
                        form_state, "soft_quote_mode"
                    )
                    ui.input("Lead source").bind_value(form_state, "lead_source")
                    ui.input("Urgency flag").bind_value(form_state, "urgency_flag")

                with ui.card().classes("flex-grow min-w-[280px]"):
                    ui.label("Pipeline parameters").classes("text-bold")
                    ui.select(
                        {"email": "email", "sms": "sms"},
                        label="Channel",
                        value=form_state["channel"],
                    ).bind_value(form_state, "channel")
                    ui.input("Sequence stage").bind_value(form_state, "sequence_stage")
                    ui.checkbox("wants_price (runs commercial engine)", value=False).bind_value(
                        form_state, "wants_price"
                    )
                    ui.checkbox("post_payment_context", value=False).bind_value(
                        form_state, "post_payment_context"
                    )
                    ui.checkbox("quoted_previously (acceptance path)", value=False).bind_value(
                        form_state, "quoted_previously"
                    )
                    ui.select(
                        {
                            "auto": "Meaningful progress: Auto (detect from inbound)",
                            "yes": "Meaningful progress: Force YES (resets counter)",
                            "no": "Meaningful progress: Force NO (always increments)",
                        },
                        label="Section 8 no-progress counter",
                        value=form_state["meaningful_progress_mode"],
                    ).bind_value(form_state, "meaningful_progress_mode").classes(
                        "w-full max-w-2xl"
                    )
                    ui.checkbox("lead_requested_price_below_floor", value=False).bind_value(
                        form_state, "lead_requested_price_below_floor"
                    )

                    ui.separator()

                    async def run_proactive() -> None:
                        if not has_key:
                            ui.notify("Set ANTHROPIC_API_KEY", type="warning")
                            return
                        sess = get_session()
                        lead = build_lead_from_bindings(form_state)

                        def work():
                            pipe, _ = get_llm_stack()
                            return pipe.run(
                                lead=lead,
                                transcript=list(sess.transcript),
                                channel=Channel(form_state["channel"]),
                                sequence_stage=form_state["sequence_stage"],
                                inbound_message=None,
                                wants_price=bool(form_state["wants_price"]),
                                post_payment_context=bool(form_state["post_payment_context"]),
                                lead_requested_price_below_floor=bool(
                                    form_state["lead_requested_price_below_floor"]
                                ),
                                quoted_previously=bool(form_state["quoted_previously"]),
                                conversation_state=sess.conversation_state,
                                meaningful_progress=meaningful_progress_param(),
                                now_override=sess.virtual_now,
                                gbp_inspection=sess.last_gbp_inspection or None,
                            )

                        try:
                            result = await run.io_bound(work)
                            await handle_pipeline_result(result)
                        except Exception as e:
                            sess = get_session()
                            sess.log(f"ERROR proactive: {e}\n{traceback.format_exc()}")
                            ui.notify(str(e), type="negative")
                            refresh_logs.refresh()

                    ui.button("Run pipeline (no inbound message)", on_click=run_proactive)

            ui.separator()
            ui.label("Post-quote stall helper").classes("text-bold")
            ui.label(
                "Stall uses virtual now vs last_commercial_turn_at from the session "
                "(set when a pricing pipeline send records a commercial turn). "
                "Advancing the virtual clock or applying ISO time runs this check automatically."
            ).classes("text-xs text-grey w-full max-w-3xl")

            stall_quote = ui.number(
                "Last quote USD/review (optional override)",
                format="%.0f",
                value=None,
            )

            def _run_post_quote_stall_eval(from_clock_tick: bool) -> None:
                sess = get_session()
                last_at = sess.conversation_state.last_commercial_turn_at
                last_q = (
                    int(stall_quote.value)
                    if stall_quote.value is not None
                    else sess.last_quote_usd
                )
                payload = evaluate_post_quote_stall(
                    lead=build_lead_from_bindings(form_state),
                    transcript=list(sess.transcript),
                    last_commercial_turn_at=last_at,
                    now=sess.virtual_now,
                    last_quote=last_q,
                )
                sess.log(f"evaluate_post_quote_stall → {payload}")
                if last_at is None and sess.last_quote_usd is not None:
                    sess.log(
                        "Stall skipped: last_commercial_turn_at is null. "
                        "The quoted send should merge state_updates.last_commercial_turn_at — "
                        "if this persists, inspect that pipeline result in the Activity log."
                    )
                if payload:
                    sess.last_pipeline_inspection = {
                        **sess.last_pipeline_inspection,
                        "stall_eval_hit": True,
                        "stall_phase": payload.get("ai_conversation_state"),
                    }
                    if from_clock_tick:
                        if payload.get("backup_page"):
                            ui.notify(
                                "Backup (Jayden) stall — see Activity log for backup_page payload",
                                type="warning",
                            )
                        else:
                            ui.notify(
                                "Salesman stall — see Activity log for salesman_page payload",
                                type="positive",
                            )
                else:
                    ins = dict(sess.last_pipeline_inspection)
                    ins.pop("stall_eval_hit", None)
                    ins.pop("stall_phase", None)
                    sess.last_pipeline_inspection = ins
                render_action_bar.refresh()
                refresh_logs.refresh()
                if not from_clock_tick:
                    ui.notify(str(payload), type="info")
                _run_nurture_followups_due(from_clock_tick)

            _stall_eval_hook.append(_run_post_quote_stall_eval)

            async def check_stall() -> None:
                _run_post_quote_stall_eval(False)

            ui.button("Evaluate stall now", on_click=check_stall)

        # ----- Conversation -----
        with ui.tab_panel(t_conv):
            slots["inbound"] = ui.column().classes("w-full p-2 bg-blue-50 rounded")
            slots["action"] = ui.column().classes("w-full p-2 bg-green-50 rounded")
            slots["chat_sys"] = ui.column().classes(
                "w-full max-h-40 overflow-y-auto border p-2 rounded bg-amber-50"
            )
            with ui.row(wrap=False).classes("w-full gap-2 flex-nowrap"):
                slots["chat_email"] = ui.column().classes(
                    "flex-1 min-w-[200px] max-h-96 overflow-y-auto border p-2 rounded bg-white"
                )
                slots["chat_sms"] = ui.column().classes(
                    "flex-1 min-w-[200px] max-h-96 overflow-y-auto border p-2 rounded bg-white"
                )
            render_inbound_bar()
            render_action_bar()
            render_chat_system()
            render_chat_email()
            render_chat_sms()

            triggers_only = ui.checkbox(
                "Triggers only (no LLM) — inbound badges only",
                value=False,
            )
            ui.checkbox(
                "When inbound contains a Maps URL, auto-run GBP inspect (Playwright) and apply recency/review count",
            ).bind_value(form_state, "auto_inspect_gbp").classes("w-full max-w-3xl")

            ui.select(
                {"email": "Email thread", "sms": "SMS thread"},
                label="Send inbound as",
                value=form_state["send_channel"],
            ).bind_value(form_state, "send_channel").classes("w-full max-w-md")

            msg_input = ui.textarea(placeholder="Lead message…").classes("w-full")
            send_btn = ui.button("Send & run pipeline", color="primary")

            ui.label("Quick-fill").classes("text-bold text-sm mt-2")

            def preset_click(t: str):
                def _() -> None:
                    msg_input.value = t

                return _

            with ui.row(wrap=True).classes("gap-1"):
                for label, text in [
                    ("How much?", "How much per review?"),
                    ("Lawyer", "We are talking to our lawyer."),
                    ("Refund", "I want a refund"),
                    ("Accept", "let's do it"),
                    ("Quote req", "send me a quote"),
                    ("Owner", "I want to speak to the owner"),
                ]:
                    ui.button(label, on_click=preset_click(text)).props("dense size=sm")

            async def send_handler() -> None:
                text = (msg_input.value or "").strip()
                sess = get_session()
                if not text:
                    ui.notify("Enter a message", type="warning")
                    return

                sess.last_inbound_inspection = inspect_inbound(
                    text,
                    post_payment_context=bool(form_state["post_payment_context"]),
                    transcript=list(sess.transcript),
                    quoted_previously=bool(form_state["quoted_previously"]),
                )
                render_inbound_bar.refresh()

                sc = form_state["send_channel"]
                sess.transcript.append({"role": "user", "body": text, "channel": sc})
                msg_input.value = ""
                render_chat_system.refresh()
                render_chat_email.refresh()
                render_chat_sms.refresh()
                sess.log(f"USER ({sc}): {text}")

                # Auto-capture GBP link from inbound message into the lead form.
                if not str(form_state.get("gbp_link") or "").strip():
                    found = extract_gbp_url(text)
                    if found:
                        form_state["gbp_link"] = found
                        sess.log(f"AUTO-CAPTURED GBP link from inbound: {found}")

                maps_url = extract_gbp_url(text)
                if maps_url and bool(form_state.get("auto_inspect_gbp", True)):
                    prev = sess.last_gbp_inspection or {}
                    already = (
                        prev.get("status") == "success"
                        and prev.get("url") == maps_url
                    )
                    if not already:

                        def inspect_work():
                            return run_inspect_gbp_sync(
                                maps_url,
                                headless=True,
                                max_seconds=90.0,
                                max_reviews=24,
                            )

                        try:
                            data = await run.io_bound(inspect_work)
                        except Exception as e:
                            tb = traceback.format_exc()
                            sess.last_gbp_inspection = {
                                "status": "error",
                                "error": str(e),
                                "traceback": tb,
                            }
                            sess.log(f"Auto GBP inspect exception: {e}\n{tb}")
                            refresh_logs.refresh()
                        else:
                            sess.last_gbp_inspection = data
                            st = data.get("status")
                            if st == "success":
                                applied = apply_inspection_dict_to_form(form_state, data)
                                if applied:
                                    sess.log(
                                        f"Auto GBP inspect applied to Lead: {applied}"
                                    )
                                else:
                                    sess.log(
                                        "Auto GBP inspect success but no lead fields "
                                        f"inferred (raw keys: {list(data.keys())})"
                                    )
                            else:
                                err = data.get("error") or "(no error string in result)"
                                sess.log(
                                    f"Auto GBP inspect failed status={st!r}: {err}"
                                )
                            refresh_logs.refresh()

                if triggers_only.value:
                    sess.last_pipeline_inspection = {}
                    render_action_bar.refresh()
                    refresh_logs.refresh()
                    ui.notify("Inbound triggers updated (no LLM)", type="info")
                    return

                if not has_key:
                    ui.notify("Set ANTHROPIC_API_KEY for full run", type="warning")
                    sess.last_pipeline_inspection = {}
                    render_action_bar.refresh()
                    refresh_logs.refresh()
                    return

                lead = build_lead_from_bindings(form_state)

                def work():
                    pipe, _ = get_llm_stack()
                    return pipe.run(
                        lead=lead,
                        transcript=list(sess.transcript[:-1]),
                        inbound_message=text,
                        wants_price=bool(form_state["wants_price"]),
                        post_payment_context=bool(form_state["post_payment_context"]),
                        lead_requested_price_below_floor=bool(
                            form_state["lead_requested_price_below_floor"]
                        ),
                        quoted_previously=bool(form_state["quoted_previously"]),
                        conversation_state=sess.conversation_state,
                        meaningful_progress=meaningful_progress_param(),
                        channel=Channel(form_state["send_channel"]),
                        sequence_stage=form_state["sequence_stage"],
                        now_override=sess.virtual_now,
                        gbp_inspection=sess.last_gbp_inspection or None,
                    )

                try:
                    result = await run.io_bound(work)
                    await handle_pipeline_result(result)
                except Exception as e:
                    sess.log(f"ERROR pipeline: {e}\n{traceback.format_exc()}")
                    ui.notify(str(e), type="negative")
                    refresh_logs.refresh()

            send_btn.on_click(send_handler)

        # ----- Activity log -----
        with ui.tab_panel(t_log):
            slots["log"] = ui.column().classes("w-full")
            refresh_logs()

            def clear_log():
                sess = get_session()
                sess.activity.clear()
                sess.log("Log cleared.")
                refresh_logs.refresh()

            ui.button("Clear log", on_click=clear_log)

        # ----- Human reviewer -----
        with ui.tab_panel(t_human):
            ui.label("Last human_queue payload (JSON)").classes("text-bold")
            slots["hq_text"] = ui.textarea(value="{}").classes("w-full").props("rows=14")
            reviewer_notes = ui.textarea("Reviewer notes (append to activity log)").classes(
                "w-full"
            )

            def refresh_human():
                sess = get_session()
                slots["hq_text"].value = json.dumps(sess.last_human_queue or {}, indent=2)

            ui.button("Refresh from session", on_click=refresh_human)

            def log_human():
                sess = get_session()
                note = reviewer_notes.value or ""
                sess.log(f"HUMAN_REVIEWER note: {note}")
                if sess.last_human_queue:
                    sess.log(
                        "HUMAN_REVIEWER payload: "
                        + json.dumps(sess.last_human_queue, indent=2)[:8000]
                    )
                refresh_logs.refresh()
                ui.notify("Logged", type="positive")

            ui.button("Append note + payload to activity log", on_click=log_human)

        # ----- Review request -----
        with ui.tab_panel(t_review):
            ui.label("CustomerReviewRequestModule").classes("text-bold")
            rr_first = ui.input("Customer first name", value="Pat")
            rr_business = ui.input("Business name", value="Kim Bakery")
            rr_summary = ui.textarea(
                "completed_job_summary",
                value="We removed three policy-violating reviews from your profile.",
            ).classes("w-full")
            rr_touch = ui.select({1: "1", 2: "2", 3: "3"}, value=1, label="Touch #")
            rr_channel = ui.select({"sms": "sms", "email": "email"}, value="sms")
            rr_link = ui.input(
                "gbp_review_link",
                value="https://g.page/r/example-review-link",
            ).classes("w-full")

            async def run_review_req() -> None:
                if not has_key:
                    ui.notify("Set ANTHROPIC_API_KEY", type="warning")
                    return
                sess = get_session()
                cust = {
                    "first_name": rr_first.value,
                    "business_name": rr_business.value,
                    "country": form_state["country"],
                    "completed_job_summary": rr_summary.value,
                }
                mod = get_review_module()

                def work():
                    return mod.draft(
                        customer=cust,
                        touch_number=int(rr_touch.value),
                        channel=Channel(rr_channel.value),
                        gbp_review_link=rr_link.value,
                    )

                try:
                    draft = await run.io_bound(work)
                except Exception as e:
                    sess.log(f"ERROR review request: {e}\n{traceback.format_exc()}")
                    ui.notify(str(e), type="negative")
                    refresh_logs.refresh()
                    return
                sess.transcript.append(
                    {
                        "role": "assistant_review_request",
                        "channel": rr_channel.value,
                        "subject": draft.subject,
                        "body": draft.body or "",
                    }
                )
                sess.log(f"REVIEW_REQUEST action={draft.action} reason={draft.reason}")
                sess.log((draft.body or "")[:4000])
                render_chat.refresh()
                refresh_logs.refresh()
                render_chat_system.refresh()
                render_chat_email.refresh()
                render_chat_sms.refresh()
                ui.notify("Draft added to Conversation tab", type="positive")

            ui.button("Generate review-request draft", on_click=run_review_req)

        # ----- GBP inspect -----
        with ui.tab_panel(t_gbp):
            ui.label(
                "Public Maps page scrape for recency / image hints (optional Playwright)."
            ).classes("text-sm text-grey")
            gbp_url = ui.input("Maps / g.page URL").classes("w-full")
            gbp_url.value = form_state.get("gbp_link") or ""
            _env_headful = os.environ.get("REVIEWARMOUR_GBP_HEADFUL", "").strip().lower() in (
                "1",
                "true",
                "yes",
            )
            headful_cb = ui.checkbox(
                "Show browser window (headful — debug Maps / consent / selectors)",
                value=_env_headful,
            ).classes("w-full max-w-3xl")
            ui.label(
                "Leave unchecked for normal headless runs. "
                "Or set REVIEWARMOUR_GBP_HEADFUL=1 to default headful on startup."
            ).classes("text-caption text-grey")
            gbp_out = ui.textarea().classes("w-full").props("rows=16")

            async def run_gbp_inspect() -> None:
                sess = get_session()
                url = (gbp_url.value or "").strip()
                if not url:
                    ui.notify("Enter a URL", type="warning")
                    return

                def work():
                    return run_inspect_gbp_sync(
                        url,
                        headless=not bool(headful_cb.value),
                        max_seconds=90.0,
                        max_reviews=24,
                    )

                try:
                    data = await run.io_bound(work)
                except Exception as e:
                    tb = traceback.format_exc()
                    sess.last_gbp_inspection = {
                        "status": "error",
                        "error": str(e),
                        "traceback": tb,
                    }
                    gbp_out.value = json.dumps(sess.last_gbp_inspection, indent=2)
                    sess.log(f"GBP inspect exception: {e}\n{tb}")
                    refresh_logs.refresh()
                    ui.notify(str(e), type="negative")
                    return
                sess.last_gbp_inspection = data
                gbp_out.value = json.dumps(data, indent=2, default=str)
                st = data.get("status")
                if st == "success":
                    sess.log(f"GBP inspect status=success")
                    ui.notify("GBP inspect finished", type="positive")
                else:
                    err = data.get("error") or "(no error string in result)"
                    sess.log(f"GBP inspect failed status={st!r}: {err}")
                    ui.notify(f"GBP inspect failed: {err}", type="negative")
                refresh_logs.refresh()

            ui.button("Run GBP inspect", on_click=run_gbp_inspect, color="primary")

            def apply_gbp_to_lead() -> None:
                sess = get_session()
                raw = sess.last_gbp_inspection or {}
                applied = apply_inspection_dict_to_form(form_state, raw)
                if not applied:
                    ui.notify("Nothing to apply (need successful inspect)", type="warning")
                    return
                ui.notify(f"Applied: {applied}", type="positive")

            ui.button("Apply inferred fields to Lead tab", on_click=apply_gbp_to_lead)

    with ui.footer():
        ui.label(
            "Harness only — wire your own paging/webhooks from stall payloads and handoffs in production."
        ).classes("text-caption")


if __name__ in {"__main__", "__mp_main__"}:
    import sys

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    port = int(os.environ.get("REVIEWARMOUR_TESTER_PORT", "8085"))
    ui.run(title="ReviewArmour tester", port=port, reload=False, show=True)
