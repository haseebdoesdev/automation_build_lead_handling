# ReviewArmour Live Integration Test Results

**Generated:** 2026-05-31 17:17:43 UTC
**Test file:** `tests/test_live_flows.py`
**Total:** 93 | **Passed:** 38 | **Failed:** 55 | **Skipped:** 0 | **XFailed:** 0
**Runtime:** 124.8s (2.1 min)

> **API billing blocked:** 55 failure(s) were caused by exhausted Anthropic API credits (`credit balance is too low`), not by application logic. Likely real failures this run: **0**.

---

## Summary

| Section | Tests | Passed | Failed |
|---------|-------|--------|--------|
| A | 23 | 17 | 6 |
| B | 19 | 10 | 9 |
| C | 10 | 0 | 10 |
| D | 8 | 1 | 7 |
| E | 7 | 0 | 7 |
| F | 8 | 7 | 1 |
| G | 1 | 1 | 0 |
| H | 6 | 1 | 5 |
| I | 11 | 1 | 10 |

---

## Per-Test Results

### `test_ca_first_touch_has_toronto_footer`

- **Class:** `TestA10_RegionalFooter`
- **Intent:** A10: CA gets Toronto footer, US gets Miami footer, no cross-contamination.
- **Verdict:** **FAILED**
- **Duration:** 0.44s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2TwAoi1a5cGAa8AmCJ'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_us_first_touch_has_miami_footer`

- **Class:** `TestA10_RegionalFooter`
- **Intent:** A10: CA gets Toronto footer, US gets Miami footer, no cross-contamination.
- **Verdict:** **FAILED**
- **Duration:** 0.50s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2Ty3uuQ6VuFmv6d7pm'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_est_scheduling_uses_america_new_york`

- **Class:** `TestA11_DSTTransition`
- **Intent:** A11: Business hours use America/New_York (auto DST).
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_sunday_deferral_respects_est_not_utc`

- **Class:** `TestA11_DSTTransition`
- **Intent:** A11: Business hours use America/New_York (auto DST).
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_pipeline_produces_email_draft_regardless`

- **Class:** `TestA12_SMSDeliveryFailureFallback`
- **Intent:** A12: SMS delivery failure — pipeline still produces a valid draft.
    Twilio not connected — verifying draft is channel-valid.
- **Verdict:** **FAILED**
- **Duration:** 1.01s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WgHgpXidtc7RMyXNJ'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_post_escalation_message_does_not_resume_ai`

- **Class:** `TestA13_AIStopsAfterEscalation`
- **Intent:** A13: After escalation, further lead messages should not produce AI send.
- **Verdict:** **FAILED**
- **Duration:** 0.84s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2U3ATmPs37frwA7ems'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_first_touch_email_has_us_footer`

- **Class:** `TestA1_BusinessHoursFormSubmission`
- **Intent:** A1: Form submission during business hours produces a first-touch draft.
- **Verdict:** **PASSED**
- **Duration:** 6.08s

#### Output produced

```json
[
  {
    "type": "self_correction",
    "input_draft_body": "Hi Test User,\n\nGot your profile for A1 Plumbing Co. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.\n\nA specialist can walk you through pricing and next steps. Reply here or let me know a good time for a quick call.\n\nJayden Faris / ReviewArmour / +1 (786) 464-3783\n1395 Brickell Avenue, Suite 800, Miami, FL 33131",
    "input_draft_subject": "Removing your Google reviews - A1 Plumbing Co",
    "verdict": "pass",
    "failed_checks": [],
    "suggested_fixes": [],
    "escalation_reason": null
  },
  {
    "type": "pipeline",
    "outcome": "send",
    "inbound_message": null,
    "wants_price": null,
    "quoted_previously": null,
    "sequence_stage": "first_touch",
    "channel": "email",
    "draft_action": "send",
    "draft_subject": "Removing your Google reviews - A1 Plumbing Co",
    "draft_body": "Hi Test User,\n\nGot your profile for A1 Plumbing Co. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.\n\nA specialist can walk you through pricing and next steps. Reply here or let me know a good time for a quick call.\n\nJayden Faris / ReviewArmour / +1 (786) 464-3783\n1395 Brickell Avenue, Suite 800, Miami, FL 33131",
    "draft_reason": null,
    "state_updates": {
      "consecutive_no_progress_turns": 0,
      "negotiation_step": 0
    },
    "handoff_payload": null,
    "human_queue_payload": null,
    "self_correction_logs": [
      {
        "attempt": 1,
        "verdict": "pass",
        "failed_checks": []
      }
    ]
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [self_correction]: verdict='pass'; failed_checks=[]
  input draft: Hi Test User,  Got your profile for A1 Plumbing Co. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.  A specialist can 
Output 2 [pipeline]: outcome='send'; draft_action='send'; authorized_quote=n/a; SC attempts=1
  draft: Hi Test User,  Got your profile for A1 Plumbing Co. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.  A specialist can walk you through pricing and next steps. Reply here or let me know a good time f…
  SC attempt 1: verdict='pass'; failed=[]
```

---

### `test_first_touch_email_references_business`

- **Class:** `TestA1_BusinessHoursFormSubmission`
- **Intent:** A1: Form submission during business hours produces a first-touch draft.
- **Verdict:** **PASSED**
- **Duration:** 8.45s

#### Output produced

