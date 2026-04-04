"""Glue Python Shell job to transform Bronze GRIB into Platinum Parquet.

This module resolves a GRIB source key from explicit arguments or by discovery,
builds normalized surface/upper dataframes, and uploads partitioned parquet files
to the Platinum bucket.
"""

import re
from datetime import datetime
from pathlib import Path

import boto3

from chucaw_preprocessor.ecmwf import (
    serialize_parquet_chunked,
    download_grib_from_s3,
    load_merged_dataset,
    upload_file_to_s3,
)
from chucaw_preprocessor.glue_args import resolve_args

DEFAULT_BRONZE_BUCKET = "chucaw-data-bronze-raw-725644097028-us-east-1-an"
DEFAULT_PLATINUM_BUCKET = "chucaw-data-platinum-processed-725644097028-us-east-1-an"
DEFAULT_BRONZE_PREFIX = ""
DEFAULT_PLATINUM_PREFIX = "ecmwf/parquet"


def _normalize_run(run_value: str) -> str:
    """Normalize run values to ECMWF format.

    Parameters
    ----------
    run_value : str
        Input run value such as ``"00"`` or ``"00z"``.

    Returns
    -------
    str
        Normalized run value in ``XXz`` format.
    """
    run_value = (run_value or "").strip().lower()
    if not run_value:
        return "00z"
    return run_value if run_value.endswith("z") else f"{run_value}z"


def _extract_date_run_from_key(bronze_key: str) -> tuple[str, str]:
    """Extract date and run from a Bronze S3 key.

    Parameters
    ----------
    bronze_key : str
        S3 object key pointing to a GRIB file.

    Returns
    -------
    tuple[str, str]
        Tuple with ``(date_yyyymmdd, run_xxz)``.
    """
    date_match = re.search(r"(20\d{6})", bronze_key)
    run_match = re.search(r"/(00z|06z|12z|18z)/", bronze_key.lower())
    date_str = date_match.group(1) if date_match else datetime.utcnow().strftime("%Y%m%d")
    run_str = run_match.group(1) if run_match else "00z"
    return date_str, run_str


def _candidate_key_from_date_run(bronze_prefix: str, date_str: str, run_str: str) -> str:
    base_name = f"{date_str}{run_str[:2]}0000-0h-oper-fc.grib2"
    prefix = bronze_prefix.strip("/")
    chunks = [prefix, date_str, run_str, "ifs", "0p25", "oper", base_name]
    return "/".join([chunk for chunk in chunks if chunk])


def _find_latest_grib_key(bronze_bucket: str, bronze_prefix: str) -> str:
    """Find the latest ``.grib2`` object in a Bronze prefix."""
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    latest_key = ""
    latest_ts = None
    prefix = bronze_prefix.strip("/")
    kwargs = {"Bucket": bronze_bucket}
    if prefix:
        kwargs["Prefix"] = f"{prefix}/"

    for page in paginator.paginate(**kwargs):
        for item in page.get("Contents", []):
            key = item["Key"]
            if key.endswith(".grib2"):
                if latest_ts is None or item["LastModified"] > latest_ts:
                    latest_key = key
                    latest_ts = item["LastModified"]

    if not latest_key:
        raise RuntimeError(
            f"No se encontraron archivos .grib2 en s3://{bronze_bucket}/{prefix or ''}"
        )
    return latest_key


def _resolve_bronze_key(args: dict[str, str]) -> str:
    """Resolve source GRIB key from arguments.

    Resolution order:
    1. ``--BRONZE_KEY``
    2. ``--DATE`` + ``--RUN`` (build candidate path)
    3. Latest ``.grib2`` in ``--BRONZE_PREFIX``
    """
    bronze_key = (args.get("BRONZE_KEY") or "").strip()
    bronze_prefix = (args.get("BRONZE_PREFIX") or DEFAULT_BRONZE_PREFIX).strip("/")
    date_str = (args.get("DATE") or "").strip()
    run_str = _normalize_run(args.get("RUN") or "")

    if bronze_key:
        return bronze_key
    if date_str:
        return _candidate_key_from_date_run(bronze_prefix, date_str, run_str)
    return _find_latest_grib_key(args["BRONZE_BUCKET"], bronze_prefix)


def _partition_prefix(base_prefix: str, date_str: str, run_str: str) -> str:
    parsed = datetime.strptime(date_str, "%Y%m%d")
    return (
        f"{base_prefix.strip('/')}"
        f"/year={parsed.year:04d}/month={parsed.month:02d}"
        f"/day={parsed.day:02d}/run={run_str}"
    ).strip("/")


def run_job(args: dict[str, str]) -> dict[str, str]:
    """Execute Bronze -> Platinum Parquet transfer.

    Parameters
    ----------
    args : dict[str, str]
        Glue/Python-shell arguments.

    Returns
    -------
    dict[str, str]
        Execution summary with source/target details.
    """
    bronze_bucket = args.get("BRONZE_BUCKET") or DEFAULT_BRONZE_BUCKET
    platinum_bucket = args.get("PLATINUM_BUCKET") or DEFAULT_PLATINUM_BUCKET
    platinum_prefix = args.get("PLATINUM_PREFIX") or DEFAULT_PLATINUM_PREFIX
    tmp_dir = args.get("TMP_DIR") or "/tmp"

    args["BRONZE_BUCKET"] = bronze_bucket
    bronze_key = _resolve_bronze_key(args)
    date_str, inferred_run = _extract_date_run_from_key(bronze_key)
    run_str = _normalize_run(args.get("RUN") or inferred_run)

    grib_path = download_grib_from_s3(bronze_bucket, bronze_key, download_dir=tmp_dir)
    ds = load_merged_dataset(grib_path)

    output_dir = str(Path(tmp_dir) / "parquet")
    surface_path, upper_path = serialize_parquet_chunked(
        ds, output_dir=output_dir, date_str=date_str, run_str=run_str
    )
    target_prefix = _partition_prefix(platinum_prefix, date_str, run_str)

    surface_key = f"{target_prefix}/dataset=surface/part-000.parquet"
    upper_key = f"{target_prefix}/dataset=upper/part-000.parquet"
    upload_file_to_s3(surface_path, platinum_bucket, surface_key)
    upload_file_to_s3(upper_path, platinum_bucket, upper_key)

    return {
        "status": "ok",
        "bronze_bucket": bronze_bucket,
        "bronze_key": bronze_key,
        "platinum_bucket": platinum_bucket,
        "surface_key": surface_key,
        "upper_key": upper_key,
        "date": date_str,
        "run": run_str,
    }


def main() -> None:
    """Glue entrypoint."""
    args = resolve_args(
        required=[],
        optional=[
            "BRONZE_BUCKET",
            "BRONZE_KEY",
            "BRONZE_PREFIX",
            "PLATINUM_BUCKET",
            "PLATINUM_PREFIX",
            "DATE",
            "RUN",
            "TMP_DIR",
        ],
    )
    result = run_job(args)
    print(result)


if __name__ == "__main__":
    main()
