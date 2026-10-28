#!/usr/bin/env python3
"""Deterministic customer churn & retention generator v4; support timing does not depend on future churn outcome."""
import argparse, csv, copy, hashlib, json, random, shutil
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

SEED_DEFAULT = 20261022
HISTORY_START = date(2025, 1, 1)
HISTORY_MONTHS = 18                 # Jan 2025 through Jun 2026
LABEL_HORIZON_DAYS = 60
EVALUATION_DATE = date(2026, 9, 1)  # after the feature-label horizon ends
RETENTION_DAYS = 60
RETENTION_END = EVALUATION_DATE + timedelta(days=RETENTION_DAYS)
DATA_END = date(2027, 1, 31)
PREDICTION_DATES = [date(2025 + ((m) // 12), (m % 12) + 1, 1) for m in range(HISTORY_MONTHS)]
PLAN_PRICES = {"BASIC_MONTHLY":399.0, "STANDARD_MONTHLY":799.0, "PREMIUM_MONTHLY":1299.0, "ANNUAL":699.0}
PLAN_CODES = list(PLAN_PRICES)
REGIONS = ["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"]
SEGMENTS = ["VALUE", "STANDARD", "PREMIUM"]


def iso(d): return d.isoformat() if d else ""
def ts(d, hour=12): return datetime(d.year,d.month,d.day,hour,0,tzinfo=timezone.utc).isoformat().replace("+00:00","Z")
def month_end(d):
    return (date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1) - timedelta(days=1))
def checksum(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        for row in rows:
            output={}
            for field in fields:
                v=row.get(field,"")
                if isinstance(v,(dict,list)): v=json.dumps(v,sort_keys=True,separators=(",",":"))
                output[field]=v
            w.writerow(output)
def read_csv(path):
    with path.open(newline="",encoding="utf-8") as f: return list(csv.DictReader(f))
def dump_json(path,obj): path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n",encoding="utf-8")

# Master data and physical table definitions. Rows are written in stable order.
FIELDS = {
"Customer": ["customer_id","signup_date","region","customer_segment","seasonal_user_flag"],
"Subscription": ["subscription_id","customer_id","plan_code","start_date","end_date","status","monthly_price_inr"],
"UsageSnapshot": ["usage_snapshot_id","subscription_id","snapshot_date","sessions_30d","usage_minutes_30d","days_since_last_use"],
"BillingEvent": ["billing_event_id","subscription_id","event_timestamp","event_type","amount_inr","due_date"],
"SupportCase": ["support_case_id","customer_id","subscription_id","created_at","resolved_at","issue_category","status"],
"Offer": ["offer_id","offer_type","discount_pct","credit_amount_inr","start_date","end_date","unit_cost_inr","minimum_post_offer_margin_inr"],
"EligibilityRule": ["eligibility_rule_id","rule_code","condition_json","rule_version"],
"OfferRule": ["offer_rule_id","offer_id","eligibility_rule_id","effective_from","effective_to","is_mandatory","priority"],
"EligibilityEvaluation": ["eligibility_evaluation_id","customer_id","offer_id","evaluated_at","risk_score","model_version","decision","rule_set_version","expected_incremental_contribution_margin_inr","expected_offer_cost_inr","expected_campaign_cost_inr","expected_net_value_inr","post_offer_margin_inr"],
"EligibilityRuleResult": ["rule_result_id","eligibility_evaluation_id","offer_id","offer_rule_id","passed","reason_code","observed_value","threshold_value"],
"CampaignContact": ["campaign_contact_id","customer_id","offer_id","eligibility_evaluation_id","experiment_id","assigned_group","assigned_at","eligibility_decision","contact_status","response_status","risk_score","rule_set_version","is_injected_anomaly","anomaly_id"],
"CampaignContactEvent": ["campaign_contact_event_id","campaign_contact_id","event_timestamp","event_type","actual_offer_id","response_code","event_payload","is_injected_anomaly","anomaly_id"],
"SubscriptionEvent": ["subscription_event_id","subscription_id","event_timestamp","effective_at","event_type","old_status","new_status","old_plan_code","new_plan_code","reason_code"],
"ChurnOutcome": ["churn_outcome_id","customer_id","outcome_year","label_status","churn_label","churn_event_date","churn_type","churn_subscription_id"],
"MonthlyChurnLabel": ["monthly_label_id","customer_id","prediction_date","horizon_days","label_rule_version","label_status","churn_label","churn_event_date","churn_type","churn_subscription_id","is_injected_anomaly","anomaly_id"],
"RetentionOutcome": ["retention_outcome_id","campaign_contact_id","customer_id","follow_up_start","follow_up_end","follow_up_complete","retained","retention_event_id","observed_contribution_margin_inr","actual_offer_cost_inr","campaign_cost_inr","attribution_status","is_injected_anomaly","anomaly_id"],
}
EXTRA_FIELDS = {
"features.csv": ["customer_id","prediction_date","region","customer_segment","seasonal_user_flag","risk_score","sessions_30d","usage_minutes_30d","days_since_last_use","tenure_days","failed_payments_90d","support_case_count_18m"],
"ground_truth.csv": ["customer_id","prediction_date","horizon_days","label_status","churn_label","churn_event_date","churn_type"],
"retention_potential_outcomes.csv": ["customer_id","campaign_contact_id","experiment_id","assigned_group","delivered","retained_if_control","retained_if_treatment_if_delivered","observed_retained","unit_treatment_effect_if_delivered"],
}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--customers",type=int,default=20000)
    parser.add_argument("--seed",type=int,default=SEED_DEFAULT)
    parser.add_argument("--out",default="customer_churn_output")
    parser.add_argument("--anomalies",action="store_true",help="write a full anomaly-injected variant in addition to the clean baseline")
    args=parser.parse_args()
    if args.customers < 1: raise SystemExit("--customers must be positive")
    rng=random.Random(args.seed)
    out=Path(args.out)
    if out.exists(): shutil.rmtree(out)
    clean_dir=out/"clean_baseline"
    clean_dir.mkdir(parents=True)

    # Generate master catalog. Rules are global; OfferRule is the many-to-many bridge.
    offers=[]
    offer_definitions=[
      ("OFF-01","PERCENT_DISCOUNT",15,"",120,100),
      ("OFF-02","FIXED_CREDIT","",150,150,100),
      ("OFF-03","FREE_PERIOD","","",220,100),
      ("OFF-04","LOYALTY_BONUS","","",75,100),
    ]
    for oid,otype,disc,credit,cost,floor in offer_definitions:
        offers.append({"offer_id":oid,"offer_type":otype,"discount_pct":disc,"credit_amount_inr":credit,
                       "start_date":"2025-01-01","end_date":"2027-12-31","unit_cost_inr":cost,
                       "minimum_post_offer_margin_inr":floor})
    rule_catalog=[
      {"eligibility_rule_id":"ER-ACTIVE-V1","rule_code":"ACTIVE_AT_DECISION","condition_json":{"require_active_subscription":True},"rule_version":"V1"},
      {"eligibility_rule_id":"ER-RISK-V1","rule_code":"RISK_THRESHOLD","condition_json":{"minimum_risk_score":0.60},"rule_version":"V1"},
      {"eligibility_rule_id":"ER-OFFER-DATE-V1","rule_code":"OFFER_ACTIVE","condition_json":{"require_offer_active":True},"rule_version":"V1"},
      {"eligibility_rule_id":"ER-MARGIN-V1","rule_code":"MIN_POST_OFFER_MARGIN","condition_json":{"source_field":"Offer.minimum_post_offer_margin_inr"},"rule_version":"V1"},
    ]
    offer_rules=[]
    for oi,o in enumerate(offers,1):
        for priority,rule in enumerate(rule_catalog,1):
            offer_rules.append({"offer_rule_id":f"OR-{oi:02d}-{priority:02d}","offer_id":o["offer_id"],
                                "eligibility_rule_id":rule["eligibility_rule_id"],"effective_from":"2025-01-01",
                                "effective_to":"","is_mandatory":1,"priority":priority})

    # Customer profiles and baseline lifecycle. Outcome dates span the 18-month feature window and 2026 follow-up.
    customers=[]; profile={}; initial_subscription=[]; usage=[]; billing=[]; support=[]; sub_events=[]
    all_lifecycle_months=[date(2025+(m//12),(m%12)+1,1) for m in range(24)]  # Jan 2025–Dec 2026
    for i in range(1,args.customers+1):
        cid=f"CUS-{i:06d}"; sid=f"SUB-{i:06d}-01"
        signup=HISTORY_START-timedelta(days=rng.randint(100,900))
        region=rng.choice(REGIONS); segment=rng.choices(SEGMENTS,[0.28,0.54,0.18])[0]
        seasonal=1 if rng.random()<0.22 else 0
        initial_plan=rng.choices(PLAN_CODES,[0.28,0.42,0.20,0.10])[0]
        base_sessions=rng.uniform(6,40) * (1.25 if segment=="PREMIUM" else 1.0)
        latent_risk=rng.betavariate(2,5); payment_risk=rng.random(); support_prone=(rng.random()<0.22)
        contribution_margin_pct=rng.uniform(0.55,0.78)
        churn_date=None; churn_type=None; plan=initial_plan; plan_changes=[]; usage_by_month={}; current_price=PLAN_PRICES[plan]
        failed_dates=[]; support_date=None
        for m,pred in enumerate(all_lifecycle_months):
            active_month_end=month_end(pred)
            if churn_date and churn_date <= pred: break
            decline=max(0.0,(m-rng.randint(4,12))/24.0)*(0.15+latent_risk)
            seasonal_factor=1.0+(0.30 if seasonal and pred.month in (11,12,1,2) else 0.0)
            mean=max(0.3,base_sessions*(1-min(0.72,decline))*seasonal_factor)
            sessions=max(0,int(rng.gauss(mean,max(1.0,mean*0.25))))
            minutes=round(max(0,sessions*rng.uniform(6,24)),1)
            days_since=min(60,max(0,int(rng.expovariate(1/max(3,mean*1.4)))))
            usage_by_month[pred]=(sessions,minutes,days_since)
            usage_penalty=max(0,20-sessions)/20
            hazard=0.0018+0.010*latent_risk+0.008*usage_penalty+0.006*payment_risk+(0.003 if support_prone else 0)
            if seasonal and pred.month in (3,4): hazard+=0.001
            if rng.random()<min(0.12,hazard):
                churn_date=pred+timedelta(days=rng.randint(1,27))
                churn_type="INVOLUNTARY" if payment_risk>0.72 and rng.random()<0.55 else "VOLUNTARY"
                break
            # Plan changes are stored as explicit lifecycle events; the master row will use the final plan.
            if rng.random()<0.035:
                new_plan=rng.choice(PLAN_CODES)
                if new_plan!=plan:
                    plan_changes.append((active_month_end,plan,new_plan,PLAN_PRICES[plan],PLAN_PRICES[new_plan]))
                    plan=new_plan; current_price=PLAN_PRICES[plan]
        # Output behavior used by as-of features. Support creation is within history and may not follow churn.
        if support_prone:
            # Generate support timing independently of the future churn outcome.
            # Do not backdate a post-churn case to make it appear predictive.
            candidate_support_date = HISTORY_START + timedelta(days=rng.randint(5, 500))
            if churn_date is None or candidate_support_date < churn_date:
                support_date = candidate_support_date
            else:
                support_date = None
        profile[cid]={"signup":signup,"sid":sid,"initial_plan":initial_plan,"plan":plan,"price":current_price,
                      "region":region,"segment":segment,"seasonal":seasonal,"base_sessions":base_sessions,
                      "latent_risk":latent_risk,"payment_risk":payment_risk,"support_prone":support_prone,
                      "contribution_margin_pct":contribution_margin_pct,"baseline_churn_date":churn_date,
                      "churn_date":churn_date,"churn_type":churn_type,"plan_changes":plan_changes,
                      "usage":usage_by_month,"failed_dates":failed_dates,"support_date":support_date}
        customers.append({"customer_id":cid,"signup_date":iso(signup),"region":region,"customer_segment":segment,"seasonal_user_flag":seasonal})

    # Build monthly observed usage history and synthetic billing/payment/support events using baseline lifecycle.
    # Future campaign effects do not affect the historical feature window.
    for i in range(1,args.customers+1):
        cid=f"CUS-{i:06d}"; p=profile[cid]; sid=p["sid"]
        bidx=0; dt=max(p["signup"],HISTORY_START)
        billing_end=date(2027,1,1)
        while dt<=billing_end:
            bidx+=1; due=dt+timedelta(days=7)
            price=PLAN_PRICES[p["initial_plan"]]
            for changed,oldplan,newplan,oldprice,newprice in p["plan_changes"]:
                if changed<=dt: price=newprice
            billing.append({"billing_event_id":f"BE-{i:06d}-{bidx:03d}","subscription_id":sid,"event_timestamp":ts(dt),"event_type":"INVOICE_ISSUED","amount_inr":round(price,2),"due_date":iso(due)})
            failed=rng.random()<(0.035+0.14*p["payment_risk"])
            if failed:
                fail_dt=dt+timedelta(days=1); p["failed_dates"].append(fail_dt)
                billing.append({"billing_event_id":f"BE-{i:06d}-{bidx:03d}-F","subscription_id":sid,"event_timestamp":ts(fail_dt),"event_type":"PAYMENT_FAILED","amount_inr":round(price,2),"due_date":iso(due)})
                if rng.random()<0.62:
                    billing.append({"billing_event_id":f"BE-{i:06d}-{bidx:03d}-R","subscription_id":sid,"event_timestamp":ts(dt+timedelta(days=5)),"event_type":"PAYMENT_SUCCEEDED","amount_inr":round(price,2),"due_date":iso(due)})
            else:
                billing.append({"billing_event_id":f"BE-{i:06d}-{bidx:03d}-P","subscription_id":sid,"event_timestamp":ts(dt+timedelta(days=2)),"event_type":"PAYMENT_SUCCEEDED","amount_inr":round(price,2),"due_date":iso(due)})
            dt+=timedelta(days=30)
        if p["support_date"]:
            created=p["support_date"]; resolved=created+timedelta(days=rng.randint(1,8))
            support.append({"support_case_id":f"SC-{i:06d}-01","customer_id":cid,"subscription_id":sid,
                            "created_at":ts(created),"resolved_at":ts(resolved),"issue_category":rng.choice(["BILLING","TECHNICAL","USAGE","ACCOUNT"]),"status":"RESOLVED"})
        for pred,vals in p["usage"].items():
            if pred not in PREDICTION_DATES: continue
            if p["baseline_churn_date"] and pred>=p["baseline_churn_date"]: continue
            sess,mins,days=vals
            usage.append({"usage_snapshot_id":f"US-{i:06d}-{pred:%Y%m}","subscription_id":sid,"snapshot_date":iso(pred),
                          "sessions_30d":sess,"usage_minutes_30d":mins,"days_since_last_use":days})

    # As-of feature matrix and monthly forward labels. Features never include future events/targets.
    features=[]; monthly_labels=[]; ground_truth=[]; feature_by_cust={}; score_lookup={}
    customer_lookup={r["customer_id"]:r for r in customers}
    for i in range(1,args.customers+1):
        cid=f"CUS-{i:06d}"; p=profile[cid]
        for pred in PREDICTION_DATES:
            if pred<p["signup"]+timedelta(days=90): continue
            if p["baseline_churn_date"] and p["baseline_churn_date"]<=pred: continue
            vals=p["usage"].get(pred)
            if vals is None: continue
            sessions,minutes,days_since=vals
            fail_count=sum(1 for d in p["failed_dates"] if pred-timedelta(days=90)<d<=pred)
            support_count=int(bool(p["support_date"] and p["support_date"]<=pred))
            score=min(0.95,max(0.01,0.15+max(0,30-sessions)*0.015+min(fail_count,3)*0.07+support_count*0.10+min(days_since,45)*0.009+(0.035 if p["seasonal"] and pred.month in (3,4) else 0)))
            f={"customer_id":cid,"prediction_date":iso(pred),"region":p["region"],"customer_segment":p["segment"],"seasonal_user_flag":p["seasonal"],
               "risk_score":round(score,4),"sessions_30d":sessions,"usage_minutes_30d":minutes,"days_since_last_use":days_since,
               "tenure_days":(pred-p["signup"]).days,"failed_payments_90d":fail_count,"support_case_count_18m":support_count}
            features.append(f); feature_by_cust.setdefault(cid,[]).append(f); score_lookup[(cid,iso(pred))]=score
            cdate=p["baseline_churn_date"]
            complete=(pred+timedelta(days=LABEL_HORIZON_DAYS)<=RETENTION_END)
            positive=bool(cdate and pred<cdate<=pred+timedelta(days=LABEL_HORIZON_DAYS))
            status="LABELED" if complete or positive else "CENSORED"
            label=(1 if positive else 0) if complete else (1 if positive else "")
            label_row={"monthly_label_id":f"MONTHLY-{cid}-{pred:%Y%m}-H60-R1","customer_id":cid,"prediction_date":iso(pred),
                       "horizon_days":LABEL_HORIZON_DAYS,"label_rule_version":"R1","label_status":status,"churn_label":label,
                       "churn_event_date":iso(cdate) if positive else "","churn_type":p["churn_type"] if positive else "",
                       "churn_subscription_id":p["sid"] if positive else "","is_injected_anomaly":0,"anomaly_id":""}
            monthly_labels.append(label_row)
            ground_truth.append({"customer_id":cid,"prediction_date":iso(pred),"horizon_days":LABEL_HORIZON_DAYS,
                                 "label_status":status,"churn_label":label,"churn_event_date":iso(cdate) if positive else "",
                                 "churn_type":p["churn_type"] if positive else ""})

    # Create evaluations for all active customers with a feature row available at evaluation time.
    latest_feature={}
    for row in features:
        if row["prediction_date"]<=iso(EVALUATION_DATE): latest_feature[row["customer_id"]]=row
    evals=[]; rule_results=[]; contacts=[]; contact_events=[]; retention_outcomes=[]; potential_outcomes=[]
    evaluation_by_customer={}; contact_by_customer={}
    offer_by_id={o["offer_id"]:o for o in offers}; rule_by_code={r["rule_code"]:r for r in rule_catalog}
    offer_rule_by_offer={o["offer_id"]:[x for x in offer_rules if x["offer_id"]==o["offer_id"]] for o in offers}
    cust_rows_by_id={x["customer_id"]:x for x in customers}
    for i in range(1,args.customers+1):
        cid=f"CUS-{i:06d}"; p=profile[cid]
        # Current state as of evaluation date. A later churn event does not make a customer inactive today.
        if p["churn_date"] and p["churn_date"]<=EVALUATION_DATE: continue
        feat=latest_feature.get(cid)
        if not feat: continue
        risk=float(feat["risk_score"]); oid=rng.choice([o["offer_id"] for o in offers]); offer=offer_by_id[oid]
        # Evaluate plan/price from plan history available at decision time, never from later plan changes.
        asof_plan=p["initial_plan"]
        for changed,oldplan,newplan,oldprice,newprice in p["plan_changes"]:
            if changed<=EVALUATION_DATE: asof_plan=newplan
        price=float(PLAN_PRICES[asof_plan]); base_margin=round(price*p["contribution_margin_pct"],2)
        if offer["offer_type"]=="PERCENT_DISCOUNT": face_value=round(price*float(offer["discount_pct"])/100,2)
        elif offer["offer_type"]=="FIXED_CREDIT": face_value=min(float(offer["credit_amount_inr"]),price)
        elif offer["offer_type"]=="FREE_PERIOD": face_value=price
        else: face_value=0.0
        # Conservative estimate: worst-case benefit cost plus per-unit fulfillment/servicing cost.
        offer_cost=round(face_value+float(offer["unit_cost_inr"]),2)
        post_margin=round(base_margin-offer_cost,2); campaign_cost=15.0
        # Expected incremental contribution is an explicit synthetic assumption, separate from observed outcome.
        expected_incremental=round(base_margin*0.10*2*0.92,2)
        expected_net=round(expected_incremental-offer_cost-campaign_cost,2)
        decision_id=f"EV-{i:06d}-202609"; decision_results=[]
        rules=offer_rule_by_offer[oid]
        rule_checks={
          "ACTIVE_AT_DECISION":(True,"ACTIVE",1),
          "RISK_THRESHOLD":(risk>=0.60,"RISK_THRESHOLD",0.60),
          "OFFER_ACTIVE":(date.fromisoformat(offer["start_date"])<=EVALUATION_DATE<=date.fromisoformat(offer["end_date"]),"OFFER_ACTIVE",iso(EVALUATION_DATE)),
          "MIN_POST_OFFER_MARGIN":(post_margin>=float(offer["minimum_post_offer_margin_inr"]),"MIN_POST_OFFER_MARGIN",offer["minimum_post_offer_margin_inr"]),
        }
        for orow in rules:
            rule=next(r for r in rule_catalog if r["eligibility_rule_id"]==orow["eligibility_rule_id"])
            passed,reason,threshold=rule_checks[rule["rule_code"]]
            observed=post_margin if rule["rule_code"]=="MIN_POST_OFFER_MARGIN" else (risk if rule["rule_code"]=="RISK_THRESHOLD" else (1 if rule["rule_code"]=="ACTIVE_AT_DECISION" else iso(EVALUATION_DATE)))
            decision_results.append((orow,rule,passed,reason,observed,threshold))
        eligible=all(x[2] for x in decision_results)
        decision="ELIGIBLE" if eligible else "INELIGIBLE"
        evaluation={"eligibility_evaluation_id":decision_id,"customer_id":cid,"offer_id":oid,"evaluated_at":ts(EVALUATION_DATE),
                    "risk_score":risk,"model_version":"synthetic-risk-v2","decision":decision,"rule_set_version":"RULESET-V1",
                    "expected_incremental_contribution_margin_inr":expected_incremental,"expected_offer_cost_inr":offer_cost,
                    "expected_campaign_cost_inr":campaign_cost,"expected_net_value_inr":expected_net,"post_offer_margin_inr":post_margin}
        evals.append(evaluation); evaluation_by_customer[cid]=evaluation
        for n,(orow,rule,passed,reason,observed,threshold) in enumerate(decision_results,1):
            rule_results.append({"rule_result_id":f"RR-{i:06d}-{n:02d}","eligibility_evaluation_id":decision_id,"offer_id":oid,"offer_rule_id":orow["offer_rule_id"],
                                 "passed":int(passed),"reason_code":"PASS" if passed else f"FAIL_{rule['rule_code']}",
                                 "observed_value":observed,"threshold_value":threshold})
        if not eligible: continue
        # Experimental candidate pool: one random assignment per customer/experiment.
        group="TREATMENT" if rng.random()<0.5 else "CONTROL"
        ccid=f"CC-{len(contacts)+1:07d}"; contact_status="NOT_ATTEMPTED"; response="UNKNOWN"; delivered=0
        contacts.append({"campaign_contact_id":ccid,"customer_id":cid,"offer_id":oid,"eligibility_evaluation_id":decision_id,
                         "experiment_id":"EXP-2026-RETENTION","assigned_group":group,"assigned_at":ts(EVALUATION_DATE),
                         "eligibility_decision":"ELIGIBLE","contact_status":contact_status,"response_status":response,
                         "risk_score":risk,"rule_set_version":"RULESET-V1","is_injected_anomaly":0,"anomaly_id":""})
        contact_by_customer[cid]=contacts[-1]
        contact_events.append({"campaign_contact_event_id":f"CCE-{len(contacts):07d}-A","campaign_contact_id":ccid,"event_timestamp":ts(EVALUATION_DATE),
                               "event_type":"ASSIGNED","actual_offer_id":"","response_code":"","event_payload":{"seed":args.seed,"group":group},
                               "is_injected_anomaly":0,"anomaly_id":""})
        if group=="TREATMENT":
            delivered=1 if rng.random()<0.92 else 0
            contact_status="DELIVERED" if delivered else "FAILED"
            response=rng.choices(["NO_RESPONSE","ACCEPTED","DECLINED","REDEEMED"],[0.58,0.15,0.18,0.09])[0] if delivered else "UNKNOWN"
            contacts[-1]["contact_status"]=contact_status; contacts[-1]["response_status"]=response
            if delivered:
                contact_events.append({"campaign_contact_event_id":f"CCE-{len(contacts):07d}-S","campaign_contact_id":ccid,"event_timestamp":ts(EVALUATION_DATE+timedelta(days=1)),
                                       "event_type":"OFFER_SENT","actual_offer_id":oid,"response_code":"","event_payload":"","is_injected_anomaly":0,"anomaly_id":""})
                contact_events.append({"campaign_contact_event_id":f"CCE-{len(contacts):07d}-D","campaign_contact_id":ccid,"event_timestamp":ts(EVALUATION_DATE+timedelta(days=1)),
                                       "event_type":"OFFER_DELIVERED","actual_offer_id":oid,"response_code":"","event_payload":"","is_injected_anomaly":0,"anomaly_id":""})
                if response in ("ACCEPTED","DECLINED","REDEEMED"):
                    contact_events.append({"campaign_contact_event_id":f"CCE-{len(contacts):07d}-R","campaign_contact_id":ccid,"event_timestamp":ts(EVALUATION_DATE+timedelta(days=2)),
                                           "event_type":"OFFER_RESPONSE","actual_offer_id":"","response_code":response,"event_payload":"","is_injected_anomaly":0,"anomaly_id":""})
                if response=="REDEEMED":
                    contact_events.append({"campaign_contact_event_id":f"CCE-{len(contacts):07d}-X","campaign_contact_id":ccid,"event_timestamp":ts(EVALUATION_DATE+timedelta(days=3)),
                                           "event_type":"OFFER_REDEEMED","actual_offer_id":oid,"response_code":"REDEEMED","event_payload":"","is_injected_anomaly":0,"anomaly_id":""})

        # Create a follow-up churn hazard for high-risk customers who were active on assignment date.
        # Treatment effects are a deliberately specified synthetic rescue mechanism, not real-world evidence.
        baseline_churn=p["baseline_churn_date"]
        if not baseline_churn or baseline_churn>RETENTION_END:
            rescue_hazard=min(0.18,max(0.03,0.06+max(0,risk-0.60)*0.25))
            if rng.random()<rescue_hazard:
                baseline_churn=EVALUATION_DATE+timedelta(days=rng.randint(1,RETENTION_DAYS))
                p["churn_type"]="VOLUNTARY" if rng.random()<0.7 else "INVOLUNTARY"
        base_retained=not (baseline_churn and EVALUATION_DATE<baseline_churn<=RETENTION_END)
        rescued=0
        treatment_retained=base_retained
        if not base_retained:
            rescued=1 if rng.random()<0.40 else 0
            treatment_retained=bool(rescued)
        observed=bool(treatment_retained if group=="TREATMENT" and delivered else base_retained)
        if group=="TREATMENT" and delivered and rescued:
            # Shift churn beyond the 2026 annual outcome window; preserve it as an event, not a deletion.
            p["churn_date"]=DATA_END
            p["churn_type"]="VOLUNTARY"
        else:
            p["churn_date"]=baseline_churn
        # Retention event represents one observed retained customer in the experiment window.
        ret_event=f"RET-EVT-{cid}-EXP2026" if observed else ""
        # Outcome margin is observed value, not an individual causal incremental value.
        obs_margin=round(base_margin*2,2) if observed else 0.0
        actual_cost=(float(offer["unit_cost_inr"]) if group=="TREATMENT" and delivered else 0.0) + (face_value if group=="TREATMENT" and delivered and response=="REDEEMED" else 0.0)
        retention_outcomes.append({"retention_outcome_id":f"RET-{len(contacts):07d}","campaign_contact_id":ccid,"customer_id":cid,
                                   "follow_up_start":iso(EVALUATION_DATE),"follow_up_end":iso(RETENTION_END),"follow_up_complete":1,"retained":int(observed),
                                   "retention_event_id":ret_event,"observed_contribution_margin_inr":obs_margin,"actual_offer_cost_inr":actual_cost,
                                   "campaign_cost_inr":campaign_cost if group=="TREATMENT" else 0.0,
                                   "attribution_status":"PRIMARY" if observed else "UNATTRIBUTED","is_injected_anomaly":0,"anomaly_id":""})
        potential_outcomes.append({"customer_id":cid,"campaign_contact_id":ccid,"experiment_id":"EXP-2026-RETENTION","assigned_group":group,
                                   "delivered":delivered,"retained_if_control":int(base_retained),"retained_if_treatment_if_delivered":int(treatment_retained),
                                   "observed_retained":int(observed),"unit_treatment_effect_if_delivered":int(treatment_retained)-int(base_retained)})

    # Retain only billing events occurring before the final effective termination date.
    # The precomputed schedule is used for as-of feature counts, so feature inputs and billing events agree.
    final_billing=[]
    for ev in billing:
        cid=ev["billing_event_id"].split("-")[1]
        final_date=profile.get(f"CUS-{int(cid):06d}",{}).get("churn_date")
        event_day=ev["event_timestamp"][:10]
        if final_date is None or event_day<iso(final_date): final_billing.append(ev)
    billing=final_billing

    # Final normalized subscription and event histories after treatment rescue has been applied.
    subscriptions=[]; subscription_events=[]
    for i in range(1,args.customers+1):
        cid=f"CUS-{i:06d}"; p=profile[cid]; sid=p["sid"]; final_date=p.get("churn_date")
        ended=bool(final_date and final_date<=DATA_END)
        subscriptions.append({"subscription_id":sid,"customer_id":cid,"plan_code":p["plan"],"start_date":iso(p["signup"]),
                              "end_date":iso(final_date) if ended else "","status":"TERMINATED" if ended else "ACTIVE",
                              "monthly_price_inr":p["price"]})
        subscription_events.append({"subscription_event_id":f"SE-{i:06d}-001","subscription_id":sid,"event_timestamp":ts(p["signup"]),
                                     "effective_at":ts(p["signup"]),"event_type":"ACTIVATED","old_status":"","new_status":"ACTIVE",
                                     "old_plan_code":"","new_plan_code":p["initial_plan"],"reason_code":"SIGNUP"})
        seq=2
        for changed,oldplan,newplan,oldprice,newprice in p["plan_changes"]:
            if final_date and changed>=final_date: continue
            subscription_events.append({"subscription_event_id":f"SE-{i:06d}-{seq:03d}","subscription_id":sid,"event_timestamp":ts(changed),
                                         "effective_at":ts(changed),"event_type":"PLAN_CHANGED","old_status":"ACTIVE","new_status":"ACTIVE",
                                         "old_plan_code":oldplan,"new_plan_code":newplan,"reason_code":f"PRICE_{oldprice}_TO_{newprice}"})
            seq+=1
        if final_date:
            subscription_events.append({"subscription_event_id":f"SE-{i:06d}-{seq:03d}","subscription_id":sid,"event_timestamp":ts(final_date),
                                         "effective_at":ts(final_date),"event_type":"TERMINATED","old_status":"ACTIVE","new_status":"TERMINATED",
                                         "old_plan_code":p["plan"],"new_plan_code":p["plan"],"reason_code":"PAYMENT_DELINQUENCY" if p["churn_type"]=="INVOLUNTARY" else "CUSTOMER_CANCELLATION"})

    # Annual churn outcomes use required ID convention. Monthly prediction labels remain separate.
    annual_outcomes=[]
    for i in range(1,args.customers+1):
        cid=f"CUS-{i:06d}"; p=profile[cid]; cdate=p.get("churn_date")
        if cdate and cdate<date(2026,1,1):
            status="NOT_AT_RISK"; label=""
        elif cdate and cdate.year==2026:
            status="LABELED"; label=1
        else:
            status="LABELED"; label=0
        annual_outcomes.append({"churn_outcome_id":f"CHURN-{cid}-2026","customer_id":cid,"outcome_year":2026,"label_status":status,
                               "churn_label":label,"churn_event_date":iso(cdate) if cdate and cdate.year==2026 else "",
                               "churn_type":p["churn_type"] if cdate and cdate.year==2026 else "",
                               "churn_subscription_id":p["sid"] if cdate and cdate.year==2026 else ""})

    # Assemble physical tables and export in stable field/row order.
    tables={
      "Customer":customers,"Subscription":subscriptions,"UsageSnapshot":usage,"BillingEvent":billing,"SupportCase":support,
      "Offer":offers,"EligibilityRule":rule_catalog,"OfferRule":offer_rules,"EligibilityEvaluation":evals,
      "EligibilityRuleResult":rule_results,"CampaignContact":contacts,"CampaignContactEvent":contact_events,
      "SubscriptionEvent":subscription_events,"ChurnOutcome":annual_outcomes,"MonthlyChurnLabel":monthly_labels,"RetentionOutcome":retention_outcomes,
    }
    for name,rows in tables.items():
        write_csv(clean_dir/f"{name}.csv",rows,FIELDS[name])
    for name,rows in [("features.csv",features),("ground_truth.csv",ground_truth),("retention_potential_outcomes.csv",potential_outcomes)]:
        write_csv(clean_dir/name,rows,EXTRA_FIELDS[name])

    # Create the anomaly-inclusive variant as full datasets with inline, labelled rows—not JSON-only test cases.
    injected_dir=out/"anomaly_injected"
    shutil.copytree(clean_dir,injected_dir)
    # Only four impacted tables are rewritten; large unchanged tables are copied byte-for-byte.
    anomaly_rows={
      "MonthlyChurnLabel":copy.deepcopy(monthly_labels),
      "CampaignContact":copy.deepcopy(contacts),
      "CampaignContactEvent":copy.deepcopy(contact_events),
      "RetentionOutcome":copy.deepcopy(retention_outcomes),
    }
    # ANOM-001: positive label whose churn event predates prediction; tag and label the deliberately bad row.
    base_label=next(r for r in anomaly_rows["MonthlyChurnLabel"] if r["label_status"]=="LABELED" and r["churn_label"]==0)
    pred=date.fromisoformat(base_label["prediction_date"])
    bad=copy.deepcopy(base_label); bad.update({"monthly_label_id":"ANOM-001-MONTHLY-LABEL","prediction_date":iso(pred+timedelta(days=2)),
        "label_status":"ANOMALOUS","churn_label":1,"churn_event_date":iso(pred-timedelta(days=5)),"churn_type":"VOLUNTARY",
        "churn_subscription_id":bad["churn_subscription_id"] or profile[bad["customer_id"]]["sid"],"is_injected_anomaly":1,"anomaly_id":"ANOM-001"})
    anomaly_rows["MonthlyChurnLabel"].append(bad)
    # ANOM-002: a sent offer against an ineligible evaluation. Make a tagged contact and event.
    ineligible=next(e for e in evals if e["decision"]=="INELIGIBLE" and not any(c["customer_id"]==e["customer_id"] for c in contacts))
    ccid="ANOM-002-CAMPAIGN-CONTACT"; oid=ineligible["offer_id"]
    anomaly_rows["CampaignContact"].append({"campaign_contact_id":ccid,"customer_id":ineligible["customer_id"],"offer_id":oid,
        "eligibility_evaluation_id":ineligible["eligibility_evaluation_id"],"experiment_id":"EXP-ANOM-002","assigned_group":"TREATMENT",
        "assigned_at":ineligible["evaluated_at"],"eligibility_decision":"INELIGIBLE","contact_status":"SENT","response_status":"UNKNOWN",
        "risk_score":ineligible["risk_score"],"rule_set_version":ineligible["rule_set_version"],"is_injected_anomaly":1,"anomaly_id":"ANOM-002"})
    anomaly_rows["CampaignContactEvent"].append({"campaign_contact_event_id":"ANOM-002-SENT-EVENT","campaign_contact_id":ccid,
        "event_timestamp":ineligible["evaluated_at"],"event_type":"OFFER_SENT","actual_offer_id":oid,"response_code":"","event_payload":"injected invalid send",
        "is_injected_anomaly":1,"anomaly_id":"ANOM-002"})
    # ANOM-003: add an actual experimental-offer exposure event to an assigned control.
    control=next(c for c in contacts if c["assigned_group"]=="CONTROL")
    anomaly_rows["CampaignContactEvent"].append({"campaign_contact_event_id":"ANOM-003-CONTROL-EXPOSURE","campaign_contact_id":control["campaign_contact_id"],
        "event_timestamp":ts(EVALUATION_DATE+timedelta(days=2)),"event_type":"OFFER_EXPOSED","actual_offer_id":control["offer_id"],
        "response_code":"","event_payload":"injected control contamination","is_injected_anomaly":1,"anomaly_id":"ANOM-003"})
    # ANOM-004: duplicate a PRIMARY retention event attribution; flagged rows bypass the clean-only unique index.
    primaries=[r for r in anomaly_rows["RetentionOutcome"] if r["attribution_status"]=="PRIMARY" and r["retention_event_id"]]
    if len(primaries)<2: raise RuntimeError("Need at least two primary retention events to build duplicate attribution anomaly")
    dup=next(r for r in primaries[1:] if r["campaign_contact_id"]!=primaries[0]["campaign_contact_id"])
    dup.update({"retention_event_id":primaries[0]["retention_event_id"],"attribution_status":"PRIMARY","is_injected_anomaly":1,"anomaly_id":"ANOM-004"})
    for name,rows in anomaly_rows.items(): write_csv(injected_dir/f"{name}.csv",rows,FIELDS[name])

    # Source manifests separately document the exact files and row counts actually present in each variant.
    def manifest_for(directory,rows_by_name,injected=False):
        csv_paths=sorted(directory.glob("*.csv"))
        row_counts={name:len(rows) for name,rows in rows_by_name.items()}
        if injected:
            row_counts["MonthlyChurnLabel"]+=1
            row_counts["CampaignContact"]+=1
            row_counts["CampaignContactEvent"]+=2
        extra_counts={"features.csv":len(features),"ground_truth.csv":len(ground_truth),"retention_potential_outcomes.csv":len(potential_outcomes)}
        return {"project":"Customer Churn & Retention","generator_version":"2.0.0","seed":args.seed,
                "customer_count":args.customers,"feature_history_start":iso(HISTORY_START),"feature_history_months":HISTORY_MONTHS,
                "feature_prediction_dates":[iso(x) for x in PREDICTION_DATES],"monthly_label_horizon_days":LABEL_HORIZON_DAYS,
                "experiment_date":iso(EVALUATION_DATE),"retention_followup_end":iso(RETENTION_END),"annual_churn_outcome_year":2026,
                "currency":"INR","row_counts":row_counts,"extra_row_counts":extra_counts,
                "checksums":{p.name:checksum(p) for p in csv_paths}}
    dump_json(clean_dir/"source_manifest.json",manifest_for(clean_dir,tables))
    dump_json(injected_dir/"source_manifest.json",manifest_for(injected_dir,tables,injected=True))
    dump_json(out/"config.json",{"seed":args.seed,"customer_count":args.customers,"feature_history_months":HISTORY_MONTHS,
        "prediction_horizon_days":LABEL_HORIZON_DAYS,"experiment_date":iso(EVALUATION_DATE),"retention_followup_days":RETENTION_DAYS,
        "annual_churn_outcome_year":2026,"treatment_control_ratio":[0.5,0.5],"expected_delivery_rate":0.92,
        "synthetic_rescue_probability_when_at_risk_and_delivered":0.40,"target_churn_rate_range":[0.05,0.20],"currency":"INR"})
    # Report the observed intention-to-treat (ITT) lift and the generator's known expected effect.
    contacts_by_id={c["campaign_contact_id"]:c for c in contacts}
    observed_by_group={"TREATMENT":[],"CONTROL":[]}
    for ro in retention_outcomes:
        cc=contacts_by_id[ro["campaign_contact_id"]]
        if ro["follow_up_complete"]==1: observed_by_group[cc["assigned_group"]].append(int(ro["retained"]))
    group_sizes={g:len(v) for g,v in observed_by_group.items()}
    group_rates={g:(sum(v)/len(v) if v else 0.0) for g,v in observed_by_group.items()}
    treatment_assigned=[c for c in contacts if c["assigned_group"]=="TREATMENT"]
    delivery_rate=sum(1 for c in treatment_assigned if c["contact_status"]=="DELIVERED")/max(1,len(treatment_assigned))
    mean_unit_effect=sum(int(x["unit_treatment_effect_if_delivered"]) for x in potential_outcomes)/max(1,len(potential_outcomes))
    observed_lift=group_rates["TREATMENT"]-group_rates["CONTROL"]
    experiment_summary={"experiment_id":"EXP-2026-RETENTION","analysis":"intention-to-treat",
        "eligible_randomized_contacts":len(contacts),"group_sizes":group_sizes,
        "retention_rates":{k:round(v,6) for k,v in group_rates.items()},
        "observed_itt_retention_lift":round(observed_lift,6),"observed_itt_lift_percentage_points":round(observed_lift*100,3),
        "mean_potential_outcome_effect_if_delivered":round(mean_unit_effect,6),
        "treatment_delivery_rate":round(delivery_rate,6),
        "expected_itt_lift_at_observed_delivery_rate":round(mean_unit_effect*delivery_rate,6),
        "effect_is_synthetic_and_not_real_world_causal_evidence":True}
    dump_json(out/"experiment_summary.json",experiment_summary)
    result={"out":str(out),"seed":args.seed,"customers":args.customers,
            "clean_row_counts":{k:len(v) for k,v in tables.items()},
            "features":len(features),"monthly_labels":len(monthly_labels),"contacts":len(contacts),
            "customers_churned_in_18_month_feature_window":sum(1 for p in profile.values() if p["churn_date"] and HISTORY_START<=p["churn_date"]<=month_end(PREDICTION_DATES[-1])),
            "customers_churned_in_2026":sum(1 for p in profile.values() if p["churn_date"] and p["churn_date"].year==2026),
            "observed_itt_lift":round(observed_lift,6),"expected_itt_lift":round(mean_unit_effect*delivery_rate,6),
            "anomaly_variant_rows":{"ANOM-001":1,"ANOM-002":1,"ANOM-003":1,"ANOM-004":1}}
    dump_json(out/"generation_summary.json",result)
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
