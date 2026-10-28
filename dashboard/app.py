from pathlib import Path
import json
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Customer Churn & Retention", page_icon="📉", layout="wide")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "generated_data_20000" / "clean_baseline"
RESULTS = ROOT / "analysis_v4" / "results"
EXP_RESULTS = ROOT / "analysis_v4" / "experiment" / "results"

st.title("Customer Churn & Retention Analytics")
st.caption("Portfolio demo using synthetic data only. Results are simulated, not real-world campaign evidence.")

@st.cache_data
def load_csv(path):
    return pd.read_csv(path) if path.exists() else pd.DataFrame()

@st.cache_data
def load_json(path):
    return json.loads(path.read_text()) if path.exists() else {}

features = load_csv(DATA / "features.csv")
labels = load_csv(DATA / "ground_truth.csv")
customers = load_csv(DATA / "Customer.csv")
contacts = load_csv(DATA / "CampaignContact.csv")
outcomes = load_csv(DATA / "RetentionOutcome.csv")
monthly = load_csv(DATA / "MonthlyChurnLabel.csv")
model_metrics = load_json(RESULTS / "analysis_metrics.json")
experiment = load_json(EXP_RESULTS / "retention_experiment_metrics.json")

if features.empty or labels.empty:
    st.error(f"Required data files were not found under: {DATA}. Extract the complete project package and run the app from its dashboard folder.")
    st.stop()

# Use the saved monthly labels where available; ground_truth is used for model-facing labels.
labels["prediction_date"] = pd.to_datetime(labels["prediction_date"], errors="coerce")
features["prediction_date"] = pd.to_datetime(features["prediction_date"], errors="coerce")
joined = features.merge(labels, on=["customer_id", "prediction_date"], how="inner", suffixes=("", "_label"))
if "label_status" in joined:
    joined = joined[joined["label_status"] == "LABELED"].copy()
joined["churn_label"] = pd.to_numeric(joined["churn_label"], errors="coerce")
joined = joined.dropna(subset=["churn_label"])

st.sidebar.header("Filters")
if "region" in joined:
    regions = sorted(joined["region"].dropna().astype(str).unique().tolist())
    chosen_regions = st.sidebar.multiselect("Region", regions, default=regions)
else:
    chosen_regions = []
if "customer_segment" in joined:
    segments = sorted(joined["customer_segment"].dropna().astype(str).unique().tolist())
    chosen_segments = st.sidebar.multiselect("Customer segment", segments, default=segments)
else:
    chosen_segments = []
filtered = joined.copy()
if chosen_regions and "region" in filtered:
    filtered = filtered[filtered["region"].astype(str).isin(chosen_regions)]
if chosen_segments and "customer_segment" in filtered:
    filtered = filtered[filtered["customer_segment"].astype(str).isin(chosen_segments)]

n_rows = len(filtered)
churn_rate = filtered["churn_label"].mean() if n_rows else 0
n_customers = filtered["customer_id"].nunique() if n_rows else 0
k1,k2,k3,k4 = st.columns(4)
k1.metric("Customers represented", f"{n_customers:,}")
k2.metric("Prediction rows", f"{n_rows:,}")
k3.metric("Positive 60-day labels", f"{churn_rate:.2%}")
k4.metric("Regions selected", str(len(chosen_regions)))

st.subheader("Churn label trend")
if n_rows:
    trend = filtered.groupby(filtered["prediction_date"].dt.to_period("M"))["churn_label"].mean().rename("Churn label rate").reset_index()
    trend["prediction_date"] = trend["prediction_date"].astype(str)
    st.line_chart(trend.set_index("prediction_date")["Churn label rate"])
else:
    st.info("No rows match the selected filters.")

left,right = st.columns(2)
with left:
    st.subheader("Churn by customer segment")
    if n_rows and "customer_segment" in filtered:
        seg = filtered.groupby("customer_segment", dropna=False)["churn_label"].mean().sort_values(ascending=False)
        st.bar_chart(seg)
with right:
    st.subheader("Observable behaviour by label")
    candidates = [c for c in ["sessions_30d", "usage_minutes_30d", "days_since_last_use", "failed_payments_90d", "support_case_count_18m", "risk_score"] if c in filtered]
    if candidates:
        means = filtered.groupby("churn_label")[candidates].mean().T
        means.columns = ["No churn label", "Churn label"] if len(means.columns)==2 else means.columns
        st.dataframe(means.round(3), use_container_width=True)
    else:
        st.info("Feature columns are not available.")

st.subheader("Model performance")
if model_metrics:
    # Flexible rendering because report versions may use different key names.
    st.json(model_metrics)
    st.caption("Read the model report before interpreting metrics. In the current project, model ranking on the held-out test set is weak; do not treat this as production-ready.")
else:
    st.warning("Model metrics JSON not found. See analysis_v4/results/EDA_and_Baseline_Model_Report.md.")

st.divider()
st.header("Retention experiment")
if experiment and "groups" in experiment:
    groups = experiment["groups"]
    c = groups.get("CONTROL", {})
    t = groups.get("TREATMENT", {})
    a,b,c_col,d = st.columns(4)
    a.metric("Control retention", f"{c.get('retention_rate', 0):.2%}", f"n={c.get('n', 0)}")
    b.metric("Treatment retention", f"{t.get('retention_rate', 0):.2%}", f"n={t.get('n', 0)}")
    lift = experiment.get("retention_lift_percentage_points", 0)
    c_col.metric("Retention lift", f"{lift:+.2f} pp")
    net = experiment.get("descriptive_net_value_difference_inr_per_customer", 0)
    d.metric("Descriptive net value / customer", f"₹{net:,.2f}")
    st.caption("Intention-to-treat synthetic experiment. Retention lift alone is not profit lift; validate margin attribution and cost definitions before making a business decision.")
    lohi = experiment.get("retention_lift_ci95_wald") or experiment.get("retention_lift_ci95_percentage_points")
    if lohi:
        st.write("Approximate 95% confidence interval for retention lift:", lohi)
    rows=[]
    for name, g in [("Control", c), ("Treatment", t)]:
        rows.append({"Group":name,"Customers":g.get("n"),"Retention":g.get("retention_rate"),"Mean margin (INR)":g.get("mean_contribution_margin_inr", g.get("mean_margin_inr")),"Mean offer cost (INR)":g.get("mean_offer_cost_inr"),"Mean campaign cost (INR)":g.get("mean_campaign_cost_inr")})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
else:
    st.warning("Experiment metrics not found. Run analysis_v4/experiment/analyze_retention_experiment.py first.")

st.subheader("Data-quality and interpretation notes")
st.markdown("""
- Data is synthetic and intended for demonstrating analytics workflows.
- A 60-day monthly label rate is not the same as the total customer churn rate over the entire simulated history.
- Avoid using post-prediction information as model features.
- Retention experiment results should use assignment groups (intention-to-treat), not only delivered or accepted offers.
- The current churn model has weak held-out ranking performance and needs further investigation before operational use.
""")

with st.expander("Show filtered prediction rows"):
    st.dataframe(filtered.head(500), use_container_width=True)
    st.caption("Showing at most 500 rows to keep the dashboard responsive.")
