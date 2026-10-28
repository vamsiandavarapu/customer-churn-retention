# Streamlit Dashboard

## Run locally
From the project root, install dependencies and run:

```bash
python -m pip install -r dashboard/requirements.txt
python -m streamlit run dashboard/app.py
```

The app reads the synthetic 5,000-customer dataset from `generated_data_5000/clean_baseline` and saved analysis results from `analysis_v4`. Keep the project folder structure intact.

## Important limitations
- All records are synthetic.
- Churn-model held-out performance is weak and not production-ready.
- Experiment economics are descriptive until margin attribution and cost rules are audited.
