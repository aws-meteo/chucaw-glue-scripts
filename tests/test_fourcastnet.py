import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from chucaw_preprocessor.fourcastnet import (
    FOURCASTNET_CONTRACT_VERSION,
    FOURCASTNET_DROPPED_STATS_CHANNEL_NAME,
    FourCastNetV0Contract,
    build_fourcastnet_channel_map,
    build_fourcastnet_contract_manifest,
    build_fourcastnet_tensor,
    build_validation_report,
    field_to_grid,
    normalize_fourcastnet_tensor,
    normalize_level_column,
    normalize_longitudes,
    prepare_fourcastnet_stats,
    resolve_expected_lats,
    select_channel_frame,
    write_manifest,
)


def _make_complete_df() -> pd.DataFrame:
    test_lats = np.array([90.0, 89.75], dtype=np.float32)
    test_lons = np.array([0.0, 0.25, 0.5], dtype=np.float32)
    rows = []
    channel_map = build_fourcastnet_channel_map()
    for cidx, (variable, level) in enumerate(channel_map):
        for i, lat in enumerate(test_lats):
            for j, lon in enumerate(test_lons):
                rows.append(
                    {
                        "isobaricInhPa": np.nan if level is None else float(level),
                        "latitude": float(lat),
                        "longitude": float(lon),
                        "variable": variable,
                        "value": float(cidx + i * 0.001 + j * 0.000001),
                        "date": "20260410",
                        "run": "00z",
                    }
                )
    return pd.DataFrame(rows), test_lats, test_lons


def test_normalize_level_column_alias() -> None:
    df = pd.DataFrame({"isobaricinhpa": [1000.0], "latitude": [0.0], "longitude": [0.0]})
    out = normalize_level_column(df)
    assert "isobaricInhPa" in out.columns
    assert out["isobaricInhPa"].iloc[0] == 1000.0


def test_normalize_longitudes_wraps_negative() -> None:
    df = pd.DataFrame({"longitude": [-180.0, 0.0, 370.0]})
    out = normalize_longitudes(df)
    assert out["longitude"].tolist() == [180.0, 0.0, 10.0]


def test_validation_report_detects_missing_channels() -> None:
    df = pd.DataFrame(
        {
            "isobaricInhPa": [np.nan],
            "latitude": [0.0],
            "longitude": [0.0],
            "variable": ["u10"],
            "value": [1.0],
            "date": ["20260410"],
            "run": ["00z"],
        }
    )
    report = build_validation_report(df)
    assert report["ok"] is False
    assert any(item["variable"] == "sp" for item in report["missing_channels"])


def test_build_tensor_shape_dtype() -> None:
    df, test_lats, test_lons = _make_complete_df()
    tensor = build_fourcastnet_tensor(df, expected_lats=test_lats, expected_lons=test_lons, validate_shape=False)
    assert tensor.shape == (1, 20, 2, 3)
    assert tensor.dtype == np.float32


def test_build_tensor_fails_on_missing_required_channel() -> None:
    df, test_lats, test_lons = _make_complete_df()
    df = df[df["variable"] != "tcwv"]
    with pytest.raises(ValueError, match="Missing required channel"):
        build_fourcastnet_tensor(df, expected_lats=test_lats, expected_lons=test_lons, validate_shape=False)


def test_write_manifest() -> None:
    tmp_path = Path("tmp/test_fourcastnet")
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = {"status": "ok", "tensor_written": False}
    out = write_manifest(tmp_path / "manifest.json", payload)
    assert Path(out).exists()
    loaded = json.loads(Path(out).read_text(encoding="utf-8"))
    assert loaded["status"] == "ok"


def test_surface_channel_accepts_zero_level() -> None:
    df = pd.DataFrame(
        {
            "isobaricInhPa": [0.0, 500.0],
            "latitude": [90.0, 90.0],
            "longitude": [0.0, 0.0],
            "variable": ["tcwv", "tcwv"],
            "value": [1.0, 2.0],
            "date": ["20260410", "20260410"],
            "run": ["00z", "00z"],
        }
    )
    selected = select_channel_frame(df, "tcwv", None)
    assert len(selected) == 1
    assert selected["value"].iloc[0] == 1.0


def test_field_to_grid_preserves_desc_lat_and_asc_lon() -> None:
    df = pd.DataFrame(
        {
            "latitude": [90.0, 90.0, 89.75, 89.75],
            "longitude": [0.0, 0.25, 0.0, 0.25],
            "value": [1.0, 2.0, 3.0, 4.0],
        }
    )
    grid = field_to_grid(
        df,
        expected_lats=np.array([90.0, 89.75], dtype=np.float32),
        expected_lons=np.array([0.0, 0.25], dtype=np.float32),
    )
    assert grid.tolist() == [[1.0, 2.0], [3.0, 4.0]]


def test_validation_report_includes_available_levels() -> None:
    df = pd.DataFrame(
        {
            "isobaricInhPa": [np.nan, 500.0, 850.0],
            "latitude": [90.0, 90.0, 90.0],
            "longitude": [0.0, 0.0, 0.0],
            "variable": ["u10", "u", "t"],
            "value": [1.0, 2.0, 3.0],
            "date": ["20260410", "20260410", "20260410"],
            "run": ["00z", "00z", "00z"],
        }
    )
    report = build_validation_report(df)
    assert "available_variable_levels" in report
    assert any(item["variable"] == "u" for item in report["available_variable_levels"])


