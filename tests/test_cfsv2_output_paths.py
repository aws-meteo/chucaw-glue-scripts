from __future__ import annotations

from chucaw_preprocessor.cfsv2 import build_manifest, build_output_key, parse_bronze_key

BRONZE_KEY = (
    "climate_long_range/provider=noaa/product=cfsv2/version=v0/run_date=20260629/"
    "cycle=00/member=01/product_kind=pgbf/valid_month=202609/raw/"
    "pgbf.01.2026062900.202609.avrg.grib.grb2"
)
SILVER_PREFIX = "climate_long_range/cfsv2_monthly_chile_long_v0"


def test_build_output_key_matches_expected_partition_layout() -> None:
    metadata = parse_bronze_key(BRONZE_KEY)
    key = build_output_key(SILVER_PREFIX, metadata)
    assert key == (
        "climate_long_range/cfsv2_monthly_chile_long_v0"
        "/run_date=20260629/cycle=00/member=01/product_kind=pgbf"
        "/valid_month=202609/avg_kind=daily/part-000.parquet"
    )


def test_build_output_key_strips_trailing_slash_on_prefix() -> None:
    metadata = parse_bronze_key(BRONZE_KEY)
    key = build_output_key(SILVER_PREFIX + "/", metadata)
    assert key.startswith("climate_long_range/cfsv2_monthly_chile_long_v0/run_date=")


def test_output_key_does_not_depend_on_ecmwf_date_run_partitions() -> None:
    """CFSv2 must use its own partition scheme, not ECMWF's year=/month=/day=/hour= layout."""
    metadata = parse_bronze_key(BRONZE_KEY)
    key = build_output_key(SILVER_PREFIX, metadata)
    partition_names = {segment.split("=", 1)[0] for segment in key.split("/") if "=" in segment}
    assert partition_names == {"run_date", "cycle", "member", "product_kind", "valid_month", "avg_kind"}
    assert "run_date=20260629" in key


def test_build_manifest_contains_key_metadata_fields() -> None:
    metadata = parse_bronze_key(BRONZE_KEY)
    silver_key = build_output_key(SILVER_PREFIX, metadata)
    manifest = build_manifest(metadata, silver_key, "s3://bucket/" + BRONZE_KEY, row_count=42)
    assert manifest["run_date"] == "20260629"
    assert manifest["silver_key"] == silver_key
    assert manifest["row_count"] == 42
    assert manifest["source_filename"] == "pgbf.01.2026062900.202609.avrg.grib.grb2"
