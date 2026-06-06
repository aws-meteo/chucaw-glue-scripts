"""FourCastNet snapshot preprocessing helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

EXPECTED_LATS = np.arange(90.0, -90.0, -0.25, dtype=np.float32)
EXPECTED_LONS = np.arange(0.0, 360.0, 0.25, dtype=np.float32)
ALLOWED_LATITUDE_POLICIES = {"fail", "drop_south_pole", "drop_north_pole"}
FOURCASTNET_CONTRACT_VERSION = "fcn_v0_nvlabs_20ch_first20stats"
FOURCASTNET_STATS_CHANNEL_POLICY = "first_20_channels"
FOURCASTNET_DROPPED_STATS_CHANNEL_INDEX = 20
FOURCASTNET_DROPPED_STATS_CHANNEL_NAME = "sst"
FOURCASTNET_EXPECTED_SHAPE = (1, 20, 720, 1440)
FOURCASTNET_INPUT_DTYPE = "float32"
FCN_DATASET_NAME = "fields"
FOURCASTNET_REQUIRED_CHANNELS = [
    ("u10", None),
    ("v10", None),
    ("t2m", None),
    ("sp", None),
    ("msl", None),
    ("t", 850.0),
    ("u", 1000.0),
    ("v", 1000.0),
    ("z", 1000.0),
    ("u", 850.0),
    ("v", 850.0),
    ("z", 850.0),
    ("u", 500.0),
    ("v", 500.0),
    ("z", 500.0),
    ("t", 500.0),
    ("z", 50.0),
    ("r", 500.0),
    ("r", 850.0),
    ("tcwv", None),
]

FOURCASTNET_CHANNEL_UNITS = {
    "u10": "m s**-1",
    "v10": "m s**-1",
    "t2m": "K",
    "sp": "Pa",
    "msl": "Pa",
    "t": "K",
    "u": "m s**-1",
    "v": "m s**-1",
    "z": "m**2 s**-2",
    "r": "%",
    "tcwv": "kg m**-2",
}


@dataclass(frozen=True)
class FourCastNetV0Contract:
    """Executable FourCastNet V0 tensor and normalization contract."""

    contract_version: str = FOURCASTNET_CONTRACT_VERSION
    channel_order: tuple[tuple[str, float | None], ...] = tuple(FOURCASTNET_REQUIRED_CHANNELS)
    expected_shape: tuple[int, int, int, int] = FOURCASTNET_EXPECTED_SHAPE
    input_dtype: str = FOURCASTNET_INPUT_DTYPE
    latitude_policy: str = "drop_south_pole"
    longitude_policy: str = "normalize_to_0_360_ascending"
    stats_channel_policy: str = FOURCASTNET_STATS_CHANNEL_POLICY
    normalization_formula: str = "(raw - global_mean[channel]) / global_std[channel]"
    grid: dict[str, Any] = field(
        default_factory=lambda: {
            "latitude_order": "descending",
            "latitude_start": 90.0,
            "latitude_end": -89.75,
            "latitude_step": -0.25,
            "longitude_order": "ascending",
            "longitude_start": 0.0,
            "longitude_end": 359.75,
            "longitude_step": 0.25,
        }
    )

    def manifest_fields(self, *, latitude_policy: str | None = None) -> dict[str, Any]:
        policy = latitude_policy or self.latitude_policy
        return {
            "contract_version": self.contract_version,
            "channel_order": build_fourcastnet_channel_descriptors(),
            "expected_shape": list(self.expected_shape),
            "input_dtype": self.input_dtype,
            "grid": self.grid,
            "latitude_policy": policy,
            "longitude_policy": self.longitude_policy,
            "stats_channel_policy": self.stats_channel_policy,
            "normalization_formula": self.normalization_formula,
            "normalization_required_before_model": True,
            "stats_channels_original": 21,
            "stats_channels_used": 20,
            "dropped_stats_channel": FOURCASTNET_DROPPED_STATS_CHANNEL_INDEX,
            "dropped_stats_channel_name": FOURCASTNET_DROPPED_STATS_CHANNEL_NAME,
        }


FOURCASTNET_V0_CONTRACT = FourCastNetV0Contract()


def normalize_level_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza el nombre de la columna de niveles de presión a 'isobaricInhPa'.

    Parameters
    ----------
    df : pd.DataFrame
        Dataframe con datos meteorológicos.

    Returns
    -------
    pd.DataFrame
        Dataframe con la columna normalizada.

    Raises
    ------
    ValueError
        Si no se encuentra una columna de nivel reconocida (isobaricInhPa o isobaricinhpa).
    """
    if "isobaricInhPa" in df.columns:
        return df
    if "isobaricinhpa" in df.columns:
        normalized = df.copy(deep=False)
        normalized["isobaricInhPa"] = normalized["isobaricinhpa"]
        return normalized
    raise ValueError("Missing pressure-level column: expected isobaricInhPa or isobaricinhpa")


