"""Audit one Platinum Parquet partition for FourCastNet readiness."""

from __future__ import annotations

import json
from pathlib import Path

import boto3
import pandas as pd

from chucaw_preprocessor.fourcastnet import (
    build_available_variable_levels,
    build_validation_report,
)
from chucaw_preprocessor.glue_args import resolve_args

DEFAULT_PLATINUM_BUCKET = "chucaw-data-platinum-processed-725644097028-us-east-1-an"
DEFAULT_PLATINUM_PARQUET_PREFIX = "ecmwf/parquet"


def _normalize_hour_arg(hour_value: str) -> tuple[str, str]:
    raw = str(hour_value or "").strip().lower()
    if not raw:
        raise ValueError("HOUR cannot be empty")
    if raw.endswith("z"):
        raw = raw[:-1]
    hour_num = int(raw)
    if hour_num < 0 or hour_num > 23:
        raise ValueError(f"Invalid HOUR value: {hour_value}")
    partition_hour = f"{hour_num:02d}"
    run_hour = f"{partition_hour}z"
    return partition_hour, run_hour


def _partition_prefix(base_prefix: str, year: str, month: str, day: str, partition_hour: str) -> str:
    return (
        f"{base_prefix.strip('/')}"
        f"/year={year}/month={month}/day={day}/hour={partition_hour}"
    ).strip("/")


def _read_partition_from_s3(bucket: str, prefix: str, tmp_dir: str) -> pd.DataFrame:
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    parquet_keys: list[str] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix.rstrip('/')}/"):
        for item in page.get("Contents", []):
            key = item["Key"]
            if key.endswith(".parquet"):
                parquet_keys.append(key)

    if not parquet_keys:
        raise RuntimeError(f"No parquet files found under s3://{bucket}/{prefix}")

    local_tmp = Path(tmp_dir)
    local_tmp.mkdir(parents=True, exist_ok=True)
    local_paths: list[str] = []

    for key in sorted(parquet_keys):
        local_file = local_tmp / Path(key).name
        s3.download_file(bucket, key, str(local_file))
        local_paths.append(str(local_file))

    frames = [pd.read_parquet(path) for path in local_paths]
    return pd.concat(frames, ignore_index=True)


def run_audit(args: dict[str, str]) -> dict[str, str]:
    bucket = args.get("PLATINUM_BUCKET") or DEFAULT_PLATINUM_BUCKET
    parquet_prefix = args.get("PLATINUM_PARQUET_PREFIX") or DEFAULT_PLATINUM_PARQUET_PREFIX
    year = f"{int(args['YEAR']):04d}"
    month = f"{int(args['MONTH']):02d}"
    day = f"{int(args['DAY']):02d}"
    partition_hour, run_hour = _normalize_hour_arg(args["HOUR"])

    output_dir = Path(args.get("OUTPUT_DIR") or "./tmp/fourcastnet_partition_audit").expanduser()
    latitude_policy = args.get("LATITUDE_POLICY") or "fail"
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = str(output_dir / "tmp")

    source_partition = _partition_prefix(parquet_prefix, year, month, day, partition_hour)
    df = _read_partition_from_s3(bucket, source_partition, tmp_dir)

    levels_df = build_available_variable_levels(df)
    validation = build_validation_report(df, latitude_policy=latitude_policy)

    available_variables = {
        "bucket": bucket,
        "source_partition": source_partition,
        "year": year,
        "month": month,
        "day": day,
        "hour": partition_hour,
        "run_hour": run_hour,
        "row_count": int(len(df)),
        "available_variables": sorted(
            df["variable"].astype(str).str.lower().dropna().unique().tolist()
        )
        if "variable" in df.columns
        else [],
    }

    variables_json_path = output_dir / "available_variables.json"
    levels_csv_path = output_dir / "available_variable_levels.csv"
    validation_json_path = output_dir / "validation_report.json"
    manifest_json_path = output_dir / "manifest.json"
    manifest = {
        "status": "ok" if validation.get("ok", False) else "incomplete",
        "source_partition": source_partition,
        "latitude_policy": latitude_policy,
        "tensor_written": False,
        "tensor_write_reason": "audit_only",
    }

    variables_json_path.write_text(json.dumps(available_variables, indent=2, sort_keys=True), encoding="utf-8")
    levels_df.to_csv(levels_csv_path, index=False)
    validation_json_path.write_text(json.dumps(validation, indent=2, sort_keys=True), encoding="utf-8")
    manifest_json_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "status": manifest["status"],
        "manifest_json": str(manifest_json_path),
        "available_variables_json": str(variables_json_path),
        "available_variable_levels_csv": str(levels_csv_path),
        "validation_report_json": str(validation_json_path),
        "source_partition": source_partition,
    }


def main() -> None:
    args = resolve_args(
        required=["YEAR", "MONTH", "DAY", "HOUR"],
        optional=[
            "PLATINUM_BUCKET",
            "PLATINUM_PARQUET_PREFIX",
            "OUTPUT_DIR",
            "LATITUDE_POLICY",
        ],
    )
    result = run_audit(args)
    print(result)


if __name__ == "__main__":
    main()