```json
[
  {
    "type": "self_correction",
    "input_draft_body": "Hi Test User,\n\nGot your profile for A1 Plumbing Co. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.\n\nWe have your profile link and can get started quickly. Reply here to go over pricing and next steps, or let me know a good time for a quick call with one of our specialists.\n\nJayden Faris / ReviewArmour / +1 (786) 464-3783\n1395 Brickell Avenue, Suite 800, Miami, FL 33131",
    "input_draft_subject": "Removing your Google reviews - A1 Plumbing Co",
    "verdict": "pass",
    "failed_checks": [],
    "suggested_fixes": [],
    "escalation_reason": null
  },
  {
    "type": "pipeline",
    "outcome": "send",
    "inbound_message": null,
    "wants_price": null,
    "quoted_previously": null,
    "sequence_stage": "first_touch",
    "channel": "email",
    "draft_action": "send",
    "draft_subject": "Removing your Google reviews - A1 Plumbing Co",
    "draft_body": "Hi Test User,\n\nGot your profile for A1 Plumbing Co. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.\n\nWe have your profile link and can get started quickly. Reply here to go over pricing and next steps, or let me know a good time for a quick call with one of our specialists.\n\nJayden Faris / ReviewArmour / +1 (786) 464-3783\n1395 Brickell Avenue, Suite 800, Miami, FL 33131",
    "draft_reason": null,
    "state_updates": {
      "consecutive_no_progress_turns": 0,
      "negotiation_step": 0
    },
    "handoff_payload": null,
    "human_queue_payload": null,
    "self_correction_logs": [
      {
        "attempt": 1,
        "verdict": "pass",
        "failed_checks": []
      }
    ]
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [self_correction]: verdict='pass'; failed_checks=[]
  input draft: Hi Test User,  Got your profile for A1 Plumbing Co. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.  We have your prof
Output 2 [pipeline]: outcome='send'; draft_action='send'; authorized_quote=n/a; SC attempts=1
  draft: Hi Test User,  Got your profile for A1 Plumbing Co. We remove policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.  We have your profile link and can get started quickly. Reply here to go over pricing and next ste…
  SC attempt 1: verdict='pass'; failed=[]
```

---

### `test_first_touch_produces_send_with_email_draft`

- **Class:** `TestA1_BusinessHoursFormSubmission`
- **Intent:** A1: Form submission during business hours produces a first-touch draft.
- **Verdict:** **PASSED**
- **Duration:** 16.87s

#### Output produced

```json
[
  {
    "type": "self_correction",
    "input_draft_body": "Hi Test User,\n\nGot your profile for A1 Plumbing Co. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis — you only pay once a review is actually down, not before.\n\nA specialist can walk you through pricing and next steps. Reply here or let me know a good time for a quick call.\n\nJayden Faris / ReviewArmour / +1 (786) 464-3783\n1395 Brickell Avenue, Suite 800, Miami, FL 33131",
    "input_draft_subject": "Review removal for A1 Plumbing Co",
    "verdict": "fix",
    "failed_checks": [
      "copy_rules: em dash present"
    ],
    "suggested_fixes": [
      "Replace em dashes with a comma or hyphen"
    ],
    "escalation_reason": null
  },
  {
    "type": "self_correction",
    "input_draft_body": "Hi Test User,\n\nWe have your Google Business Profile for A1 Plumbing Co. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis, meaning you only pay once a review is actually down.\n\nWant to go over pricing or get a specialist on a quick call? Just reply here and we can move forward.\n\nJayden Faris / ReviewArmour / +1 (786) 464-3783\n1395 Brickell Avenue, Suite 800, Miami, FL 33131",
    "input_draft_subject": "Removing your Google reviews - A1 Plumbing Co",
    "verdict": "pass",
    "failed_checks": [],
    "suggested_fixes": [],
    "escalation_reason": null
  },
  {
    "type": "pipeline",
    "outcome": "send",
    "inbound_message": null,
    "wants_price": null,
    "quoted_previously": null,
    "sequence_stage": "first_touch",
    "channel": "email",
    "draft_action": "send",
    "draft_subject": "Removing your Google reviews - A1 Plumbing Co",
    "draft_body": "Hi Test User,\n\nWe have your Google Business Profile for A1 Plumbing Co. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis, meaning you only pay once a review is actually down.\n\nWant to go over pricing or get a specialist on a quick call? Just reply here and we can move forward.\n\nJayden Faris / ReviewArmour / +1 (786) 464-3783\n1395 Brickell Avenue, Suite 800, Miami, FL 33131",
    "draft_reason": null,
    "state_updates": {
      "consecutive_no_progress_turns": 0,
      "negotiation_step": 0
    },
    "handoff_payload": null,
    "human_queue_payload": null,
    "self_correction_logs": [
      {
        "attempt": 1,
        "verdict": "fix",
        "failed_checks": [
          "copy_rules: em dash present"
        ]
      },
      {
        "attempt": 2,
        "verdict": "pass",
        "failed_checks": []
      }
    ]
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [self_correction]: verdict='fix'; failed_checks=['copy_rules: em dash present']
  input draft: Hi Test User,  Got your profile for A1 Plumbing Co. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis — you only pay once a review is actually down, not before.  A spec
Output 2 [self_correction]: verdict='pass'; failed_checks=[]
  input draft: Hi Test User,  We have your Google Business Profile for A1 Plumbing Co. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis, meaning you only pay once a review is actuall
Output 3 [pipeline]: outcome='send'; draft_action='send'; authorized_quote=n/a; SC attempts=2
  draft: Hi Test User,  We have your Google Business Profile for A1 Plumbing Co. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis, meaning you only pay once a review is actually down.  Want to go over pricing or get a specialist on a quick call? Just reply…
  SC attempt 1: verdict='fix'; failed=['copy_rules: em dash present']
  SC attempt 2: verdict='pass'; failed=[]
```

---

### `test_first_touch_sms_under_320_chars`

- **Class:** `TestA1_BusinessHoursFormSubmission`
- **Intent:** A1: Form submission during business hours produces a first-touch draft.
- **Verdict:** **PASSED**
- **Duration:** 10.78s

#### Output produced

