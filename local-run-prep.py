import pandas as pd

costs = pd.read_csv("costs.csv")
flow_owners = pd.read_csv("flow_ownership.csv")
project_owners = pd.read_csv("project_ownership.csv")

# Both ownership files have a column named "owner".
# Rename the columns so we can tell them apart after joining the tables.
flow_owners = flow_owners.rename(columns={"owner": "flow_owner"})
project_owners = project_owners.rename(columns={"owner": "project_owner"})

# Take the costs.csv table and add matching data from flow_owners.csv.
# Match rows where both "project" and "flow" are the same.
#
# .merge(...) is a DataFrame method.
# "how='left'" means: keep all rows from the left table (costs),
# even if there is no matching owner row.
data = costs.merge(flow_owners, on=["project", "flow"], how="left")

# Add the project owner too.
# This match only uses the "project" column.
data = data.merge(project_owners, on="project", how="left")

# Create one final "owner" column.
#
# data["flow_owner"] means: take the "flow_owner" column from the table.
# data["owner"] = ... means: create or replace the "owner" column.
data["owner"] = data["flow_owner"]

# .fillna(...) is a Series method.
# A Series is basically one column from a DataFrame.
#
# First, fill missing flow owners with the project owner.
data["owner"] = data["owner"].fillna(data["project_owner"])

# Then, if the owner is still missing, use the text "Unassigned".
data["owner"] = data["owner"].fillna("Unassigned")

# Drop helper columns, so there is only one owner column in the final table.
data = data.drop(columns=["flow_owner", "project_owner"])

# Save the cleaned table to a CSV file.
# index=False means: do not write pandas' row numbers into the file.
data.to_csv("final.csv", index=False)

# Show the first 100 rows in the terminal so we can quickly check the result.
print(data.head(100))

# Detect anomalies.

# Convert the "day" column from text into real dates.
# pd.to_datetime(...) is a pandas function.
data["day"] = pd.to_datetime(data["day"])

# Find the latest date in the data.
#
# data["day"] selects the "day" column.
# .max() is a method that returns the biggest/latest value in that column.
# This script treats the latest date in the file as "today".
today = data["day"].max()

# Create a date that is 28 days before "today".
#
# pd.Timedelta(days=28) means "a length of time equal to 28 days".
# Subtracting it from today gives the start of the comparison period.
baseline_start = today - pd.Timedelta(days=28)

# Build the baseline table: the recent past we compare today against.
#
# data["day"] < today creates a True/False column:
# True for rows before today, False for today's rows.
#
# data[that True/False column] keeps only the rows where the condition is True.
baseline = data[data["day"] < today]

# Keep only baseline rows from the last 28 days.
# This removes older history that should not be used for comparison.
baseline = baseline[baseline["day"] >= baseline_start]

# Keep only rows from today.
today_data = data[data["day"] == today]

# For each project+flow pair, calculate normal historical cost numbers.
#
# .groupby(["project", "flow"]) means:
#   split the table into groups where project and flow are the same.
#
# ["cost"] means:
#   only calculate stats from the "cost" column.
#
# .agg(...) means:
#   aggregate each group into summary numbers.
baseline_stats = baseline.groupby(["project", "flow"])["cost"].agg(
    avg_cost="mean",
    median_cost="median",
    p95_cost=lambda costs: costs.quantile(0.95),
)

# Keep the identifying columns and today's cost.
today_costs = today_data[["project", "flow", "owner", "cost"]]

# Rename "cost" to "today_cost" so it is clear this number is only for today.
today_costs = today_costs.rename(columns={"cost": "today_cost"})

# Put today's cost next to the historical baseline stats for the same project+flow.
anomalies = today_costs.merge(baseline_stats, on=["project", "flow"], how="left")

# Calculate comparison numbers.
# Example: ratio_to_avg = 3 means today's cost is 3 times the average.
anomalies["ratio_to_avg"] = anomalies["today_cost"] / anomalies["avg_cost"]
anomalies["ratio_to_median"] = anomalies["today_cost"] / anomalies["median_cost"]
anomalies["absolute_increase"] = anomalies["today_cost"] - anomalies["avg_cost"]

# Mark a row as an anomaly only if all three checks are true:
# 1. today's cost is more than 2x the recent average
# 2. today's cost is above the 95th percentile of recent costs
# 3. today's cost increased by more than 10 currency units
anomalies["is_anomaly"] = (
    (anomalies["today_cost"] > 2 * anomalies["avg_cost"])
    & (anomalies["today_cost"] > anomalies["p95_cost"])
    & (anomalies["absolute_increase"] > 10)
)

# Keep only the rows marked as anomalies.
anomalies = anomalies[anomalies["is_anomaly"]]

# Save anomalies to a CSV file.
anomalies.to_csv("anomalies.csv", index=False)

# Print anomalies in the terminal.
print(anomalies)