def normalize_longitudes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza las longitudes al rango [0, 360).

    Parameters
    ----------
    df : pd.DataFrame
        Dataframe que debe contener la columna 'longitude'.

    Returns
    -------
    pd.DataFrame
        Dataframe con las longitudes normalizadas.

    Raises
    ------
    ValueError
        Si falta la columna 'longitude'.
    """
    if "longitude" not in df.columns:
        raise ValueError("Missing required column: longitude")
    normalized = df.copy(deep=False)
    normalized["longitude"] = np.mod(normalized["longitude"].astype(float), 360.0)
    return normalized


def validate_latitude_policy(latitude_policy: str) -> str:
    """
    Valida que la política de latitudes sea una de las permitidas.

    Parameters
    ----------
    latitude_policy : str
        Nombre de la política (fail, drop_south_pole, drop_north_pole).

    Returns
    -------
    str
        La política normalizada en minúsculas.

    Raises
    ------
    ValueError
        Si la política no es válida.
    """
    policy = str(latitude_policy or "fail").strip().lower()
    if policy not in ALLOWED_LATITUDE_POLICIES:
        raise ValueError(
            f"Invalid latitude_policy={latitude_policy!r}. "
            f"Expected one of {sorted(ALLOWED_LATITUDE_POLICIES)}"
        )
    return policy


def resolve_expected_lats(
    observed_lats: np.ndarray,
    latitude_policy: str = "fail",
) -> tuple[np.ndarray | None, dict[str, Any]]:
    """
    Resuelve y valida las latitudes observadas según la política definida.

    Parameters
    ----------
    observed_lats : np.ndarray
        Array de latitudes presentes en los datos.
    latitude_policy : str, opcional
        Política para manejar grids de 721 puntos (ej. con polos), por defecto "fail".

    Returns
    -------
    tuple[np.ndarray | None, dict[str, Any]]
        Tupla con las latitudes finales (o None si falló) y un diccionario con detalles.
    """
    policy = validate_latitude_policy(latitude_policy)
    lats = np.array(sorted(np.asarray(observed_lats, dtype=float).tolist(), reverse=True), dtype=np.float32)

    details: dict[str, Any] = {
        "original_lat_count": int(len(lats)),
        "final_lat_count": int(len(lats)),
        "original_lat_min": float(np.min(lats)) if len(lats) else None,
        "original_lat_max": float(np.max(lats)) if len(lats) else None,
        "final_lat_min": float(np.min(lats)) if len(lats) else None,
        "final_lat_max": float(np.max(lats)) if len(lats) else None,
        "latitude_policy": policy,
        "latitude_policy_applied": "none",
    }

    if len(lats) == 720:
        return lats, details

    if len(lats) == 721:
        if policy == "fail":
            details["latitude_policy_applied"] = "latitude_policy_required"
            return None, details
        if policy == "drop_south_pole":
            dropped_lat = -90.0
            out = lats[lats > -90.0]
        else:
            dropped_lat = 90.0
            out = lats[lats < 90.0]
        details["latitude_policy_applied"] = policy
        details["dropped_latitude"] = dropped_lat
        details["final_lat_count"] = int(len(out))
        details["final_lat_min"] = float(np.min(out)) if len(out) else None
        details["final_lat_max"] = float(np.max(out)) if len(out) else None
        return out.astype(np.float32), details

    details["latitude_policy_applied"] = "unsupported_latitude_count"
    return None, details


def build_fourcastnet_channel_map() -> list[tuple[str, float | None]]:
    """
    Retorna el mapa de canales de FourCastNet V0.

    Returns
    -------
    list[tuple[str, float | None]]
        Lista de tuplas (variable, nivel_de_presion).
    """
    return list(FOURCASTNET_REQUIRED_CHANNELS)


def build_fourcastnet_channel_descriptors() -> list[dict[str, Any]]:
    """
    Retorna los descriptores de canales con su índice y orden estable.

    Returns
    -------
    list[dict[str, Any]]
        Lista de diccionarios con metadatos de cada canal.
    """
    out: list[dict[str, Any]] = []
    for idx, (variable, level) in enumerate(build_fourcastnet_channel_map()):
        level_name = "surface" if level is None else f"{level:g}hPa"
        out.append(
            {
                "channel_index": idx,
                "name": variable if level is None else f"{variable}{level:g}",
                "variable": variable,
                "level": level,
                "level_name": level_name,
                "expected_raw_unit": FOURCASTNET_CHANNEL_UNITS.get(variable),
                "stats_index_used": idx,
            }
        )
    return out


def build_fourcastnet_contract_manifest(latitude_policy: str | None = None) -> dict[str, Any]:
    """Return JSON-serializable metadata for the FCN V0 normalization contract."""
    return FOURCASTNET_V0_CONTRACT.manifest_fields(latitude_policy=latitude_policy)


def _reshape_single_stat(
    arr: np.ndarray,
    tensor_channels: int,
    *,
    policy: str | None,
    name: str,
) -> tuple[np.ndarray, dict[str, Any]]:
    stat = np.asarray(arr, dtype=np.float32)
    meta: dict[str, Any] = {
        "name": name,
        "stats_original_shape": list(stat.shape),
        "stats_channels_original": None,
        "stats_channels_used": None,
        "stats_channel_policy": policy,
        "dropped_stats_channel": None,
        "dropped_stats_channel_name": None,
    }

    if stat.ndim == 1:
        channels = int(stat.shape[0])
        meta["stats_channels_original"] = channels
        source = stat.reshape(1, channels, 1, 1)
    elif stat.ndim == 4:
        channels = int(stat.shape[1])
        meta["stats_channels_original"] = channels
        source = stat
    else:
        raise ValueError(f"Unsupported {name} stats shape: {stat.shape}")

    if channels == tensor_channels:
        meta["stats_channels_used"] = tensor_channels
        meta["stats_channel_policy"] = "exact_match"
        out = source
    elif channels == 21 and tensor_channels == 20:
        if policy != FOURCASTNET_STATS_CHANNEL_POLICY:
            raise ValueError(
                "Stats has 21 channels while tensor has 20; "
                "--STATS_CHANNEL_POLICY first_20_channels is required"
            )
        out = source[:, :20, :, :]
        meta["stats_channels_used"] = 20
        meta["dropped_stats_channel"] = FOURCASTNET_DROPPED_STATS_CHANNEL_INDEX
        meta["dropped_stats_channel_name"] = FOURCASTNET_DROPPED_STATS_CHANNEL_NAME
    else:
        raise ValueError(
            f"Stats channel count mismatch for {name}: stats={channels}, tensor={tensor_channels}"
        )

    if out.shape[0] not in {1} or out.shape[2:] != (1, 1):
        raise ValueError(f"{name} stats must broadcast as (1, C, 1, 1), got {out.shape}")
    if not np.isfinite(out).all():
        raise ValueError(f"{name} stats contain non-finite values")
    return out.astype(np.float32, copy=False), meta


def prepare_fourcastnet_stats(
    means: np.ndarray,
    stds: np.ndarray,
    policy: str | None = FOURCASTNET_STATS_CHANNEL_POLICY,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Align FourCastNet global mean/std arrays to the 20-channel V0 tensor."""
    means_out, means_meta = _reshape_single_stat(
        means,
        FOURCASTNET_EXPECTED_SHAPE[1],
        policy=policy,
        name="means",
    )
    stds_out, stds_meta = _reshape_single_stat(
        stds,
        FOURCASTNET_EXPECTED_SHAPE[1],
        policy=policy,
        name="stds",
    )
    if means_out.shape != stds_out.shape:
        raise ValueError(f"Means/stds shape mismatch: {means_out.shape} != {stds_out.shape}")
    if means_meta["stats_channels_original"] != stds_meta["stats_channels_original"]:
        raise ValueError(
            "Means/stds original channel counts differ: "
            f"{means_meta['stats_channels_original']} != {stds_meta['stats_channels_original']}"
        )
    if not np.all(stds_out > 0):
        raise ValueError("stds must be strictly positive")

    meta = {
        "contract_version": FOURCASTNET_CONTRACT_VERSION,
        "stats_channel_policy": means_meta["stats_channel_policy"],
        "stats_channels_original": means_meta["stats_channels_original"],
        "stats_channels_used": means_meta["stats_channels_used"],
        "dropped_stats_channel": means_meta["dropped_stats_channel"],
        "dropped_stats_channel_name": means_meta["dropped_stats_channel_name"],
        "means_metadata": means_meta,
        "stds_metadata": stds_meta,
    }
    return means_out, stds_out, meta


