PRAGMA foreign_keys = ON;

-- Ten core business entities plus normalized audit, bridge, and monthly-label tables.
CREATE TABLE Customer (
  customer_id TEXT PRIMARY KEY NOT NULL,
  signup_date TEXT NOT NULL CHECK(date(signup_date) IS NOT NULL),
  region TEXT NOT NULL CHECK(region IN ('NORTH','SOUTH','EAST','WEST','CENTRAL')),
  customer_segment TEXT NOT NULL CHECK(customer_segment IN ('VALUE','STANDARD','PREMIUM')),
  seasonal_user_flag INTEGER NOT NULL CHECK(seasonal_user_flag IN (0,1))
);

CREATE TABLE Subscription (
  subscription_id TEXT PRIMARY KEY NOT NULL,
  customer_id TEXT NOT NULL,
  plan_code TEXT NOT NULL CHECK(plan_code IN ('BASIC_MONTHLY','STANDARD_MONTHLY','PREMIUM_MONTHLY','ANNUAL')),
  start_date TEXT NOT NULL CHECK(date(start_date) IS NOT NULL),
  end_date TEXT CHECK(end_date IS NULL OR date(end_date) IS NOT NULL),
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','PAST_DUE','CANCELLATION_PENDING','TERMINATED')),
  monthly_price_inr NUMERIC NOT NULL CHECK(monthly_price_inr >= 0),
  UNIQUE(subscription_id, customer_id),
  FOREIGN KEY(customer_id) REFERENCES Customer(customer_id),
  CHECK(end_date IS NULL OR end_date >= start_date),
  CHECK((status='TERMINATED' AND end_date IS NOT NULL) OR status<>'TERMINATED')
);

CREATE TABLE UsageSnapshot (
  usage_snapshot_id TEXT PRIMARY KEY NOT NULL,
  subscription_id TEXT NOT NULL,
  snapshot_date TEXT NOT NULL CHECK(date(snapshot_date) IS NOT NULL),
  sessions_30d INTEGER NOT NULL CHECK(sessions_30d >= 0),
  usage_minutes_30d NUMERIC NOT NULL CHECK(usage_minutes_30d >= 0),
  days_since_last_use INTEGER NOT NULL CHECK(days_since_last_use >= 0),
  UNIQUE(subscription_id, snapshot_date),
  FOREIGN KEY(subscription_id) REFERENCES Subscription(subscription_id)
);

CREATE TABLE BillingEvent (
  billing_event_id TEXT PRIMARY KEY NOT NULL,
  subscription_id TEXT NOT NULL,
  event_timestamp TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK(event_type IN ('INVOICE_ISSUED','PAYMENT_SUCCEEDED','PAYMENT_FAILED','REFUND_ISSUED','CREDIT_APPLIED')),
  amount_inr NUMERIC NOT NULL CHECK(amount_inr >= 0),
  due_date TEXT,
  FOREIGN KEY(subscription_id) REFERENCES Subscription(subscription_id)
);

CREATE TABLE SupportCase (
  support_case_id TEXT PRIMARY KEY NOT NULL,
  customer_id TEXT NOT NULL,
  subscription_id TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  issue_category TEXT NOT NULL CHECK(issue_category IN ('BILLING','TECHNICAL','USAGE','ACCOUNT','CANCELLATION','OTHER')),
  status TEXT NOT NULL CHECK(status IN ('OPEN','IN_PROGRESS','RESOLVED','CLOSED')),
  FOREIGN KEY(customer_id) REFERENCES Customer(customer_id),
  FOREIGN KEY(subscription_id, customer_id) REFERENCES Subscription(subscription_id, customer_id),
  CHECK(resolved_at IS NULL OR resolved_at >= created_at),
  CHECK((status IN ('RESOLVED','CLOSED') AND resolved_at IS NOT NULL) OR status IN ('OPEN','IN_PROGRESS'))
);