```json
[
  {
    "type": "self_correction",
    "input_draft_body": "Hi, this is ReviewArmour. We have your Google profile for A1 Plumbing Co. We remove policy-violating reviews — you only pay after each one comes down. Want to go over pricing or set up a quick call?",
    "input_draft_subject": null,
    "verdict": "fix",
    "failed_checks": [
      "copy_rules: em dash present"
    ],
    "suggested_fixes": [
      "Replace em dashes with a comma or hyphen"
    ],
    "escalation_reason": null
  },
  {
    "type": "self_correction",
    "input_draft_body": "Hi, this is ReviewArmour. We have your Google profile for A1 Plumbing Co. We remove policy-violating reviews, and you only pay after each one comes down. Want to go over pricing or set up a quick call?",
    "input_draft_subject": null,
    "verdict": "pass",
    "failed_checks": [],
    "suggested_fixes": [],
    "escalation_reason": null
  },
  {
    "type": "pipeline",
    "outcome": "send",
    "inbound_message": null,
    "wants_price": null,
    "quoted_previously": null,
    "sequence_stage": "first_touch",
    "channel": "sms",
    "draft_action": "send",
    "draft_subject": null,
    "draft_body": "Hi, this is ReviewArmour. We have your Google profile for A1 Plumbing Co. We remove policy-violating reviews, and you only pay after each one comes down. Want to go over pricing or set up a quick call?",
    "draft_reason": null,
    "state_updates": {
      "consecutive_no_progress_turns": 0,
      "negotiation_step": 0
    },
    "handoff_payload": null,
    "human_queue_payload": null,
    "self_correction_logs": [
      {
        "attempt": 1,
        "verdict": "fix",
        "failed_checks": [
          "copy_rules: em dash present"
        ]
      },
      {
        "attempt": 2,
        "verdict": "pass",
        "failed_checks": []
      }
    ]
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [self_correction]: verdict='fix'; failed_checks=['copy_rules: em dash present']
  input draft: Hi, this is ReviewArmour. We have your Google profile for A1 Plumbing Co. We remove policy-violating reviews — you only pay after each one comes down. Want to go over pricing or set up a quick call?
Output 2 [self_correction]: verdict='pass'; failed_checks=[]
  input draft: Hi, this is ReviewArmour. We have your Google profile for A1 Plumbing Co. We remove policy-violating reviews, and you only pay after each one comes down. Want to go over pricing or set up a quick call
Output 3 [pipeline]: outcome='send'; draft_action='send'; authorized_quote=n/a; SC attempts=2
  draft: Hi, this is ReviewArmour. We have your Google profile for A1 Plumbing Co. We remove policy-violating reviews, and you only pay after each one comes down. Want to go over pricing or set up a quick call?
  SC attempt 1: verdict='fix'; failed=['copy_rules: em dash present']
  SC attempt 2: verdict='pass'; failed=[]
```

---

### `test_pipeline_produces_send_outcome_for_dispatch`

- **Class:** `TestA2_SalesmanDispatchDecision`
- **Intent:** A2/A3: Pipeline produces correct state for salesman dispatch/fallback.
    External platform not connected — verifying the decision layer only.
- **Verdict:** **FAILED**
- **Duration:** 0.89s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WbxUyt16txZfRWaio'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_after_hours_ai_first_touch_email`

- **Class:** `TestA4_AfterHoursFormSubmission`
- **Intent:** A4: After-hours submission — AI sends first-touch email with correct framing.
- **Verdict:** **PASSED**
- **Duration:** 6.33s

#### Output produced

```json
[
  {
    "type": "self_correction",
    "input_draft_body": "Hi Test User,\n\nGot your profile for A4 Bakery. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.\n\nWe have your profile link and will be in touch shortly with pricing. If you want to move faster, reply here or schedule a call with a specialist.\n\nJayden Faris / ReviewArmour / +1 (786) 464-3783\n1395 Brickell Avenue, Suite 800, Miami, FL 33131",
    "input_draft_subject": "Removing your Google reviews - A4 Bakery",
    "verdict": "pass",
    "failed_checks": [],
    "suggested_fixes": [],
    "escalation_reason": null
  },
  {
    "type": "pipeline",
    "outcome": "send",
    "inbound_message": null,
    "wants_price": null,
    "quoted_previously": null,
    "sequence_stage": "first_touch",
    "channel": "email",
    "draft_action": "send",
    "draft_subject": "Removing your Google reviews - A4 Bakery",
    "draft_body": "Hi Test User,\n\nGot your profile for A4 Bakery. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.\n\nWe have your profile link and will be in touch shortly with pricing. If you want to move faster, reply here or schedule a call with a specialist.\n\nJayden Faris / ReviewArmour / +1 (786) 464-3783\n1395 Brickell Avenue, Suite 800, Miami, FL 33131",
    "draft_reason": null,
    "state_updates": {
      "consecutive_no_progress_turns": 0,
      "negotiation_step": 0
    },
    "handoff_payload": null,
    "human_queue_payload": null,
    "self_correction_logs": [
      {
        "attempt": 1,
        "verdict": "pass",
        "failed_checks": []
      }
    ]
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [self_correction]: verdict='pass'; failed_checks=[]
  input draft: Hi Test User,  Got your profile for A4 Bakery. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.  We have you
Output 2 [pipeline]: outcome='send'; draft_action='send'; authorized_quote=n/a; SC attempts=1
  draft: Hi Test User,  Got your profile for A4 Bakery. ReviewArmour removes policy-violating Google reviews on a pay-after-removal basis - you only pay once a review is actually down, not before.  We have your profile link and will be in touch shortly with pricing. If you want to move fa…
  SC attempt 1: verdict='pass'; failed=[]
```

---

### `test_after_hours_ai_first_touch_sms`

- **Class:** `TestA4_AfterHoursFormSubmission`
- **Intent:** A4: After-hours submission — AI sends first-touch email with correct framing.
- **Verdict:** **PASSED**
- **Duration:** 17.72s

#### Output produced

```json
[
  {
    "type": "self_correction",
    "input_draft_body": "Hi, this is ReviewArmour. We have your profile for A4 Bakery. We remove policy-violating Google reviews — you only pay after each one comes down. Want to go over pricing or set up a quick call?",
    "input_draft_subject": null,
    "verdict": "fix",
    "failed_checks": [
      "copy_rules: em dash present"
    ],
    "suggested_fixes": [
      "Replace em dashes with a comma or hyphen"
    ],
    "escalation_reason": null
  },
  {
    "type": "self_correction",
    "input_draft_body": "Hi, this is ReviewArmour. We have your profile for A4 Bakery. We remove policy-violating Google reviews - you only pay after each one comes down. Want to go over pricing or set up a quick call?",
    "input_draft_subject": null,
    "verdict": "pass",
    "failed_checks": [],
    "suggested_fixes": [],
    "escalation_reason": null
  },
  {
    "type": "pipeline",
    "outcome": "send",
    "inbound_message": null,
    "wants_price": null,
    "quoted_previously": null,
    "sequence_stage": "first_touch",
    "channel": "sms",
    "draft_action": "send",
    "draft_subject": null,
    "draft_body": "Hi, this is ReviewArmour. We have your profile for A4 Bakery. We remove policy-violating Google reviews - you only pay after each one comes down. Want to go over pricing or set up a quick call?",
    "draft_reason": null,
    "state_updates": {
      "consecutive_no_progress_turns": 0,
      "negotiation_step": 0
    },
    "handoff_payload": null,
    "human_queue_payload": null,
    "self_correction_logs": [
      {
        "attempt": 1,
        "verdict": "fix",
        "failed_checks": [
          "copy_rules: em dash present"
        ]
      },
      {
        "attempt": 2,
        "verdict": "pass",
        "failed_checks": []
      }
    ]
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [self_correction]: verdict='fix'; failed_checks=['copy_rules: em dash present']
  input draft: Hi, this is ReviewArmour. We have your profile for A4 Bakery. We remove policy-violating Google reviews — you only pay after each one comes down. Want to go over pricing or set up a quick call?
Output 2 [self_correction]: verdict='pass'; failed_checks=[]
  input draft: Hi, this is ReviewArmour. We have your profile for A4 Bakery. We remove policy-violating Google reviews - you only pay after each one comes down. Want to go over pricing or set up a quick call?
Output 3 [pipeline]: outcome='send'; draft_action='send'; authorized_quote=n/a; SC attempts=2
  draft: Hi, this is ReviewArmour. We have your profile for A4 Bakery. We remove policy-violating Google reviews - you only pay after each one comes down. Want to go over pricing or set up a quick call?
  SC attempt 1: verdict='fix'; failed=['copy_rules: em dash present']
  SC attempt 2: verdict='pass'; failed=[]
```

