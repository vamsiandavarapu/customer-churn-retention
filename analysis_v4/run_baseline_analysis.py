"""Run a simple time-based Logistic Regression baseline on the clean synthetic dataset."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score, precision_score, recall_score, brier_score_loss
import joblib

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'generated_data_20000' / 'clean_baseline'
OUT = ROOT / 'analysis_v4' / 'results'
FIG = OUT / 'figures'
MODELS = OUT / 'models'
for folder in (OUT, FIG, MODELS): folder.mkdir(parents=True, exist_ok=True)
features = pd.read_csv(DATA / 'features.csv')
labels = pd.read_csv(DATA / 'ground_truth.csv')
joined = features.merge(labels, on=['customer_id','prediction_date'], how='inner', validate='one_to_one', suffixes=('', '_label'))
joined = joined[joined['label_status'] == 'LABELED'].copy()
joined['churn_label'] = pd.to_numeric(joined['churn_label'], errors='coerce')
joined = joined.dropna(subset=['churn_label'])
joined['prediction_date'] = pd.to_datetime(joined['prediction_date'])
# Explicit chronological split; no random row split across time.
train = joined[joined.prediction_date <= '2025-10-01']
valid = joined[(joined.prediction_date >= '2025-11-01') & (joined.prediction_date <= '2026-02-01')]
test = joined[(joined.prediction_date >= '2026-03-01') & (joined.prediction_date <= '2026-06-01')]
cat_cols = ['region','customer_segment']
num_cols = ['seasonal_user_flag','sessions_30d','usage_minutes_30d','days_since_last_use','tenure_days','failed_payments_90d','support_case_count_18m']
# risk_score is omitted from the primary model because it is a hand-built score derived from some of these features.
X_train, y_train = train[cat_cols+num_cols], train.churn_label.astype(int)
X_valid, y_valid = valid[cat_cols+num_cols], valid.churn_label.astype(int)
X_test, y_test = test[cat_cols+num_cols], test.churn_label.astype(int)
prep = ColumnTransformer([
 ('categorical', Pipeline([('imputer',SimpleImputer(strategy='most_frequent')),('onehot',OneHotEncoder(handle_unknown='ignore'))]), cat_cols),
 ('numeric', Pipeline([('imputer',SimpleImputer(strategy='median')),('scale',StandardScaler())]), num_cols)
])
model = Pipeline([('prep',prep),('classifier',LogisticRegression(max_iter=1000,class_weight='balanced',random_state=20261022))])
model.fit(X_train,y_train)

def metrics(X,y,split):
    prob=model.predict_proba(X)[:,1]
    pred=(prob>=0.5).astype(int)
    top_n=max(1,int(np.ceil(len(prob)*0.05)))
    top_idx=np.argsort(prob)[-top_n:]
    return {'split':split,'rows':int(len(y)),'positive_labels':int(y.sum()),'prevalence':float(y.mean()),
      'roc_auc':float(roc_auc_score(y,prob)) if y.nunique()==2 else None,
      'average_precision':float(average_precision_score(y,prob)) if y.nunique()==2 else None,
      'precision_at_5_percent':float(y.iloc[top_idx].mean()),'lift_at_5_percent':float(y.iloc[top_idx].mean()/y.mean()) if y.mean()>0 else None,
      'precision_threshold_0_5':float(precision_score(y,pred,zero_division=0)),
      'recall_threshold_0_5':float(recall_score(y,pred,zero_division=0)),
      'brier_score':float(brier_score_loss(y,prob))}
results={'dataset':'generated_data_20000/clean_baseline','target':'churn within 60 days after prediction date','features_used':cat_cols+num_cols,
 'excluded_feature_note':'risk_score omitted from primary model because it is a heuristic derived from overlapping feature inputs.',
 'split_rules':{'train':'prediction_date <= 2025-10-01','validation':'2025-11-01 through 2026-02-01','test':'2026-03-01 through 2026-06-01'},
 'metrics':{'train':metrics(X_train,y_train,'train'),'validation':metrics(X_valid,y_valid,'validation'),'test':metrics(X_test,y_test,'test')},
 'limitations':['Synthetic data only; results do not establish real-world predictive performance.','The data-generating process may be simpler than real customer behavior.','Threshold 0.5 is not a business decision threshold; ranking and lift metrics are included because churn is rare.','No production deployment or operational benefit is claimed.']}
(OUT/'analysis_metrics.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
joblib.dump(model,MODELS/'baseline_churn_model.joblib')
test_out=test[['customer_id','prediction_date','churn_label']].copy(); test_out['predicted_probability']=model.predict_proba(X_test)[:,1]
test_out.to_csv(OUT/'test_predictions.csv',index=False)
# Small, reproducible descriptive summaries.
for col in ['region','customer_segment','seasonal_user_flag']:
    summary=joined.groupby(col,dropna=False).agg(rows=('churn_label','size'),positive_labels=('churn_label','sum'),label_rate=('churn_label','mean')).reset_index()
    summary.to_csv(OUT/f'churn_by_{col}.csv',index=False)
missing=features.isna().mean().rename('missing_fraction').reset_index(); missing=missing.rename(columns={'index':'column'})
missing.to_csv(OUT/'feature_missingness.csv',index=False)
monthly=joined.groupby(joined.prediction_date.dt.to_period('M')).agg(rows=('churn_label','size'),positive_labels=('churn_label','sum'),label_rate=('churn_label','mean')).reset_index()
monthly['prediction_month']=monthly.prediction_date.astype(str); monthly.drop(columns=['prediction_date']).to_csv(OUT/'monthly_label_summary.csv',index=False)
# Plot monthly label rate.
plt.figure(figsize=(10,4)); plt.plot(monthly['prediction_month'],monthly['label_rate'],marker='o'); plt.xticks(rotation=45,ha='right'); plt.ylabel('Positive 60-day label rate'); plt.title('Monthly 60-day churn label rate'); plt.tight_layout(); plt.savefig(FIG/'monthly_churn_label_rate.png',dpi=140); plt.close()
# Segment plot.
seg=joined.groupby('customer_segment').churn_label.mean().sort_values(ascending=False)
plt.figure(figsize=(6,4)); seg.plot(kind='bar'); plt.ylabel('Positive 60-day label rate'); plt.title('Churn label rate by customer segment'); plt.tight_layout(); plt.savefig(FIG/'churn_by_segment.png',dpi=140); plt.close()
report=['# EDA and Baseline Model Report','', '## Dataset',f"- Customers: {features.customer_id.nunique():,}",f"- Feature/label rows: {len(joined):,}",f"- Prediction months: {features.prediction_date.nunique()}",f"- Feature window: {features.prediction_date.min()} to {features.prediction_date.max()}",f"- Overall positive 60-day label rate: {joined.churn_label.mean():.2%}",'', '## Model', 'A Logistic Regression baseline was trained with a chronological split. The primary model excludes the heuristic `risk_score` to reduce the risk of relying on a hand-built score that overlaps with the underlying feature inputs.', '', '| Split | Rows | Positives | Prevalence | ROC-AUC | Average precision | Precision in top 5% | Lift in top 5% |', '|---|---:|---:|---:|---:|---:|---:|---:|']
for k in ['train','validation','test']:
 m=results['metrics'][k]; report.append(f"| {k.title()} | {m['rows']:,} | {m['positive_labels']:,} | {m['prevalence']:.2%} | {m['roc_auc']:.3f} | {m['average_precision']:.4f} | {m['precision_at_5_percent']:.2%} | {m['lift_at_5_percent']:.2f}x |")
report += ['', '## Interpretation and limitations', *[f'- {x}' for x in results['limitations']], '', 'The held-out test set is the final reported estimate; avoid repeatedly tuning against it. A modest or weak score is a valid result and should be reported honestly.']
(OUT/'EDA_and_Baseline_Model_Report.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
print(json.dumps(results,indent=2))