def normalize_fourcastnet_tensor(
    tensor: np.ndarray,
    means: np.ndarray,
    stds: np.ndarray,
    contract_version: str = FOURCASTNET_CONTRACT_VERSION,
) -> np.ndarray:
    """Normalize a raw FourCastNet tensor using broadcast mean/std arrays."""
    if contract_version != FOURCASTNET_CONTRACT_VERSION:
        raise ValueError(
            f"Unsupported contract_version={contract_version!r}; "
            f"expected {FOURCASTNET_CONTRACT_VERSION!r}"
        )
    arr = np.asarray(tensor, dtype=np.float32)
    if arr.ndim != 4 or arr.shape[0] != 1 or arr.shape[1] != FOURCASTNET_EXPECTED_SHAPE[1]:
        raise ValueError(f"Unexpected tensor shape for normalization: {arr.shape}")
    if not np.isfinite(arr).all():
        raise ValueError("tensor contains non-finite values")

    mean_arr = np.asarray(means, dtype=np.float32)
    std_arr = np.asarray(stds, dtype=np.float32)
    expected_stats_shape = (1, arr.shape[1], 1, 1)
    if mean_arr.shape != expected_stats_shape or std_arr.shape != expected_stats_shape:
        raise ValueError(
            f"Stats must have shape {expected_stats_shape}, got {mean_arr.shape} and {std_arr.shape}"
        )
    if not np.isfinite(mean_arr).all() or not np.isfinite(std_arr).all():
        raise ValueError("mean/std stats contain non-finite values")
    if not np.all(std_arr > 0):
        raise ValueError("stds must be strictly positive")

    normalized = (arr - mean_arr) / std_arr
    if not np.isfinite(normalized).all():
        raise ValueError("normalized tensor contains non-finite values")
    return normalized.astype(np.float32, copy=False)


