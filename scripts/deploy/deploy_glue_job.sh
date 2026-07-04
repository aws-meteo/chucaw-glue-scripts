#!/usr/bin/env bash
#
# Deploy a single AWS Glue job from its glue/jobs/<name>/ folder.
#
# What it does:
#   1. Reads job.json and extracts Command.ScriptLocation (the S3 URI for the script).
#   2. Uploads scripts/glue_jobs/<basename-of-ScriptLocation> to that S3 URI.
#   3. Creates the job (aws glue create-job) if it does not exist, otherwise updates it
#      (aws glue update-job) using an update payload derived from job.json.
#
# The Glue job name is job.json's "Name" (which equals the folder name by convention).
# There is a single source of truth per job (job.json); the update payload is generated
# on the fly, so no separate update-job.json is needed.
#
# Usage:
#   scripts/deploy/deploy_glue_job.sh glue/jobs/bronze_to_platinum_as_parquet
#   scripts/deploy/deploy_glue_job.sh --dry-run glue/jobs/bronze_to_pangu
#
# Requires: aws CLI, jq. AWS credentials must already be configured in the environment
# (in CI this is done by aws-actions/configure-aws-credentials via GitHub OIDC).
#
set -euo pipefail

DRY_RUN=0
JOB_DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) JOB_DIR="${1%/}"; shift ;;
  esac
done

if [ -z "$JOB_DIR" ]; then
  echo "ERROR: pass a job folder, e.g. glue/jobs/bronze_to_platinum_as_parquet" >&2
  exit 2
fi

# Resolve repo root relative to this script so it works from any CWD.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
JOB_JSON="$REPO_ROOT/$JOB_DIR/job.json"

if [ ! -f "$JOB_JSON" ]; then
  echo "ERROR: not found: $JOB_JSON" >&2
  exit 2
fi

command -v jq >/dev/null || { echo "ERROR: jq is required" >&2; exit 2; }

JOB_NAME="$(jq -r '.Name' "$JOB_JSON")"
SCRIPT_S3="$(jq -r '.Command.ScriptLocation' "$JOB_JSON")"
SCRIPT_BASENAME="$(basename "$SCRIPT_S3")"
LOCAL_SCRIPT="$REPO_ROOT/scripts/glue_jobs/$SCRIPT_BASENAME"

if [ "$JOB_NAME" = "null" ] || [ -z "$JOB_NAME" ]; then
  echo "ERROR: job.json has no .Name: $JOB_JSON" >&2
  exit 2
fi
if [ "$SCRIPT_S3" = "null" ] || [ -z "$SCRIPT_S3" ]; then
  echo "ERROR: job.json has no .Command.ScriptLocation: $JOB_JSON" >&2
  exit 2
fi
if [ ! -f "$LOCAL_SCRIPT" ]; then
  echo "ERROR: script referenced by ScriptLocation not found locally: $LOCAL_SCRIPT" >&2
  exit 2
fi

echo "== Deploying Glue job: $JOB_NAME =="
echo "   script:   $LOCAL_SCRIPT"
echo "   uploadTo: $SCRIPT_S3"

run() {
  # Print the command; execute it unless --dry-run.
  echo "+ $*"
  if [ "$DRY_RUN" -eq 0 ]; then
    "$@"
  fi
}

# 1. Upload the job script to S3.
run aws s3 cp "$LOCAL_SCRIPT" "$SCRIPT_S3"

# 2. Create or update the job.
JOB_EXISTS=0
if [ "$DRY_RUN" -eq 0 ]; then
  if aws glue get-job --job-name "$JOB_NAME" >/dev/null 2>&1; then
    JOB_EXISTS=1
  fi
else
  echo "+ aws glue get-job --job-name $JOB_NAME   # (dry-run: assuming job does not exist)"
fi

if [ "$JOB_EXISTS" -eq 1 ]; then
  echo "-> job exists; updating"
  # AWS Glue's JobUpdate structure does not accept Name or Tags (Tags are only
  # honored by create-job / the tag-resource API), so strip both for the update.
  UPDATE_PAYLOAD="$(jq '{JobName: .Name, JobUpdate: (del(.Name, .Tags))}' "$JOB_JSON")"
  if [ "$DRY_RUN" -eq 0 ]; then
    echo "$UPDATE_PAYLOAD" | aws glue update-job --cli-input-json file:///dev/stdin
  else
    echo "+ aws glue update-job --cli-input-json <derived-from-job.json>"
  fi
else
  echo "-> job does not exist; creating"
  run aws glue create-job --cli-input-json "file://$JOB_JSON"
fi

echo "== Done: $JOB_NAME =="