---

### `test_ai_engages_with_lead_reply`

- **Class:** `TestA5_AfterHoursLeadReplies`
- **Intent:** A5: Lead replies to after-hours AI first touch.
- **Verdict:** **FAILED**
- **Duration:** 9.26s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2TtAUe51rh8aefXFFL'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_defamation_lawyer_escalates`

- **Class:** `TestA6_EscalationTriggerLanguage`
- **Intent:** A6: Lead sends escalation trigger (defamation/lawyer).
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

```json
[
  {
    "type": "pipeline",
    "outcome": "escalate",
    "inbound_message": "This is defamation. I'm going to talk to my lawyer about this.",
    "wants_price": null,
    "quoted_previously": null,
    "sequence_stage": "main",
    "channel": "email",
    "draft_action": "escalate",
    "draft_subject": null,
    "draft_body": null,
    "draft_reason": "legal_escalation:lawyer",
    "state_updates": {
      "consecutive_no_progress_turns": 0
    },
    "handoff_payload": null,
    "human_queue_payload": null,
    "self_correction_logs": []
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [pipeline]: outcome='escalate'; draft_action='escalate'; authorized_quote=n/a; SC attempts=0
  inbound: "This is defamation. I'm going to talk to my lawyer about this."
```

---

### `test_escalation_no_ai_message_sent`

- **Class:** `TestA6_EscalationTriggerLanguage`
- **Intent:** A6: Lead sends escalation trigger (defamation/lawyer).
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

```json
[
  {
    "type": "pipeline",
    "outcome": "escalate",
    "inbound_message": "My attorney will be in touch.",
    "wants_price": null,
    "quoted_previously": null,
    "sequence_stage": "main",
    "channel": "email",
    "draft_action": "escalate",
    "draft_subject": null,
    "draft_body": null,
    "draft_reason": "legal_escalation:attorney",
    "state_updates": {
      "consecutive_no_progress_turns": 0
    },
    "handoff_payload": null,
    "human_queue_payload": null,
    "self_correction_logs": []
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [pipeline]: outcome='escalate'; draft_action='escalate'; authorized_quote=n/a; SC attempts=0
  inbound: 'My attorney will be in touch.'
```

---

### `test_followup_3_at_24h_non_sunday`

- **Class:** `TestA7_LeadDoesNotReplyOvernight`
- **Intent:** A7: Follow-up cadence: T+30m, T+60m, T+24h, then queued_for_morning.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_followup_schedule_3_touches`

- **Class:** `TestA7_LeadDoesNotReplyOvernight`
- **Intent:** A7: Follow-up cadence: T+30m, T+60m, T+24h, then queued_for_morning.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_followup_timings`

- **Class:** `TestA7_LeadDoesNotReplyOvernight`
- **Intent:** A7: Follow-up cadence: T+30m, T+60m, T+24h, then queued_for_morning.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_morning_brief_contains_lead_data`

- **Class:** `TestA8_MorningQueueRelease`
- **Intent:** A8: Morning queue brief accuracy and priority sorting.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_morning_queue_priority_sorting`

- **Class:** `TestA8_MorningQueueRelease`
- **Intent:** A8: Morning queue brief accuracy and priority sorting.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_brief_has_opening_lines`

- **Class:** `TestA9_TalkingPointsBriefAccuracy`
- **Intent:** A9: Brief uses 'not stated' for unknowns, never invents.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_brief_uses_not_stated_for_unknowns`

- **Class:** `TestA9_TalkingPointsBriefAccuracy`
- **Intent:** A9: Brief uses 'not stated' for unknowns, never invents.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_ca6_step2_margin_fail_escalates`

- **Class:** `TestB10_MarginDiscipline`
- **Intent:** B10: Quote that would violate 20% margin → escalation.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "CA-6",
    "authorized_quote_usd_per_review": null,
    "negotiation_step": 2,
    "can_quote": false,
    "escalate": true,
    "escalation_reason": "Margin discipline: quote below 20 percent minimum margin",
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [commercial]: tier='CA-6'; quote=None; step=2; escalate=True
```

---

### `test_margin_fails_over_1_month_at_250`

- **Class:** `TestB10_MarginDiscipline`
- **Intent:** B10: Quote that would violate 20% margin → escalation.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_pipeline_quotes_500_for_dental`

- **Class:** `TestB1_USDental1ReviewUnderMonth`
- **Intent:** B1: US dental, 1 review, under 1 month → Tier US-2, $500.
- **Verdict:** **FAILED**
- **Duration:** 0.94s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2U7CZ1f19ax5ZbwFJt'}`

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-2",
    "authorized_quote_usd_per_review": 500,
    "negotiation_step": 0,
    "can_quote": true,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-2'; quote=500; step=0; escalate=False