def validate_fourcastnet_contract(
    tensor: np.ndarray,
    means: np.ndarray | None = None,
    stds: np.ndarray | None = None,
    manifest: dict[str, Any] | None = None,
    *,
    allow_test_grid: bool = False,
    stats_channel_policy: str | None = FOURCASTNET_STATS_CHANNEL_POLICY,
) -> dict[str, Any]:
    """Validate tensor, optional stats, and optional manifest against FCN V0."""
    arr = np.asarray(tensor)
    report: dict[str, Any] = {
        "ok": False,
        "tensor_ok": False,
        "stats_ok": None,
        "normalization_ok": None,
        "contract_version": FOURCASTNET_CONTRACT_VERSION,
        "shape": list(arr.shape),
        "dtype": str(arr.dtype),
    }

    expected_shape = FOURCASTNET_EXPECTED_SHAPE
    if allow_test_grid:
        shape_ok = arr.ndim == 4 and arr.shape[0] == 1 and arr.shape[1] == expected_shape[1]
    else:
        shape_ok = tuple(arr.shape) == expected_shape
    if not shape_ok:
        raise ValueError(f"Invalid tensor shape: {arr.shape}")
    if not np.issubdtype(arr.dtype, np.floating):
        arr = arr.astype(np.float32)
    else:
        arr = arr.astype(np.float32, copy=False)
    if not np.isfinite(arr).all():
        raise ValueError("tensor contains non-finite values")
    report["tensor_ok"] = True

    if manifest is not None:
        manifest_version = manifest.get("contract_version")
        if manifest_version not in {None, FOURCASTNET_CONTRACT_VERSION}:
            raise ValueError(
                f"Manifest contract_version mismatch: {manifest_version!r} != {FOURCASTNET_CONTRACT_VERSION!r}"
            )
        if manifest.get("normalization_required_before_model") is False:
            raise ValueError("Manifest incorrectly marks normalization as not required")

    if means is not None or stds is not None:
        if means is None or stds is None:
            raise ValueError("Both means and stds are required together")
        prepared_means, prepared_stds, stats_meta = prepare_fourcastnet_stats(
            means,
            stds,
            policy=stats_channel_policy,
        )
        report.update(stats_meta)
        normalized = normalize_fourcastnet_tensor(arr, prepared_means, prepared_stds)
        report["stats_ok"] = True
        report["normalization_ok"] = True
        report["normalized_abs_channel_mean_max"] = float(
            np.max(np.abs(np.mean(normalized, axis=(0, 2, 3))))
        )

    report["ok"] = bool(
        report["tensor_ok"]
        and (report["stats_ok"] in {None, True})
        and (report["normalization_ok"] in {None, True})
    )
    return report