def test_latitude_policy_720_passes_with_fail() -> None:
    df, _, test_lons = _make_complete_df()
    lats = np.array([90.0, 89.75], dtype=np.float32)
    tensor = build_fourcastnet_tensor(
        df,
        expected_lats=lats,
        expected_lons=test_lons,
        validate_shape=False,
        latitude_policy="fail",
    )
    assert tensor.shape == (1, 20, 2, 3)


def test_latitude_policy_721_fail_is_incomplete() -> None:
    lats = np.arange(-90.0, 90.0001, 0.25, dtype=np.float32)
    resolved, meta = resolve_expected_lats(lats, latitude_policy="fail")
    assert resolved is None
    assert meta["latitude_policy_applied"] == "latitude_policy_required"
    assert meta["original_lat_count"] == 721
    assert meta["final_lat_count"] == 721


def test_latitude_policy_drop_south_pole() -> None:
    lats = np.arange(-90.0, 90.0001, 0.25, dtype=np.float32)
    resolved, meta = resolve_expected_lats(lats, latitude_policy="drop_south_pole")
    assert resolved is not None
    assert meta["latitude_policy_applied"] == "drop_south_pole"
    assert meta["dropped_latitude"] == -90.0
    assert meta["final_lat_count"] == 720
    assert float(np.min(resolved)) == -89.75


def test_latitude_policy_drop_north_pole() -> None:
    lats = np.arange(-90.0, 90.0001, 0.25, dtype=np.float32)
    resolved, meta = resolve_expected_lats(lats, latitude_policy="drop_north_pole")
    assert resolved is not None
    assert meta["latitude_policy_applied"] == "drop_north_pole"
    assert meta["dropped_latitude"] == 90.0
    assert meta["final_lat_count"] == 720
    assert float(np.max(resolved)) == 89.75


def test_fourcastnet_v0_contract_manifest_is_explicit() -> None:
    contract = FourCastNetV0Contract()
    manifest = build_fourcastnet_contract_manifest(latitude_policy="drop_south_pole")
    assert contract.contract_version == FOURCASTNET_CONTRACT_VERSION
    assert manifest["contract_version"] == FOURCASTNET_CONTRACT_VERSION
    assert manifest["expected_shape"] == [1, 20, 720, 1440]
    assert manifest["input_dtype"] == "float32"
    assert manifest["latitude_policy"] == "drop_south_pole"
    assert manifest["longitude_policy"] == "normalize_to_0_360_ascending"
    assert manifest["stats_channel_policy"] == "first_20_channels"
    assert manifest["normalization_required_before_model"] is True
    assert len(manifest["channel_order"]) == 20
    assert manifest["channel_order"][0]["variable"] == "u10"
    assert manifest["channel_order"][19]["variable"] == "tcwv"


def test_prepare_stats_21_channels_uses_first_20_and_reports_sst_drop() -> None:
    means_raw = np.arange(21, dtype=np.float32)
    stds_raw = np.ones((21,), dtype=np.float32)
    means, stds, meta = prepare_fourcastnet_stats(means_raw, stds_raw, policy="first_20_channels")
    assert means.shape == (1, 20, 1, 1)
    assert stds.shape == (1, 20, 1, 1)
    assert meta["stats_channels_original"] == 21
    assert meta["stats_channels_used"] == 20
    assert meta["dropped_stats_channel"] == 20
    assert meta["dropped_stats_channel_name"] == FOURCASTNET_DROPPED_STATS_CHANNEL_NAME
    assert float(means[0, -1, 0, 0]) == 19.0


def test_prepare_stats_21_channels_without_policy_fails() -> None:
    means_raw = np.zeros((21,), dtype=np.float32)
    stds_raw = np.ones((21,), dtype=np.float32)
    with pytest.raises(ValueError, match="first_20_channels is required"):
        prepare_fourcastnet_stats(means_raw, stds_raw, policy=None)


def test_normalize_fourcastnet_tensor_preserves_shape_and_float32() -> None:
    tensor = np.ones((1, 20, 2, 3), dtype=np.float32)
    means, stds, _ = prepare_fourcastnet_stats(
        np.zeros((20,), dtype=np.float32),
        np.ones((20,), dtype=np.float32),
    )
    normalized = normalize_fourcastnet_tensor(tensor, means, stds)
    assert normalized.shape == tensor.shape
    assert normalized.dtype == np.float32
    assert np.allclose(normalized, 1.0)


def test_prepare_stats_fails_on_non_finite_or_non_positive_std() -> None:
    means_raw = np.zeros((20,), dtype=np.float32)
    stds_raw = np.ones((20,), dtype=np.float32)
    means_raw[0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        prepare_fourcastnet_stats(means_raw, stds_raw)

    means_raw[0] = 0.0
    stds_raw[0] = 0.0
    with pytest.raises(ValueError, match="strictly positive"):
        prepare_fourcastnet_stats(means_raw, stds_raw)


def test_normalize_fourcastnet_tensor_fails_on_non_finite_tensor() -> None:
    tensor = np.ones((1, 20, 2, 3), dtype=np.float32)
    tensor[0, 0, 0, 0] = np.inf
    means, stds, _ = prepare_fourcastnet_stats(
        np.zeros((20,), dtype=np.float32),
        np.ones((20,), dtype=np.float32),
    )
    with pytest.raises(ValueError, match="non-finite"):
        normalize_fourcastnet_tensor(tensor, means, stds)