```

---

### `test_tier_us2_dental`

- **Class:** `TestB1_USDental1ReviewUnderMonth`
- **Intent:** B1: US dental, 1 review, under 1 month → Tier US-2, $500.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-2",
    "authorized_quote_usd_per_review": 500,
    "negotiation_step": 0,
    "can_quote": true,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-2'; quote=500; step=0; escalate=False
```

---

### `test_tier_us3`

- **Class:** `TestB2_USPlumber4ReviewsMostlyUnder`
- **Intent:** B2: US plumber, 4 reviews, mostly under 1 month → Tier US-3, $425.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-3",
    "authorized_quote_usd_per_review": 425,
    "negotiation_step": 0,
    "can_quote": true,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-3'; quote=425; step=0; escalate=False
```

---

### `test_pipeline_ca_quotes_usd_not_cad`

- **Class:** `TestB3_CARestaurant2ReviewsUnder`
- **Intent:** B3: CA restaurant, 2 reviews, under 1 month → Tier CA-1, $375 USD.
- **Verdict:** **FAILED**
- **Duration:** 1.28s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UD3n6SA2YM3vNqgLj'}`

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "CA-1",
    "authorized_quote_usd_per_review": 375,
    "negotiation_step": 0,
    "can_quote": true,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
Output 1 [commercial]: tier='CA-1'; quote=375; step=0; escalate=False
```

---

### `test_tier_ca1`

- **Class:** `TestB3_CARestaurant2ReviewsUnder`
- **Intent:** B3: CA restaurant, 2 reviews, under 1 month → Tier CA-1, $375 USD.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "CA-1",
    "authorized_quote_usd_per_review": 375,
    "negotiation_step": 0,
    "can_quote": true,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [commercial]: tier='CA-1'; quote=375; step=0; escalate=False
```

---

### `test_first_pushback_us1`

- **Class:** `TestB4_PushbackFirstStep`
- **Intent:** B4: Lead pushes back once → negotiation step 1.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-1",
    "authorized_quote_usd_per_review": 425,
    "negotiation_step": 1,
    "can_quote": true,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-1'; quote=425; step=1; escalate=False
```

---

### `test_pipeline_pushback_step1`

- **Class:** `TestB4_PushbackFirstStep`
- **Intent:** B4: Lead pushes back once → negotiation step 1.
- **Verdict:** **FAILED**
- **Duration:** 1.65s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UK5vHPQLJx7CsMrEX'}`

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-1",
    "authorized_quote_usd_per_review": 425,
    "negotiation_step": 1,
    "can_quote": true,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-1'; quote=425; step=1; escalate=False
```

---

### `test_second_pushback_us1`

- **Class:** `TestB5_PushbackSecondStep`
- **Intent:** B5: Lead pushes back again → negotiation step 2.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-1",
    "authorized_quote_usd_per_review": 400,
    "negotiation_step": 2,
    "can_quote": true,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-1'; quote=400; step=2; escalate=False
```

---

### `test_below_floor_escalates`

- **Class:** `TestB6_PushbackBelowFloor`
- **Intent:** B6: Lead pushes below floor → human escalation.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-1",
    "authorized_quote_usd_per_review": null,
    "negotiation_step": 3,
    "can_quote": false,
    "escalate": true,
    "escalation_reason": "Negotiation past step 2",
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-1'; quote=None; step=3; escalate=True
```

---

### `test_pipeline_below_floor_escalates`

- **Class:** `TestB6_PushbackBelowFloor`
- **Intent:** B6: Lead pushes below floor → human escalation.
- **Verdict:** **PASSED**
- **Duration:** 0.77s

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-1",
    "authorized_quote_usd_per_review": null,
    "negotiation_step": 2,
    "can_quote": false,
    "escalate": true,
    "escalation_reason": "Lead pushing below floor",
    "request_gbp_first": false
  },
  {
    "type": "pipeline",
    "outcome": "escalate",
    "inbound_message": "I need it under $250 per review.",
    "wants_price": true,
    "quoted_previously": true,
    "sequence_stage": "main",
    "channel": "email",
    "draft_action": "escalate",
    "draft_subject": null,
    "draft_body": null,
    "draft_reason": "Lead pushing below floor",
    "state_updates": {
      "consecutive_no_progress_turns": 0,
      "ai_conversation_state": "escalated_to_human"
    },
    "handoff_payload": null,
    "human_queue_payload": null,
    "self_correction_logs": [],
    "commercial": {
      "tier_id": "US-1",
      "authorized_quote_usd_per_review": null,
      "negotiation_step": 2,
      "can_quote": false,
      "escalate": true,
      "escalation_reason": "Lead pushing below floor",
      "request_gbp_first": false
    }
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-1'; quote=None; step=2; escalate=True
Output 2 [pipeline]: outcome='escalate'; draft_action='escalate'; authorized_quote=None; SC attempts=0
  inbound: 'I need it under $250 per review.'
```

---

### `test_sc_catches_invented_price`

- **Class:** `TestB7_InventedPrice`
- **Intent:** B7: Self-correction catches invented price not in the matrix.
- **Verdict:** **FAILED**
- **Duration:** 0.36s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2URKDwqkwBwZ41Gihp'}`

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-1",
    "authorized_quote_usd_per_review": 450,
    "negotiation_step": 0,
    "can_quote": true,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-1'; quote=450; step=0; escalate=False
```

---

### `test_commercial_engine_requests_gbp`

- **Class:** `TestB8_GBPLinkMissingLeadAsksPrice`
- **Intent:** B8: GBP link missing, lead asks for price → AI asks for link first.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-1",
    "authorized_quote_usd_per_review": null,
    "negotiation_step": 0,
    "can_quote": false,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": true
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-1'; quote=None; step=0; escalate=False
```

---

### `test_pipeline_asks_for_gbp_link`

- **Class:** `TestB8_GBPLinkMissingLeadAsksPrice`
- **Intent:** B8: GBP link missing, lead asks for price → AI asks for link first.
- **Verdict:** **FAILED**
- **Duration:** 1.10s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UW8guYTFv7mdtdQFf'}`

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-1",
    "authorized_quote_usd_per_review": null,
    "negotiation_step": 0,
    "can_quote": false,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": true
  }
]
```

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-1'; quote=None; step=0; escalate=False
```

---

### `test_hidden_cost_caught[Our cost to remove this review is $80 per case.-expected_verdict0]`

