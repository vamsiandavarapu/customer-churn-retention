# AI Prompt History — Customer Churn & Retention Project

I used ChatGPT as an assistant while working through this project. The prompts below are reconstructed summaries of the questions I asked during the work, not exact copies of every message from the original conversations.

## Prompts and notes

### 1. Breaking down the assignment
**Prompt:**  
“I need to build this customer churn and retention project. Can you turn the assignment into a clear list of things I need to implement, including the data, labels, anomalies, exports and validation?”

**Note:** This helped me map the assignment to implementation tasks before making more changes.

### 2. Deciding the tables
**Prompt:**  
“What tables should I create for customer, subscription, usage, billing, support, offers, campaigns, churn and retention? How should the keys connect?”

**Note:** I used the proposed structure to plan the generated records and relationships.

### 3. Choosing a fixed seed
**Prompt:**  
“How do I make the synthetic data repeatable so the same seed produces the same dataset?”

**Note:** This helped me focus on reproducibility rather than treating each generation as a separate dataset.

### 4. Generating enough customers
**Prompt:**  
“My working version has 5,000 customers, but the assignment asks for 20,000. How should I update the generator without just duplicating rows?”

**Note:** This highlighted that the dataset needed to be regenerated at the required scale, not padded with copies.

### 5. Understanding the 18-month history
**Prompt:**  
“How should the monthly prediction dates work across the 18-month period, and how can I check the number of rows generated?”

**Note:** I used this to think about customer-level counts separately from customer-date prediction rows.

### 6. Defining churn labels
**Prompt:**  
“For a 60-day churn horizon, when should a label be 1, 0, or censored? Can you explain it with a small example?”

**Note:** This clarified that a negative label needs a fully observed horizon and that a future churn event must fall after the prediction date.

### 7. Handling failed payments
**Prompt:**  
“If a customer has a failed payment, should I label them as churned, or should I wait for the subscription to actually end?”

**Note:** I kept the distinction between payment problems and actual churn in mind when reviewing the rules.

### 8. Checking label timing
**Prompt:**  
“Help me check that positive churn events happen after the prediction date and within 60 days, and that there are no duplicate customer/date labels.”

**Note:** I ran the label audit and reviewed its output. It reported no positive labels outside the defined time window.

### 9. Checking feature leakage
**Prompt:**  
“Which of these feature columns could leak future information into the model? How can I check the dates used to calculate them?”

**Note:** The column-name check was useful, but I learned it cannot prove that the feature-generation logic is temporally correct. That needs source-code review too.

### 10. Creating the required anomalies
**Prompt:**  
“I need the four required anomaly scenarios in the dataset. How should I represent them separately from the clean baseline, and how do I verify each one is present?”

**Note:** This helped me separate clean data from deliberately injected anomalies and keep anomaly checks explicit.

### 11. Checking foreign keys
**Prompt:**  
“How can I validate primary keys and foreign keys across the generated tables, and find records that point to missing parents?”

**Note:** I used separate validation checks instead of assuming that successful CSV generation meant the relationships were valid.

### 12. Exporting JSON and SQLite
**Prompt:**  
“I need CSV, JSON and SQL/SQLite outputs. Can you help me keep the exports consistent and check that the database loaded correctly?”

**Note:** This guided the export and database-loading workflow. The final output still needed to be checked after running the scripts.

### 13. Understanding the class imbalance
**Prompt:**  
“My churn-positive class is much smaller than the negative class. Is accuracy enough to evaluate the model, and what should I look at instead?”

**Note:** This led me to pay attention to ROC-AUC, average precision, precision among the highest-risk customers and lift, rather than accuracy alone.

### 14. Comparing baseline models
**Prompt:**  
“Help me compare a simple baseline churn model with another model using the same split and metrics. How should I decide whether the second model is actually better?”

**Note:** I used the comparison as an evaluation exercise rather than assuming a more complicated model must perform better.

### 15. Understanding weak test results
**Prompt:**  
“My validation results looked better than the held-out test results. What could cause that, and how should I report it honestly?”

**Note:** This helped me avoid presenting the model as production-ready when the test results were modest.

### 16. Understanding feature importance
**Prompt:**  
“How should I interpret permutation importance, and what does it tell me compared with just looking at the model coefficients?”

**Note:** This helped me treat feature importance as a diagnostic, not proof that a feature causes churn.

### 17. Comparing treatment and control
**Prompt:**  
“How do I calculate retention rates for the treatment and control groups and report the difference in percentage points?”

**Note:** I used this structure for the synthetic retention experiment.

### 18. Including campaign costs
**Prompt:**  
“The treatment group has higher retention, but the offer costs money. How should I include offer and campaign costs when comparing the groups?”

**Note:** This made the financial comparison more useful than looking at retention lift alone.

### 19. Interpreting experiment uncertainty
**Prompt:**  
“How should I explain uncertainty around the treatment-control difference, and what limitations should I mention because the data is synthetic?”

**Note:** I kept the results framed as simulated and avoided claiming that they prove real-world causal impact.

### 20. Running the dashboard
**Prompt:**  
“The dashboard opens, but how can I make sure it is reading the final 20,000-customer dataset rather than the earlier 5,000-customer version?”

**Note:** This highlighted the importance of checking the dashboard's data path and displayed row counts after changing datasets.

### 21. Cleaning up project files
**Prompt:**  
“These folders have lots of CSVs, reports, figures and scripts. Which files are genuinely redundant, and which ones might be needed by the code or submission?”

**Note:** I compared likely duplicates before deleting anything and kept the scripts that support generation, analysis, export and validation.

### 22. Preparing the project to run elsewhere
**Prompt:**  
“What should someone install and run to reproduce the project from a fresh environment? Which checks should I run before submitting it?”

**Note:** This helped me organize the setup and verification steps. I still need to confirm the final cleaned repository from a fresh environment.

## What I took from the AI assistance

ChatGPT helped me break down the assignment, understand parts of the modelling and evaluation workflow, draft and debug code, and organise the validation and documentation. I reviewed the outputs and made decisions about what to keep, how to describe the model results, and which limitations needed to be visible.

The main parts I need to explain myself are the data-generation process, the 60-day label logic, possible leakage, the model metrics, the treatment/control calculation, and the limits of synthetic data.

**Record note:** These are reconstructed prompt summaries, not a verbatim transcript. If exact prompt history is required, I should attach an export of the original conversations separately.
