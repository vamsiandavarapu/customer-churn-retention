#!/usr/bin/env python3
"""Detect four required anomaly cases embedded inline in the anomaly-injected dataset."""
import argparse,csv,json
from pathlib import Path
from collections import defaultdict

def read(path):
    with path.open(newline='',encoding='utf-8') as f: return list(csv.DictReader(f))
def main():
    p=argparse.ArgumentParser(); p.add_argument('--data',required=True); args=p.parse_args(); d=Path(args.data)
    labels=read(d/'MonthlyChurnLabel.csv'); contacts=read(d/'CampaignContact.csv'); events=read(d/'CampaignContactEvent.csv'); outcomes=read(d/'RetentionOutcome.csv')
    contact={r['campaign_contact_id']:r for r in contacts}
    findings={}
    # ANOM-001: positive forward label with churn date on or before prediction timestamp.
    bad=[r for r in labels if r.get('anomaly_id')=='ANOM-001' and r['churn_label']=='1' and r['churn_event_date']<=r['prediction_date']]
    findings['ANOM-001']={'expected':'TEMPORAL_LABEL_VIOLATION','detected':'TEMPORAL_LABEL_VIOLATION' if bad else None,'row_ids':[r['monthly_label_id'] for r in bad]}
    # ANOM-002: ineligible contact has an actual send/delivery event.
    badc=[c for c in contacts if c.get('anomaly_id')=='ANOM-002' and c['eligibility_decision']=='INELIGIBLE' and c['contact_status'] in ('SENT','DELIVERED')]
    bade=[e for e in events if e.get('anomaly_id')=='ANOM-002' and e['event_type'] in ('OFFER_SENT','OFFER_DELIVERED') and contact.get(e['campaign_contact_id'],{}).get('eligibility_decision')=='INELIGIBLE']
    findings['ANOM-002']={'expected':'ELIGIBILITY_VIOLATION','detected':'ELIGIBILITY_VIOLATION' if badc and bade else None,'row_ids':[c['campaign_contact_id'] for c in badc] + [e['campaign_contact_event_id'] for e in bade]}
    # ANOM-003: control assignment receives the experimental candidate offer.
    bad=[e for e in events if e.get('anomaly_id')=='ANOM-003' and e['event_type'] in ('OFFER_SENT','OFFER_DELIVERED','OFFER_EXPOSED','OFFER_REDEEMED') and
         contact.get(e['campaign_contact_id'],{}).get('assigned_group')=='CONTROL' and e.get('actual_offer_id')==contact.get(e['campaign_contact_id'],{}).get('offer_id')]
    findings['ANOM-003']={'expected':'EXPERIMENT_CONTAMINATION','detected':'EXPERIMENT_CONTAMINATION' if bad else None,'row_ids':[e['campaign_contact_event_id'] for e in bad]}
    # ANOM-004: same retention event is credited as PRIMARY across contacts; at least one row is marked injected.
    by_event=defaultdict(list)
    for r in outcomes:
        if r['attribution_status']=='PRIMARY' and r['retention_event_id']:
            by_event[r['retention_event_id']].append(r)
    dups=[]
    for event_id,rows in by_event.items():
        if len({r['campaign_contact_id'] for r in rows})>1 and any(r.get('anomaly_id')=='ANOM-004' for r in rows):
            dups.append({'retention_event_id':event_id,'outcome_ids':[r['retention_outcome_id'] for r in rows]})
    findings['ANOM-004']={'expected':'DUPLICATE_RETENTION_ATTRIBUTION','detected':'DUPLICATE_RETENTION_ATTRIBUTION' if dups else None,'duplicates':dups}
    for k,v in findings.items(): v['pass']=v['expected']==v['detected']
    report={'status':'PASS' if all(v['pass'] for v in findings.values()) else 'FAIL','variant':'anomaly_injected','fixtures_detected':sum(v['pass'] for v in findings.values()),'required':4,'results':findings}
    (d/'anomaly_validation_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2)); raise SystemExit(0 if report['status']=='PASS' else 1)
if __name__=='__main__': main()