- **Class:** `TestB9_HiddenCostLeaked`
- **Intent:** B9: Self-correction catches hidden cost numbers in draft.
- **Verdict:** **FAILED**
- **Duration:** 0.46s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UY4mp2vRFGFMpnsHs'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_hidden_cost_caught[The effective cost is approximately $214 per review.-expected_verdict3]`

- **Class:** `TestB9_HiddenCostLeaked`
- **Intent:** B9: Self-correction catches hidden cost numbers in draft.
- **Verdict:** **FAILED**
- **Duration:** 0.62s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2Ug8x3US3LN1f5eYLo'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_hidden_cost_caught[The lead acquisition cost was $50.-expected_verdict1]`

- **Class:** `TestB9_HiddenCostLeaked`
- **Intent:** B9: Self-correction catches hidden cost numbers in draft.
- **Verdict:** **FAILED**
- **Duration:** 0.63s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UagnEiZdnw2W9K1B2'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_hidden_cost_caught[We maintain a 20% margin on each deal.-expected_verdict2]`

- **Class:** `TestB9_HiddenCostLeaked`
- **Intent:** B9: Self-correction catches hidden cost numbers in draft.
- **Verdict:** **FAILED**
- **Duration:** 0.61s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UdQFAKx3VRTxVuxDC'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_pipeline_includes_timeline_paragraph`

- **Class:** `TestC1_HowLongUnderMonth`
- **Intent:** C1: 'How long?' with under-1-month reviews.
- **Verdict:** **FAILED**
- **Duration:** 0.96s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UkPSVYVYSFx7NQdtk'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_pipeline_includes_mixed_timeline`

- **Class:** `TestC2_HowLongMixedOver`
- **Intent:** C2: 'How long?' with mixed/over-1-month reviews.
- **Verdict:** **FAILED**
- **Duration:** 1.10s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2Uq9giZBPGZFaXSg6e'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_pipeline_success_rate_response`

- **Class:** `TestC3_SuccessRate`
- **Intent:** C3: 'What's your success rate?' → approved framing, no percentage.
- **Verdict:** **FAILED**
- **Duration:** 0.40s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UsDww3e8s8GiZECRX'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_sc_catches_percentage`

- **Class:** `TestC4_DraftContainsPercentage`
- **Intent:** C4: Self-correction catches specific percentage in draft.
- **Verdict:** **FAILED**
- **Duration:** 0.62s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2Utrg1SU7E88Hf4SEU'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_methodology_response`

- **Class:** `TestC5_HowDoYouRemoveReviews`
- **Intent:** C5: Methodology question → approved framing.
- **Verdict:** **FAILED**
- **Duration:** 0.87s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UyMJM4g8UtBD9zNu6'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_operational_detail_deflects`

- **Class:** `TestC6_OperationalDetail`
- **Intent:** C6: Lead asks for operational detail → deflect to call.
- **Verdict:** **FAILED**
- **Duration:** 0.94s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2V3rQzxagoyerFjqTQ'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_warranty_response`

- **Class:** `TestC7_WillReviewComeBack`
- **Intent:** C7: Warranty questions → approved framing.
- **Verdict:** **FAILED**
- **Duration:** 0.82s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2V7UT6U4AuYYowiHtg'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_invented_framing_caught[We guarantee removal within 48 hours.]`

- **Class:** `TestC8_InventedFraming`
- **Intent:** C8: Self-correction catches invented framing.
- **Verdict:** **FAILED**
- **Duration:** 0.68s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2V9VF4UmM1VkCZpqn9'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_invented_framing_caught[We have a direct contact at Google who handles these.]`

- **Class:** `TestC8_InventedFraming`
- **Intent:** C8: Self-correction catches invented framing.
- **Verdict:** **FAILED**
- **Duration:** 0.50s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VBypHTeC29KfZffmM'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_invented_framing_caught[We remove 19 out of 20 reviews successfully.]`

- **Class:** `TestC8_InventedFraming`
- **Intent:** C8: Self-correction catches invented framing.
- **Verdict:** **FAILED**
- **Duration:** 0.36s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VEB2gcwH7eTmixLBD'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_em_dash_caught`

- **Class:** `TestD1_EmDash`
- **Intent:** D1: Em dash in draft → fix.
- **Verdict:** **FAILED**
- **Duration:** 0.39s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VFjnTC7TsQvq4yxar'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_exclamation_caught`

- **Class:** `TestD2_ExclamationMark`
- **Intent:** D2: Exclamation mark in draft → fix.
- **Verdict:** **FAILED**
- **Duration:** 0.57s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VJB8RJMZg8u9Ti7UJ'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_flagged_caught`

- **Class:** `TestD3_FlaggedInsteadOfIdentified`
- **Intent:** D3: 'flagged' instead of 'identified' → fix.
- **Verdict:** **FAILED**
- **Duration:** 0.85s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VMFRqxuUTYZKCK1VD'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_wrong_business_name`

- **Class:** `TestD4_WrongBusinessName`
- **Intent:** D4: Wrong business name → fix.
- **Verdict:** **FAILED**
- **Duration:** 0.49s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VQ7pDBd1u6ezoaF1o'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_hard_timeline_caught`

- **Class:** `TestD5_HardTimelineCommitment`
- **Intent:** D5: Hard timeline commitment → fix.
- **Verdict:** **FAILED**
- **Duration:** 0.57s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VSYv5bskVUU1nZsPc'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_three_failures_human_queue`

- **Class:** `TestD6_ThreeFailedRedrafts`
- **Intent:** D6: Three consecutive SC failures → human_queue with full history.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

