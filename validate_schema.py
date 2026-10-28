#!/usr/bin/env python3
"""Smoke-test the DDL and report declared tables, indexes, and schema constraints."""
import argparse,sqlite3
from pathlib import Path
EXPECTED={'Customer','Subscription','UsageSnapshot','BillingEvent','SupportCase','Offer','EligibilityRule','OfferRule',
          'EligibilityEvaluation','EligibilityRuleResult','CampaignContact','CampaignContactEvent','SubscriptionEvent',
          'ChurnOutcome','MonthlyChurnLabel','RetentionOutcome'}
def main():
    p=argparse.ArgumentParser(); p.add_argument('--schema',default='schema.sql'); args=p.parse_args()
    path=Path(args.schema)
    if not path.exists(): raise SystemExit(f'Schema file missing: {path}')
    c=sqlite3.connect(':memory:'); c.execute('PRAGMA foreign_keys=ON'); c.executescript(path.read_text(encoding='utf-8'))
    tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    indexes=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")]
    result={'status':'PASS' if EXPECTED<=tables else 'FAIL','expected_tables':len(EXPECTED),'found_tables':len(tables),
            'missing_tables':sorted(EXPECTED-tables),'indexes':sorted(indexes),'foreign_keys_enabled':c.execute('PRAGMA foreign_keys').fetchone()[0]==1}
    print(result); c.close(); raise SystemExit(0 if result['status']=='PASS' else 1)
if __name__=='__main__': main()
