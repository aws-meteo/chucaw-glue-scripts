"""Glue job: Platinum Parquet partition -> FourCastNet snapshot artifacts.

Memory-safe version for recent ECMWF `oper` Parquet files.

Why this exists
---------------
The previous script used `pd.read_parquet(local_path)` for each Parquet file.
For June 2026 `oper` files, one Parquet can contain ~191M rows. In Glue G.1X
this caused exit 137/OOM before the first validation report was written.

This version keeps Bronze -> Platinum unchanged and fixes only the
Platinum-Parquet -> FourCastNet conversion step.
"""

from __future__ import annotations

import gc
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import boto3
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from chucaw_preprocessor.fourcastnet import (
    EXPECTED_LONS,
    FOURCASTNET_V0_CONTRACT,
    build_fourcastnet_contract_manifest,
    build_fourcastnet_tensor,
    build_validation_report,
    resolve_expected_lats,
    write_manifest,
)
from chucaw_preprocessor.glue_args import resolve_args


DEFAULT_PLATINUM_BUCKET = "chucaw-data-platinum-processed-725644097028-us-east-1-an"
DEFAULT_PLATINUM_PARQUET_PREFIX = "ecmwf/parquet"
DEFAULT_FOURCASTNET_PREFIX = "ecmwf/fourcastnet"

# Conservative 20-channel FourCastNet-style contract. If your packaged
# chucaw_preprocessor.fourcastnet uses a different channel list, override with
# --CHANNEL_SPEC_JSON.
DEFAULT_CHANNEL_SPECS: list[dict[str, object]] = [
    {"name": "u10", "variable": "u10", "level_hpa": None},
    {"name": "v10", "variable": "v10", "level_hpa": None},
    {"name": "t2m", "variable": "t2m", "level_hpa": None},
    {"name": "sp", "variable": "sp", "level_hpa": None},
    {"name": "msl", "variable": "msl", "level_hpa": None},
    {"name": "t850", "variable": "t", "level_hpa": 850.0},
    {"name": "u1000", "variable": "u", "level_hpa": 1000.0},
    {"name": "v1000", "variable": "v", "level_hpa": 1000.0},
    {"name": "z1000", "variable": "z", "level_hpa": 1000.0},
    {"name": "u850", "variable": "u", "level_hpa": 850.0},
    {"name": "v850", "variable": "v", "level_hpa": 850.0},
    {"name": "z850", "variable": "z", "level_hpa": 850.0},
    {"name": "u500", "variable": "u", "level_hpa": 500.0},
    {"name": "v500", "variable": "v", "level_hpa": 500.0},
    {"name": "z500", "variable": "z", "level_hpa": 500.0},
    {"name": "t500", "variable": "t", "level_hpa": 500.0},
    {"name": "z50", "variable": "z", "level_hpa": 50.0},
    {"name": "r500", "variable": "r", "level_hpa": 500.0},
    {"name": "r850", "variable": "r", "level_hpa": 850.0},
    {"name": "tcwv", "variable": "tcwv", "level_hpa": None},
]

DEFAULT_READ_COLUMNS = ["latitude", "longitude", "variable", "value", "isobaricInhPa"]
STEP_RE = re.compile(r"-(\d{1,3})h-")

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _csv(value: str | None) -> list[str]:
    return [x.strip() for x in str(value or "").split(",") if x.strip()]


def _csv_int(value: str | None) -> list[int]:
    return [int(x) for x in _csv(value)]


def _normalize_hour_arg(hour_value: str) -> tuple[str, str]:
    """Return `(partition_hour, run_hour)`.

    The existing Platinum layout uses `hour=06z`, so both values deliberately
    include the `z` suffix.
    """
    raw = str(hour_value or "").strip().lower()
    if not raw:
        raise ValueError("HOUR cannot be empty")
    if raw.endswith("z"):
        raw = raw[:-1]
    hour_num = int(raw)
    if hour_num < 0 or hour_num > 23:
        raise ValueError(f"Invalid HOUR value: {hour_value}")
    partition_hour = f"{hour_num:02d}z"
    return partition_hour, partition_hour


