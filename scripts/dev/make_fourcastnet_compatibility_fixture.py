from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from chucaw_preprocessor.fourcastnet import (
    build_fourcastnet_channel_descriptors,
    build_fourcastnet_channel_map,
    build_validation_report,
    normalize_level_column,
    normalize_longitudes,
    resolve_expected_lats,
    specific_humidity_to_relative_humidity,
    write_manifest,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build FourCastNet compatibility fixture parquet")
    p.add_argument("--INPUT_PARQUET", required=True)
    p.add_argument("--OUTPUT_DIR", required=True)
    p.add_argument("--OUTPUT_BASENAME", default=None)
    p.add_argument("--MODE", choices=["strict", "compatibility_fixture"], default="strict")
    p.add_argument("--LATITUDE_POLICY", choices=["fail", "drop_south_pole", "drop_north_pole"], default="fail")
    p.add_argument("--ROW_GROUP_SIZE", type=int, default=None)
    p.add_argument("--FORCE", action="store_true")
    p.add_argument("--ALLOW_TEST_GRID", action="store_true")
    return p.parse_args()


def _channel_key(variable: str, level: float | None) -> str:
    if level is None:
        return f"{variable}@surface"
    return f"{variable}@{int(level)}"


def _grid_from_channel(df: pd.DataFrame, variable: str, level: float | None, lats: np.ndarray, lons: np.ndarray) -> np.ndarray | None:
    vdf = df[df["variable"] == variable].copy()
    levels = pd.to_numeric(vdf["isobaricInhPa"], errors="coerce")
    if level is None:
        sel = vdf[levels.isna() | np.isclose(levels, 0.0, atol=1e-6)]
    else:
        sel = vdf[np.isclose(levels, float(level), atol=1e-6)]
    if sel.empty:
        return None

    sel = sel[["latitude", "longitude", "value"]].copy()
    sel["latitude"] = pd.to_numeric(sel["latitude"], errors="coerce")
    sel["longitude"] = pd.to_numeric(sel["longitude"], errors="coerce")
    sel["value"] = pd.to_numeric(sel["value"], errors="coerce")
    sel = sel.dropna()
    if sel.empty:
        return None
    if sel.duplicated(subset=["latitude", "longitude"]).any():
        raise ValueError(f"Duplicate points for {variable}@{level}")
    pivot = sel.pivot(index="latitude", columns="longitude", values="value")
    pivot = pivot.reindex(index=lats, columns=lons)
    if pivot.isnull().any().any():
        return None
    return pivot.to_numpy(dtype=np.float32)


def _tcwv_proxy(grids: dict[str, np.ndarray], lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    q850 = grids.get("q@850")
    q500 = grids.get("q@500")
    if q850 is not None and q500 is not None:
        return ((q850 + q500) * 5000.0).astype(np.float32)
    return np.zeros((len(lats), len(lons)), dtype=np.float32)


def _normalize_output_basename(raw: str) -> str:
    candidate = str(raw).strip()
    if not candidate:
        raise ValueError("OUTPUT_BASENAME cannot be empty")
    if Path(candidate).name != candidate:
        raise ValueError("OUTPUT_BASENAME must be a basename only (no directory separators)")
    if not candidate.lower().endswith(".parquet"):
        candidate = f"{candidate}.parquet"
    return candidate


def _derive_output_basename(df: pd.DataFrame, output_basename: str | None) -> str:
    if output_basename:
        return _normalize_output_basename(output_basename)

    if "date" not in df.columns or "run" not in df.columns:
        raise RuntimeError(
            "Cannot derive output basename: input parquet is missing date/run. "
            "Provide --OUTPUT_BASENAME explicitly."
        )

    date_raw = str(df["date"].iloc[0]).strip()
    run_raw = str(df["run"].iloc[0]).strip().lower()

    ymd: str | None = None
    digits = "".join(ch for ch in date_raw if ch.isdigit())
    if len(digits) >= 8:
        ymd = digits[:8]
    else:
        parsed = pd.to_datetime(date_raw, errors="coerce")
        if pd.notna(parsed):
            ymd = parsed.strftime("%Y%m%d")

    run_match = re.search(r"(\d{1,2})", run_raw)
    run_hh: str | None = None
    if run_match:
        hour = int(run_match.group(1))
        if 0 <= hour <= 23:
            run_hh = f"{hour:02d}"

    if ymd is None or run_hh is None:
        raise RuntimeError(
            "Cannot derive output basename from date/run. "
            "Expected date like YYYYMMDD and run like HHz. Provide --OUTPUT_BASENAME."
        )

    return f"fcn_compat_{ymd}_{run_hh}z.parquet"


def _build_manifest(
    mode: str,
    scientific_validity: bool,
    source: Path,
    output_parquet: Path | None,
    report: dict[str, Any],
    provenance: list[dict[str, Any]],
) -> dict[str, Any]:
    any_proxy_channels = any(c.get("status") == "proxy" for c in provenance)
    any_derived_channels = any(c.get("status") == "derived" for c in provenance)
    all_channels_original = all(c.get("status") == "original" for c in provenance)
    return {
        "mode": mode,
        "scientific_validity": scientific_validity,
        "compatibility_fixture": mode == "compatibility_fixture",
        "any_proxy_channels": any_proxy_channels,
        "any_derived_channels": any_derived_channels,
        "all_channels_original": all_channels_original,
        "source_parquet": str(source),
        "output_parquet": str(output_parquet) if output_parquet else None,
        "warning": "NOT_SCIENTIFICALLY_VALID" if not scientific_validity else "SCIENTIFICALLY_VALID",
        "missing_channels": report.get("missing_channels", []),
        "channel_count": len(provenance),
    }


def main() -> None:
    args = _parse_args()
    input_parquet = Path(args.INPUT_PARQUET)
    output_dir = Path(args.OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    report_path = output_dir / "validation_report.json"
    provenance_path = output_dir / "channel_provenance.json"

    df = pd.read_parquet(input_parquet)
    df = normalize_longitudes(normalize_level_column(df))
    var_cat = df["variable"].astype("category")
    lowered = var_cat.cat.categories.astype("string").str.lower()
    df["variable"] = var_cat.cat.rename_categories(lowered)
    output_basename = _derive_output_basename(df, args.OUTPUT_BASENAME)
    output_parquet = output_dir / output_basename

    if output_parquet.exists() and not args.FORCE:
        raise FileExistsError(f"Output exists, use --FORCE: {output_parquet}")

    lats_all = pd.to_numeric(df["latitude"], errors="coerce").dropna().unique()
    lons = np.array(sorted(np.mod(pd.to_numeric(df["longitude"], errors="coerce").dropna().unique(), 360.0)), dtype=np.float32)
    resolved_lats, lat_meta = resolve_expected_lats(lats_all, latitude_policy=args.LATITUDE_POLICY)
    if resolved_lats is None:
        if args.ALLOW_TEST_GRID:
            resolved_lats = np.array(sorted(lats_all.tolist(), reverse=True), dtype=np.float32)
            lat_meta = {**lat_meta, "latitude_policy_applied": "allow_test_grid"}
        else:
            raise RuntimeError(f"Latitude policy failed: {lat_meta}")

    report = build_validation_report(df, latitude_policy=args.LATITUDE_POLICY)

    raw_grids: dict[str, np.ndarray] = {}
    for var in ["q", "t", "msl", "u10", "v10", "t2m", "u", "v", "z", "sp", "r", "tcwv"]:
        for lvl in [None, 1000.0, 850.0, 500.0, 50.0]:
            grid = _grid_from_channel(df, var, lvl, resolved_lats, lons)
            if grid is not None:
                raw_grids[_channel_key(var, lvl)] = grid

    channel_map = build_fourcastnet_channel_map()
    provenance: list[dict[str, Any]] = []
    out_rows: list[pd.DataFrame] = []

    missing_required: list[dict[str, Any]] = []

    for desc in build_fourcastnet_channel_descriptors():
        idx = int(desc["channel_index"])
        var = str(desc["variable"])
        lvl = desc["level"]
        key = _channel_key(var, lvl)
        status = "missing"
        src_vars: list[str] = []
        formula = ""
        scientific_valid = True
        notes = ""
        grid = raw_grids.get(key)

        if grid is not None:
            status = "original"
            src_vars = [var]
            formula = "observed from parquet"
        elif args.MODE == "compatibility_fixture":
            scientific_valid = False
            if key == "sp@surface":
                msl = raw_grids.get("msl@surface")
                if msl is not None:
                    grid = msl.copy()
                    status = "proxy"
                    src_vars = ["msl"]
                    formula = "sp proxy from msl"
                    notes = "COMPATIBILITY_FIXTURE"
            elif key in {"r@850", "r@500"}:
                q_grid = raw_grids.get(f"q@{int(lvl)}")
                t_grid = raw_grids.get(f"t@{int(lvl)}")
                if q_grid is not None and t_grid is not None:
                    rh, summary = specific_humidity_to_relative_humidity(q_grid, t_grid, float(lvl), clip_percent=True)
                    grid = rh
                    status = "derived"
                    src_vars = ["q", "t"]
                    formula = "RH derived from specific humidity and temperature"
                    notes = json.dumps(summary, sort_keys=True)
            elif key == "tcwv@surface":
                grid = _tcwv_proxy(raw_grids, resolved_lats, lons)
                status = "proxy"
                src_vars = ["q"]
                formula = "debug tcwv proxy"
                notes = "COMPATIBILITY_FIXTURE"

        if grid is None:
            missing_required.append({"variable": var, "level": lvl})
            scientific_valid = False
        else:
            lat_col = np.repeat(resolved_lats, len(lons))
            lon_col = np.tile(lons, len(resolved_lats))
            out_rows.append(
                pd.DataFrame(
                    {
                        "isobaricInhPa": np.nan if lvl is None else float(lvl),
                        "latitude": lat_col,
                        "longitude": lon_col,
                        "variable": var,
                        "value": grid.reshape(-1),
                        "date": str(df["date"].iloc[0]) if "date" in df.columns else "",
                        "run": str(df["run"].iloc[0]) if "run" in df.columns else "",
                    }
                )
            )

        provenance.append(
            {
                "channel_index": idx,
                "variable": var,
                "level": lvl,
                "status": status,
                "source_variables": src_vars,
                "formula_or_proxy_description": formula,
                "scientific_validity": bool(scientific_valid and status == "original"),
                "notes": notes,
            }
        )

    strict_fail = args.MODE == "strict" and len(missing_required) > 0
    compat_fail = args.MODE == "compatibility_fixture" and len(missing_required) > 0
    compatibility_fixture = args.MODE == "compatibility_fixture"
    any_proxy_channels = any(c["status"] == "proxy" for c in provenance)
    any_derived_channels = any(c["status"] == "derived" for c in provenance)
    all_channels_original = all(c["status"] == "original" for c in provenance)
    scientific_validity = (not compatibility_fixture) and all_channels_original and len(missing_required) == 0

    report_payload: dict[str, Any] = {
        "ok": not strict_fail and not compat_fail,
        "mode": args.MODE,
        "scientific_validity": bool(scientific_validity),
        "compatibility_fixture": compatibility_fixture,
        "any_proxy_channels": any_proxy_channels,
        "any_derived_channels": any_derived_channels,
        "all_channels_original": all_channels_original,
        "latitude": lat_meta,
        "missing_channels": missing_required,
        "warnings": ["NOT_SCIENTIFICALLY_VALID"] if not scientific_validity else [],
    }

    write_manifest(report_path, report_payload)
    write_manifest(provenance_path, {"channels": provenance})

    manifest = _build_manifest(
        args.MODE,
        scientific_validity=scientific_validity,
        source=input_parquet,
        output_parquet=output_parquet if (not strict_fail and not compat_fail) else None,
        report=report_payload,
        provenance=provenance,
    )
    write_manifest(manifest_path, manifest)

    if strict_fail:
        return
    if compat_fail:
        raise RuntimeError(f"compatibility_fixture failed; still missing channels: {missing_required}")

    out_df = pd.concat(out_rows, ignore_index=True)
    out_df.to_parquet(output_parquet, index=False, row_group_size=args.ROW_GROUP_SIZE)


if __name__ == "__main__":
    main()
