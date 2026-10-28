# Customer Churn & Retention Analysis

A portfolio project that generates synthetic subscription data, validates customer and campaign lifecycles, trains a baseline churn model, and evaluates a simulated retention experiment.

> **Important:** The data and campaign results are synthetic. The model is a baseline for learning and is not production-ready. The simulated treatment/control difference is not evidence of real-world campaign effectiveness.

## What this project demonstrates

- Reproducible generation of **20,000 unique customers** and 18 monthly prediction dates from January 2025 through June 2026.
- Customer, subscription, usage, billing, support, eligibility, campaign, churn-label, and retention-outcome tables.
- A clean baseline and a separate anomaly-injected dataset with four labelled scenarios.
- Primary-key, foreign-key, lifecycle, label timing, and experiment checks.
- CSV and JSON Lines data exports plus a SQLite database built from the SQL schema.
- Time-based Logistic Regression evaluation and descriptive intention-to-treat retention analysis.
- A Streamlit dashboard for exploring labels, segments, model metrics, and experiment results.

## Project structure

```text
Customer_Churn_Retention_Project_v4/
├── generated_data_20000/
│   ├── clean_baseline/          # Canonical clean CSVs, manifest and validation report
│   ├── anomaly_injected/        # CSVs with four labelled anomaly scenarios
│   ├── jsonl_clean_baseline/    # JSON Lines export of clean CSVs
│   ├── customer_churn_clean.sqlite
│   ├── customer_churn_clean.load_report.json
│   ├── config.json
│   ├── generation_summary.json
│   └── experiment_summary.json
├── analysis_v4/
│   ├── results/                 # EDA, baseline model, predictions and figures
│   ├── experiment/results/      # Retention analysis outputs
│   └── run_baseline_analysis.py
├── dashboard/                   # Streamlit dashboard
├── generate_data.py
├── export_json.py
├── validate_data.py
├── validate_anomalies.py
├── validate_schema.py
├── load_sqlite.py
├── schema.sql
├── DATA_DICTIONARY.md
└── README.md
```
## Dataset

The generated dataset is distributed separately from the source code to keep the Git repository lightweight.

The dataset includes:
- **Clean baseline data** — generated customer records and related tables.
- **Anomaly-injected data** — records containing the required anomaly scenarios for validation.
- **JSONL exports** — JSON Lines versions of the clean baseline tables.
- **Database and metadata** — SQLite database, configuration, generation summary, manifests, and validation reports.

### Download the dataset

Download the dataset archives from the [GitHub Releases](https://github.com/vamsiandavarapu/customer-churn-retention/releases) page.

Download the required archive files and extract them into the project root, preserving the `generated_data_20000` directory structure expected by the scripts.

After extraction, the expected structure is:

```text
generated_data_20000/
├── clean_baseline/
├── anomaly_injected/
├── jsonl_clean_baseline/
├── customer_churn_clean.sqlite
├── config.json
└── generation_summary.json
```

The exact files included in each archive are described by the archive names. Check that all required archives have been downloaded and extracted before running the validation scripts.

### Generate the dataset locally

Alternatively, use the project's data-generation script and the configuration documented in this repository to regenerate the synthetic data. Run the validation scripts afterward to check the generated outputs.

The dataset is synthetic and does not represent real customers or actual business outcomes.


## Install and run on Windows

Open PowerShell in the project folder. Create and activate a clean virtual environment, then install the analysis and dashboard dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-analysis.txt
python -m pip install -r dashboard\requirements.txt
```

If PowerShell blocks environment activation, use `\.venv\Scripts\python.exe -m pip ...` and `\.venv\Scripts\python.exe -m streamlit ...` instead.

Launch the dashboard:

```powershell
python -m streamlit run dashboard\app.py
```

The dashboard reads from `generated_data_20000\clean_baseline` and uses the matching `analysis_v4` result files. Keep these files from the same package version together.

## Rebuild the dataset

```powershell
python generate_data.py --customers 20000 --seed 20261022 --out generated_data_20000 --anomalies
```

The generator writes both `clean_baseline` and `anomaly_injected`. The clean folder is the source for modelling and business analysis; the injected folder is for testing data-quality detection. The generator removes an existing output folder with the same name, so back it up first if you need to preserve it.

## Validation commands

```powershell
python validate_data.py --data generated_data_20000\clean_baseline --expected-customers 20000 --require-target-rate
python validate_data.py --data generated_data_20000\anomaly_injected --expected-customers 20000 --variant anomaly --require-target-rate
python validate_anomalies.py --data generated_data_20000\anomaly_injected
python validate_schema.py
python load_sqlite.py --data generated_data_20000\clean_baseline --schema schema.sql --db generated_data_20000\customer_churn_clean.sqlite
```

## Model analysis

```powershell
python analysis_v4\run_baseline_analysis.py
python analysis_v4\experiment\analyze_retention_experiment.py
```

The baseline model uses chronological train, validation, and test periods. The hand-built `risk_score` is omitted from the primary model because it overlaps with the underlying feature inputs. Review `analysis_v4\results\EDA_and_Baseline_Model_Report.md` before discussing performance.

## Data and label notes

- Monthly labels represent churn within 60 days after the prediction date. A failed payment by itself is not treated as churn; the generated subscription termination is the churn event.
- The 18-month observed churn rate is computed from subscription end dates in the January 2025–June 2026 feature window. It is not the same as the monthly positive-label prevalence.
- `support_case_count_18m` currently represents whether a prior support case exists (0/1), not a multi-case count; interpret it as a support-case indicator.
- `risk_score` is a synthetic heuristic, not a trained model output.
- `retention_potential_outcomes.csv` includes synthetic potential-outcome information for validation. It is not a feature table and must not be used as a real deployable predictor.
- `ground_truth.csv` is kept separate from `features.csv` to reduce accidental target leakage.

## Current validated results

- 20,000 unique customers.
- 332,897 feature rows across 18 prediction months.
- 15.58% observed churn over the defined 18-month feature window (within the assignment's 5–20% range).
- Clean dataset validator: PASS; 16 relational tables checked.
- Anomaly detector: PASS; all four required injected scenarios detected.
- SQLite import: PASS; 16 tables loaded and zero foreign-key violations.
- Held-out model ROC-AUC is modest (see the generated report); do not claim production readiness.
- Simulated retention lift is positive in this seeded run, but recorded offer/campaign costs make the descriptive net-value difference negative. See the experiment report for exact estimates and uncertainty.

## AI assistance and ownership

AI tools were used as assistants for coding, debugging, and documentation. The project author should be able to explain the data-generation assumptions, validation checks, model split, metrics, and limitations. Synthetic results must not be presented as actual customer or company data.


## Submission guidance

- `SOLUTION_WALKTHROUGH.md` explains the main decisions, data flow, tests, and limitations.
- `AI_PROMPT_HISTORY.md` documents AI assistance transparently; it is a curated reconstruction, not a verbatim export of the full conversation.
- `SUBMISSION_CHECKLIST.md` lists the remaining clean-environment, public GitHub, and evidence steps.
- Use a public GitHub repository you control and real, meaningful commits. Do not fabricate commit history or claim unrun checks.
