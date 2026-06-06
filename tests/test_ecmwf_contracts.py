from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from chucaw_preprocessor.ecmwf import (
    EXPECTED_PRESSURE_LEVELS,
    PANGU_SURFACE_VARS,
    PANGU_UPPER_VARS,
    build_pangu_arrays,
    build_parquet_frames,
    serialize_parquet_chunked,
)
from chucaw_preprocessor.fourcastnet import build_fourcastnet_tensor


def _base_dataset(include_r: bool, include_extra_level: bool) -> xr.Dataset:
    lats = np.array([90.0, 89.75], dtype=np.float32)
    lons = np.array([0.0, 0.25], dtype=np.float32)
    levels = np.array(EXPECTED_PRESSURE_LEVELS, dtype=np.float32)
    if include_extra_level:
        levels = np.concatenate([levels, np.array([775.0], dtype=np.float32)])

    surf_shape = (len(lats), len(lons))
    pl_shape = (len(levels), len(lats), len(lons))

    ds = xr.Dataset(
        data_vars={
            "msl": (("latitude", "longitude"), np.full(surf_shape, 100000.0, dtype=np.float32)),
            "u10": (("latitude", "longitude"), np.full(surf_shape, 1.0, dtype=np.float32)),
            "v10": (("latitude", "longitude"), np.full(surf_shape, 2.0, dtype=np.float32)),
            "t2m": (("latitude", "longitude"), np.full(surf_shape, 280.0, dtype=np.float32)),
            "sp": (("latitude", "longitude"), np.full(surf_shape, 99000.0, dtype=np.float32)),
            "tcwv": (("latitude", "longitude"), np.full(surf_shape, 10.0, dtype=np.float32)),
            "q": (("isobaricInhPa", "latitude", "longitude"), np.full(pl_shape, 0.004, dtype=np.float32)),
            "t": (("isobaricInhPa", "latitude", "longitude"), np.full(pl_shape, 260.0, dtype=np.float32)),
            "u": (("isobaricInhPa", "latitude", "longitude"), np.full(pl_shape, 5.0, dtype=np.float32)),
            "v": (("isobaricInhPa", "latitude", "longitude"), np.full(pl_shape, -5.0, dtype=np.float32)),
            "gh": (("isobaricInhPa", "latitude", "longitude"), np.full(pl_shape, 100.0, dtype=np.float32)),
            "foo_surface_extra": (("latitude", "longitude"), np.full(surf_shape, 7.0, dtype=np.float32)),
        },
        coords={"latitude": lats, "longitude": lons, "isobaricInhPa": levels},
    )
    if include_r:
        ds["r"] = (("isobaricInhPa", "latitude", "longitude"), np.full(pl_shape, 70.0, dtype=np.float32))
    return ds


def _fcn_df_for_test_grid() -> pd.DataFrame:
    lats = np.array([90.0, 89.75], dtype=np.float32)
    lons = np.array([0.0, 0.25], dtype=np.float32)
    channels = [
        ("u10", None), ("v10", None), ("t2m", None), ("sp", None), ("msl", None),
        ("t", 850.0), ("u", 1000.0), ("v", 1000.0), ("z", 1000.0), ("u", 850.0),
        ("v", 850.0), ("z", 850.0), ("u", 500.0), ("v", 500.0), ("z", 500.0),
        ("t", 500.0), ("z", 50.0), ("r", 500.0), ("r", 850.0), ("tcwv", None),
    ]
    rows: list[dict[str, float | str]] = []
    for cidx, (var, level) in enumerate(channels):
        for lat in lats:
            for lon in lons:
                rows.append(
                    {
                        "isobaricInhPa": np.nan if level is None else float(level),
                        "latitude": float(lat),
                        "longitude": float(lon),
                        "variable": var,
                        "value": float(cidx + lat * 0.001 + lon * 0.001),
                        "date": "20260511",
                        "run": "00z",
                    }
                )
    return pd.DataFrame(rows)


def test_pangu_shape_is_strict_with_extra_vars_and_levels() -> None:
    ds = _base_dataset(include_r=True, include_extra_level=True)
    surface, upper = build_pangu_arrays(ds)
    assert surface.shape[0] == len(PANGU_SURFACE_VARS)
    assert upper.shape[0] == len(PANGU_UPPER_VARS) + 1  # +z
    assert surface.shape == (4, 2, 2)
    assert upper.shape == (5, len(EXPECTED_PRESSURE_LEVELS), 2, 2)


def test_build_parquet_frames_includes_r_when_present_and_not_when_absent() -> None:
    ds_with_r = _base_dataset(include_r=True, include_extra_level=False)
    _, upper_with_r = build_parquet_frames(ds_with_r)
    assert "r" in set(upper_with_r["variable"].astype(str))

    ds_without_r = _base_dataset(include_r=False, include_extra_level=False)
    _, upper_without_r = build_parquet_frames(ds_without_r)
    assert "r" not in set(upper_without_r["variable"].astype(str))


def test_serialize_parquet_chunked_includes_extra_pressure_levels_for_platinum(tmp_path: Path) -> None:
    ds = _base_dataset(include_r=True, include_extra_level=True)
    out_path = tmp_path / "platinum.parquet"
    serialize_parquet_chunked(ds, str(out_path), "20260511", "00z")

    df = pd.read_parquet(out_path)
    r_levels = (
        df[df["variable"] == "r"]["isobaricInhPa"]
        .dropna()
        .astype(float)
        .unique()
        .tolist()
    )
    assert 775.0 in r_levels


def test_fourcastnet_tensor_contract_is_explicit_and_stable_for_test_grid() -> None:
    df = _fcn_df_for_test_grid()
    tensor = build_fourcastnet_tensor(
        df,
        expected_lats=np.array([90.0, 89.75], dtype=np.float32),
        expected_lons=np.array([0.0, 0.25], dtype=np.float32),
        validate_shape=False,
    )
    assert tensor.shape == (1, 20, 2, 2)