```json
[
  {
    "type": "pipeline",
    "outcome": "human_queue",
    "inbound_message": null,
    "wants_price": null,
    "quoted_previously": null,
    "sequence_stage": "main",
    "channel": "email",
    "draft_action": "send",
    "draft_subject": "Test",
    "draft_body": "Bad draft — always has em dash!",
    "draft_reason": null,
    "state_updates": {},
    "handoff_payload": null,
    "human_queue_payload": {
      "draft": {
        "subject": "Test",
        "body": "Bad draft — always has em dash!"
      },
      "verdict": "fix",
      "failed_checks": [
        "copy_rules: em dash"
      ],
      "escalation_reason": null,
      "attempts": [
        {
          "attempt": 1,
          "verdict": "fix",
          "failed_checks": [
            "copy_rules: em dash"
          ],
          "timestamp": "2026-05-31T17:17:18.238188+00:00"
        },
        {
          "attempt": 2,
          "verdict": "fix",
          "failed_checks": [
            "copy_rules: em dash"
          ],
          "timestamp": "2026-05-31T17:17:18.238188+00:00"
        },
        {
          "attempt": 3,
          "verdict": "fix",
          "failed_checks": [
            "copy_rules: em dash"
          ],
          "timestamp": "2026-05-31T17:17:18.238188+00:00"
        }
      ]
    },
    "self_correction_logs": [
      {
        "attempt": 1,
        "verdict": "fix",
        "failed_checks": [
          "copy_rules: em dash"
        ]
      },
      {
        "attempt": 2,
        "verdict": "fix",
        "failed_checks": [
          "copy_rules: em dash"
        ]
      },
      {
        "attempt": 3,
        "verdict": "fix",
        "failed_checks": [
          "copy_rules: em dash"
        ]
      }
    ]
  }
]
```

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
Output 1 [pipeline]: outcome='human_queue'; draft_action='send'; authorized_quote=n/a; SC attempts=3
  draft: Bad draft — always has em dash!
  SC attempt 1: verdict='fix'; failed=['copy_rules: em dash']
  SC attempt 2: verdict='fix'; failed=['copy_rules: em dash']
  SC attempt 3: verdict='fix'; failed=['copy_rules: em dash']
```

---

### `test_wrong_footer_caught`

- **Class:** `TestD7_WrongRegionalFooter`
- **Intent:** D7: CA lead with US/Miami footer → fix.
- **Verdict:** **FAILED**
- **Duration:** 0.62s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VVD9kJaSLgbZqW8x3'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_clean_draft_passes`

- **Class:** `TestD8_CleanDraftPasses`
- **Intent:** D8: Well-formed draft passes on first attempt.
- **Verdict:** **FAILED**
- **Duration:** 0.47s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VXSMBWmUCLbDV8wKn'}`

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-2",
    "authorized_quote_usd_per_review": 500,
    "negotiation_step": 0,
    "can_quote": true,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-2'; quote=500; step=0; escalate=False
```

---

### `test_acceptance_lets_do_it`

- **Class:** `TestE1_LetsDoIt`
- **Intent:** E1: Lead replies 'let's do it' → quote_accepted + handoff.
- **Verdict:** **FAILED**
- **Duration:** 1.39s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VdLJixFxyTpxVwPyo'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_confirmation_body_rules`

- **Class:** `TestE1_LetsDoIt`
- **Intent:** E1: Lead replies 'let's do it' → quote_accepted + handoff.
- **Verdict:** **FAILED**
- **Duration:** 1.80s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2Vkp1nFgqjYYo6YMe1'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_send_invoice_acceptance`

- **Class:** `TestE2_SendTheInvoice`
- **Intent:** E2: 'Send the invoice' triggers same acceptance flow.
- **Verdict:** **FAILED**
- **Duration:** 1.36s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VriDtBz7rzPhLUswz'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_ok_not_accepted_by_llm`

- **Class:** `TestE3_AmbiguousOk`
- **Intent:** E3: Ambiguous 'ok' after quote — LLM should not accept.
- **Verdict:** **FAILED**
- **Duration:** 1.41s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VxftzGsSc11gnv4Yj'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_acceptance_state_set_before_slack`

- **Class:** `TestE4_SlackDeliveryFails`
- **Intent:** E4: Slack delivery fails — pipeline records acceptance state regardless.
    Slack not connected — verifying state is set before Slack would fire.
- **Verdict:** **FAILED**
- **Duration:** 1.12s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WmELqASYzbJ6BW92g'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_confirmation_ca_footer`

- **Class:** `TestE5_ConfirmationMessageRules`
- **Intent:** E5: Confirmation message passes all copy rules.
- **Verdict:** **FAILED**
- **Duration:** 1.49s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WCnxZZhrvHbsR9TJH'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_confirmation_us_footer`

- **Class:** `TestE5_ConfirmationMessageRules`
- **Intent:** E5: Confirmation message passes all copy rules.
- **Verdict:** **FAILED**
- **Duration:** 1.70s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2W6E4mqZZq9ALfE7oc'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_no_stall_at_5h59`

- **Class:** `TestF1_StallAt6Hours`
- **Intent:** F1: 6-hour silence after quote → stalled_post_quote.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_stall_at_6h`

- **Class:** `TestF1_StallAt6Hours`
- **Intent:** F1: 6-hour silence after quote → stalled_post_quote.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_stall_payload_has_salesman_page`

- **Class:** `TestF1_StallAt6Hours`
- **Intent:** F1: 6-hour silence after quote → stalled_post_quote.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_backup_at_12h`

- **Class:** `TestF2_BackupAt12Hours`
- **Intent:** F2: 12-hour silence → backup_jayden page.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_lead_reply_during_stall`

- **Class:** `TestF3_LeadRepliesBeforeSalesman`
- **Intent:** F3: Lead replies during stall window — pipeline resumes normally.
- **Verdict:** **FAILED**
- **Duration:** 1.45s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WJL5nPU6Xv59LFNSy'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_hard_no_stall_at_2h`

- **Class:** `TestF4_StallWindowConfigurable`
- **Intent:** F4: soft_quote_mode changes stall window from 6h to 2h.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_soft_stall_at_2h`

- **Class:** `TestF4_StallWindowConfigurable`
- **Intent:** F4: soft_quote_mode changes stall window from 6h to 2h.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_stall_payloads_independent`

- **Class:** `TestF5_MultipleStalls`
- **Intent:** F5: Multiple stalled leads — each has independent context.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_sunday_deferred`

- **Class:** `TestG5_SundayDeferral`
- **Intent:** G5: Sunday touch defers to Monday 08:00 EST.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_touch1_sms_draft`

- **Class:** `TestH2_Touch1SMS`
- **Intent:** H2: Touch 1 SMS — contains first name, summary, link, under 200 chars.
- **Verdict:** **FAILED**
- **Duration:** 0.52s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WLucgcudQ8EyA3qu1'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_touch2_email_draft`

- **Class:** `TestH3_Touch2Email`
- **Intent:** H3: Touch 2 email — under 80 words.
- **Verdict:** **FAILED**
- **Duration:** 0.53s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WPfZLvnKUkV4BzjBE'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_touch3_sms_draft`

