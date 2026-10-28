#!/usr/bin/env python3
"""Export each CSV in a dataset folder to newline-delimited JSON (one record per line)."""
import argparse,csv,json
from pathlib import Path

def main():
 p=argparse.ArgumentParser(); p.add_argument('--data',required=True); p.add_argument('--out',required=True); a=p.parse_args()
 src=Path(a.data); out=Path(a.out); out.mkdir(parents=True,exist_ok=True); results=[]
 for file in sorted(src.glob('*.csv')):
  target=out/(file.stem+'.jsonl'); count=0
  with file.open(newline='',encoding='utf-8') as f, target.open('w',encoding='utf-8') as g:
   for row in csv.DictReader(f):
    g.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n'); count+=1
  results.append({'csv':file.name,'jsonl':target.name,'rows':count})
 (out/'export_manifest.json').write_text(json.dumps({'source':str(src),'format':'JSON Lines','files':results},indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':'PASS','files_exported':len(results),'total_rows':sum(x['rows'] for x in results),'output':str(out)},indent=2))
if __name__=='__main__': main()
