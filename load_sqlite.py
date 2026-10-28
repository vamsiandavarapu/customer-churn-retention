#!/usr/bin/env python3
"""Load a dataset variant into SQLite; verify all declared FKs after bulk load."""
import argparse,csv,json,sqlite3,time
from pathlib import Path
ORDER=['Customer','Offer','Subscription','UsageSnapshot','BillingEvent','SupportCase','EligibilityRule','OfferRule',
       'EligibilityEvaluation','EligibilityRuleResult','CampaignContact','CampaignContactEvent','SubscriptionEvent',
       'ChurnOutcome','MonthlyChurnLabel','RetentionOutcome']
def main():
    p=argparse.ArgumentParser(); p.add_argument('--data',required=True); p.add_argument('--schema',default='schema.sql'); p.add_argument('--db',required=True); args=p.parse_args()
    d=Path(args.data); schema=Path(args.schema); db=Path(args.db); db.parent.mkdir(parents=True,exist_ok=True)
    if db.exists(): db.unlink()
    start=time.time(); c=sqlite3.connect(str(db))
    c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA journal_mode=OFF'); c.execute('PRAGMA synchronous=OFF')
    c.execute('PRAGMA temp_store=MEMORY'); c.execute('PRAGMA cache_size=-100000')
    c.executescript(schema.read_text(encoding='utf-8'))
    c.execute('BEGIN')
    for table in ORDER:
        with (d/f'{table}.csv').open(newline='',encoding='utf-8') as f:
            reader=csv.DictReader(f); cols=reader.fieldnames
            q=f'INSERT INTO "{table}" ({",".join(chr(34)+x+chr(34) for x in cols)}) VALUES ({",".join("?" for _ in cols)})'
            batch=[]
            for row in reader:
                batch.append(tuple(None if row.get(col,'')=='' else row[col] for col in cols))
                if len(batch)>=20000: c.executemany(q,batch); batch=[]
            if batch: c.executemany(q,batch)
    c.commit()
    fk=c.execute('PRAGMA foreign_key_check').fetchall()
    counts={t:c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in ORDER}
    summary={'status':'PASS' if not fk else 'FAIL','database':str(db),'tables_loaded':len(ORDER),'foreign_key_violations':len(fk),
             'table_row_counts':counts,'elapsed_seconds':round(time.time()-start,2)}
    report_path=db.with_suffix('.load_report.json'); report_path.write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    c.close(); print(json.dumps(summary,indent=2)); raise SystemExit(0 if not fk else 1)
if __name__=='__main__': main()
