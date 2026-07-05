"""Glue Python Shell job: CFSv2 monthly Bronze GRIB -> Silver Parquet.

Processes a single Bronze CFSv2 GRIB object (one run_date/cycle/member/product_kind/
valid_month combination), subsets it to the Chile bbox, and writes one tidy Parquet
file to the Silver partition layout. Kept independent of the ECMWF job/partitions.
"""

import json
from pathlib import Path

from chucaw_preprocessor.cfsv2 import (
    DEFAULT_BBOX,
    build_manifest,
    build_output_key,
    parse_bronze_key,
    process_grib_to_long_frame,
    write_long_frame_parquet,
)
from chucaw_preprocessor.ecmwf import download_grib_from_s3, upload_file_to_s3
from chucaw_preprocessor.glue_args import resolve_args

DEFAULT_BRONZE_BUCKET = "chucaw-data-bronze-raw-725644097028-us-east-1-an"
DEFAULT_SILVER_BUCKET = "chucaw-data-platinum-processed-725644097028-us-east-1-an"
DEFAULT_SILVER_PREFIX = "climate_long_range/cfsv2_monthly_chile_long_v0"


def _resolve_bbox(args: dict[str, str]) -> dict[str, float]:
    return {
        "north": float(args.get("BBOX_NORTH") or DEFAULT_BBOX["north"]),
        "south": float(args.get("BBOX_SOUTH") or DEFAULT_BBOX["south"]),
        "west": float(args.get("BBOX_WEST") or DEFAULT_BBOX["west"]),
        "east": float(args.get("BBOX_EAST") or DEFAULT_BBOX["east"]),
    }


def _write_manifest(manifest: dict, silver_bucket: str, silver_key: str, tmp_dir: str) -> str:
    manifest_path = str(Path(tmp_dir) / (Path(silver_key).name + ".manifest.json"))
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)
    manifest_key = f"{silver_key}.manifest.json"
    upload_file_to_s3(manifest_path, silver_bucket, manifest_key)
    return manifest_key


def run_job(args: dict[str, str]) -> dict[str, str]:
    """Execute CFSv2 Bronze -> Silver Parquet transfer for a single Bronze key."""
    bronze_key = (args.get("BRONZE_KEY") or "").strip()
    if not bronze_key:
        raise ValueError("--BRONZE_KEY is required")

    bronze_bucket = args.get("BRONZE_BUCKET") or DEFAULT_BRONZE_BUCKET
    silver_bucket = args.get("SILVER_BUCKET") or DEFAULT_SILVER_BUCKET
    silver_prefix = args.get("SILVER_PREFIX") or DEFAULT_SILVER_PREFIX
    tmp_dir = args.get("TMP_DIR") or "/tmp"
    bbox = _resolve_bbox(args)

    metadata = parse_bronze_key(bronze_key)
    source_s3_uri = f"s3://{bronze_bucket}/{bronze_key}"

    grib_path = download_grib_from_s3(bronze_bucket, bronze_key, download_dir=tmp_dir)
    long_df = process_grib_to_long_frame(grib_path, metadata, bbox, source_s3_uri)

    local_output_path = str(Path(tmp_dir) / f"cfsv2_{Path(bronze_key).stem}.parquet")
    write_long_frame_parquet(long_df, local_output_path)

    silver_key = build_output_key(silver_prefix, metadata)
    upload_file_to_s3(local_output_path, silver_bucket, silver_key)

    result = {
        "status": "ok",
        "bronze_bucket": bronze_bucket,
        "bronze_key": bronze_key,
        "silver_bucket": silver_bucket,
        "silver_key": silver_key,
        "rows": str(len(long_df)),
    }

    if (args.get("WRITE_MANIFEST") or "").strip().lower() in ("1", "true", "yes"):
        manifest = build_manifest(metadata, silver_key, source_s3_uri, len(long_df))
        result["manifest_key"] = _write_manifest(manifest, silver_bucket, silver_key, tmp_dir)

    return result


def main() -> None:
    """Glue entrypoint."""
    args = resolve_args(
        required=[],
        optional=[
            "BRONZE_BUCKET",
            "BRONZE_KEY",
            "SILVER_BUCKET",
            "SILVER_PREFIX",
            "TMP_DIR",
            "BBOX_NORTH",
            "BBOX_SOUTH",
            "BBOX_WEST",
            "BBOX_EAST",
            "WRITE_MANIFEST",
        ],
    )
    result = run_job(args)
    print(result)


if __name__ == "__main__":
    main()
