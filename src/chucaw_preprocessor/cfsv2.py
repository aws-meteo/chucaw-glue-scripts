"""Core CFSv2 preprocessing utilities: Bronze GRIB key parsing and Silver long-frame conversion.

Kept intentionally separate from ``chucaw_preprocessor.ecmwf``: CFSv2 Bronze keys carry their
own partition scheme (run_date/cycle/member/product_kind/valid_month) and must not assume the
ECMWF date/run partition layout.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

try:
    import cfgrib
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test envs
    cfgrib = None

DEFAULT_BBOX = {"north": -17.0, "south": -56.0, "west": -76.0, "east": -66.0}

_PARTITION_RE = re.compile(
    r"(provider|product|version|run_date|cycle|member|product_kind|valid_month)=([^/]+)"
)
_REQUIRED_PARTITIONS = [
    "provider",
    "product",
    "version",
    "run_date",
    "cycle",
    "member",
    "product_kind",
    "valid_month",
]

# Coordinates that cfgrib attaches per-message but that are safe to drop when they are
# scalar (non-dimension) attributes rather than the axes data is indexed on.
_NOISY_COORDS = ("number", "surface", "meanSea", "entireAtmosphere", "depthBelowLandLayer")

_METADATA_COLUMNS = _REQUIRED_PARTITIONS + ["lead_month", "avg_kind"]
_OUTPUT_COLUMNS = _METADATA_COLUMNS + [
    "latitude",
    "longitude",
    "variable",
    "level_type",
    "level_value",
    "value",
    "unit",
    "source_s3_uri",
]


def _compute_lead_month(run_date: str, valid_month: str) -> int:
    """Calendar-month offset from run_date to valid_month."""
    run_year, run_month = int(run_date[:4]), int(run_date[4:6])
    valid_year, valid_month_num = int(valid_month[:4]), int(valid_month[4:6])
    return (valid_year - run_year) * 12 + (valid_month_num - run_month)


def parse_bronze_key(key: str) -> dict:
    """Parse a CFSv2 Bronze S3 key into partition metadata; raises ValueError if incomplete."""
    parts = dict(_PARTITION_RE.findall(key))
    missing = [name for name in _REQUIRED_PARTITIONS if name not in parts]
    if missing:
        raise ValueError(f"Cannot parse required CFSv2 partitions {missing} from key: {key}")

    filename = key.rsplit("/", 1)[-1]
    avg_kind = "6hourly" if filename.endswith(".avrg.grib.00Z.grb2") else "daily"

    metadata = dict(parts)
    metadata["source_filename"] = filename
    metadata["avg_kind"] = avg_kind
    metadata["lead_month"] = _compute_lead_month(parts["run_date"], parts["valid_month"])
    return metadata


def _drop_noisy_coords(ds: xr.Dataset) -> xr.Dataset:
    """Drop known noisy scalar coordinates, never a coordinate backing a real dimension."""
    drop = [c for c in ds.coords if c in _NOISY_COORDS and c not in ds.dims]
    return ds.drop_vars(drop, errors="ignore")


def subset_bbox(ds: xr.Dataset, north: float, south: float, west: float, east: float) -> xr.Dataset:
    """Subset to a -180..180-convention bbox, tolerant of a 0..360 dataset; fails fast if empty."""
    if "latitude" not in ds.coords or "longitude" not in ds.coords:
        raise ValueError("Dataset is missing latitude/longitude coordinates required for bbox subsetting")

    lon_values = ds["longitude"].values
    ds_uses_0_360 = bool(lon_values.size) and float(lon_values.max()) > 180.0
    west_n = west % 360 if ds_uses_0_360 else west
    east_n = east % 360 if ds_uses_0_360 else east

    lat_mask = (ds["latitude"] <= north) & (ds["latitude"] >= south)
    lon_mask = (ds["longitude"] >= west_n) & (ds["longitude"] <= east_n)

    if int(lat_mask.sum()) == 0 or int(lon_mask.sum()) == 0:
        raise ValueError(
            f"Bbox selection (north={north}, south={south}, west={west}, east={east}) "
            "returned no data for this dataset's grid"
        )

    return ds.sel(latitude=ds["latitude"][lat_mask], longitude=ds["longitude"][lon_mask])


def _variable_to_long_frame(da: xr.DataArray, var_name: str) -> pd.DataFrame:
    """Convert a single data variable into a tidy long-frame with level metadata."""
    da = da.squeeze(drop=True)
    extra_dims = [d for d in da.dims if d not in ("latitude", "longitude")]
    if len(extra_dims) > 1:
        raise ValueError(
            f"Variable '{var_name}' has unsupported extra dimensions {extra_dims}; "
            "expected at most one level dimension besides latitude/longitude"
        )

    unit = da.attrs.get("units") or da.attrs.get("GRIB_units") or None

    df = da.to_dataframe(name="value").reset_index()
    if extra_dims:
        level_dim = extra_dims[0]
        df["level_type"] = level_dim
        df["level_value"] = df[level_dim].astype("float64")
    else:
        df["level_type"] = "surface"
        df["level_value"] = np.nan

    df["variable"] = var_name
    df["unit"] = unit
    df["value"] = df["value"].astype("float32")

    return df[["latitude", "longitude", "variable", "level_type", "level_value", "value", "unit"]]


def _cast_output_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Cast columns to the Silver Parquet contract dtypes."""
    non_string_cols = {"lead_month", "latitude", "longitude", "level_value", "value", "unit"}
    for col in [c for c in _OUTPUT_COLUMNS if c not in non_string_cols]:
        df[col] = df[col].astype(str)
    df["lead_month"] = df["lead_month"].astype("int32")
    df["latitude"] = df["latitude"].astype("float64")
    df["longitude"] = df["longitude"].astype("float64")
    df["level_value"] = df["level_value"].astype("float64")
    df["value"] = df["value"].astype("float32")
    return df


