Live flow test run — 2026-05-31T17:17:43.475732+00:00
Results: 38 passed, 55 failed, 0 skipped, 0 xfailed / 93 total
API credit blocks: 55 (likely real failures: 0)
Duration: 124.8s
Detailed report: tests/TEST_RESULTS_REPORT.md

## Quick listing

tests/test_live_flows.py::TestA10_RegionalFooter::test_ca_first_touch_has_toronto_footer FAILED
tests/test_live_flows.py::TestA10_RegionalFooter::test_us_first_touch_has_miami_footer FAILED
tests/test_live_flows.py::TestA11_DSTTransition::test_est_scheduling_uses_america_new_york PASSED
tests/test_live_flows.py::TestA11_DSTTransition::test_sunday_deferral_respects_est_not_utc PASSED
tests/test_live_flows.py::TestA12_SMSDeliveryFailureFallback::test_pipeline_produces_email_draft_regardless FAILED
tests/test_live_flows.py::TestA13_AIStopsAfterEscalation::test_post_escalation_message_does_not_resume_ai FAILED
tests/test_live_flows.py::TestA1_BusinessHoursFormSubmission::test_first_touch_email_has_us_footer PASSED
tests/test_live_flows.py::TestA1_BusinessHoursFormSubmission::test_first_touch_email_references_business PASSED
tests/test_live_flows.py::TestA1_BusinessHoursFormSubmission::test_first_touch_produces_send_with_email_draft PASSED
tests/test_live_flows.py::TestA1_BusinessHoursFormSubmission::test_first_touch_sms_under_320_chars PASSED
tests/test_live_flows.py::TestA2_SalesmanDispatchDecision::test_pipeline_produces_send_outcome_for_dispatch FAILED
tests/test_live_flows.py::TestA4_AfterHoursFormSubmission::test_after_hours_ai_first_touch_email PASSED
tests/test_live_flows.py::TestA4_AfterHoursFormSubmission::test_after_hours_ai_first_touch_sms PASSED
tests/test_live_flows.py::TestA5_AfterHoursLeadReplies::test_ai_engages_with_lead_reply FAILED
tests/test_live_flows.py::TestA6_EscalationTriggerLanguage::test_defamation_lawyer_escalates PASSED
tests/test_live_flows.py::TestA6_EscalationTriggerLanguage::test_escalation_no_ai_message_sent PASSED
tests/test_live_flows.py::TestA7_LeadDoesNotReplyOvernight::test_followup_3_at_24h_non_sunday PASSED
tests/test_live_flows.py::TestA7_LeadDoesNotReplyOvernight::test_followup_schedule_3_touches PASSED
tests/test_live_flows.py::TestA7_LeadDoesNotReplyOvernight::test_followup_timings PASSED
tests/test_live_flows.py::TestA8_MorningQueueRelease::test_morning_brief_contains_lead_data PASSED
tests/test_live_flows.py::TestA8_MorningQueueRelease::test_morning_queue_priority_sorting PASSED
tests/test_live_flows.py::TestA9_TalkingPointsBriefAccuracy::test_brief_has_opening_lines PASSED
tests/test_live_flows.py::TestA9_TalkingPointsBriefAccuracy::test_brief_uses_not_stated_for_unknowns PASSED
tests/test_live_flows.py::TestB10_MarginDiscipline::test_ca6_step2_margin_fail_escalates PASSED
tests/test_live_flows.py::TestB10_MarginDiscipline::test_margin_fails_over_1_month_at_250 PASSED
tests/test_live_flows.py::TestB1_USDental1ReviewUnderMonth::test_pipeline_quotes_500_for_dental FAILED
tests/test_live_flows.py::TestB1_USDental1ReviewUnderMonth::test_tier_us2_dental PASSED
tests/test_live_flows.py::TestB2_USPlumber4ReviewsMostlyUnder::test_tier_us3 PASSED
tests/test_live_flows.py::TestB3_CARestaurant2ReviewsUnder::test_pipeline_ca_quotes_usd_not_cad FAILED
tests/test_live_flows.py::TestB3_CARestaurant2ReviewsUnder::test_tier_ca1 PASSED
tests/test_live_flows.py::TestB4_PushbackFirstStep::test_first_pushback_us1 PASSED
tests/test_live_flows.py::TestB4_PushbackFirstStep::test_pipeline_pushback_step1 FAILED
tests/test_live_flows.py::TestB5_PushbackSecondStep::test_second_pushback_us1 PASSED
tests/test_live_flows.py::TestB6_PushbackBelowFloor::test_below_floor_escalates PASSED
tests/test_live_flows.py::TestB6_PushbackBelowFloor::test_pipeline_below_floor_escalates PASSED
tests/test_live_flows.py::TestB7_InventedPrice::test_sc_catches_invented_price FAILED
tests/test_live_flows.py::TestB8_GBPLinkMissingLeadAsksPrice::test_commercial_engine_requests_gbp PASSED
tests/test_live_flows.py::TestB8_GBPLinkMissingLeadAsksPrice::test_pipeline_asks_for_gbp_link FAILED
tests/test_live_flows.py::TestB9_HiddenCostLeaked::test_hidden_cost_caught[Our cost to remove this review is $80 per case.-expected_verdict0] FAILED
tests/test_live_flows.py::TestB9_HiddenCostLeaked::test_hidden_cost_caught[The effective cost is approximately $214 per review.-expected_verdict3] FAILED
tests/test_live_flows.py::TestB9_HiddenCostLeaked::test_hidden_cost_caught[The lead acquisition cost was $50.-expected_verdict1] FAILED
tests/test_live_flows.py::TestB9_HiddenCostLeaked::test_hidden_cost_caught[We maintain a 20% margin on each deal.-expected_verdict2] FAILED
tests/test_live_flows.py::TestC1_HowLongUnderMonth::test_pipeline_includes_timeline_paragraph FAILED
tests/test_live_flows.py::TestC2_HowLongMixedOver::test_pipeline_includes_mixed_timeline FAILED
tests/test_live_flows.py::TestC3_SuccessRate::test_pipeline_success_rate_response FAILED
tests/test_live_flows.py::TestC4_DraftContainsPercentage::test_sc_catches_percentage FAILED
tests/test_live_flows.py::TestC5_HowDoYouRemoveReviews::test_methodology_response FAILED
tests/test_live_flows.py::TestC6_OperationalDetail::test_operational_detail_deflects FAILED
tests/test_live_flows.py::TestC7_WillReviewComeBack::test_warranty_response FAILED
tests/test_live_flows.py::TestC8_InventedFraming::test_invented_framing_caught[We guarantee removal within 48 hours.] FAILED
tests/test_live_flows.py::TestC8_InventedFraming::test_invented_framing_caught[We have a direct contact at Google who handles these.] FAILED
tests/test_live_flows.py::TestC8_InventedFraming::test_invented_framing_caught[We remove 19 out of 20 reviews successfully.] FAILED
tests/test_live_flows.py::TestD1_EmDash::test_em_dash_caught FAILED
tests/test_live_flows.py::TestD2_ExclamationMark::test_exclamation_caught FAILED
tests/test_live_flows.py::TestD3_FlaggedInsteadOfIdentified::test_flagged_caught FAILED
tests/test_live_flows.py::TestD4_WrongBusinessName::test_wrong_business_name FAILED
tests/test_live_flows.py::TestD5_HardTimelineCommitment::test_hard_timeline_caught FAILED
tests/test_live_flows.py::TestD6_ThreeFailedRedrafts::test_three_failures_human_queue PASSED
tests/test_live_flows.py::TestD7_WrongRegionalFooter::test_wrong_footer_caught FAILED
tests/test_live_flows.py::TestD8_CleanDraftPasses::test_clean_draft_passes FAILED
tests/test_live_flows.py::TestE1_LetsDoIt::test_acceptance_lets_do_it FAILED
tests/test_live_flows.py::TestE1_LetsDoIt::test_confirmation_body_rules FAILED
tests/test_live_flows.py::TestE2_SendTheInvoice::test_send_invoice_acceptance FAILED
tests/test_live_flows.py::TestE3_AmbiguousOk::test_ok_not_accepted_by_llm FAILED
tests/test_live_flows.py::TestE4_SlackDeliveryFails::test_acceptance_state_set_before_slack FAILED
tests/test_live_flows.py::TestE5_ConfirmationMessageRules::test_confirmation_ca_footer FAILED
tests/test_live_flows.py::TestE5_ConfirmationMessageRules::test_confirmation_us_footer FAILED
tests/test_live_flows.py::TestF1_StallAt6Hours::test_no_stall_at_5h59 PASSED
tests/test_live_flows.py::TestF1_StallAt6Hours::test_stall_at_6h PASSED
tests/test_live_flows.py::TestF1_StallAt6Hours::test_stall_payload_has_salesman_page PASSED
tests/test_live_flows.py::TestF2_BackupAt12Hours::test_backup_at_12h PASSED
tests/test_live_flows.py::TestF3_LeadRepliesBeforeSalesman::test_lead_reply_during_stall FAILED
tests/test_live_flows.py::TestF4_StallWindowConfigurable::test_hard_no_stall_at_2h PASSED
tests/test_live_flows.py::TestF4_StallWindowConfigurable::test_soft_stall_at_2h PASSED
tests/test_live_flows.py::TestF5_MultipleStalls::test_stall_payloads_independent PASSED
tests/test_live_flows.py::TestG5_SundayDeferral::test_sunday_deferred PASSED
tests/test_live_flows.py::TestH2_Touch1SMS::test_touch1_sms_draft FAILED
tests/test_live_flows.py::TestH3_Touch2Email::test_touch2_email_draft FAILED
tests/test_live_flows.py::TestH4_Touch3SMS::test_touch3_sms_draft FAILED
tests/test_live_flows.py::TestH6_SundayReviewRequestDefers::test_sunday_deferred PASSED
tests/test_live_flows.py::TestH7_StarRatingInDraft::test_star_rating_caught FAILED
tests/test_live_flows.py::TestH8_IncentiveInDraft::test_incentive_caught FAILED
tests/test_live_flows.py::TestI10_USOffTopicRedirect::test_off_topic_redirect_then_reengage FAILED
tests/test_live_flows.py::TestI1_USDentistCooperativeAcceptsOpening::test_full_conversation FAILED
tests/test_live_flows.py::TestI2_USContractorPushesBackTwice::test_full_negotiation FAILED
tests/test_live_flows.py::TestI2_USContractorPushesBackTwice::test_negotiation_triggers_logged PASSED
tests/test_live_flows.py::TestI3_CABulkMixedRecency::test_bulk_pricing_conversation FAILED
tests/test_live_flows.py::TestI4_USLawyerGooglePartnerBooksCall::test_google_partner_methodology_framing FAILED
tests/test_live_flows.py::TestI5_CASuccessRateTimelineAccepts::test_full_conversation_with_framing FAILED
tests/test_live_flows.py::TestI6_USPushesBelowFloorEscalates::test_full_negotiation_to_escalation FAILED
tests/test_live_flows.py::TestI7_USStallAfterQuote::test_stall_detection_after_silence FAILED
tests/test_live_flows.py::TestI8_USLawyerMentionEscalation::test_lawyer_escalation_and_followup_blocked FAILED
tests/test_live_flows.py::TestI9_CAPayAfterRemovalAccepts::test_pay_anchor_then_acceptance FAILED

