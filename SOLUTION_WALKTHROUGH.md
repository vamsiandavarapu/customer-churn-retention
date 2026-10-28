# Solution Walkthrough: Customer Churn & Retention

## 1. Problem

The project creates synthetic subscription and customer-history data to demonstrate a repeatable churn-analysis workflow and a small retention-experiment analysis. It is a technical demonstration, not real company data or a production deployment.

## 2. Main flow

1. `generate_data.py` creates a deterministic synthetic dataset using a configured seed.
2. `generated_data_20000/clean_baseline/` is the canonical dataset for analysis. `anomaly_injected/` is kept separate for data-quality testing.
3. `validate_data.py`, `validate_anomalies.py`, and `validate_schema.py` check different aspects of data quality and structure.
4. `load_sqlite.py` loads relational tables into SQLite using `schema.sql`.
5. `analysis_v4/run_baseline_analysis.py` runs the baseline churn analysis and writes metrics, predictions, and plots.
6. `analysis_v4/experiment/analyze_retention_experiment.py` produces a descriptive treatment/control analysis.
7. `dashboard/app.py` presents the generated results for exploration.

## 3. Important decisions and trade-offs

- **Synthetic data:** makes the project reproducible without exposing real customer information, but patterns and effects may not match real users.
- **Separate clean and anomaly-injected variants:** preserves a usable modelling dataset while allowing known quality failures to be tested.
- **60-day label horizon:** positive when a churn event occurs after the prediction date and within 60 days. A negative label requires a fully observed horizon; otherwise the row is censored.
- **Failed payment is not itself churn:** churn is defined by the generated subscription termination event.
- **Chronological evaluation:** better reflects predicting future observations than randomly mixing dates across train and test.
- **Simple baseline:** prioritises an explainable reference point over model complexity. Modest performance is reported honestly.
- **Treatment/control economics:** retention-rate differences are not enough; offer and campaign costs affect net value. Synthetic results do not establish real-world causal effectiveness.

## 4. Testing approach

The project includes checks for expected customer count, duplicate identifiers/keys, temporal label rules, relational integrity, known injected anomalies, and SQLite foreign-key integrity. Use the exact commands in `README.md`; save the terminal output as submission evidence. A successful validation run only proves the checks implemented by those validators passed, not that every conceivable defect is absent.

## 5. Limitations

- All data and experiment outcomes are synthetic.
- The baseline model is not production-ready and should be judged by its held-out metrics, not training performance.
- The synthetic risk score is a heuristic, not an independently trained probability.
- `support_case_count_18m` currently behaves as a 0/1 indicator of a prior support case rather than a true count.
- Results are valid only when the dataset, model outputs, and dashboard artifacts come from the same project version.
- Reproducibility should be demonstrated by generating twice with the same seed and comparing output hashes; a seed alone is not evidence that two runs match.

## 6. Suggested 3-minute walkthrough

1. State the problem and the synthetic-data limitation.
2. Show the clean/anomaly-injected split and explain the 60-day label rule.
3. Run the validators and point to their reports.
4. Show the chronological model evaluation and explain the held-out results.
5. Show treatment/control retention alongside costs, then explain why the synthetic uplift is not a real-world claim.
6. Finish with the limitations and the next improvement you would prioritise.