def specific_humidity_to_relative_humidity(
    q: np.ndarray,
    t_k: np.ndarray,
    pressure_hpa: float,
    *,
    clip_percent: bool = True,
) -> tuple[np.ndarray, dict[str, Any]]:
    """
    Deriva la humedad relativa (RH %) a partir de la humedad específica (q).

    Calcula la RH para compatibilidad con FourCastNet usando humedad específica (kg/kg),
    temperatura (K) y presión (hPa). Utiliza la fórmula de Bolton para la presión
    de vapor de saturación.

    Parameters
    ----------
    q : np.ndarray
        Humedad específica en kg/kg.
    t_k : np.ndarray
        Temperatura en Kelvin.
    pressure_hpa : float
        Presión en hPa.
    clip_percent : bool, opcional
        Si se deben limitar los valores al rango [0, 100], por defecto True.

    Returns
    -------
    tuple[np.ndarray, dict[str, Any]]
        Tupla con el array de RH (float32) y un resumen estadístico.

    Raises
    ------
    ValueError
        Si hay discrepancias en las formas de los arrays o valores no finitos.
    """
    q_arr = np.asarray(q, dtype=np.float64)
    t_arr = np.asarray(t_k, dtype=np.float64)
    if q_arr.shape != t_arr.shape:
        raise ValueError(f"q and t_k shape mismatch: {q_arr.shape} != {t_arr.shape}")
    if not np.isfinite(pressure_hpa) or pressure_hpa <= 0.0:
        raise ValueError(f"Invalid pressure_hpa={pressure_hpa!r}")
    if not np.all(np.isfinite(q_arr)) or not np.all(np.isfinite(t_arr)):
        raise ValueError("q and t_k must be finite")

    # Bolton-style saturation vapor pressure over water (hPa).
    e_s = 6.112 * np.exp((17.67 * (t_arr - 273.15)) / (t_arr - 29.65))
    # Convert q to mixing ratio.
    w = q_arr / np.maximum(1.0 - q_arr, 1e-12)
    epsilon = 0.622
    p = float(pressure_hpa)
    ws = (epsilon * e_s) / np.maximum(p - e_s, 1e-6)
    rh_ratio = w / np.maximum(ws, 1e-12)
    rh_percent = 100.0 * rh_ratio

    clipped_count = 0
    if clip_percent:
        before = rh_percent.copy()
        rh_percent = np.clip(rh_percent, 0.0, 100.0)
        clipped_count = int(np.count_nonzero(before != rh_percent))

    if not np.all(np.isfinite(rh_percent)):
        raise ValueError("Derived RH contains non-finite values")

    summary = {
        "pressure_hpa": float(pressure_hpa),
        "clip_percent": bool(clip_percent),
        "clipped_value_count": clipped_count,
        "rh_percent_min": float(np.min(rh_percent)),
        "rh_percent_max": float(np.max(rh_percent)),
        "rh_percent_mean": float(np.mean(rh_percent)),
    }
    return rh_percent.astype(np.float32), summary


