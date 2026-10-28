# EDA and Baseline Model Report

## Dataset
- Customers: 20,000
- Feature/label rows: 332,897
- Prediction months: 18
- Feature window: 2025-01-01 to 2026-06-01
- Overall positive 60-day label rate: 1.88%

## Model
A Logistic Regression baseline was trained with a chronological split. The primary model excludes the heuristic `risk_score` to reduce the risk of relying on a hand-built score that overlaps with the underlying feature inputs.

| Split | Rows | Positives | Prevalence | ROC-AUC | Average precision | Precision in top 5% | Lift in top 5% |
|---|---:|---:|---:|---:|---:|---:|---:|
| Train | 191,912 | 3,572 | 1.86% | 0.552 | 0.0224 | 2.62% | 1.41x |
| Validation | 71,813 | 1,341 | 1.87% | 0.552 | 0.0229 | 2.90% | 1.55x |
| Test | 69,172 | 1,330 | 1.92% | 0.575 | 0.0239 | 2.75% | 1.43x |

## Interpretation and limitations
- Synthetic data only; results do not establish real-world predictive performance.
- The data-generating process may be simpler than real customer behavior.
- Threshold 0.5 is not a business decision threshold; ranking and lift metrics are included because churn is rare.
- No production deployment or operational benefit is claimed.

The held-out test set is the final reported estimate; avoid repeatedly tuning against it. A modest or weak score is a valid result and should be reported honestly.
