from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import h5py
import numpy as np

from chucaw_preprocessor.fourcastnet import (
    FCN_DATASET_NAME,
    FOURCASTNET_CONTRACT_VERSION,
    FOURCASTNET_STATS_CHANNEL_POLICY,
    normalize_fourcastnet_tensor,
    prepare_fourcastnet_stats,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate FourCastNet HDF5 preflight")
    p.add_argument("--INPUT_H5", required=True)
    p.add_argument("--GLOBAL_MEANS", default=None)
    p.add_argument("--GLOBAL_STDS", default=None)
    p.add_argument("--STATS_CHANNEL_POLICY", default=FOURCASTNET_STATS_CHANNEL_POLICY)
    p.add_argument("--OUTPUT_REPORT", required=True)
    return p.parse_args()


def _reshape_stats(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float32)
    if arr.shape == (20,):
        return arr.reshape(1, 20, 1, 1)
    if arr.shape == (1, 20, 1, 1):
        return arr
    if arr.ndim == 4 and arr.shape[1] == 20:
        return arr
    raise ValueError(f"Unsupported stats shape: {arr.shape}")


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    h5_path = Path(args.INPUT_H5)
    out = Path(args.OUTPUT_REPORT)
    report: dict[str, object] = {
        "ok": False,
        "contract_version": FOURCASTNET_CONTRACT_VERSION,
        "input_h5": str(h5_path),
        "dataset": FCN_DATASET_NAME,
        "dataset_names": [],
    }
    stage = "input_open"
    x: np.ndarray | None = None

    try:
        if not h5_path.exists():
            raise FileNotFoundError(str(h5_path))

        stage = "dataset_discovery"
        with h5py.File(h5_path, "r") as h5f:
            report["dataset_names"] = list(h5f.keys())
            if FCN_DATASET_NAME not in h5f:
                raise RuntimeError(f"Missing dataset: {FCN_DATASET_NAME}")

            dset = h5f[FCN_DATASET_NAME]
            report["shape"] = list(dset.shape)
            report["dtype"] = str(dset.dtype)

            stage = "dataset_read"
            x = dset[:]

        assert x is not None
        report["finite"] = bool(np.isfinite(x).all())

        stage = "shape_validation"
        if tuple(x.shape) != (1, 20, 720, 1440):
            raise RuntimeError(f"Invalid shape: {x.shape}")

        stage = "finite_validation"
        if not np.isfinite(x).all():
            raise RuntimeError("Non-finite values in fields")

        stage = "channel_stats"
        per_channel = []
        for i in range(20):
            c = x[0, i]
            per_channel.append(
                {
                    "channel_index": i,
                    "min": float(np.min(c)),
                    "max": float(np.max(c)),
                    "mean": float(np.mean(c)),
                }
            )
        report["per_channel"] = per_channel

        if args.GLOBAL_MEANS and args.GLOBAL_STDS:
            stage = "normalization_validation"
            means, stds, stats_meta = prepare_fourcastnet_stats(
                np.load(args.GLOBAL_MEANS),
                np.load(args.GLOBAL_STDS),
                policy=args.STATS_CHANNEL_POLICY,
            )
            report.update(stats_meta)
            norm = normalize_fourcastnet_tensor(x, means, stds)
            norm_stats = []
            for i in range(20):
                c = norm[0, i]
                norm_stats.append(
                    {
                        "channel_index": i,
                        "min": float(np.min(c)),
                        "max": float(np.max(c)),
                        "mean": float(np.mean(c)),
                    }
                )
            report["normalized_per_channel"] = norm_stats

        report["ok"] = True
        _write_report(out, report)
        return 0
    except Exception as exc:
        report["ok"] = False
        report["error_stage"] = stage
        report["error_message"] = str(exc)
        _write_report(out, report)
        return 1


if __name__ == "__main__":
    sys.exit(main())
