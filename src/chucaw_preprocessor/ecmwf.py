"""Core ECMWF preprocessing utilities for GRIB ingestion and serialization."""

import os
from pathlib import Path

import boto3

try:
    import eccodeslib

    lib_dir_candidate = Path(eccodeslib.__file__).resolve().parent / "lib"
    if lib_dir_candidate.exists():
        lib_dir = lib_dir_candidate
    else:
        eccodes_root = Path(eccodeslib.__file__).resolve().parent
        matches = list(eccodes_root.rglob("libeccodes*.so*"))
        if matches:
            lib_dir = matches[0].parent
        else:
            lib_dir = None

    if lib_dir and lib_dir.exists():
        os.environ["ECCODES_DIR"] = str(lib_dir)
        current_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = f"{lib_dir}:{current_ld_path}" if current_ld_path else str(lib_dir)
except ImportError:
    pass

import cfgrib
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import xarray as xr

EXPECTED_PRESSURE_LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]
_DROP_COORDS = ["heightAboveGround", "meanSea", "entireAtmosphere", "soilLayer"]
_SURFACE_VARS = ["msl", "u10", "v10", "t2m"]
_UPPER_VARS = ["q", "t", "u", "v"]
_GRAVITY = 9.80665


def download_grib_from_s3(bucket: str, key: str, download_dir: str = "/tmp") -> str:
    """Download GRIB object from S3.

    Parameters
    ----------
    bucket : str
        Source S3 bucket.
    key : str
        Source S3 key.
    download_dir : str, default "/tmp"
        Local directory used for temporary download.

    Returns
    -------
    str
        Local path to downloaded GRIB file.
    """
    local_path = str(Path(download_dir) / Path(key).name)
    s3 = boto3.client("s3")
    s3.download_file(bucket, key, local_path)
    return local_path


def upload_file_to_s3(local_path: str, bucket: str, key: str) -> None:
    """Upload local file to S3."""
    s3 = boto3.client("s3")
    s3.upload_file(local_path, bucket, key)


def load_merged_dataset(grib_path: str) -> xr.Dataset:
    """Load and merge GRIB message groups into a single dataset.

    Parameters
    ----------
    grib_path : str
        Local path to a GRIB file.

    Returns
    -------
    xarray.Dataset
        Merged dataset sorted by latitude (descending), when available.
    """
    # Use decode_timedelta=False to avoid pandas 3.x compatibility issues
    backend_kwargs = {"decode_timedelta": False}
    datasets = cfgrib.open_datasets(grib_path, backend_kwargs=backend_kwargs)
    cleaned = []
    for dataset in datasets:
        cleaned.append(dataset.drop_vars([c for c in dataset.coords if c in _DROP_COORDS], errors="ignore"))
    merged = xr.merge(cleaned, compat="override")
    if "latitude" in merged.coords:
        merged = merged.sortby("latitude", ascending=False)
    return merged


def _squeeze(data_array: xr.DataArray) -> np.ndarray:
    return np.asarray(data_array.values).squeeze()


def build_pangu_arrays(ds: xr.Dataset) -> tuple[np.ndarray, np.ndarray]:
    """Build Pangu tensors from merged ECMWF dataset.

    Parameters
    ----------
    ds : xarray.Dataset
        Merged ECMWF dataset.

    Returns
    -------
    tuple[numpy.ndarray, numpy.ndarray]
        ``(surface_array, upper_array)`` with ``float32`` dtype.
    """
    surface_values = [_squeeze(ds[var]) for var in _SURFACE_VARS]
    surface_array = np.stack(surface_values, axis=0).astype(np.float32)

    ds_pl = ds.sel(isobaricInhPa=EXPECTED_PRESSURE_LEVELS)
    z = _squeeze(ds_pl["gh"]) * _GRAVITY
    upper_values = [z] + [_squeeze(ds_pl[var]) for var in _UPPER_VARS]
    upper_array = np.stack(upper_values, axis=0).astype(np.float32)
    return surface_array, upper_array