def _partition_prefix(base_prefix: str, year: str, month: str, day: str, partition_hour: str) -> str:
    return (
        f"{base_prefix.strip('/')}"
        f"/year={year}/month={month}/day={day}/hour={partition_hour}"
    ).strip("/")


def _upload_file(local_path: str, bucket: str, key: str) -> None:
    boto3.client("s3").upload_file(local_path, bucket, key)


def _write_and_upload_json(payload: dict, local_path: Path, bucket: str, key: str) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _upload_file(str(local_path), bucket, key)


def _extract_step_hours_from_name(path_or_key: str) -> int | None:
    match = STEP_RE.search(Path(path_or_key).name)
    return int(match.group(1)) if match else None


def _memory_mib(df: pd.DataFrame) -> float:
    return float(df.memory_usage(deep=True).sum() / 1024 / 1024)


def _json_value(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def _level_values(df: pd.DataFrame) -> pd.Series:
    if "isobaricInhPa" in df.columns:
        return pd.to_numeric(df["isobaricInhPa"], errors="coerce")
    if "isobaricinhpa" in df.columns:
        return pd.to_numeric(df["isobaricinhpa"], errors="coerce")
    raise ValueError("Missing pressure-level column: expected isobaricInhPa or isobaricinhpa")


def _channel_mask(df: pd.DataFrame, variable: str, level_hpa: float | None) -> pd.Series:
    variables = df["variable"].astype(str).str.lower()
    levels = _level_values(df)
    var_mask = variables == str(variable).lower()
    if level_hpa is None:
        level_mask = levels.isna() | np.isclose(levels, 0.0, atol=1e-6)
    else:
        level_mask = np.isclose(levels, float(level_hpa), atol=1e-6)
    return var_mask & level_mask


def _diagnose_channel(
    df: pd.DataFrame,
    spec: dict[str, object],
    *,
    expected_n_lat_after_policy: int | None,
    expected_n_lon: int,
) -> dict[str, Any]:
    variable = str(spec["variable"])
    level_hpa = None if spec.get("level_hpa") is None else float(spec["level_hpa"])
    selected = df.loc[_channel_mask(df, variable, level_hpa), ["latitude", "longitude"]].copy()

    if selected.empty:
        return {
            "channel_name": spec.get("name"),
            "variable": variable,
            "level_hpa": level_hpa,
            "row_count": 0,
            "n_lat": 0,
            "n_lon": 0,
            "min_lat": None,
            "max_lat": None,
            "min_lon": None,
            "max_lon": None,
            "duplicate_count": 0,
            "expected_n_lat_after_policy": expected_n_lat_after_policy,
            "expected_n_lon": expected_n_lon,
            "sample_duplicated_rows": [],
        }

    selected["latitude"] = pd.to_numeric(selected["latitude"], errors="coerce")
    selected["longitude"] = np.mod(pd.to_numeric(selected["longitude"], errors="coerce"), 360.0)
    dup_mask = selected.duplicated(subset=["latitude", "longitude"], keep=False)
    sample_dups = selected.loc[dup_mask, ["latitude", "longitude"]].head(10)

    return {
        "channel_name": spec.get("name"),
        "variable": variable,
        "level_hpa": level_hpa,
        "row_count": int(len(selected)),
        "n_lat": int(selected["latitude"].nunique(dropna=True)),
        "n_lon": int(selected["longitude"].nunique(dropna=True)),
        "min_lat": _json_value(selected["latitude"].min()),
        "max_lat": _json_value(selected["latitude"].max()),
        "min_lon": _json_value(selected["longitude"].min()),
        "max_lon": _json_value(selected["longitude"].max()),
        "duplicate_count": int(selected.duplicated(subset=["latitude", "longitude"]).sum()),
        "expected_n_lat_after_policy": expected_n_lat_after_policy,
        "expected_n_lon": expected_n_lon,
        "sample_duplicated_rows": [
            {key: _json_value(value) for key, value in row.items()}
            for row in sample_dups.to_dict(orient="records")
        ],
    }


def _build_pre_tensor_debug(
    df: pd.DataFrame,
    channel_specs: list[dict[str, object]],
    latitude_policy: str,
) -> dict[str, Any]:
    observed_lats = pd.to_numeric(df["latitude"], errors="coerce").dropna().unique()
    expected_lats, lat_meta = resolve_expected_lats(observed_lats, latitude_policy=latitude_policy)
    expected_n_lat = int(len(expected_lats)) if expected_lats is not None else None
    expected_n_lon = int(len(EXPECTED_LONS))
    channels = [
        _diagnose_channel(
            df,
            spec,
            expected_n_lat_after_policy=expected_n_lat,
            expected_n_lon=expected_n_lon,
        )
        for spec in channel_specs
    ]
    return {
        "latitude_policy": latitude_policy,
        "latitude": lat_meta,
        "expected_n_lat_after_policy": expected_n_lat,
        "expected_n_lon": expected_n_lon,
        "row_count": int(len(df)),
        "memory_mib": _memory_mib(df),
        "channels": channels,
    }


def _prepare_df_for_tensor(df: pd.DataFrame, latitude_policy: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    observed_lats = pd.to_numeric(df["latitude"], errors="coerce").dropna().unique()
    expected_lats, lat_meta = resolve_expected_lats(observed_lats, latitude_policy=latitude_policy)
    if expected_lats is None:
        return df, {
            "latitude_policy": latitude_policy,
            "latitude": lat_meta,
            "rows_before": int(len(df)),
            "rows_after_latitude_policy": int(len(df)),
            "rows_after_deduplicate": int(len(df)),
            "duplicate_rows_removed": 0,
        }

    prepared = df
    prepared["latitude"] = pd.to_numeric(prepared["latitude"], errors="coerce")
    policy_applied = str(lat_meta.get("latitude_policy_applied") or "")
    dropped_latitude = lat_meta.get("dropped_latitude")
    rows_before = int(len(prepared))
    if policy_applied in {"drop_south_pole", "drop_north_pole"} and dropped_latitude is not None:
        drop_mask = np.isclose(prepared["latitude"], float(dropped_latitude), atol=1e-6)
        if bool(np.any(drop_mask)):
            prepared.drop(index=prepared.index[drop_mask], inplace=True)
    rows_after_lat = int(len(prepared))

    return prepared, {
        "latitude_policy": latitude_policy,
        "latitude": lat_meta,
        "rows_before": rows_before,
        "rows_after_latitude_policy": rows_after_lat,
        "rows_after_deduplicate": int(len(prepared)),
        "duplicate_rows_removed": 0,
        "deduplicate_applied": False,
        "memory_mib_after_prepare": _memory_mib(prepared),
    }


def _load_channel_specs(args: dict[str, str]) -> list[dict[str, object]]:
    raw_json = (args.get("CHANNEL_SPEC_JSON") or "").strip()
    if not raw_json:
        return DEFAULT_CHANNEL_SPECS
    parsed = json.loads(raw_json)
    if not isinstance(parsed, list):
        raise ValueError("CHANNEL_SPEC_JSON must be a JSON list")
    out: list[dict[str, object]] = []
    for item in parsed:
        if not isinstance(item, dict) or "variable" not in item:
            raise ValueError(f"Invalid channel spec: {item!r}")
        out.append(
            {
                "name": item.get("name") or f"{item['variable']}_{item.get('level_hpa')}",
                "variable": str(item["variable"]),
                "level_hpa": None if item.get("level_hpa") is None else float(item["level_hpa"]),
            }
        )
    return out


def _channel_index(channel_specs: list[dict[str, object]]) -> tuple[set[str], set[tuple[str, float | None]]]:
    variables = {str(spec["variable"]) for spec in channel_specs}
    pairs = {(str(spec["variable"]), spec.get("level_hpa")) for spec in channel_specs}
    return variables, pairs


def _list_partition_parquet_keys(bucket: str, prefix: str, lead_hours: set[int] | None) -> list[str]:
    """List Parquet files in one partition, optionally filtering lead hour."""
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    parquet_keys: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix.rstrip('/')}/"):
        for item in page.get("Contents", []):
            key = item["Key"]
            if not key.endswith(".parquet"):
                continue
            step = _extract_step_hours_from_name(key)
            if lead_hours is not None and step not in lead_hours:
                logger.info("Skipping parquet outside requested lead hours: key=%s step=%s", key, step)
                continue
            parquet_keys.append(key)
    if not parquet_keys:
        raise RuntimeError(f"No parquet files found under s3://{bucket}/{prefix}")
    return sorted(parquet_keys)


def _download_s3_keys(bucket: str, keys: Iterable[str], tmp_dir: str) -> list[str]:
    s3 = boto3.client("s3")
    Path(tmp_dir).mkdir(parents=True, exist_ok=True)
    local_paths: list[str] = []
    for key in keys:
        target = str(Path(tmp_dir) / Path(key).name)
        logger.info("Downloading s3://%s/%s -> %s", bucket, key, target)
        s3.download_file(bucket, key, target)
        local_paths.append(target)
    return local_paths


@dataclass(frozen=True)
class RowGroupDecision:
    row_group: int
    variable: str | None
    level_hpa: float | None
    num_rows: int
    selected: bool
    reason: str


def _column_names(meta: pq.FileMetaData) -> list[str]:
    return [meta.schema.column(i).name for i in range(meta.num_columns)]


def _stats_min_max(meta: pq.FileMetaData, row_group: int, column_name: str) -> tuple[object, object]:
    names = _column_names(meta)
    if column_name not in names:
        raise ValueError(f"Required column {column_name!r} missing. Available columns: {names}")
    col = meta.row_group(row_group).column(names.index(column_name))
    stats = col.statistics
    if stats is None:
        return None, None
    return stats.min, stats.max


def _to_float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _row_group_decisions(
    parquet_path: str,
    channel_specs: list[dict[str, object]],
) -> tuple[list[RowGroupDecision], list[int]]:
    """Select row groups by variable/level statistics.

    Observed June 2026 files are ordered by variable and level. If a row group
    ever has mixed/unknown stats, select it conservatively and filter later.
    """
    pf = pq.ParquetFile(parquet_path)
    meta = pf.metadata
    required_variables, required_pairs = _channel_index(channel_specs)

    decisions: list[RowGroupDecision] = []
    selected_row_groups: list[int] = []

    # A June 2026 `oper` Parquet can contain duplicate row-group blocks for
    # the same logical FourCastNet channel, observed especially for z-levels.
    # Validation correctly flags those as duplicate grid points. Keep the
    # first row group per required (variable, level_hpa) pair and skip later
    # duplicates before materializing pandas data.
    seen_required_pairs: set[tuple[str, float | None]] = set()

    for rg in range(meta.num_row_groups):
        var_min, var_max = _stats_min_max(meta, rg, "variable")
        lev_min, lev_max = _stats_min_max(meta, rg, "isobaricInhPa")
        n_rows = meta.row_group(rg).num_rows

        variable = str(var_min) if var_min == var_max and var_min is not None else None
        level_hpa = _to_float_or_none(lev_min) if lev_min == lev_max else None

        selected = False
        reason = "not_required"
        if variable is None:
            selected = True
            reason = "mixed_or_unknown_variable_select_conservatively"
        elif variable not in required_variables:
            reason = "variable_not_required"
        elif (variable, level_hpa) in required_pairs:
            pair = (variable, level_hpa)
            if pair in seen_required_pairs:
                selected = False
                reason = "duplicate_required_pair_skipped"
            else:
                selected = True
                reason = "required_variable_level"
                seen_required_pairs.add(pair)
        elif level_hpa is None and (variable, None) in required_pairs:
            pair = (variable, None)
            if pair in seen_required_pairs:
                selected = False
                reason = "duplicate_required_surface_pair_skipped"
            else:
                selected = True
                reason = "required_surface_variable"
                seen_required_pairs.add(pair)
        elif lev_min != lev_max:
            selected = True
            reason = "mixed_or_unknown_level_select_conservatively"
        else:
            reason = "level_not_required"

        decisions.append(RowGroupDecision(rg, variable, level_hpa, n_rows, selected, reason))
        if selected:
            selected_row_groups.append(rg)
    return decisions, selected_row_groups


def _read_fourcastnet_relevant_parquet(
    parquet_path: str,
    channel_specs: list[dict[str, object]],
    include_date_run: bool,
) -> tuple[pd.DataFrame, dict]:
    """Read only FourCastNet-relevant rows/columns from one Parquet file."""
    pf = pq.ParquetFile(parquet_path)
    meta = pf.metadata
    names = _column_names(meta)

    columns = list(DEFAULT_READ_COLUMNS)
    # Date and run are added synthetically below instead of read from Parquet
    columns = [c for c in columns if c in names]

    decisions, selected_row_groups = _row_group_decisions(parquet_path, channel_specs)
    selected_rows = sum(d.num_rows for d in decisions if d.selected)
    logger.info(
        "Parquet selection: file=%s row_groups_total=%d row_groups_selected=%d rows_total=%d rows_selected_by_rowgroup=%d",
        parquet_path, meta.num_row_groups, len(selected_row_groups), meta.num_rows, selected_rows,
    )

    if not selected_row_groups:
        preview = [d.__dict__ for d in decisions[:40]]
        raise RuntimeError(f"No row groups selected for FourCastNet channels. First decisions: {preview}")

    tables = [pf.read_row_group(rg, columns=columns) for rg in selected_row_groups]
    table = pa.concat_tables(tables, promote_options="default")
    df = table.to_pandas(self_destruct=True)

    _, required_pairs = _channel_index(channel_specs)
    surface_vars = {var for var, level in required_pairs if level is None}
    upper_pairs = {(var, float(level)) for var, level in required_pairs if level is not None}

    level_col = "isobaricInhPa"
    surface_mask = df["variable"].isin(surface_vars) & df[level_col].isna()
    upper_mask = pd.Series(False, index=df.index)
    if upper_pairs:
        upper_var_names = {var for var, _ in upper_pairs}
        upper_candidate = df[df["variable"].isin(upper_var_names) & df[level_col].notna()]
        upper_pair_index = pd.MultiIndex.from_tuples(upper_pairs, names=["variable", level_col])
        candidate_index = pd.MultiIndex.from_frame(upper_candidate[["variable", level_col]])
        upper_mask.loc[upper_candidate.index] = candidate_index.isin(upper_pair_index)

    df = df.loc[surface_mask | upper_mask].copy()

    # Do not change Bronze->Platinum. Add compatibility alias only for this stage.
    if "isobaricinhpa" not in df.columns and "isobaricInhPa" in df.columns:
        df["isobaricinhpa"] = df["isobaricInhPa"]

    if "variable" in df.columns:
        df["variable"] = df["variable"].astype("category")

    file_stem = Path(parquet_path).stem
    inferred_date = file_stem.split("-")[0]
    inferred_run = inferred_date[8:10] + "z" if len(inferred_date) >= 10 else "00z"
    
    df["date"] = inferred_date
    df["run"] = inferred_run

    read_report = {
        "file": str(parquet_path),
        "inferred_date": inferred_date,
        "inferred_run": inferred_run,
        "added_synthetic_columns": ["date", "run"],
        "rows_total": int(meta.num_rows),
        "row_groups_total": int(meta.num_row_groups),
        "row_groups_selected": int(len(selected_row_groups)),
        "rows_selected_by_rowgroup": int(selected_rows),
        "rows_after_pair_filter": int(len(df)),
        "columns_read": columns,
        "memory_mib_after_filter": _memory_mib(df),
        "variables_after_filter": sorted([str(x) for x in df["variable"].dropna().unique()]),
        "selected_row_groups_preview": [d.__dict__ for d in decisions if d.selected][:80],
        "row_groups_skipped_duplicate_required_pair": int(
            sum(1 for d in decisions if str(d.reason).startswith("duplicate_"))
        ),
        "skipped_duplicate_row_groups_preview": [
            d.__dict__ for d in decisions if str(d.reason).startswith("duplicate_")
        ][:40],
    }
    if "isobaricInhPa" in df.columns:
        read_report["levels_after_filter"] = sorted([float(x) for x in df["isobaricInhPa"].dropna().unique()])
    return df, read_report


def run_job(args: dict[str, str]) -> dict:
    platinum_bucket = args.get("PLATINUM_BUCKET") or DEFAULT_PLATINUM_BUCKET
    parquet_prefix = args.get("PLATINUM_PARQUET_PREFIX") or DEFAULT_PLATINUM_PARQUET_PREFIX
    fourcastnet_prefix = args.get("FOURCASTNET_PREFIX") or DEFAULT_FOURCASTNET_PREFIX
    tmp_dir = args.get("TMP_DIR") or "/tmp"
    allow_incomplete = _truthy(args.get("ALLOW_INCOMPLETE") or "false")
    latitude_policy = args.get("LATITUDE_POLICY") or FOURCASTNET_V0_CONTRACT.latitude_policy
    include_date_run = _truthy(args.get("INCLUDE_DATE_RUN") or "false")
    channel_specs = _load_channel_specs(args)

    max_files = int(args["MAX_FILES"]) if (args.get("MAX_FILES") or "").strip() else None
    lead_hours = set(_csv_int(args["LEAD_HOURS"])) if (args.get("LEAD_HOURS") or "").strip() else None

    year = f"{int(args['YEAR']):04d}"
    month = f"{int(args['MONTH']):02d}"
    day = f"{int(args['DAY']):02d}"
    partition_hour, run_hour = _normalize_hour_arg(args["HOUR"])

    source_partition = _partition_prefix(parquet_prefix, year, month, day, run_hour)
    target_partition = _partition_prefix(fourcastnet_prefix, year, month, day, run_hour)

    parquet_keys = _list_partition_parquet_keys(platinum_bucket, source_partition, lead_hours)
    if max_files is not None:
        parquet_keys = parquet_keys[:max_files]
        logger.info("MAX_FILES active. Processing first %d files only.", max_files)

    local_paths = _download_s3_keys(platinum_bucket, parquet_keys, tmp_dir)
    local_out = Path(tmp_dir) / "fourcastnet_out"
    local_out.mkdir(parents=True, exist_ok=True)

    contract_manifest = build_fourcastnet_contract_manifest(latitude_policy=latitude_policy)
    global_manifest: dict = {
        "status": "ok",
        "platinum_bucket": platinum_bucket,
        "source_partition": source_partition,
        "target_partition": target_partition,
        "year": year,
        "month": month,
        "day": day,
        "hour": partition_hour,
        "run_hour": run_hour,
        "allow_incomplete": allow_incomplete,
        "latitude_policy": latitude_policy,
        "lead_hours": sorted(lead_hours) if lead_hours is not None else None,
        "max_files": max_files,
        "channel_specs": channel_specs,
        "processed_files": [],
        **contract_manifest,
    }

    for local_path in local_paths:
        file_name = Path(local_path).stem
        step_manifest: dict = {
            "source_file": file_name + ".parquet",
            "source_local_path": str(local_path),
            "allow_incomplete": allow_incomplete,
            "tensor_written": False,
            "latitude_policy": latitude_policy,
            "contract_version": contract_manifest["contract_version"],
            "stats_channel_policy": contract_manifest["stats_channel_policy"],
            "normalization_required_before_model": True,
            "tensor_write_reason": "validation_pending",
        }

        try:
            df, read_report = _read_fourcastnet_relevant_parquet(local_path, channel_specs, include_date_run)
            step_manifest["read_report"] = read_report

            validation_report = build_validation_report(df, latitude_policy=latitude_policy)
            validation_report["_read_report"] = read_report
            local_validation = local_out / f"{file_name}_validation_report.json"
            write_manifest(str(local_validation), validation_report)
            _upload_file(str(local_validation), platinum_bucket, f"{target_partition}/{file_name}_validation_report.json")

            if not validation_report.get("ok", False):
                step_manifest["status"] = "incomplete"
                step_manifest["tensor_write_reason"] = "validation_failed"
                global_manifest["processed_files"].append(step_manifest)
                if not allow_incomplete:
                    raise RuntimeError(f"Validation failed for {file_name}: tensor was not written")
                continue

            pre_tensor_debug = _build_pre_tensor_debug(df, channel_specs, latitude_policy)
            local_pre_tensor_debug = local_out / f"{file_name}_pre_tensor_debug.json"
            write_manifest(str(local_pre_tensor_debug), pre_tensor_debug)
            _upload_file(
                str(local_pre_tensor_debug),
                platinum_bucket,
                f"{target_partition}/{file_name}_pre_tensor_debug.json",
            )

            df_for_tensor, tensor_prepare_report = _prepare_df_for_tensor(df, latitude_policy)
            step_manifest["pre_tensor_debug_file"] = f"{file_name}_pre_tensor_debug.json"
            step_manifest["tensor_prepare_report"] = tensor_prepare_report

            tensor = build_fourcastnet_tensor(df_for_tensor, latitude_policy=latitude_policy)
            tensor_finite = bool(np.isfinite(tensor).all())
            if not tensor_finite:
                raise ValueError("Tensor contains non-finite values")
            local_tensor = local_out / f"{file_name}_tensor.npy"
            np.save(str(local_tensor), tensor)
            _upload_file(str(local_tensor), platinum_bucket, f"{target_partition}/{file_name}_tensor.npy")

            step_manifest["status"] = "ok"
            step_manifest["tensor_written"] = True
            step_manifest["tensor_write_reason"] = "written"
            step_manifest["tensor_shape"] = list(tensor.shape)
            step_manifest["tensor_dtype"] = str(tensor.dtype)
            step_manifest["tensor_finite"] = tensor_finite
            step_manifest["tensor_file"] = f"{file_name}_tensor.npy"
            step_manifest["tensor_size_mib"] = float(local_tensor.stat().st_size / 1024 / 1024)
            global_manifest["processed_files"].append(step_manifest)

        except Exception as exc:
            logger.exception("Failed while processing %s", local_path)
            step_manifest["status"] = "error"
            step_manifest["error_type"] = type(exc).__name__
            step_manifest["error_message"] = str(exc)
            step_manifest["tensor_write_reason"] = "error"
            global_manifest["processed_files"].append(step_manifest)
            global_manifest["status"] = "error"
            _write_and_upload_json(
                step_manifest,
                local_out / f"{file_name}_error_manifest.json",
                platinum_bucket,
                f"{target_partition}/{file_name}_error_manifest.json",
            )
            if not allow_incomplete:
                raise

        finally:
            try:
                del df  # type: ignore[name-defined]
            except Exception:
                pass
            try:
                del tensor  # type: ignore[name-defined]
            except Exception:
                pass
            gc.collect()

    local_manifest = local_out / "manifest.json"
    write_manifest(str(local_manifest), global_manifest)
    _upload_file(str(local_manifest), platinum_bucket, f"{target_partition}/manifest.json")
    return global_manifest


def main() -> None:
    args = resolve_args(
        required=["YEAR", "MONTH", "DAY", "HOUR"],
        optional=[
            "PLATINUM_BUCKET",
            "PLATINUM_PARQUET_PREFIX",
            "FOURCASTNET_PREFIX",
            "TMP_DIR",
            "ALLOW_INCOMPLETE",
            "LATITUDE_POLICY",
            "INCLUDE_DATE_RUN",
            "LEAD_HOURS",
            "MAX_FILES",
            "CHANNEL_SPEC_JSON",
        ],
    )
    result = run_job(args)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
