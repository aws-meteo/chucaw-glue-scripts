"""Core ECMWF preprocessing utilities for GRIB ingestion and serialization."""

import os
from pathlib import Path

import boto3
import cfgrib
import numpy as np
import pandas as pd
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
    datasets = cfgrib.open_datasets(grib_path)
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