def select_channel_frame(df: pd.DataFrame, variable: str, level: float | None) -> pd.DataFrame:
    """
    Selecciona un subconjunto de datos (canal) basado en variable y nivel.

    Parameters
    ----------
    df : pd.DataFrame
        Dataframe 'tidy' con datos normalizados.
    variable : str
        Nombre de la variable.
    level : float | None
        Nivel de presión. None indica variables de superficie.

    Returns
    -------
    pd.DataFrame
        Dataframe filtrado con los datos del canal.

    Raises
    ------
    ValueError
        Si faltan columnas requeridas en el dataframe.
    """
    base = normalize_level_column(df)
    required = {"variable", "latitude", "longitude", "value", "isobaricInhPa"}
    missing_cols = sorted(required - set(base.columns))
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    vdf = base[base["variable"].astype(str).str.lower() == variable.lower()].copy()
    level_values = pd.to_numeric(vdf["isobaricInhPa"], errors="coerce")
    if level is None:
        surface_mask = level_values.isna() | np.isclose(level_values, 0.0, atol=1e-6)
        return vdf[surface_mask].copy()

    return vdf[np.isclose(level_values, float(level), atol=1e-6)].copy()


def field_to_grid(
    df_channel: pd.DataFrame,
    expected_lats: np.ndarray = EXPECTED_LATS,
    expected_lons: np.ndarray = EXPECTED_LONS,
) -> np.ndarray:
    """
    Convierte un dataframe de canal en un grid 2D ordenado para FourCastNet.

    Normaliza longitudes, valida la cardinalidad de las coordenadas y realiza
    un pivotado para obtener la matriz latitud x longitud.

    Parameters
    ----------
    df_channel : pd.DataFrame
        Dataframe con los datos de un canal específico.
    expected_lats : np.ndarray, opcional
        Latitudes esperadas del grid.
    expected_lons : np.ndarray, opcional
        Longitudes esperadas del grid.

    Returns
    -------
    np.ndarray
        Array 2D (float32) con la forma (len(expected_lats), len(expected_lons)).

    Raises
    ------
    ValueError
        Si hay discrepancias en las coordenadas, duplicados o puntos faltantes.
    """
    if df_channel.empty:
        raise ValueError("Channel frame is empty")

    work = normalize_longitudes(df_channel)
    work = work[["latitude", "longitude", "value"]].copy()
    work["latitude"] = work["latitude"].astype(float)
    work["longitude"] = work["longitude"].astype(float)

    rounded_lats = np.round(work["latitude"].to_numpy(), 5)
    rounded_lons = np.round(work["longitude"].to_numpy(), 5)
    if len(np.unique(rounded_lats)) != len(expected_lats):
        raise ValueError("Latitude cardinality mismatch for channel")
    if len(np.unique(rounded_lons)) != len(expected_lons):
        raise ValueError("Longitude cardinality mismatch for channel")

    duplicates = work.duplicated(subset=["latitude", "longitude"]).any()
    if duplicates:
        raise ValueError("Duplicate (latitude, longitude) points found")

    pivot = work.pivot(index="latitude", columns="longitude", values="value")
    pivot = pivot.reindex(index=expected_lats, columns=expected_lons)

    if pivot.isnull().any().any():
        raise ValueError("Channel grid has missing points after reindex")

    return pivot.to_numpy(dtype=np.float32)