def build_long_frame_from_datasets(
    datasets: list[xr.Dataset],
    metadata: dict,
    bbox: dict,
    source_s3_uri: str,
) -> pd.DataFrame:
    """Build the tidy Silver long-frame from already-opened xarray datasets.

    Pure function (no file/network I/O) so it can be unit tested with synthetic datasets.
    """
    frames: list[pd.DataFrame] = []
    for ds in datasets:
        ds = _drop_noisy_coords(ds)
        ds = subset_bbox(ds, **bbox)
        for var_name in ds.data_vars:
            frames.append(_variable_to_long_frame(ds[var_name], var_name))

    if not frames:
        raise ValueError("No data variables found across GRIB datasets after bbox subsetting")

    long_df = pd.concat(frames, ignore_index=True)

    for col in _METADATA_COLUMNS:
        long_df[col] = metadata[col]
    long_df["source_s3_uri"] = source_s3_uri

    long_df = _cast_output_schema(long_df)
    return long_df[_OUTPUT_COLUMNS]


def process_grib_to_long_frame(
    grib_path: str,
    metadata: dict,
    bbox: dict,
    source_s3_uri: str,
) -> pd.DataFrame:
    """Open a CFSv2 GRIB file defensively (per-message-group, no forced merge) and build the Silver long-frame."""
    if cfgrib is None:
        raise ModuleNotFoundError(
            "cfgrib is required to load GRIB files. Install cfgrib/eccodes for runtime ingestion."
        )
    datasets = cfgrib.open_datasets(grib_path, backend_kwargs={"decode_timedelta": False})
    return build_long_frame_from_datasets(datasets, metadata, bbox, source_s3_uri)


def build_output_key(silver_prefix: str, metadata: dict) -> str:
    """Build the Silver Parquet partition key for a single CFSv2 GRIB file.

    Deliberately independent of ECMWF's ``year=/month=/day=/hour=`` partition scheme.
    """
    return (
        f"{silver_prefix.strip('/')}"
        f"/run_date={metadata['run_date']}"
        f"/cycle={metadata['cycle']}"
        f"/member={metadata['member']}"
        f"/product_kind={metadata['product_kind']}"
        f"/valid_month={metadata['valid_month']}"
        f"/avg_kind={metadata['avg_kind']}"
        "/part-000.parquet"
    )


def write_long_frame_parquet(df: pd.DataFrame, output_path: str) -> str:
    """Write the long-frame to a single local Parquet file."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False, compression="snappy")
    return output_path


def build_manifest(metadata: dict, silver_key: str, source_s3_uri: str, row_count: int) -> dict:
    """Build a small manifest describing the written Silver Parquet output."""
    manifest = {k: metadata[k] for k in _METADATA_COLUMNS}
    manifest["source_filename"] = metadata.get("source_filename")
    manifest["silver_key"] = silver_key
    manifest["source_s3_uri"] = source_s3_uri
    manifest["row_count"] = row_count
    return manifest
