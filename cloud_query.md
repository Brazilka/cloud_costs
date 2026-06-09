Context: The BI team runs workloads on Google Cloud Platform. Projects spin up pipelines, analysts run ad-hoc queries, and costs accumulate across flows. Right now, nobody has a reliable way to know when something is burning money unexpectedly — until they check the billing dashboard, which nobody does consistently.

Agent instructions: Write simple and understandeable code in small pieces. Write code in a way that a beginner would. Keep the code as concise as possible. 

Goal: Build a daily job that queries BigQuery to detect cost anomalies across flows, posts a single, well-structured natural language summary to Slack, runs on GCP using Cloud Run and is triggered by Cloud Scheduler.

Sample prompts:
Step 1: Load and prepare data locally

- Read costs.csv, flow_ownership.csv, and project_ownership.csv with pandas.
- Join costs to flow_ownership using project + flow.
- Join the result to project_ownership using project.
- Resolve final owner:
    1. flow owner
    2. project owner
    3. "Unassigned"
Step 2: Flag anomalies

For each project + flow:

- Use the previous 28 days as the baseline.
- Calculate:
    - avg_cost
    - median_cost
    - p95_cost
    - today_cost
    - ratio_to_avg
    - ratio_to_median
    - absolute_increase

Flag as anomaly if:

today_cost > 2 × avg_cost
AND today_cost > p95_cost
AND absolute_increase > 10
