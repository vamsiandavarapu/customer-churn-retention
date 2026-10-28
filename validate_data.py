#!/usr/bin/env python3
"""Cross-table validation for clean baseline or anomaly-injected CSV dataset."""
import argparse,csv,json
from pathlib import Path
from collections import Counter,defaultdict
from datetime import date,timedelta

def read_csv(path):
    with path.open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))
def duplicates(rows,key):
    c=Counter(r.get(key,'') for r in rows)
    return [v for v,n in c.items() if not v or n>1]
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data',required=True)
    ap.add_argument('--expected-customers',type=int,default=20000)
    ap.add_argument('--variant',choices=['clean','anomaly'],default='clean')
    ap.add_argument('--require-target-rate',action='store_true')
    args=ap.parse_args(); d=Path(args.data)
    tables=['Customer','Subscription','UsageSnapshot','BillingEvent','SupportCase','Offer','EligibilityRule','OfferRule',
            'EligibilityEvaluation','EligibilityRuleResult','CampaignContact','CampaignContactEvent','SubscriptionEvent',
            'ChurnOutcome','MonthlyChurnLabel','RetentionOutcome']
    data={t:read_csv(d/f'{t}.csv') for t in tables}; issues=[]
    def check(ok,msg):
        if not ok: issues.append(msg)
    pk={'Customer':'customer_id','Subscription':'subscription_id','UsageSnapshot':'usage_snapshot_id','BillingEvent':'billing_event_id',
        'SupportCase':'support_case_id','Offer':'offer_id','EligibilityRule':'eligibility_rule_id','OfferRule':'offer_rule_id',
        'EligibilityEvaluation':'eligibility_evaluation_id','EligibilityRuleResult':'rule_result_id','CampaignContact':'campaign_contact_id',
        'CampaignContactEvent':'campaign_contact_event_id','SubscriptionEvent':'subscription_event_id','ChurnOutcome':'churn_outcome_id',
        'MonthlyChurnLabel':'monthly_label_id','RetentionOutcome':'retention_outcome_id'}
    for t,k in pk.items(): check(not duplicates(data[t],k),f'{t}: null or duplicate primary keys')
    check(len(data['Customer'])==args.expected_customers,f"Customer count {len(data['Customer'])} != {args.expected_customers}")
    byid={t:{r[pk[t]]:r for r in data[t]} for t in tables}
    fk=[('Subscription','customer_id','Customer',False),('UsageSnapshot','subscription_id','Subscription',False),
        ('BillingEvent','subscription_id','Subscription',False),('SupportCase','customer_id','Customer',False),
        ('SupportCase','subscription_id','Subscription',True),('OfferRule','offer_id','Offer',False),
        ('OfferRule','eligibility_rule_id','EligibilityRule',False),('EligibilityEvaluation','customer_id','Customer',False),
        ('EligibilityEvaluation','offer_id','Offer',False),('EligibilityRuleResult','eligibility_evaluation_id','EligibilityEvaluation',False),
        ('EligibilityRuleResult','offer_id','Offer',False),('EligibilityRuleResult','offer_rule_id','OfferRule',False),('CampaignContact','customer_id','Customer',False),
        ('CampaignContact','offer_id','Offer',False),('CampaignContact','eligibility_evaluation_id','EligibilityEvaluation',False),
        ('CampaignContactEvent','campaign_contact_id','CampaignContact',False),('CampaignContactEvent','actual_offer_id','Offer',True),
        ('SubscriptionEvent','subscription_id','Subscription',False),('ChurnOutcome','customer_id','Customer',False),
        ('ChurnOutcome','churn_subscription_id','Subscription',True),('MonthlyChurnLabel','customer_id','Customer',False),
        ('MonthlyChurnLabel','churn_subscription_id','Subscription',True),('RetentionOutcome','campaign_contact_id','CampaignContact',False),
        ('RetentionOutcome','customer_id','Customer',False)]
    for child,field,parent,nullable in fk:
        for r in data[child]:
            value=r.get(field,'')
            if (not value and nullable): continue
            if not value or value not in byid[parent]:
                issues.append(f'{child}.{field}: unresolved foreign key {value!r}'); break
    check(not duplicates(data['UsageSnapshot'],'usage_snapshot_id'),'UsageSnapshot duplicate ID')
    check(len({(r['subscription_id'],r['snapshot_date']) for r in data['UsageSnapshot']})==len(data['UsageSnapshot']),
          'UsageSnapshot duplicate (subscription_id, snapshot_date)')
    check(len({(r['customer_id'],r['experiment_id']) for r in data['CampaignContact'] if r.get('is_injected_anomaly')!='1'})==
          sum(1 for r in data['CampaignContact'] if r.get('is_injected_anomaly')!='1'),'duplicate customer/experiment assignment in clean records')
    # Customer-level cross-reference checks
    sub_owner={r['subscription_id']:r['customer_id'] for r in data['Subscription']}
    for r in data['SupportCase']:
        if r.get('subscription_id') and sub_owner.get(r['subscription_id'])!=r['customer_id']:
            issues.append('SupportCase subscription/customer mismatch'); break
    cc_by_id=byid['CampaignContact']
    for r in data['RetentionOutcome']:
        cc=cc_by_id.get(r['campaign_contact_id'])
        if cc and cc['customer_id']!=r['customer_id']:
            issues.append('RetentionOutcome customer/contact mismatch'); break
    # ID convention: one annual churn record per customer for 2026.
    check(len(data['ChurnOutcome'])==len(data['Customer']),'ChurnOutcome does not contain exactly one annual row per customer')
    check(all(r['churn_outcome_id']==f"CHURN-{r['customer_id']}-2026" and r['outcome_year']=='2026' for r in data['ChurnOutcome']),
          'ChurnOutcome ID convention must be CHURN-<customer_id>-2026')
    # Rule catalog and N:M bridge constraints.
    rules_by_id=byid['EligibilityRule']; offr_by_id=byid['OfferRule']; offer_rule_counts=Counter(r['offer_id'] for r in data['OfferRule'])
    rule_offer_counts=Counter(r['eligibility_rule_id'] for r in data['OfferRule'])
    check(bool(offer_rule_counts) and min(offer_rule_counts.values())>=2,'OfferRule bridge must attach multiple rules to every offer')
    check(sum(1 for n in rule_offer_counts.values() if n>=2)>=2,'OfferRule bridge does not demonstrate rules reused across multiple offers')
    check(len({(r['offer_id'],r['eligibility_rule_id'],r['effective_from']) for r in data['OfferRule']})==len(data['OfferRule']),
          'Duplicate OfferRule effective binding')
    eval_results=defaultdict(list)
    for r in data['EligibilityRuleResult']:
        er=byid['EligibilityEvaluation'].get(r['eligibility_evaluation_id']); orow=offr_by_id.get(r['offer_rule_id'])
        if er and orow and er['offer_id']!=orow['offer_id']:
            issues.append('EligibilityRuleResult references a rule binding for a different offer'); break
        eval_results[r['eligibility_evaluation_id']].append(r)
    for e in data['EligibilityEvaluation']:
        rr=eval_results.get(e['eligibility_evaluation_id'],[])
        expected_rules=[r for r in data['OfferRule'] if r['offer_id']==e['offer_id']]
        if len(rr)!=len(expected_rules):
            issues.append(f"Eligibility evaluation {e['eligibility_evaluation_id']} lacks a complete rule-result trace"); break
        calc=round(float(e['expected_incremental_contribution_margin_inr'])-float(e['expected_offer_cost_inr'])-float(e['expected_campaign_cost_inr']),2)
        if abs(calc-float(e['expected_net_value_inr']))>0.02:
            issues.append('EligibilityEvaluation expected_net_value arithmetic mismatch'); break
        result_codes={byid['EligibilityRule'][orow['eligibility_rule_id']]['rule_code']:int(r['passed'])
                      for r in rr for orow in [offr_by_id[r['offer_rule_id']]]}
        should_eligible=all(v==1 for v in result_codes.values())
        if (e['decision']=='ELIGIBLE')!=should_eligible:
            issues.append('Eligibility decision does not match mandatory rule results'); break
    # Feature/label separation and as-of feature checks.
    features=read_csv(d/'features.csv'); ground_truth=read_csv(d/'ground_truth.csv')
    feature_fields=set(features[0]) if features else set()
    check(not ({'churn_label','churn_event_date','churn_type','retained','retention_outcome_id'} & feature_fields),
          'Feature matrix contains outcome/target fields')
    check(len(features)==len(ground_truth),'Features and monthly ground truth row counts differ')
    cust_by_id=byid['Customer']; subscription_by_customer={r['customer_id']:r for r in data['Subscription']}
    usage_idx={(r['subscription_id'],r['snapshot_date']):r for r in data['UsageSnapshot']}
    failed_dates=defaultdict(list)
    for r in data['BillingEvent']:
        if r['event_type']=='PAYMENT_FAILED': failed_dates[r['subscription_id']].append(r['event_timestamp'][:10])
    support_dates=defaultdict(list)
    for r in data['SupportCase']: support_dates[r['customer_id']].append(r['created_at'][:10])
    feature_keys=set()
    for fr in features:
        cid=fr['customer_id']; pred=fr['prediction_date']; key=(cid,pred); feature_keys.add(key)
        sub=subscription_by_customer.get(cid); us=usage_idx.get((sub['subscription_id'],pred)) if sub else None
        if not us:
            issues.append('Feature row has no same-date UsageSnapshot'); break
        if any(fr[k]!=us[src] for k,src in [('sessions_30d','sessions_30d'),('usage_minutes_30d','usage_minutes_30d'),('days_since_last_use','days_since_last_use')]):
            issues.append('Feature values disagree with UsageSnapshot'); break
        pd=date.fromisoformat(pred); low=(pd-timedelta(days=90)).isoformat()
        fc=sum(1 for dt in failed_dates[sub['subscription_id']] if low<dt<=pred)
        sc=int(any(dt<=pred for dt in support_dates.get(cid,[])))
        if int(fr['failed_payments_90d'])!=fc or int(fr['support_case_count_18m'])!=sc:
            issues.append('Payment/support feature not correct as-of prediction date'); break
        cust=cust_by_id[cid]; season=int(cust['seasonal_user_flag'])
        score=min(.95,max(.01,.15+max(0,30-int(fr['sessions_30d']))*.015+min(fc,3)*.07+sc*.10+
                         (.035 if season and pd.month in (3,4) else 0)+min(int(fr['days_since_last_use']),45)*.009))
        if abs(score-float(fr['risk_score']))>.00011:
            issues.append('Risk score not reproducible from as-of feature inputs'); break
    monthly_by_key={(r['customer_id'],r['prediction_date'],r['horizon_days']):r for r in data['MonthlyChurnLabel'] if r['is_injected_anomaly']!='1'}
    for gr in ground_truth:
        lr=monthly_by_key.get((gr['customer_id'],gr['prediction_date'],gr['horizon_days']))
        if not lr or any(lr[k]!=gr[k] for k in ['label_status','churn_label','churn_event_date','churn_type']):
            issues.append('ground_truth.csv differs from MonthlyChurnLabel clean rows'); break
    for lab in data['MonthlyChurnLabel']:
        is_anom=lab.get('is_injected_anomaly')=='1'
        if not is_anom and lab['label_status']=='CENSORED' and lab['churn_label']!='':
            issues.append('CENSORED monthly label has a non-null target'); break
        if not is_anom and lab['churn_label']=='1':
            if not lab['churn_event_date'] or lab['churn_event_date']<=lab['prediction_date']:
                issues.append('Temporal label violation in clean baseline'); break
            if date.fromisoformat(lab['churn_event_date'])>date.fromisoformat(lab['prediction_date'])+timedelta(days=int(lab['horizon_days'])):
                issues.append('Positive label event outside horizon'); break
    # Subscription plan history: validate explicit transitions and final plan agreement.
    events_by_sub=defaultdict(list)
    for e in data['SubscriptionEvent']:
        if e['event_type']=='PLAN_CHANGED':
            if not e['old_plan_code'] or not e['new_plan_code'] or e['old_plan_code']==e['new_plan_code']:
                issues.append('PLAN_CHANGED event lacks old/new plan values'); break
        events_by_sub[e['subscription_id']].append(e)
    changes=0
    for sid,evs in events_by_sub.items():
        evs.sort(key=lambda x:x['effective_at'])
        prev_plan=''
        for e in evs:
            if e['event_type']=='ACTIVATED': prev_plan=e['new_plan_code']
            elif e['event_type']=='PLAN_CHANGED':
                changes+=1
                if e['old_plan_code']!=prev_plan:
                    issues.append(f'Plan-history chain broken for {sid}'); break
                prev_plan=e['new_plan_code']
        else: continue
        break
    check(changes>0,'No PLAN_CHANGED history rows generated')
    # Assignment, exposure, and retention-outcome consistency in the selected variant.
    for c in data['CampaignContact']:
        if c.get('is_injected_anomaly')=='1': continue
        e=byid['EligibilityEvaluation'].get(c['eligibility_evaluation_id'])
        if not e or c['eligibility_decision']!=e['decision'] or c['risk_score']!=e['risk_score'] or c['rule_set_version']!=e['rule_set_version']:
            issues.append('CampaignContact differs from referenced evaluation'); break
        if args.variant=='clean' and c['eligibility_decision']!='ELIGIBLE':
            issues.append('Ineligible contact in clean baseline'); break
    for ev in data['CampaignContactEvent']:
        if ev.get('is_injected_anomaly')=='1': continue
        c=cc_by_id.get(ev['campaign_contact_id'])
        if not c: continue
        if c['assigned_group']=='CONTROL' and ev['event_type'] in ('OFFER_SENT','OFFER_DELIVERED','OFFER_EXPOSED','OFFER_REDEEMED') and ev.get('actual_offer_id')==c['offer_id']:
            issues.append('Control contamination in clean records'); break
        if c['eligibility_decision']=='INELIGIBLE' and ev['event_type'] in ('OFFER_SENT','OFFER_DELIVERED'):
            issues.append('Ineligible offer send in clean records'); break
    outcomes_by_contact={r['campaign_contact_id']:r for r in data['RetentionOutcome']}
    potential=read_csv(d/'retention_potential_outcomes.csv')
    for po in potential:
        rr=outcomes_by_contact.get(po['campaign_contact_id'])
        if not rr or int(rr['retained'])!=int(po['observed_retained']) or int(po['unit_treatment_effect_if_delivered'])!=int(po['retained_if_treatment_if_delivered'])-int(po['retained_if_control']):
            issues.append('Retention outcome does not match potential-outcome truth'); break
    primary_events=[r['retention_event_id'] for r in data['RetentionOutcome'] if r['attribution_status']=='PRIMARY' and r['retention_event_id'] and r.get('is_injected_anomaly')!='1']
    check(len(primary_events)==len(set(primary_events)),'Duplicate primary retention attribution among clean rows')
    # Randomized experiment check: observed lift should be plausible relative to the generator's saved potential outcomes.
    group_values=defaultdict(list)
    for rr in data['RetentionOutcome']:
        cc=cc_by_id.get(rr['campaign_contact_id'])
        if cc and rr['follow_up_complete']=='1' and rr.get('is_injected_anomaly')!='1':
            group_values[cc['assigned_group']].append(int(rr['retained']))
    group_n={g:len(vals) for g,vals in group_values.items()}
    group_rates={g:(sum(vals)/len(vals) if vals else 0.0) for g,vals in group_values.items()}
    treatment_contacts=[c for c in data['CampaignContact'] if c['assigned_group']=='TREATMENT' and c.get('is_injected_anomaly')!='1']
    delivery_rate=sum(1 for c in treatment_contacts if c['contact_status']=='DELIVERED')/max(1,len(treatment_contacts))
    mean_unit_effect=sum(int(x['unit_treatment_effect_if_delivered']) for x in potential)/max(1,len(potential))
    expected_itt_lift=mean_unit_effect*delivery_rate
    observed_itt_lift=group_rates.get('TREATMENT',0.0)-group_rates.get('CONTROL',0.0)
    nt=group_n.get('TREATMENT',0); nc=group_n.get('CONTROL',0)
    check(not (nt and nc) or .40 <= nt/(nt+nc) <= .60, 'Treatment/control allocation outside 40:60–60:40 bounds')
    if nt>=30 and nc>=30:
        standard_error=((group_rates.get('TREATMENT',0)*(1-group_rates.get('TREATMENT',0))/nt)+
                        (group_rates.get('CONTROL',0)*(1-group_rates.get('CONTROL',0))/nc))**0.5
        recovery_tolerance=3*standard_error+0.015
        check(abs(observed_itt_lift-expected_itt_lift)<=recovery_tolerance,
              f'Observed ITT lift {observed_itt_lift:.4f} inconsistent with known synthetic effect {expected_itt_lift:.4f}')
    churn_in_window={r['customer_id'] for r in data['Subscription'] if r['end_date'] and '2025-01-01'<=r['end_date']<='2026-06-30'}
    churn_rate=len(churn_in_window)/max(1,len(data['Customer']))
    if args.require_target_rate: check(.05<=churn_rate<=.20,f'18-month-window churn rate {churn_rate:.4f} outside 5–20%')
    if args.variant=='clean':
        check(all(r.get('is_injected_anomaly','0') in ('','0') for t in ('CampaignContact','CampaignContactEvent','MonthlyChurnLabel','RetentionOutcome') for r in data[t]),
              'Clean baseline contains injected anomaly flags')
    report={'status':'PASS' if not issues else 'FAIL','variant':args.variant,'customers':len(data['Customer']),
            'monthly_feature_rows':len(features),'monthly_label_rows':len(ground_truth),'annual_churn_outcome_rows':len(data['ChurnOutcome']),
            'customers_churned_in_18_month_feature_window':len(churn_in_window),'observed_churn_rate_18_month_window':round(churn_rate,4),
            'plan_change_events':changes,'experiment_group_sizes':group_n,'experiment_retention_rates':{k:round(v,6) for k,v in group_rates.items()},'observed_itt_lift':round(observed_itt_lift,6),'known_effect_expected_itt_lift':round(expected_itt_lift,6),'treatment_delivery_rate':round(delivery_rate,6),'tables_checked':len(tables),'issues':issues}
    (d/'validation_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if not issues else 1)
if __name__=='__main__': main()
