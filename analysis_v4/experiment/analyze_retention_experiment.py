from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'generated_data_20000' / 'clean_baseline'
OUT = Path(__file__).resolve().parent / 'results'
OUT.mkdir(parents=True, exist_ok=True)
a = pd.read_csv(DATA / 'CampaignContact.csv')
r = pd.read_csv(DATA / 'RetentionOutcome.csv')
if a.customer_id.duplicated().any(): raise ValueError('Customer has multiple assignments')
if r.campaign_contact_id.duplicated().any(): raise ValueError('Multiple outcomes per contact')
d = a.merge(r, on=['campaign_contact_id','customer_id'], how='left', validate='one_to_one')
if d.retained.isna().any(): raise ValueError('Missing retention outcomes')
if not (d.follow_up_complete == 1).all(): raise ValueError('Incomplete follow-up')

def ci_binary(x, n):
    p=x/n; se=np.sqrt(p*(1-p)/n)
    return [float(p-1.96*se), float(p+1.96*se)]

groups={}
for name in ['CONTROL','TREATMENT']:
    g=d[d.assigned_group==name]; n=len(g); x=int(g.retained.sum())
    groups[name]={'n':n,'retained':x,'retention_rate':float(x/n),'retention_ci95':ci_binary(x,n),
      'mean_margin_inr':float(g.observed_contribution_margin_inr.mean()),
      'mean_offer_cost_inr':float(g.actual_offer_cost_inr.mean()),
      'mean_campaign_cost_inr':float(g.campaign_cost_inr.mean()),
      'delivery_rate':float((g.contact_status=='DELIVERED').mean()) if name=='TREATMENT' else None,
      'response_rate':float(g.response_status.isin(['RESPONDED','ACCEPTED']).mean()) if name=='TREATMENT' else None}
c,t=groups['CONTROL'],groups['TREATMENT']
lift=t['retention_rate']-c['retention_rate']
se=np.sqrt(c['retention_rate']*(1-c['retention_rate'])/c['n']+t['retention_rate']*(1-t['retention_rate'])/t['n'])
ci=[float(lift-1.96*se),float(lift+1.96*se)]
net_c=c['mean_margin_inr']-c['mean_offer_cost_inr']-c['mean_campaign_cost_inr']
net_t=t['mean_margin_inr']-t['mean_offer_cost_inr']-t['mean_campaign_cost_inr']
result={'experiment_id':str(d.experiment_id.iloc[0]),'analysis_unit':'assigned customer (intention-to-treat)',
 'n_assigned':len(d),'unique_customers':int(d.customer_id.nunique()),'complete_follow_up_rate':float(d.follow_up_complete.mean()),
 'groups':groups,'retention_lift_percentage_points':float(100*lift),
 'retention_lift_ci95_percentage_points':[100*ci[0],100*ci[1]],
 'incremental_margin_inr_per_customer':float(t['mean_margin_inr']-c['mean_margin_inr']),
 'incremental_cost_inr_per_customer':float(t['mean_offer_cost_inr']+t['mean_campaign_cost_inr']-c['mean_offer_cost_inr']-c['mean_campaign_cost_inr']),
 'descriptive_net_value_difference_inr_per_customer':float(net_t-net_c),
 'limitations':['Synthetic data only.','Approximate Wald confidence interval.','Validate randomization, attribution, and consistent margin windows before business decisions.','Do not filter primary analysis by delivery or response.']}
(OUT/'retention_experiment_metrics.json').write_text(json.dumps(result,indent=2))
d.to_csv(OUT/'joined_experiment_analysis.csv',index=False)
report = '''# Retention Experiment Analysis

## Intention-to-treat results

| Group | Customers | Retained | Retention rate |
|---|---:|---:|---:|
| Control | {cn} | {cr} | {cp:.2%} |
| Treatment | {tn} | {tr} | {tp:.2%} |

Treatment-minus-control retention lift: **{liftpp:.2f} percentage points**.
Approximate 95% confidence interval: **{low:.2f} to {high:.2f} percentage points**.

## Descriptive economics per assigned customer

| Measure | Control | Treatment |
|---|---:|---:|
| Contribution margin | ₹{cm:.2f} | ₹{tm:.2f} |
| Offer cost | ₹{co:.2f} | ₹{to:.2f} |
| Campaign cost | ₹{cc:.2f} | ₹{tc:.2f} |
| Margin less recorded costs | ₹{nc:.2f} | ₹{nt:.2f} |

Difference in observed margin: **₹{md:.2f} per customer**.
Difference in recorded costs: **₹{cd:.2f} per customer**.
Descriptive net-value difference: **₹{nd:.2f} per customer**.

Treatment delivery rate: {delivery:.2%}. Response/acceptance rate: {response:.2%}.

## Interpretation and limitations
This is synthetic data, not real-world evidence. The confidence interval is an approximate Wald interval. Customers remain in their assigned groups even when an offer fails delivery; this is intention-to-treat analysis. Delivery and response are post-assignment variables and should not be used to filter the primary analysis. Before making a campaign decision, validate randomization, contribution-margin attribution, follow-up windows, and all costs. Retention lift alone does not prove profit lift.
'''.format(cn=c['n'],cr=c['retained'],cp=c['retention_rate'],tn=t['n'],tr=t['retained'],tp=t['retention_rate'],liftpp=100*lift,low=100*ci[0],high=100*ci[1],cm=c['mean_margin_inr'],tm=t['mean_margin_inr'],co=c['mean_offer_cost_inr'],to=t['mean_offer_cost_inr'],cc=c['mean_campaign_cost_inr'],tc=t['mean_campaign_cost_inr'],nc=net_c,nt=net_t,md=t['mean_margin_inr']-c['mean_margin_inr'],cd=t['mean_offer_cost_inr']+t['mean_campaign_cost_inr']-c['mean_offer_cost_inr']-c['mean_campaign_cost_inr'],nd=net_t-net_c,delivery=t['delivery_rate'],response=t['response_rate'])
(OUT/'Retention_Experiment_Report.md').write_text(report)
print(json.dumps(result,indent=2))
