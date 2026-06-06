from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

from chucaw_preprocessor.fourcastnet import (
    FCN_DATASET_NAME,
    build_fourcastnet_channel_map,
    build_fourcastnet_tensor,
    build_validation_report,
    normalize_level_column,
    normalize_longitudes,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export FCN-compatible parquet to HDF5")
    p.add_argument("--INPUT_PARQUET", required=True)
    p.add_argument("--OUTPUT_H5", required=True)
    p.add_argument("--LATITUDE_POLICY", choices=["fail", "drop_south_pole", "drop_north_pole"], default="fail")
    p.add_argument("--REQUIRE_COMPLETE", default="true")
    p.add_argument("--ALLOW_TEST_GRID", action="store_true")
    p.add_argument("--COMPRESSION", default="gzip")
    p.add_argument("--COMPRESSION_LEVEL", type=int, default=1)
    return p.parse_args()


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


def main() -> None:
    args = _parse_args()
    in_path = Path(args.INPUT_PARQUET)
    out_path = Path(args.OUTPUT_H5)
    report_path = out_path.with_name("h5_validation_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(in_path)
    report = build_validation_report(df, latitude_policy=args.LATITUDE_POLICY)
    require_complete = _truthy(args.REQUIRE_COMPLETE)
    if require_complete and not report.get("ok", False):
        raise RuntimeError(f"Input parquet not complete: {report.get('missing_channels')}")

    if args.ALLOW_TEST_GRID:
        normalized = normalize_longitudes(normalize_level_column(df))
        expected_lats = np.array(
            sorted(pd.to_numeric(normalized["latitude"], errors="coerce").dropna().unique().tolist(), reverse=True),
            dtype=np.float32,
        )
        expected_lons = np.array(
            sorted(np.mod(pd.to_numeric(normalized["longitude"], errors="coerce").dropna().unique(), 360.0).tolist()),
            dtype=np.float32,
        )
        tensor = build_fourcastnet_tensor(
            df,
            expected_lats=expected_lats,
            expected_lons=expected_lons,
            validate_shape=False,
            latitude_policy=args.LATITUDE_POLICY,
        )
    else:
        tensor = build_fourcastnet_tensor(df, latitude_policy=args.LATITUDE_POLICY)
    if (not args.ALLOW_TEST_GRID) and tensor.shape != (1, 20, 720, 1440):
        raise RuntimeError(f"Unexpected tensor shape: {tensor.shape}")
    if not np.isfinite(tensor).all():
        raise RuntimeError("Non-finite values in tensor")

    compression = args.COMPRESSION if args.COMPRESSION and args.COMPRESSION.lower() != "none" else None
    comp_opts = args.COMPRESSION_LEVEL if compression == "gzip" else None
    with h5py.File(out_path, "w") as h5f:
        dset = h5f.create_dataset(FCN_DATASET_NAME, data=tensor.astype(np.float32), compression=compression, compression_opts=comp_opts)
        dset.attrs["channel_order_json"] = json.dumps(build_fourcastnet_channel_map())
        if "date" in df.columns:
            dset.attrs["date"] = str(df["date"].iloc[0])
        if "run" in df.columns:
            dset.attrs["run"] = str(df["run"].iloc[0])
        dset.attrs["latitude_policy"] = args.LATITUDE_POLICY
        dset.attrs["scientific_validity"] = "false"
        dset.attrs["created_by"] = "scripts/dev/export_fourcastnet_h5.py"

    payload = {
        "ok": True,
        "dataset": FCN_DATASET_NAME,
        "shape": list(tensor.shape),
        "dtype": str(tensor.dtype),
        "finite": bool(np.isfinite(tensor).all()),
        "output_h5": str(out_path),
    }
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
