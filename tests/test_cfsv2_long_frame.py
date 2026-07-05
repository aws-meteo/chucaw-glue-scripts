from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from chucaw_preprocessor.cfsv2 import build_long_frame_from_datasets, parse_bronze_key

BRONZE_KEY = (
    "climate_long_range/provider=noaa/product=cfsv2/version=v0/run_date=20260629/"
    "cycle=00/member=01/product_kind=pgbf/valid_month=202609/raw/"
    "pgbf.01.2026062900.202609.avrg.grib.grb2"
)
BBOX = {"north": -17.0, "south": -56.0, "west": -76.0, "east": -66.0}


def _synthetic_datasets() -> list[xr.Dataset]:
    lats = np.arange(-20.0, -50.0, -5.0, dtype=np.float64)
    lons = np.arange(-80.0, -60.0, 5.0, dtype=np.float64)
    surf_shape = (len(lats), len(lons))

    surface_ds = xr.Dataset(
        data_vars={
            "t2m": (
                ("latitude", "longitude"),
                np.full(surf_shape, 280.0, dtype=np.float32),
                {"units": "K"},
            )
        },
        coords={"latitude": lats, "longitude": lons},
    )

    levels = np.array([1000.0, 500.0], dtype=np.float64)
    pl_shape = (len(levels), len(lats), len(lons))
    pressure_ds = xr.Dataset(
        data_vars={
            "t": (
                ("isobaricInhPa", "latitude", "longitude"),
                np.full(pl_shape, 260.0, dtype=np.float32),
                {"units": "K"},
            )
        },
        coords={"latitude": lats, "longitude": lons, "isobaricInhPa": levels},
    )

    return [surface_ds, pressure_ds]


def _metadata() -> dict:
    return parse_bronze_key(BRONZE_KEY)


def test_long_frame_has_expected_schema_columns() -> None:
    df = build_long_frame_from_datasets(
        _synthetic_datasets(), _metadata(), BBOX, "s3://bucket/" + BRONZE_KEY
    )
    expected_columns = {
        "provider", "product", "version", "run_date", "cycle", "member",
        "product_kind", "valid_month", "lead_month", "avg_kind",
        "latitude", "longitude", "variable", "level_type", "level_value",
        "value", "unit", "source_s3_uri",
    }
    assert set(df.columns) == expected_columns


def test_long_frame_surface_variable_has_null_level() -> None:
    df = build_long_frame_from_datasets(
        _synthetic_datasets(), _metadata(), BBOX, "s3://bucket/" + BRONZE_KEY
    )
    surface_rows = df[df["variable"] == "t2m"]
    assert not surface_rows.empty
    assert (surface_rows["level_type"] == "surface").all()
    assert surface_rows["level_value"].isna().all()
    assert (surface_rows["unit"] == "K").all()


def test_long_frame_pressure_level_variable_encodes_level_type_and_value() -> None:
    df = build_long_frame_from_datasets(
        _synthetic_datasets(), _metadata(), BBOX, "s3://bucket/" + BRONZE_KEY
    )
    level_rows = df[df["variable"] == "t"]
    assert not level_rows.empty
    assert (level_rows["level_type"] == "isobaricInhPa").all()
    assert set(level_rows["level_value"].unique()) == {1000.0, 500.0}


def test_long_frame_value_dtype_is_float32() -> None:
    df = build_long_frame_from_datasets(
        _synthetic_datasets(), _metadata(), BBOX, "s3://bucket/" + BRONZE_KEY
    )
    assert df["value"].dtype == np.float32


def test_long_frame_carries_metadata_and_source_uri() -> None:
    source_uri = "s3://bucket/" + BRONZE_KEY
    df = build_long_frame_from_datasets(_synthetic_datasets(), _metadata(), BBOX, source_uri)
    assert (df["run_date"] == "20260629").all()
    assert (df["member"] == "01").all()
    assert (df["lead_month"] == 3).all()
    assert (df["source_s3_uri"] == source_uri).all()


def test_long_frame_raises_when_no_data_variables_in_bbox() -> None:
    with pytest.raises(ValueError):
        build_long_frame_from_datasets([], _metadata(), BBOX, "s3://bucket/key")
