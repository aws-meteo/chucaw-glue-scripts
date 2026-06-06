"""Local dry-run: one parquet file -> FourCastNet local artifacts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from chucaw_preprocessor.fourcastnet import (
    build_available_variable_levels,
    build_fourcastnet_contract_manifest,
    build_fourcastnet_tensor,
    build_validation_report,
    normalize_longitudes,
    write_manifest,
)
from chucaw_preprocessor.glue_args import resolve_args


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def main() -> None:
    args = resolve_args(
        required=["PARQUET_PATH"],
        optional=["OUTPUT_DIR", "ALLOW_INCOMPLETE", "ALLOW_TEST_GRID", "LATITUDE_POLICY"],
    )

    parquet_path = Path(args["PARQUET_PATH"]).expanduser()
    if not parquet_path.exists():
        raise FileNotFoundError(f"No local parquet file found: {parquet_path}")

    output_dir = Path(args.get("OUTPUT_DIR") or "./tmp/fourcastnet_dryrun").expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    allow_incomplete = _truthy(args.get("ALLOW_INCOMPLETE") or "false")
    allow_test_grid = _truthy(args.get("ALLOW_TEST_GRID") or "false")
    latitude_policy = args.get("LATITUDE_POLICY") or "fail"

    df = pd.read_parquet(parquet_path)
    validation = build_validation_report(df, latitude_policy=latitude_policy)
    levels_df = build_available_variable_levels(df)
    available_variables = {
        "source": str(parquet_path),
        "row_count": int(len(df)),
        "available_variables": sorted(
            df["variable"].astype(str).str.lower().dropna().unique().tolist()
        )
        if "variable" in df.columns
        else [],
    }

    manifest = {
        **build_fourcastnet_contract_manifest(latitude_policy=latitude_policy),
        "status": "ok",
        "source": str(parquet_path),
        "tensor_file": "input_fourcastnet.npy",
        "tensor_written": False,
        "allow_incomplete": allow_incomplete,
        "allow_test_grid": allow_test_grid,
        "latitude_policy": latitude_policy,
        "tensor_write_reason": "validation_pending",
    }

    write_manifest(output_dir / "validation_report.json", validation)
    write_manifest(output_dir / "available_variables.json", available_variables)
    levels_df.to_csv(output_dir / "available_variable_levels.csv", index=False)
    write_manifest(output_dir / "manifest.json", manifest)

    if not validation.get("ok", False):
        manifest["status"] = "incomplete"
        manifest["tensor_write_reason"] = "validation_failed"
        write_manifest(output_dir / "manifest.json", manifest)
        if not allow_incomplete:
            raise RuntimeError("Validation failed for local parquet. See validation_report.json")
        print(manifest)
        return

    if allow_test_grid:
        normalized = normalize_longitudes(df)
        expected_lats = np.array(
            sorted(pd.to_numeric(normalized["latitude"], errors="coerce").dropna().unique(), reverse=True),
            dtype=np.float32,
        )
        expected_lons = np.array(
            sorted(pd.to_numeric(normalized["longitude"], errors="coerce").dropna().unique()),
            dtype=np.float32,
        )
        tensor = build_fourcastnet_tensor(
            df,
            expected_lats=expected_lats,
            expected_lons=expected_lons,
            validate_shape=False,
            latitude_policy=latitude_policy,
        )
    else:
        tensor = build_fourcastnet_tensor(df, latitude_policy=latitude_policy)
    np.save(output_dir / "input_fourcastnet.npy", tensor)

    manifest["tensor_written"] = True
    manifest["tensor_write_reason"] = "written"
    manifest["tensor_shape"] = list(tensor.shape)
    manifest["tensor_dtype"] = str(tensor.dtype)
    write_manifest(output_dir / "manifest.json", manifest)
    print(manifest)


if __name__ == "__main__":
    main()