def build_validation_report(df: pd.DataFrame, latitude_policy: str = "fail") -> dict[str, Any]:
    """
    Genera un informe detallado de validación para la cobertura de canales y el grid.

    Verifica la presencia de columnas, canales requeridos para FCN, duplicados
    y compatibilidad con el grid esperado (720x1440).

    Parameters
    ----------
    df : pd.DataFrame
        Dataframe con los datos a validar.
    latitude_policy : str, opcional
        Política para el manejo de latitudes, por defecto "fail".

    Returns
    -------
    dict[str, Any]
        Informe con el estado 'ok', variables disponibles, canales faltantes y metadatos.
    """
    report: dict[str, Any] = {
        "ok": False,
        "missing_columns": [],
        "missing_channels": [],
        "available_variables": [],
        "available_variable_levels": [],
        "duplicate_points_by_channel": [],
        "grid": {},
        "row_count": int(len(df)),
    }

    required_cols = ["latitude", "longitude", "variable", "value", "date", "run"]
    missing_cols = [col for col in required_cols if col not in df.columns]

    has_level = "isobaricInhPa" in df.columns or "isobaricinhpa" in df.columns
    if not has_level:
        missing_cols.append("isobaricInhPa|isobaricinhpa")

    report["missing_columns"] = missing_cols
    if missing_cols:
        return report

    normalized = normalize_level_column(df)
    levels = pd.to_numeric(normalized["isobaricInhPa"], errors="coerce")
    lat_values = pd.to_numeric(normalized["latitude"], errors="coerce").dropna().unique()
    lon_values = np.mod(pd.to_numeric(normalized["longitude"], errors="coerce").dropna().unique(), 360.0)
    expected_lats, lat_meta = resolve_expected_lats(lat_values, latitude_policy=latitude_policy)
    variable_raw = normalized["variable"]
    variable_cat = variable_raw.astype("category")
    unique_variables = variable_cat.cat.categories.tolist()
    lower_to_variants: dict[str, list[Any]] = {}
    for raw in unique_variables:
        lower_to_variants.setdefault(str(raw).lower(), []).append(raw)
    report["available_variables"] = sorted(lower_to_variants.keys())

    lowered_categories = variable_cat.cat.categories.astype("string").str.lower()
    lowered_variable = variable_cat.cat.rename_categories(lowered_categories)
    grouped = pd.DataFrame({"variable": lowered_variable, "isobaricInhPa": levels}).drop_duplicates()
    grouped = grouped.sort_values(["variable", "isobaricInhPa"], na_position="first")
    grouped["count"] = None
    report["available_variable_levels"] = grouped.to_dict(orient="records")

    missing_channels: list[dict[str, Any]] = []
    duplicate_channels: list[dict[str, Any]] = []
    for variable, level in build_fourcastnet_channel_map():
        variants = lower_to_variants.get(variable, [])
        if not variants:
            missing_channels.append({"variable": variable, "level": level})
            continue
        var_mask = variable_raw.isin(variants)
        if level is None:
            lvl_mask = levels.isna() | np.isclose(levels, 0.0, atol=1e-6)
        else:
            lvl_mask = np.isclose(levels, float(level), atol=1e-6)
        selected = normalized.loc[var_mask & lvl_mask, ["latitude", "longitude"]]
        if selected.empty:
            missing_channels.append({"variable": variable, "level": level})
            continue
        dup_count = int(selected.duplicated(subset=["latitude", "longitude"]).sum())
        if dup_count > 0:
            duplicate_channels.append(
                {"variable": variable, "level": level, "duplicate_points": dup_count}
            )

    report["missing_channels"] = missing_channels
    report["duplicate_points_by_channel"] = duplicate_channels
    report["grid"] = {
        "expected_lat_count": int(len(EXPECTED_LATS)),
        "expected_lon_count": int(len(EXPECTED_LONS)),
        "observed_lat_count": int(len(lat_values)),
        "observed_lon_count": int(len(lon_values)),
        "lat_descending_expected": True,
        "lon_ascending_expected": True,
        "longitude_normalization_status": "normalized_to_0_360",
    }
    report["latitude"] = lat_meta
    latitude_ready = expected_lats is not None and len(expected_lats) == 720
    report["ok"] = (
        len(missing_channels) == 0
        and len(report["duplicate_points_by_channel"]) == 0
        and latitude_ready
    )
    return report