CREATE TABLE Offer (
  offer_id TEXT PRIMARY KEY NOT NULL,
  offer_type TEXT NOT NULL CHECK(offer_type IN ('PERCENT_DISCOUNT','FIXED_CREDIT','FREE_PERIOD','LOYALTY_BONUS')),
  discount_pct NUMERIC CHECK(discount_pct IS NULL OR (discount_pct > 0 AND discount_pct <= 100)),
  credit_amount_inr NUMERIC CHECK(credit_amount_inr IS NULL OR credit_amount_inr >= 0),
  start_date TEXT NOT NULL CHECK(date(start_date) IS NOT NULL),
  end_date TEXT NOT NULL CHECK(date(end_date) IS NOT NULL),
  unit_cost_inr NUMERIC NOT NULL CHECK(unit_cost_inr >= 0),
  minimum_post_offer_margin_inr NUMERIC NOT NULL CHECK(minimum_post_offer_margin_inr >= 0),
  CHECK(end_date >= start_date),
  CHECK((offer_type='PERCENT_DISCOUNT' AND discount_pct IS NOT NULL AND credit_amount_inr IS NULL)
     OR (offer_type='FIXED_CREDIT' AND credit_amount_inr IS NOT NULL AND discount_pct IS NULL)
     OR (offer_type IN ('FREE_PERIOD','LOYALTY_BONUS') AND discount_pct IS NULL AND credit_amount_inr IS NULL))
);

-- Rule catalog is offer-independent. OfferRule supplies the intentional N:M bridge.
CREATE TABLE EligibilityRule (
  eligibility_rule_id TEXT PRIMARY KEY NOT NULL,
  rule_code TEXT NOT NULL,
  condition_json TEXT NOT NULL CHECK(json_valid(condition_json)),
  rule_version TEXT NOT NULL,
  UNIQUE(rule_code, rule_version)
);

CREATE TABLE OfferRule (
  offer_rule_id TEXT PRIMARY KEY NOT NULL,
  offer_id TEXT NOT NULL,
  eligibility_rule_id TEXT NOT NULL,
  effective_from TEXT NOT NULL CHECK(date(effective_from) IS NOT NULL),
  effective_to TEXT,
  is_mandatory INTEGER NOT NULL CHECK(is_mandatory IN (0,1)),
  priority INTEGER NOT NULL CHECK(priority > 0),
  FOREIGN KEY(offer_id) REFERENCES Offer(offer_id),
  FOREIGN KEY(eligibility_rule_id) REFERENCES EligibilityRule(eligibility_rule_id),
  CHECK(effective_to IS NULL OR effective_to >= effective_from),
  UNIQUE(offer_id, eligibility_rule_id, effective_from),
  UNIQUE(offer_rule_id, offer_id)
);

CREATE TABLE EligibilityEvaluation (
  eligibility_evaluation_id TEXT PRIMARY KEY NOT NULL,
  customer_id TEXT NOT NULL,
  offer_id TEXT NOT NULL,
  evaluated_at TEXT NOT NULL,
  risk_score NUMERIC NOT NULL CHECK(risk_score >= 0 AND risk_score <= 1),
  model_version TEXT NOT NULL,
  decision TEXT NOT NULL CHECK(decision IN ('ELIGIBLE','INELIGIBLE')),
  rule_set_version TEXT NOT NULL,
  expected_incremental_contribution_margin_inr NUMERIC NOT NULL,
  expected_offer_cost_inr NUMERIC NOT NULL CHECK(expected_offer_cost_inr >= 0),
  expected_campaign_cost_inr NUMERIC NOT NULL CHECK(expected_campaign_cost_inr >= 0),
  expected_net_value_inr NUMERIC NOT NULL,
  post_offer_margin_inr NUMERIC NOT NULL,
  FOREIGN KEY(customer_id) REFERENCES Customer(customer_id),
  FOREIGN KEY(offer_id) REFERENCES Offer(offer_id),
  UNIQUE(eligibility_evaluation_id, customer_id, offer_id),
  UNIQUE(eligibility_evaluation_id, offer_id),
  CHECK(abs(expected_net_value_inr - (expected_incremental_contribution_margin_inr - expected_offer_cost_inr - expected_campaign_cost_inr)) < 0.02)
);

