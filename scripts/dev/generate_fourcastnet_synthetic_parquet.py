"""Generate synthetic FourCastNet-style parquet samples for local smoke tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from chucaw_preprocessor.fourcastnet import build_fourcastnet_channel_map
from chucaw_preprocessor.glue_args import resolve_args


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def build_synthetic_dataframe(complete: bool, use_level_alias: bool) -> pd.DataFrame:
    lats = np.array([90.0, 89.75], dtype=np.float32)
    lons = np.array([0.0, 0.25, 0.5], dtype=np.float32)

    drop_channels = {("tcwv", None), ("r", 850.0)} if not complete else set()

    rows: list[dict[str, float | str]] = []
    for cidx, (variable, level) in enumerate(build_fourcastnet_channel_map()):
        if (variable, level) in drop_channels:
            continue
        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                rows.append(
                    {
                        "isobaricInhPa": np.nan if level is None else float(level),
                        "latitude": float(lat),
                        "longitude": float(lon),
                        "variable": variable,
                        "value": float(cidx + i * 0.1 + j * 0.01),
                        "date": "20260410",
                        "run": "06z",
                    }
                )

    df = pd.DataFrame(rows)
    if use_level_alias:
        df = df.rename(columns={"isobaricInhPa": "isobaricinhpa"})
    return df


def main() -> None:
    args = resolve_args(
        required=[],
        optional=["OUTPUT_PATH", "COMPLETE", "USE_LEVEL_ALIAS"],
    )

    output_path = Path(args.get("OUTPUT_PATH") or "tmp/fourcastnet_synthetic_complete.parquet").expanduser()
    complete = _truthy(args.get("COMPLETE") or "true")
    use_level_alias = _truthy(args.get("USE_LEVEL_ALIAS") or "false")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = build_synthetic_dataframe(complete=complete, use_level_alias=use_level_alias)
    df.to_parquet(output_path, index=False)

    print({
        "status": "ok",
        "output_path": str(output_path),
        "complete": complete,
        "use_level_alias": use_level_alias,
        "row_count": int(len(df)),
    })


if __name__ == "__main__":
    main()