def build_available_variable_levels(df: pd.DataFrame) -> pd.DataFrame:
    """
    Retorna una matriz de disponibilidad agrupada por variable y nivel de presión.

    Parameters
    ----------
    df : pd.DataFrame
        Dataframe con los datos meteorológicos.

    Returns
    -------
    pd.DataFrame
        Dataframe único con las combinaciones de variable y nivel presentes.
    """
    normalized = normalize_level_column(df)
    variable_cat = normalized["variable"].astype("category")
    lowered_categories = variable_cat.cat.categories.astype("string").str.lower()
    variables = variable_cat.cat.rename_categories(lowered_categories)
    levels = pd.to_numeric(normalized["isobaricInhPa"], errors="coerce")
    unique_levels = (
        pd.DataFrame({"variable": variables.str.lower(), "isobaricInhPa": levels})
        .drop_duplicates()
        .sort_values(["variable", "isobaricInhPa"], na_position="first")
    )
    unique_levels["count"] = None
    return unique_levels


def build_fourcastnet_tensor(
    df: pd.DataFrame,
    expected_lats: np.ndarray = EXPECTED_LATS,
    expected_lons: np.ndarray = EXPECTED_LONS,
    validate_shape: bool = True,
    latitude_policy: str = "fail",
) -> np.ndarray:
    """
    Construye un tensor completo para FourCastNet con forma (1, 20, 720, 1440).

    Itera sobre todos los canales requeridos, extrae sus grids y los apila
    en un único array de numpy.

    Parameters
    ----------
    df : pd.DataFrame
        Dataframe con todos los datos necesarios.
    expected_lats : np.ndarray, opcional
        Latitudes del grid.
    expected_lons : np.ndarray, opcional
        Longitudes del grid.
    validate_shape : bool, opcional
        Si se debe validar la forma final del tensor, por defecto True.
    latitude_policy : str, opcional
        Política para el manejo de latitudes, por defecto "fail".

    Returns
    -------
    np.ndarray
        Tensor de FourCastNet (float32).

    Raises
    ------
    ValueError
        Si falta algún canal o si la forma final es incorrecta.
    """
    normalized = normalize_longitudes(normalize_level_column(df))
    normalized["variable"] = normalized["variable"].astype(str).str.lower()
    if expected_lats is EXPECTED_LATS:
        observed_lats = pd.to_numeric(normalized["latitude"], errors="coerce").dropna().unique()
        resolved_lats, lat_meta = resolve_expected_lats(observed_lats, latitude_policy=latitude_policy)
        if resolved_lats is None:
            raise ValueError(
                f"Latitude policy prevented tensor build: {lat_meta['latitude_policy_applied']}"
            )
        expected_lats = resolved_lats

    channels = []
    for variable, level in build_fourcastnet_channel_map():
        selected = select_channel_frame(normalized, variable, level)
        if selected.empty:
            level_text = "surface" if level is None else f"{level:g}"
            raise ValueError(f"Missing required channel: variable={variable}, level={level_text}")
        channels.append(field_to_grid(selected, expected_lats, expected_lons))

    stacked = np.stack(channels, axis=0).astype(np.float32)
    tensor = np.expand_dims(stacked, axis=0)

    if validate_shape and tensor.shape != (1, 20, 720, 1440):
        raise ValueError(f"Unexpected tensor shape: {tensor.shape}")
    return tensor


def write_manifest(path: str | Path, payload: dict[str, Any]) -> str:
    """
    Escribe un manifiesto JSON o informe de validación en el disco.

    Parameters
    ----------
    path : str | Path
        Ruta del archivo de salida.
    payload : dict[str, Any]
        Datos a serializar en formato JSON.

    Returns
    -------
    str
        Ruta absoluta del archivo escrito.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(out)
