from __future__ import annotations

import pytest

from chucaw_preprocessor.cfsv2 import parse_bronze_key

PGBF_KEY = (
    "climate_long_range/provider=noaa/product=cfsv2/version=v0/run_date=20260629/"
    "cycle=00/member=01/product_kind=pgbf/valid_month=202609/raw/"
    "pgbf.01.2026062900.202609.avrg.grib.grb2"
)

FLXF_KEY = (
    "climate_long_range/provider=noaa/product=cfsv2/version=v0/run_date=20260629/"
    "cycle=00/member=01/product_kind=flxf/valid_month=202609/raw/"
    "flxf.01.2026062900.202609.avrg.grib.grb2"
)

SIXHOURLY_KEY = (
    "climate_long_range/provider=noaa/product=cfsv2/version=v0/run_date=20260629/"
    "cycle=00/member=01/product_kind=pgbf/valid_month=202609/raw/"
    "pgbf.01.2026062900.202609.avrg.grib.00Z.grb2"
)


def test_parse_bronze_key_extracts_all_partitions() -> None:
    metadata = parse_bronze_key(PGBF_KEY)
    assert metadata["provider"] == "noaa"
    assert metadata["product"] == "cfsv2"
    assert metadata["version"] == "v0"
    assert metadata["run_date"] == "20260629"
    assert metadata["cycle"] == "00"
    assert metadata["member"] == "01"
    assert metadata["product_kind"] == "pgbf"
    assert metadata["valid_month"] == "202609"
    assert metadata["source_filename"] == "pgbf.01.2026062900.202609.avrg.grib.grb2"


def test_parse_bronze_key_works_for_flxf_product_kind() -> None:
    metadata = parse_bronze_key(FLXF_KEY)
    assert metadata["product_kind"] == "flxf"
    assert metadata["avg_kind"] == "daily"


def test_avg_kind_defaults_to_daily() -> None:
    metadata = parse_bronze_key(PGBF_KEY)
    assert metadata["avg_kind"] == "daily"


def test_avg_kind_is_6hourly_for_00z_suffix() -> None:
    metadata = parse_bronze_key(SIXHOURLY_KEY)
    assert metadata["avg_kind"] == "6hourly"


@pytest.mark.parametrize(
    ("run_date", "valid_month", "expected_lead_month"),
    [
        ("20260910", "202609", 0),
        ("20260629", "202609", 3),
        ("20260629", "202612", 6),
        ("20261129", "202701", 2),  # crosses a year boundary
    ],
)
def test_lead_month_computation(run_date: str, valid_month: str, expected_lead_month: int) -> None:
    key = (
        f"climate_long_range/provider=noaa/product=cfsv2/version=v0/run_date={run_date}/"
        f"cycle=00/member=01/product_kind=pgbf/valid_month={valid_month}/raw/"
        f"pgbf.01.{run_date}00.{valid_month}.avrg.grib.grb2"
    )
    metadata = parse_bronze_key(key)
    assert metadata["lead_month"] == expected_lead_month


def test_parse_bronze_key_raises_clear_error_when_partition_missing() -> None:
    bad_key = "climate_long_range/provider=noaa/product=cfsv2/version=v0/raw/pgbf.grb2"
    with pytest.raises(ValueError, match="run_date"):
        parse_bronze_key(bad_key)