def build_parquet_frames(ds: xr.Dataset) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build tidy dataframes for surface and upper-level fields.

    Parameters
    ----------
    ds : xarray.Dataset
        Merged ECMWF dataset.

    Returns
    -------
    tuple[pandas.DataFrame, pandas.DataFrame]
        ``(surface_df, upper_df)``.
    """
    surface = ds[_SURFACE_VARS].to_array("variable").rename("value").to_dataframe().reset_index()
    surface["value"] = surface["value"].astype("float32")

    ds_pl = ds.sel(isobaricInhPa=EXPECTED_PRESSURE_LEVELS)
    upper = xr.Dataset(
        {
            "z": ds_pl["gh"] * _GRAVITY,
            "q": ds_pl["q"],
            "t": ds_pl["t"],
            "u": ds_pl["u"],
            "v": ds_pl["v"],
        }
    )
    upper = upper.to_array("variable").rename("value").to_dataframe().reset_index()
    upper["value"] = upper["value"].astype("float32")
    return surface, upper


def write_pangu_arrays(surface_array: np.ndarray, upper_array: np.ndarray, output_dir: str) -> tuple[str, str]:
    """Write Pangu arrays to ``.npy`` files."""
    os.makedirs(output_dir, exist_ok=True)
    surface_path = str(Path(output_dir) / "input_surface.npy")
    upper_path = str(Path(output_dir) / "input_upper.npy")
    np.save(surface_path, surface_array)
    np.save(upper_path, upper_array)
    return surface_path, upper_path


def write_parquet_frames(surface_df: pd.DataFrame, upper_df: pd.DataFrame, output_dir: str) -> tuple[str, str]:
    """Write surface/upper dataframes to parquet files."""
    os.makedirs(output_dir, exist_ok=True)
    surface_path = str(Path(output_dir) / "surface.parquet")
    upper_path = str(Path(output_dir) / "upper.parquet")
    surface_df.to_parquet(surface_path, index=False, compression="snappy")
    upper_df.to_parquet(upper_path, index=False, compression="snappy")
    return surface_path, upper_path

import pyarrow as pa
import pyarrow.parquet as pq


def serialize_parquet_chunked(ds: xr.Dataset, output_path: str, date_str: str, run_str: str) -> str:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    writer = None
    for var in _SURFACE_VARS:
        if var not in ds.data_vars: continue
        ds_var = ds[[var]].to_dataframe().reset_index()
        ds_var = ds_var.rename(columns={var: "value"})
        ds_var["variable"] = var
        ds_var["value"] = ds_var["value"].astype("float32")
        ds_var["date"] = date_str
        ds_var["run"] = run_str
        ds_var["isobaricInhPa"] = np.nan
        cols = ["isobaricInhPa", "latitude", "longitude", "variable", "value", "date", "run"]
        table = pa.Table.from_pandas(ds_var[cols])
        if writer is None:
            writer = pq.ParquetWriter(output_path, table.schema, compression="snappy")
        writer.write_table(table)

    ds_pl = ds.sel(isobaricInhPa=EXPECTED_PRESSURE_LEVELS)
    
    if "gh" in ds_pl.data_vars:
        for p_level in ds_pl.isobaricInhPa.values:
            ds_sub = ds_pl[["gh"]].sel(isobaricInhPa=p_level)
            z_array = ds_sub["gh"] * _GRAVITY
            z_array.name = "z"
            ds_var = z_array.to_dataframe().reset_index()
            ds_var = ds_var.rename(columns={"z": "value"})
            ds_var["variable"] = "z"
            ds_var["value"] = ds_var["value"].astype("float32")
            ds_var["date"] = date_str
            ds_var["run"] = run_str
            ds_var["isobaricInhPa"] = float(p_level)
            cols = ["isobaricInhPa", "latitude", "longitude", "variable", "value", "date", "run"]
            table = pa.Table.from_pandas(ds_var[cols])
            if writer is None:
                writer = pq.ParquetWriter(output_path, table.schema, compression="snappy")
            writer.write_table(table)

    for var in _UPPER_VARS:
        if var not in ds_pl.data_vars: continue
        for p_level in ds_pl.isobaricInhPa.values:
            ds_sub = ds_pl[[var]].sel(isobaricInhPa=p_level)
            ds_var = ds_sub.to_dataframe().reset_index()
            ds_var = ds_var.rename(columns={var: "value"})
            ds_var["variable"] = var
            ds_var["value"] = ds_var["value"].astype("float32")
            ds_var["date"] = date_str
            ds_var["run"] = run_str
            ds_var["isobaricInhPa"] = float(p_level)
            cols = ["isobaricInhPa", "latitude", "longitude", "variable", "value", "date", "run"]
            table = pa.Table.from_pandas(ds_var[cols])
            if writer is None:
                writer = pq.ParquetWriter(output_path, table.schema, compression="snappy")
            writer.write_table(table)

    if writer: writer.close()
    return output_path
