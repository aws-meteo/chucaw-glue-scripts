from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from chucaw_preprocessor.fourcastnet import (
    build_fourcastnet_contract_manifest,
    build_fourcastnet_channel_map,
    build_fourcastnet_tensor,
    build_validation_report,
    normalize_level_column,
    normalize_longitudes,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export FCN-compatible parquet to tensor artifact")
    p.add_argument("--INPUT_PARQUET", required=True)
    p.add_argument("--OUTPUT_DIR", required=True)
    p.add_argument("--LATITUDE_POLICY", choices=["fail", "drop_south_pole", "drop_north_pole"], default="fail")
    p.add_argument("--OUTPUT_FORMAT", choices=["npy", "pt"], default="npy")
    p.add_argument("--REQUIRE_COMPLETE", default="true")
    p.add_argument("--FORCE", action="store_true")
    p.add_argument("--ALLOW_TEST_GRID", action="store_true")
    return p.parse_args()


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _discover_source_metadata(input_parquet: Path) -> tuple[str | None, str | None, dict[str, Any] | None]:
    parent = input_parquet.parent
    manifest_path = parent / "manifest.json"
    provenance_path = parent / "channel_provenance.json"
    manifest_payload: dict[str, Any] | None = None

    if manifest_path.exists():
        try:
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest_payload = None
            manifest_path = Path()

    if not provenance_path.exists():
        provenance_path = Path()

    return (
        str(manifest_path) if str(manifest_path) else None,
        str(provenance_path) if str(provenance_path) else None,
        manifest_payload,
    )


def main() -> int:
    args = _parse_args()
    input_parquet = Path(args.INPUT_PARQUET)
    output_dir = Path(args.OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_tensor = output_dir / ("input_tensor.npy" if args.OUTPUT_FORMAT == "npy" else "input_tensor.pt")
    manifest_path = output_dir / "tensor_manifest.json"
    validation_path = output_dir / "tensor_validation_report.json"

    report: dict[str, Any] = {
        "ok": False,
        "input_parquet": str(input_parquet),
        "output_tensor": str(output_tensor),
    }

    if output_tensor.exists() and not args.FORCE:
        report["error_stage"] = "output_path_check"
        report["error_message"] = f"Output exists. Use --FORCE to overwrite: {output_tensor}"
        _write_json(validation_path, report)
        return 1

    try:
        df = pd.read_parquet(input_parquet)
        require_complete = _truthy(args.REQUIRE_COMPLETE)
        validation = build_validation_report(df, latitude_policy=args.LATITUDE_POLICY)
        report["source_validation_ok"] = bool(validation.get("ok", False))
        report["source_missing_channels"] = validation.get("missing_channels", [])

        complete_for_export = bool(validation.get("ok", False))
        if args.ALLOW_TEST_GRID and not complete_for_export:
            complete_for_export = (
                len(validation.get("missing_columns", [])) == 0
                and len(validation.get("missing_channels", [])) == 0
                and len(validation.get("duplicate_points_by_channel", [])) == 0
            )

        if require_complete and not complete_for_export:
            raise RuntimeError(f"Input parquet is incomplete: {validation.get('missing_channels')}")

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
            if tensor.shape != (1, 20, 720, 1440):
                raise RuntimeError(f"Unexpected tensor shape: {tensor.shape}")

        if not np.isfinite(tensor).all():
            raise RuntimeError("Non-finite values in tensor")

        if args.OUTPUT_FORMAT == "npy":
            np.save(output_tensor, tensor.astype(np.float32))
        else:
            import torch

            torch.save(torch.from_numpy(tensor.astype(np.float32)), output_tensor)

        source_manifest_path, source_provenance_path, source_manifest = _discover_source_metadata(input_parquet)
        scientific_validity = None if source_manifest is None else source_manifest.get("scientific_validity")
        compatibility_fixture = None if source_manifest is None else source_manifest.get("compatibility_fixture")

        manifest = {
            **build_fourcastnet_contract_manifest(latitude_policy=args.LATITUDE_POLICY),
            "shape": list(tensor.shape),
            "dtype": str(tensor.dtype),
            "channel_order_pairs": build_fourcastnet_channel_map(),
            "latitude_policy": args.LATITUDE_POLICY,
            "scientific_validity": scientific_validity,
            "compatibility_fixture": compatibility_fixture,
            "source_parquet": str(input_parquet),
            "source_manifest": source_manifest_path,
            "source_channel_provenance": source_provenance_path,
            "created_by": "scripts/dev/export_fourcastnet_tensor.py",
            "note": "This tensor can be passed directly to PyTorch model code after normalization.",
            "output_tensor": str(output_tensor),
            "output_format": args.OUTPUT_FORMAT,
        }
        _write_json(manifest_path, manifest)

        report.update(
            {
                "ok": True,
                "shape": list(tensor.shape),
                "dtype": str(tensor.dtype),
                "finite": bool(np.isfinite(tensor).all()),
                "channel_count": int(tensor.shape[1]),
            }
        )
        _write_json(validation_path, report)
        return 0
    except Exception as exc:
        report["ok"] = False
        report["error_stage"] = report.get("error_stage", "tensor_export")
        report["error_message"] = str(exc)
        _write_json(validation_path, report)
        return 1


if __name__ == "__main__":
    sys.exit(main())