CREATE TABLE EligibilityRuleResult (
  rule_result_id TEXT PRIMARY KEY NOT NULL,
  eligibility_evaluation_id TEXT NOT NULL,
  offer_id TEXT NOT NULL,
  offer_rule_id TEXT NOT NULL,
  passed INTEGER NOT NULL CHECK(passed IN (0,1)),
  reason_code TEXT NOT NULL,
  observed_value TEXT,
  threshold_value TEXT,
  FOREIGN KEY(eligibility_evaluation_id, offer_id) REFERENCES EligibilityEvaluation(eligibility_evaluation_id, offer_id),
  FOREIGN KEY(offer_rule_id, offer_id) REFERENCES OfferRule(offer_rule_id, offer_id),
  UNIQUE(eligibility_evaluation_id, offer_rule_id)
);

CREATE TABLE CampaignContact (
  campaign_contact_id TEXT PRIMARY KEY NOT NULL,
  customer_id TEXT NOT NULL,
  offer_id TEXT NOT NULL,
  eligibility_evaluation_id TEXT NOT NULL UNIQUE,
  experiment_id TEXT NOT NULL,
  assigned_group TEXT NOT NULL CHECK(assigned_group IN ('TREATMENT','CONTROL')),
  assigned_at TEXT NOT NULL,
  eligibility_decision TEXT NOT NULL CHECK(eligibility_decision IN ('ELIGIBLE','INELIGIBLE')),
  contact_status TEXT NOT NULL CHECK(contact_status IN ('NOT_ATTEMPTED','SENT','DELIVERED','FAILED','SUPPRESSED')),
  response_status TEXT NOT NULL CHECK(response_status IN ('UNKNOWN','NO_RESPONSE','ACCEPTED','DECLINED','REDEEMED')),
  risk_score NUMERIC NOT NULL CHECK(risk_score >= 0 AND risk_score <= 1),
  rule_set_version TEXT NOT NULL,
  is_injected_anomaly INTEGER NOT NULL DEFAULT 0 CHECK(is_injected_anomaly IN (0,1)),
  anomaly_id TEXT,
  FOREIGN KEY(customer_id) REFERENCES Customer(customer_id),
  FOREIGN KEY(offer_id) REFERENCES Offer(offer_id),
  FOREIGN KEY(eligibility_evaluation_id, customer_id, offer_id)
    REFERENCES EligibilityEvaluation(eligibility_evaluation_id, customer_id, offer_id),
  UNIQUE(customer_id, experiment_id),
  UNIQUE(campaign_contact_id, offer_id),
  UNIQUE(campaign_contact_id, customer_id),
  CHECK(eligibility_decision='ELIGIBLE' OR contact_status NOT IN ('SENT','DELIVERED') OR is_injected_anomaly=1),
  CHECK((is_injected_anomaly=0 AND anomaly_id IS NULL) OR (is_injected_anomaly=1 AND anomaly_id IS NOT NULL))
);

CREATE TABLE CampaignContactEvent (
  campaign_contact_event_id TEXT PRIMARY KEY NOT NULL,
  campaign_contact_id TEXT NOT NULL,
  event_timestamp TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK(event_type IN ('ASSIGNED','OFFER_SENT','OFFER_DELIVERED','OFFER_FAILED','OFFER_EXPOSED','OFFER_RESPONSE','OFFER_REDEEMED')),
  actual_offer_id TEXT,
  response_code TEXT,
  event_payload TEXT CHECK(event_payload IS NULL OR json_valid(event_payload) OR is_injected_anomaly=1),
  is_injected_anomaly INTEGER NOT NULL DEFAULT 0 CHECK(is_injected_anomaly IN (0,1)),
  anomaly_id TEXT,
  FOREIGN KEY(campaign_contact_id) REFERENCES CampaignContact(campaign_contact_id),
  FOREIGN KEY(actual_offer_id) REFERENCES Offer(offer_id),
  FOREIGN KEY(campaign_contact_id, actual_offer_id) REFERENCES CampaignContact(campaign_contact_id, offer_id),
  CHECK((event_type IN ('OFFER_SENT','OFFER_DELIVERED','OFFER_EXPOSED','OFFER_REDEEMED') AND actual_offer_id IS NOT NULL)
     OR event_type NOT IN ('OFFER_SENT','OFFER_DELIVERED','OFFER_EXPOSED','OFFER_REDEEMED')),
  CHECK((is_injected_anomaly=0 AND anomaly_id IS NULL) OR (is_injected_anomaly=1 AND anomaly_id IS NOT NULL))
);

