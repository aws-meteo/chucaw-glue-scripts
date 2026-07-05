from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from chucaw_preprocessor.cfsv2 import DEFAULT_BBOX, subset_bbox


def _dataset(lats: np.ndarray, lons: np.ndarray) -> xr.Dataset:
    shape = (len(lats), len(lons))
    return xr.Dataset(
        data_vars={"t2m": (("latitude", "longitude"), np.full(shape, 280.0, dtype=np.float32))},
        coords={"latitude": lats, "longitude": lons},
    )


def test_subset_bbox_handles_minus180_to_180_convention() -> None:
    lats = np.arange(0.0, -60.0, -2.0, dtype=np.float64)  # descending, covers -56..-17
    lons = np.arange(-90.0, -60.0, 2.0, dtype=np.float64)  # covers -76..-66
    ds = _dataset(lats, lons)

    subset = subset_bbox(ds, **DEFAULT_BBOX)

    assert subset["latitude"].size > 0
    assert subset["longitude"].size > 0
    assert float(subset["latitude"].max()) <= DEFAULT_BBOX["north"]
    assert float(subset["latitude"].min()) >= DEFAULT_BBOX["south"]
    assert float(subset["longitude"].min()) >= DEFAULT_BBOX["west"]
    assert float(subset["longitude"].max()) <= DEFAULT_BBOX["east"]


def test_subset_bbox_handles_0_to_360_convention() -> None:
    lats = np.arange(0.0, -60.0, -2.0, dtype=np.float64)
    lons = np.arange(270.0, 300.0, 2.0, dtype=np.float64)  # equivalent to -90..-60
    ds = _dataset(lats, lons)

    subset = subset_bbox(ds, **DEFAULT_BBOX)

    assert subset["latitude"].size > 0
    assert subset["longitude"].size > 0
    # -76..-66 maps to 284..294 in the 0..360 convention
    assert float(subset["longitude"].min()) >= 284.0
    assert float(subset["longitude"].max()) <= 294.0


def test_subset_bbox_raises_clear_error_when_selection_is_empty() -> None:
    lats = np.arange(80.0, 60.0, -2.0, dtype=np.float64)  # never overlaps Chile bbox
    lons = np.arange(-90.0, -60.0, 2.0, dtype=np.float64)
    ds = _dataset(lats, lons)

    with pytest.raises(ValueError, match="returned no data"):
        subset_bbox(ds, **DEFAULT_BBOX)


def test_subset_bbox_requires_lat_lon_coords() -> None:
    ds = xr.Dataset(data_vars={"t2m": (("y", "x"), np.zeros((2, 2), dtype=np.float32))})
    with pytest.raises(ValueError, match="latitude/longitude"):
        subset_bbox(ds, **DEFAULT_BBOX)