## Failures

- `tests/test_live_flows.py::TestA10_RegionalFooter::test_ca_first_touch_has_toronto_footer`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2TwAoi1a5cGAa8AmCJ'}
- `tests/test_live_flows.py::TestA10_RegionalFooter::test_us_first_touch_has_miami_footer`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2Ty3uuQ6VuFmv6d7pm'}
- `tests/test_live_flows.py::TestA12_SMSDeliveryFailureFallback::test_pipeline_produces_email_draft_regardless`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WgHgpXidtc7RMyXNJ'}
- `tests/test_live_flows.py::TestA13_AIStopsAfterEscalation::test_post_escalation_message_does_not_resume_ai`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2U3ATmPs37frwA7ems'}
- `tests/test_live_flows.py::TestA2_SalesmanDispatchDecision::test_pipeline_produces_send_outcome_for_dispatch`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WbxUyt16txZfRWaio'}
- `tests/test_live_flows.py::TestA5_AfterHoursLeadReplies::test_ai_engages_with_lead_reply`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2TtAUe51rh8aefXFFL'}
- `tests/test_live_flows.py::TestB1_USDental1ReviewUnderMonth::test_pipeline_quotes_500_for_dental`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2U7CZ1f19ax5ZbwFJt'}
- `tests/test_live_flows.py::TestB3_CARestaurant2ReviewsUnder::test_pipeline_ca_quotes_usd_not_cad`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UD3n6SA2YM3vNqgLj'}
- `tests/test_live_flows.py::TestB4_PushbackFirstStep::test_pipeline_pushback_step1`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UK5vHPQLJx7CsMrEX'}
- `tests/test_live_flows.py::TestB7_InventedPrice::test_sc_catches_invented_price`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2URKDwqkwBwZ41Gihp'}
- `tests/test_live_flows.py::TestB8_GBPLinkMissingLeadAsksPrice::test_pipeline_asks_for_gbp_link`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UW8guYTFv7mdtdQFf'}
- `tests/test_live_flows.py::TestB9_HiddenCostLeaked::test_hidden_cost_caught[Our cost to remove this review is $80 per case.-expected_verdict0]`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UY4mp2vRFGFMpnsHs'}
- `tests/test_live_flows.py::TestB9_HiddenCostLeaked::test_hidden_cost_caught[The effective cost is approximately $214 per review.-expected_verdict3]`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2Ug8x3US3LN1f5eYLo'}
- `tests/test_live_flows.py::TestB9_HiddenCostLeaked::test_hidden_cost_caught[The lead acquisition cost was $50.-expected_verdict1]`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UagnEiZdnw2W9K1B2'}
- `tests/test_live_flows.py::TestB9_HiddenCostLeaked::test_hidden_cost_caught[We maintain a 20% margin on each deal.-expected_verdict2]`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UdQFAKx3VRTxVuxDC'}
- `tests/test_live_flows.py::TestC1_HowLongUnderMonth::test_pipeline_includes_timeline_paragraph`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UkPSVYVYSFx7NQdtk'}
- `tests/test_live_flows.py::TestC2_HowLongMixedOver::test_pipeline_includes_mixed_timeline`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2Uq9giZBPGZFaXSg6e'}
- `tests/test_live_flows.py::TestC3_SuccessRate::test_pipeline_success_rate_response`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UsDww3e8s8GiZECRX'}
- `tests/test_live_flows.py::TestC4_DraftContainsPercentage::test_sc_catches_percentage`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2Utrg1SU7E88Hf4SEU'}
- `tests/test_live_flows.py::TestC5_HowDoYouRemoveReviews::test_methodology_response`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2UyMJM4g8UtBD9zNu6'}
- `tests/test_live_flows.py::TestC6_OperationalDetail::test_operational_detail_deflects`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2V3rQzxagoyerFjqTQ'}
- `tests/test_live_flows.py::TestC7_WillReviewComeBack::test_warranty_response`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2V7UT6U4AuYYowiHtg'}
- `tests/test_live_flows.py::TestC8_InventedFraming::test_invented_framing_caught[We guarantee removal within 48 hours.]`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2V9VF4UmM1VkCZpqn9'}
- `tests/test_live_flows.py::TestC8_InventedFraming::test_invented_framing_caught[We have a direct contact at Google who handles these.]`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VBypHTeC29KfZffmM'}
- `tests/test_live_flows.py::TestC8_InventedFraming::test_invented_framing_caught[We remove 19 out of 20 reviews successfully.]`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VEB2gcwH7eTmixLBD'}
- `tests/test_live_flows.py::TestD1_EmDash::test_em_dash_caught`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VFjnTC7TsQvq4yxar'}
- `tests/test_live_flows.py::TestD2_ExclamationMark::test_exclamation_caught`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VJB8RJMZg8u9Ti7UJ'}
- `tests/test_live_flows.py::TestD3_FlaggedInsteadOfIdentified::test_flagged_caught`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VMFRqxuUTYZKCK1VD'}
- `tests/test_live_flows.py::TestD4_WrongBusinessName::test_wrong_business_name`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VQ7pDBd1u6ezoaF1o'}
- `tests/test_live_flows.py::TestD5_HardTimelineCommitment::test_hard_timeline_caught`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VSYv5bskVUU1nZsPc'}
- `tests/test_live_flows.py::TestD7_WrongRegionalFooter::test_wrong_footer_caught`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VVD9kJaSLgbZqW8x3'}
- `tests/test_live_flows.py::TestD8_CleanDraftPasses::test_clean_draft_passes`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VXSMBWmUCLbDV8wKn'}
- `tests/test_live_flows.py::TestE1_LetsDoIt::test_acceptance_lets_do_it`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VdLJixFxyTpxVwPyo'}
- `tests/test_live_flows.py::TestE1_LetsDoIt::test_confirmation_body_rules`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2Vkp1nFgqjYYo6YMe1'}
- `tests/test_live_flows.py::TestE2_SendTheInvoice::test_send_invoice_acceptance`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VriDtBz7rzPhLUswz'}
- `tests/test_live_flows.py::TestE3_AmbiguousOk::test_ok_not_accepted_by_llm`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2VxftzGsSc11gnv4Yj'}
- `tests/test_live_flows.py::TestE4_SlackDeliveryFails::test_acceptance_state_set_before_slack`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WmELqASYzbJ6BW92g'}
- `tests/test_live_flows.py::TestE5_ConfirmationMessageRules::test_confirmation_ca_footer`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WCnxZZhrvHbsR9TJH'}
- `tests/test_live_flows.py::TestE5_ConfirmationMessageRules::test_confirmation_us_footer`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2W6E4mqZZq9ALfE7oc'}
- `tests/test_live_flows.py::TestF3_LeadRepliesBeforeSalesman::test_lead_reply_during_stall`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WJL5nPU6Xv59LFNSy'}
- `tests/test_live_flows.py::TestH2_Touch1SMS::test_touch1_sms_draft`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WLucgcudQ8EyA3qu1'}
- `tests/test_live_flows.py::TestH3_Touch2Email::test_touch2_email_draft`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WPfZLvnKUkV4BzjBE'}
- `tests/test_live_flows.py::TestH4_Touch3SMS::test_touch3_sms_draft`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WRLmQBVeVk293bGaZ'}
- `tests/test_live_flows.py::TestH7_StarRatingInDraft::test_star_rating_caught`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WSyEs82zWp35waGhX'}
- `tests/test_live_flows.py::TestH8_IncentiveInDraft::test_incentive_caught`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WY26kS8o3bECfkEvx'}
- `tests/test_live_flows.py::TestI10_USOffTopicRedirect::test_off_topic_redirect_then_reengage`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2XJSKFHxHmaAAmLuCS'}
- `tests/test_live_flows.py::TestI1_USDentistCooperativeAcceptsOpening::test_full_conversation`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2Wo6TuZAyt3f6YousD'}
- `tests/test_live_flows.py::TestI2_USContractorPushesBackTwice::test_full_negotiation`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WpmRRJmLJsyhQG1c9'}
- `tests/test_live_flows.py::TestI3_CABulkMixedRecency::test_bulk_pricing_conversation`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WrPA5CM22hxcGzQBg'}
- `tests/test_live_flows.py::TestI4_USLawyerGooglePartnerBooksCall::test_google_partner_methodology_framing`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WutzXxyf4qJZ1tdAx'}
- `tests/test_live_flows.py::TestI5_CASuccessRateTimelineAccepts::test_full_conversation_with_framing`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2WwVjHX6QvWLWWU3Wh'}
- `tests/test_live_flows.py::TestI6_USPushesBelowFloorEscalates::test_full_negotiation_to_escalation`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2X1kTxQ2jEGLkqSe6N'}
- `tests/test_live_flows.py::TestI7_USStallAfterQuote::test_stall_detection_after_silence`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2X5Qz1oHWnvvWGEhsN'}
- `tests/test_live_flows.py::TestI8_USLawyerMentionEscalation::test_lawyer_escalation_and_followup_blocked`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2X8znQ1RQVxExCR59M'}
- `tests/test_live_flows.py::TestI9_CAPayAfterRemovalAccepts::test_pay_anchor_then_acceptance`: Anthropic API error: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.'}, 'request_id': 'req_011Cbb2XFJJARXvSEg59bxzt'}