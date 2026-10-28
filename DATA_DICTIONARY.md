# Data Dictionary and Lifecycle Notes

## Dataset overview

The generator creates 20,000 unique synthetic customers and monthly prediction rows for 18 dates (2025-01-01 through 2026-06-01). Clean data is under `generated_data_20000/clean_baseline`; the separate `anomaly_injected` folder deliberately contains four data-quality violations for detector testing.

## Relational tables

| Table | Grain / primary key | Purpose |
|---|---|---|
| `Customer` | One row per customer; `customer_id` | Signup date, region, segment, seasonal-user flag |
| `Subscription` | One row per generated subscription; `subscription_id` | Plan, price, lifecycle status and end date |
| `UsageSnapshot` | Subscription-month; `usage_snapshot_id` | Sessions, minutes and recency snapshot |
| `BillingEvent` | One invoice/payment event; `billing_event_id` | Invoice, payment failure and payment success history |
| `SupportCase` | One support case; `support_case_id` | Case creation, resolution, category and status |
| `Offer` | One offer definition; `offer_id` | Offer type, cost and minimum-margin rule |
| `EligibilityRule` | One rule definition; `eligibility_rule_id` | Rule code, condition and version |
| `OfferRule` | Offer-to-rule bridge; `offer_rule_id` | Effective dates, priority and mandatory flag |
| `EligibilityEvaluation` | One customer decision; `eligibility_evaluation_id` | Risk, eligibility decision and expected economics |
| `EligibilityRuleResult` | One rule evaluation; `rule_result_id` | Pass/fail and observed/threshold values |
| `CampaignContact` | One randomized customer assignment; `campaign_contact_id` | Treatment/control assignment, eligibility and contact status |
| `CampaignContactEvent` | One campaign event; `campaign_contact_event_id` | Assignment, offer-send/delivery/response/redemption events |
| `SubscriptionEvent` | One lifecycle event; `subscription_event_id` | Activation, plan change and termination history |
| `ChurnOutcome` | One annual outcome per customer; `churn_outcome_id` | Annual 2026 outcome using `CHURN-<customer_id>-2026` IDs |
| `MonthlyChurnLabel` | Customer-prediction date; `monthly_label_id` | Label status, 60-day horizon and event metadata |
| `RetentionOutcome` | One follow-up outcome per assigned contact; `retention_outcome_id` | Retention, margin, offer/campaign costs and attribution |

## Model-facing files

| File | Grain | Use |
|---|---|---|
| `features.csv` | Customer-prediction date | Pre-prediction features only |
| `ground_truth.csv` | Customer-prediction date | Separate model target and event timing |
| `retention_potential_outcomes.csv` | Randomized contact | Synthetic potential outcomes used for generator validation; not model features |
| `source_manifest.json` | One manifest per variant | Seed, row counts and CSV SHA-256 checksums |
| `validation_report.json` | One report per variant | Relational and business-rule validation results |

## Feature definitions

- `sessions_30d`: synthetic sessions observed in the recent 30-day period.
- `usage_minutes_30d`: synthetic usage minutes in the recent 30-day period.
- `days_since_last_use`: recency measure, capped by the generator.
- `tenure_days`: prediction date minus signup date.
- `failed_payments_90d`: failed payment events in the 90-day lookback window.
- `support_case_count_18m`: despite the historical column name, currently a binary prior-support-case indicator (0/1).
- `risk_score`: hand-built synthetic heuristic based on selected behavior and payment indicators; it is not a trained model probability.

## Label definition

For a prediction date, a positive label means the generated churn/termination date occurs strictly after the prediction date and on or before 60 days later. A negative label requires the full 60-day observation horizon and no churn event in that window. Incomplete horizons should be censored, not automatically labelled negative. The current generated feature dates all have a complete horizon under the configured observation end date.

A failed payment is not sufficient to label churn. The subscription lifecycle termination is the churn event. Annual outcomes and monthly prediction labels serve different purposes and should not be mixed.

## Deliberate anomaly fixtures

| ID | Scenario | Expected detection |
|---|---|---|
| `ANOM-001` | Churn label event date is not after prediction date | Temporal label violation |
| `ANOM-002` | Offer sent to a customer marked ineligible | Eligibility violation |
| `ANOM-003` | Offer exposure is recorded for a control assignment | Experiment contamination |
| `ANOM-004` | One retention event is attributed as primary to multiple customers/contacts | Duplicate retention attribution |

Use only the clean baseline for model training and primary experiment analysis. The anomaly-injected variant exists to demonstrate that checks can identify known defects.

## Economics and causal interpretation

The treatment/control experiment is randomly assigned within the synthetic generator, but the outcomes and treatment effect are also generated by explicit assumptions. Report the results as a simulation exercise, use intention-to-treat for the primary comparison, and do not imply that the estimated lift predicts a real campaign. Margin less recorded offer and campaign costs is descriptive; cost definitions and attribution require review before any business decision.
