import os

import pandas as pd
import requests
from flask import Flask, jsonify
from google.cloud import bigquery


app = Flask(__name__)


def get_required_env(name):
    """Read an environment variable and fail clearly if it is missing."""
    value = os.environ.get(name)

    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")

    return value


def read_bigquery_tables():
    """Read the three source tables from BigQuery into pandas DataFrames."""
    client = bigquery.Client()

    costs_table = get_required_env("COSTS_TABLE")
    flow_ownership_table = get_required_env("FLOW_OWNERSHIP_TABLE")
    project_ownership_table = get_required_env("PROJECT_OWNERSHIP_TABLE")

    # Only read the latest day plus the 28 days before it.
    # That is enough data for today's anomaly check.
    costs_sql = f"""
        SELECT
            project,
            flow,
            CAST(day AS DATE) AS day,
            CAST(cost AS FLOAT64) AS cost
        FROM `{costs_table}`
        WHERE CAST(day AS DATE) >= DATE_SUB(
            (SELECT MAX(CAST(day AS DATE)) FROM `{costs_table}`),
            INTERVAL 28 DAY
        )
    """

    flow_ownership_sql = f"""
        SELECT project, flow, owner
        FROM `{flow_ownership_table}`
    """

    project_ownership_sql = f"""
        SELECT project, owner
        FROM `{project_ownership_table}`
    """

    costs = client.query(costs_sql).to_dataframe()
    flow_owners = client.query(flow_ownership_sql).to_dataframe()
    project_owners = client.query(project_ownership_sql).to_dataframe()

    return costs, flow_owners, project_owners


def prepare_data(costs, flow_owners, project_owners):
    """Join costs with owner data and create one final owner column."""
    flow_owners = flow_owners.rename(columns={"owner": "flow_owner"})
    project_owners = project_owners.rename(columns={"owner": "project_owner"})

    data = costs.merge(flow_owners, on=["project", "flow"], how="left")
    data = data.merge(project_owners, on="project", how="left")

    data["owner"] = data["flow_owner"]
    data["owner"] = data["owner"].fillna(data["project_owner"])
    data["owner"] = data["owner"].fillna("Unassigned")

    data = data.drop(columns=["flow_owner", "project_owner"])

    return data


def find_anomalies(data):
    """Compare today's costs with the previous 28 days."""
    data["day"] = pd.to_datetime(data["day"])

    today = data["day"].max()
    baseline_start = today - pd.Timedelta(days=28)

    baseline = data[data["day"] < today]
    baseline = baseline[baseline["day"] >= baseline_start]

    today_data = data[data["day"] == today]

    baseline_stats = baseline.groupby(["project", "flow"])["cost"].agg(
        avg_cost="mean",
        median_cost="median",
        p95_cost=lambda costs: costs.quantile(0.95),
    )

    today_costs = today_data[["project", "flow", "owner", "cost"]]
    today_costs = today_costs.rename(columns={"cost": "today_cost"})

    anomalies = today_costs.merge(baseline_stats, on=["project", "flow"], how="left")

    anomalies["ratio_to_avg"] = anomalies["today_cost"] / anomalies["avg_cost"]
    anomalies["ratio_to_median"] = anomalies["today_cost"] / anomalies["median_cost"]
    anomalies["absolute_increase"] = anomalies["today_cost"] - anomalies["avg_cost"]

    anomalies["is_anomaly"] = (
        (anomalies["today_cost"] > 2 * anomalies["avg_cost"])
        & (anomalies["today_cost"] > anomalies["p95_cost"])
        & (anomalies["absolute_increase"] > 10)
    )

    anomalies = anomalies[anomalies["is_anomaly"]]
    anomalies = anomalies.sort_values("absolute_increase", ascending=False)

    return today, anomalies


def money(value):
    """Format a number for the Slack message."""
    return f"{value:,.2f}"


def make_slack_message(today, anomalies):
    """Create one human-readable Slack message."""
    day_text = today.strftime("%Y-%m-%d")

    if anomalies.empty:
        return f"Daily cost anomaly check for {day_text}: no anomalies found."

    lines = [
        f"Daily cost anomaly check for {day_text}: {len(anomalies)} anomalies found."
    ]

    for _, row in anomalies.head(10).iterrows():
        lines.append(
            "- "
            f"{row['project']} / {row['flow']} "
            f"(owner: {row['owner']}): "
            f"today {money(row['today_cost'])}, "
            f"avg {money(row['avg_cost'])}, "
            f"increase {money(row['absolute_increase'])}, "
            f"{row['ratio_to_avg']:.1f}x avg"
        )

    if len(anomalies) > 10:
        lines.append(f"...and {len(anomalies) - 10} more.")

    return "\n".join(lines)


def post_to_slack(message):
    """Post the summary to Slack if a webhook URL is configured."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")

    if not webhook_url:
        print(message)
        return False

    response = requests.post(webhook_url, json={"text": message}, timeout=10)
    response.raise_for_status()

    return True


def run_job():
    """Run the full daily anomaly check."""
    costs, flow_owners, project_owners = read_bigquery_tables()
    data = prepare_data(costs, flow_owners, project_owners)
    today, anomalies = find_anomalies(data)

    message = make_slack_message(today, anomalies)
    slack_posted = post_to_slack(message)

    return {
        "date": today.strftime("%Y-%m-%d"),
        "anomaly_count": int(len(anomalies)),
        "slack_posted": slack_posted,
        "message": message,
    }


@app.get("/")
def home():
    return jsonify({"service": "cost-anomaly-detector", "status": "ok"})


@app.get("/health")
def health():
    return jsonify({"status": "healthy"})


@app.route("/run", methods=["GET", "POST"])
def run():
    try:
        result = run_job()
        return jsonify(result)
    except Exception as error:
        app.logger.exception("Cost anomaly job failed")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Cost anomaly job failed. Check Cloud Run logs for details.",
                    "error_type": type(error).__name__,
                }
            ),
            500,
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