- **Class:** `TestH4_Touch3SMS`
- **Intent:** H4: Touch 3 SMS — under 160 chars, non-pressuring.
- **Verdict:** **FAILED**
- **Duration:** 0.38s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WRLmQBVeVk293bGaZ'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_sunday_deferred`

- **Class:** `TestH6_SundayReviewRequestDefers`
- **Intent:** H6: Sunday-due review request touch defers to Monday 08:00 EST.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_star_rating_caught`

- **Class:** `TestH7_StarRatingInDraft`
- **Intent:** H7: Self-correction catches star-rating ask in review request.
- **Verdict:** **FAILED**
- **Duration:** 0.42s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WSyEs82zWp35waGhX'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_incentive_caught`

- **Class:** `TestH8_IncentiveInDraft`
- **Intent:** H8: Self-correction catches incentive language in review request.
- **Verdict:** **FAILED**
- **Duration:** 1.16s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WY26kS8o3bECfkEvx'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_off_topic_redirect_then_reengage`

- **Class:** `TestI10_USOffTopicRedirect`
- **Intent:** I10: US, sends off-topic (SEO). AI redirects. Lead re-engages.
- **Verdict:** **FAILED**
- **Duration:** 0.74s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2XJSKFHxHmaAAmLuCS'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_full_conversation`

- **Class:** `TestI1_USDentistCooperativeAcceptsOpening`
- **Intent:** I1: US, 2 reviews under 1 month, dentist. Cooperative. Accepts opening quote.
- **Verdict:** **FAILED**
- **Duration:** 0.43s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2Wo6TuZAyt3f6YousD'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_full_negotiation`

- **Class:** `TestI2_USContractorPushesBackTwice`
- **Intent:** I2: US, 1 review under 1 month, contractor (high-ticket). Pushes back twice.
- **Verdict:** **FAILED**
- **Duration:** 0.37s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WpmRRJmLJsyhQG1c9'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_negotiation_triggers_logged`

- **Class:** `TestI2_USContractorPushesBackTwice`
- **Intent:** I2: US, 1 review under 1 month, contractor (high-ticket). Pushes back twice.
- **Verdict:** **PASSED**
- **Duration:** 0.00s

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions passed against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_bulk_pricing_conversation`

- **Class:** `TestI3_CABulkMixedRecency`
- **Intent:** I3: CA, 5 reviews mixed recency, restaurant. Bulk pricing CA-6.
- **Verdict:** **FAILED**
- **Duration:** 0.37s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WrPA5CM22hxcGzQBg'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_google_partner_methodology_framing`

- **Class:** `TestI4_USLawyerGooglePartnerBooksCall`
- **Intent:** I4: US lawyer asks 'are you a Google partner?' — methodology framing, not escalation.
- **Verdict:** **FAILED**
- **Duration:** 0.81s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WutzXxyf4qJZ1tdAx'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_full_conversation_with_framing`

- **Class:** `TestI5_CASuccessRateTimelineAccepts`
- **Intent:** I5: CA, 2 reviews under 1 month. Asks success rate, timeline, price, then accepts.
- **Verdict:** **FAILED**
- **Duration:** 0.44s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WwVjHX6QvWLWWU3Wh'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---

### `test_full_negotiation_to_escalation`

- **Class:** `TestI6_USPushesBelowFloorEscalates`
- **Intent:** I6: US, 2 reviews. Pushes through all steps and below floor → escalation.
- **Verdict:** **FAILED**
- **Duration:** 0.94s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2X1kTxQ2jEGLkqSe6N'}`

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-1",
    "authorized_quote_usd_per_review": 450,
    "negotiation_step": 0,
    "can_quote": true,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-1'; quote=450; step=0; escalate=False
```

---

### `test_stall_detection_after_silence`

- **Class:** `TestI7_USStallAfterQuote`
- **Intent:** I7: US, accepts quote thinking, goes silent. Stall fires at hour 6.
- **Verdict:** **FAILED**
- **Duration:** 0.87s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2X5Qz1oHWnvvWGEhsN'}`

#### Output produced

```json
[
  {
    "type": "commercial",
    "wants_price": true,
    "tier_id": "US-1",
    "authorized_quote_usd_per_review": 450,
    "negotiation_step": 0,
    "can_quote": true,
    "escalate": false,
    "escalation_reason": null,
    "request_gbp_first": false
  }
]
```

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
Output 1 [commercial]: tier='US-1'; quote=450; step=0; escalate=False
```

---

### `test_lawyer_escalation_and_followup_blocked`

- **Class:** `TestI8_USLawyerMentionEscalation`
- **Intent:** I8: US, mentions lawyer. Immediate escalation. Follow-up routes to human.
- **Verdict:** **FAILED**
- **Duration:** 0.78s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2X8znQ1RQVxExCR59M'}`

#### Output produced

```json
[
  {
    "type": "pipeline",
    "outcome": "escalate",
    "inbound_message": "This review is defamatory. I might call my lawyer about it.",
    "wants_price": null,
    "quoted_previously": null,
    "sequence_stage": "main",
    "channel": "email",
    "draft_action": "escalate",
    "draft_subject": null,
    "draft_body": null,
    "draft_reason": "legal_escalation:lawyer",
    "state_updates": {
      "consecutive_no_progress_turns": 0
    },
    "handoff_payload": null,
    "human_queue_payload": null,
    "self_correction_logs": []
  }
]
```

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
Output 1 [pipeline]: outcome='escalate'; draft_action='escalate'; authorized_quote=n/a; SC attempts=0
  inbound: 'This review is defamatory. I might call my lawyer about it.'
```

---

### `test_pay_anchor_then_acceptance`

- **Class:** `TestI9_CAPayAfterRemovalAccepts`
- **Intent:** I9: CA, 'what if it doesn't work' (pre-payment concern). Pay-after-removal anchor.
- **Verdict:** **FAILED**
- **Duration:** 1.46s
- **Failure:** `Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2XFJJARXvSEg59bxzt'}`

#### Output produced

_No pipeline/SC/commercial output captured._

#### Verdict on output

Test assertions **failed** against the captured output(s) above.

```text
No API output captured (deterministic assertion only).
```

---
