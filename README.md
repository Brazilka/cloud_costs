# Cost anomaly detector

This project has two parts:

- `local-run-prep.py` is the local learning version. It reads CSV files.
- `main.py` is the GCP version. It reads BigQuery tables and runs on Cloud Run.

## What the cloud version does

1. Cloud Scheduler calls the Cloud Run URL once per day.
2. Cloud Run starts the Python app.
3. The app reads costs and ownership data from BigQuery.
4. The app compares today's cost with the previous 28 days.
5. The app sends one summary message to Slack.

## Required BigQuery tables

The app expects these columns:

- costs table: `project`, `flow`, `day`, `cost`
- flow ownership table: `project`, `flow`, `owner`
- project ownership table: `project`, `owner`

## Environment variables

Set these on Cloud Run:

- `COSTS_TABLE`: BigQuery table id, for example `project.dataset.xy`
- `FLOW_OWNERSHIP_TABLE`: BigQuery table id, for example `project.dataset.xy`
- `PROJECT_OWNERSHIP_TABLE`: BigQuery table id, for example `project.dataset.xy`
- `SLACK_WEBHOOK_URL`: Slack incoming webhook URL

## Deploy to Cloud Run

Replace the placeholder values first.

```bash
gcloud run deploy cost-anomaly-detector \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars COSTS_TABLE="project-c4f8de0b-5696-4403-a71.heureka.costs" \
  --set-env-vars FLOW_OWNERSHIP_TABLE="project-c4f8de0b-5696-4403-a71.heureka.flow_ownership" \
  --set-env-vars PROJECT_OWNERSHIP_TABLE="project-c4f8de0b-5696-4403-a71.heureka.project_ownership" \
  --set-env-vars SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

Cloud Run will print a service URL. The daily endpoint is:

```text
https://YOUR-CLOUD-RUN-URL/run
```

## Create the daily Cloud Scheduler trigger

Replace `YOUR-CLOUD-RUN-URL` with the URL from Cloud Run.

```bash
gcloud scheduler jobs create http cost-anomaly-detector-daily \
  --location europe-west1 \
  --schedule "0 8 * * *" \
  --time-zone "Europe/Prague" \
  --uri "https://costs-586224708135.europe-west1.run.app/run" \
  --http-method POST
```

This example runs every day at 08:00 Prague time.

## Permissions

The Cloud Run service account needs permission to read the BigQuery tables.

At minimum, grant it:

- `BigQuery Data Viewer`
- `BigQuery Job User`

## Local note

The cloud app needs Google credentials and real BigQuery table names. The local CSV script is still the easiest way to understand and test the pandas logic.