CREATE TABLE SubscriptionEvent (
  subscription_event_id TEXT PRIMARY KEY NOT NULL,
  subscription_id TEXT NOT NULL,
  event_timestamp TEXT NOT NULL,
  effective_at TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK(event_type IN ('ACTIVATED','PAYMENT_PAST_DUE','PAYMENT_RECOVERED','CANCELLATION_REQUESTED','CANCELLATION_RESCINDED','TERMINATED','PLAN_CHANGED','REACTIVATED')),
  old_status TEXT CHECK(old_status IS NULL OR old_status IN ('ACTIVE','PAST_DUE','CANCELLATION_PENDING','TERMINATED')),
  new_status TEXT CHECK(new_status IS NULL OR new_status IN ('ACTIVE','PAST_DUE','CANCELLATION_PENDING','TERMINATED')),
  old_plan_code TEXT CHECK(old_plan_code IS NULL OR old_plan_code IN ('BASIC_MONTHLY','STANDARD_MONTHLY','PREMIUM_MONTHLY','ANNUAL')),
  new_plan_code TEXT CHECK(new_plan_code IS NULL OR new_plan_code IN ('BASIC_MONTHLY','STANDARD_MONTHLY','PREMIUM_MONTHLY','ANNUAL')),
  reason_code TEXT,
  FOREIGN KEY(subscription_id) REFERENCES Subscription(subscription_id),
  CHECK(event_type<>'PLAN_CHANGED' OR (old_plan_code IS NOT NULL AND new_plan_code IS NOT NULL AND old_plan_code<>new_plan_code))
);

-- Canonical annual outcome uses the exact required ID convention: CHURN-<customer_id>-2026.
CREATE TABLE ChurnOutcome (
  churn_outcome_id TEXT PRIMARY KEY NOT NULL,
  customer_id TEXT NOT NULL,
  outcome_year INTEGER NOT NULL CHECK(outcome_year=2026),
  label_status TEXT NOT NULL CHECK(label_status IN ('LABELED','NOT_AT_RISK','CENSORED','ANOMALOUS')),
  churn_label INTEGER CHECK(churn_label IS NULL OR churn_label IN (0,1)),
  churn_event_date TEXT,
  churn_type TEXT CHECK(churn_type IS NULL OR churn_type IN ('VOLUNTARY','INVOLUNTARY')),
  churn_subscription_id TEXT,
  FOREIGN KEY(customer_id) REFERENCES Customer(customer_id),
  FOREIGN KEY(churn_subscription_id, customer_id) REFERENCES Subscription(subscription_id, customer_id),
  UNIQUE(customer_id, outcome_year),
  CHECK(churn_outcome_id = 'CHURN-' || customer_id || '-2026'),
  CHECK(label_status='ANOMALOUS' OR (label_status IN ('NOT_AT_RISK','CENSORED') AND churn_label IS NULL) OR (label_status='LABELED' AND churn_label IN (0,1))),
  CHECK(label_status='ANOMALOUS' OR churn_label IS NULL OR churn_label=0 OR (churn_event_date IS NOT NULL AND churn_type IS NOT NULL AND churn_subscription_id IS NOT NULL)),
  CHECK(label_status='ANOMALOUS' OR churn_label IS NULL OR churn_label=1 OR (churn_event_date IS NULL AND churn_type IS NULL AND churn_subscription_id IS NULL))
);

-- Monthly prediction labels are a supporting modeling table/export, distinct from annual ChurnOutcome IDs.
CREATE TABLE MonthlyChurnLabel (
  monthly_label_id TEXT PRIMARY KEY NOT NULL,
  customer_id TEXT NOT NULL,
  prediction_date TEXT NOT NULL CHECK(date(prediction_date) IS NOT NULL),
  horizon_days INTEGER NOT NULL CHECK(horizon_days > 0),
  label_rule_version TEXT NOT NULL,
  label_status TEXT NOT NULL CHECK(label_status IN ('LABELED','CENSORED','ANOMALOUS')),
  churn_label INTEGER CHECK(churn_label IS NULL OR churn_label IN (0,1)),
  churn_event_date TEXT,
  churn_type TEXT CHECK(churn_type IS NULL OR churn_type IN ('VOLUNTARY','INVOLUNTARY')),
  churn_subscription_id TEXT,
  is_injected_anomaly INTEGER NOT NULL DEFAULT 0 CHECK(is_injected_anomaly IN (0,1)),
  anomaly_id TEXT,
  FOREIGN KEY(customer_id) REFERENCES Customer(customer_id),
  FOREIGN KEY(churn_subscription_id, customer_id) REFERENCES Subscription(subscription_id, customer_id),
  CHECK((is_injected_anomaly=0 AND anomaly_id IS NULL) OR (is_injected_anomaly=1 AND anomaly_id IS NOT NULL)),
  CHECK(label_status='ANOMALOUS' OR (label_status='CENSORED' AND churn_label IS NULL) OR (label_status='LABELED' AND churn_label IN (0,1))),
  CHECK(label_status='ANOMALOUS' OR churn_label IS NULL OR churn_label=0 OR (churn_event_date IS NOT NULL AND churn_type IS NOT NULL AND churn_event_date>prediction_date AND churn_event_date<=date(prediction_date,'+'||horizon_days||' days'))),
  CHECK(label_status='ANOMALOUS' OR churn_label IS NOT 0 OR (churn_event_date IS NULL AND churn_type IS NULL AND churn_subscription_id IS NULL))
);

CREATE TABLE RetentionOutcome (
  retention_outcome_id TEXT PRIMARY KEY NOT NULL,
  campaign_contact_id TEXT NOT NULL UNIQUE,
  customer_id TEXT NOT NULL,
  follow_up_start TEXT NOT NULL,
  follow_up_end TEXT NOT NULL,
  follow_up_complete INTEGER NOT NULL CHECK(follow_up_complete IN (0,1)),
  retained INTEGER CHECK(retained IS NULL OR retained IN (0,1)),
  retention_event_id TEXT,
  observed_contribution_margin_inr NUMERIC,
  actual_offer_cost_inr NUMERIC NOT NULL CHECK(actual_offer_cost_inr >= 0),
  campaign_cost_inr NUMERIC NOT NULL CHECK(campaign_cost_inr >= 0),
  attribution_status TEXT NOT NULL CHECK(attribution_status IN ('PRIMARY','DUPLICATE_CANDIDATE','UNATTRIBUTED','EXCLUDED')),
  is_injected_anomaly INTEGER NOT NULL DEFAULT 0 CHECK(is_injected_anomaly IN (0,1)),
  anomaly_id TEXT,
  FOREIGN KEY(campaign_contact_id, customer_id) REFERENCES CampaignContact(campaign_contact_id, customer_id),
  FOREIGN KEY(customer_id) REFERENCES Customer(customer_id),
  CHECK(follow_up_end >= follow_up_start),
  CHECK((follow_up_complete=1 AND retained IS NOT NULL) OR (follow_up_complete=0 AND retained IS NULL)),
  CHECK(observed_contribution_margin_inr IS NULL OR observed_contribution_margin_inr >= 0),
  CHECK((is_injected_anomaly=0 AND anomaly_id IS NULL) OR (is_injected_anomaly=1 AND anomaly_id IS NOT NULL))
);

-- Unique primary attribution applies to valid baseline rows; tagged anomaly rows are deliberately allowed through for detector testing.
CREATE UNIQUE INDEX ux_retention_primary_event_clean ON RetentionOutcome(retention_event_id)
WHERE attribution_status='PRIMARY' AND retention_event_id IS NOT NULL AND is_injected_anomaly=0;
CREATE INDEX ix_usage_subscription_date ON UsageSnapshot(subscription_id,snapshot_date);
CREATE INDEX ix_billing_subscription_time ON BillingEvent(subscription_id,event_timestamp);
CREATE INDEX ix_churn_customer_year ON ChurnOutcome(customer_id,outcome_year);
CREATE INDEX ix_monthly_label_customer_date ON MonthlyChurnLabel(customer_id,prediction_date);
CREATE INDEX ix_campaign_experiment_group ON CampaignContact(experiment_id,assigned_group);
CREATE INDEX ix_campaign_events_contact_time ON CampaignContactEvent(campaign_contact_id,event_timestamp);
