from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from chucaw_preprocessor.fourcastnet import (
    FOURCASTNET_CONTRACT_VERSION,
    FOURCASTNET_EXPECTED_SHAPE,
    prepare_fourcastnet_stats,
    normalize_fourcastnet_tensor,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate FourCastNet tensor artifact")
    p.add_argument("--INPUT_TENSOR", required=True)
    p.add_argument("--GLOBAL_MEANS", default=None)
    p.add_argument("--GLOBAL_STDS", default=None)
    p.add_argument("--STATS_CHANNEL_POLICY", default=None, help="Policy for aligning stats with tensor (e.g., first_20_channels)")
    p.add_argument("--OUTPUT_REPORT", required=True)
    p.add_argument("--ALLOW_TEST_GRID", action="store_true")
    return p.parse_args()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_tensor(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix == ".npy":
        return np.load(path)
    if suffix == ".pt":
        import torch

        loaded = torch.load(path, map_location="cpu")
        if hasattr(loaded, "detach"):
            return loaded.detach().cpu().numpy()
        return np.asarray(loaded)
    raise ValueError(f"Unsupported tensor extension: {suffix}. Expected .npy or .pt")


def _channel_stats(arr: np.ndarray) -> list[dict[str, Any]]:
    stats = []
    for idx in range(arr.shape[1]):
        c = arr[0, idx]
        stats.append(
            {
                "channel_index": int(idx),
                "min": float(np.min(c)),
                "max": float(np.max(c)),
                "mean": float(np.mean(c)),
            }
        )
    return stats


def main() -> int:
    args = _parse_args()
    input_tensor = Path(args.INPUT_TENSOR)
    output_report = Path(args.OUTPUT_REPORT)

    report: dict[str, Any] = {
        "ok": False,
        "contract_version": FOURCASTNET_CONTRACT_VERSION,
        "input_tensor": str(input_tensor),
        "tensor_ok": False,
        "stats_ok": None,
        "normalization_ok": None,
    }
    stage = "input_check"

    try:
        if not input_tensor.exists():
            raise FileNotFoundError(str(input_tensor))

        stage = "tensor_load"
        tensor = _load_tensor(input_tensor)
        report["shape"] = list(np.asarray(tensor).shape)
        report["dtype"] = str(np.asarray(tensor).dtype)

        stage = "tensor_cast"
        if not np.issubdtype(np.asarray(tensor).dtype, np.floating):
            tensor = np.asarray(tensor, dtype=np.float32)
        else:
            tensor = np.asarray(tensor).astype(np.float32, copy=False)

        stage = "tensor_shape"
        if args.ALLOW_TEST_GRID:
            if tensor.ndim != 4 or tensor.shape[0] != 1 or tensor.shape[1] != 20:
                raise RuntimeError(f"Invalid tensor shape for test-grid mode: {tensor.shape}")
        else:
            if tuple(tensor.shape) != FOURCASTNET_EXPECTED_SHAPE:
                raise RuntimeError(f"Invalid shape: {tensor.shape}")

        stage = "tensor_finite"
        finite = bool(np.isfinite(tensor).all())
        report["finite"] = finite
        if not finite:
            raise RuntimeError("Non-finite values in tensor")

        report["channel_stats"] = _channel_stats(tensor)
        report["tensor_ok"] = True

        if args.GLOBAL_MEANS or args.GLOBAL_STDS:
            stage = "stats_path_check"
            if not args.GLOBAL_MEANS or not args.GLOBAL_STDS:
                raise RuntimeError("Both --GLOBAL_MEANS and --GLOBAL_STDS are required together")

            means_path = Path(args.GLOBAL_MEANS)
            stds_path = Path(args.GLOBAL_STDS)
            if not means_path.exists():
                raise FileNotFoundError(str(means_path))
            if not stds_path.exists():
                raise FileNotFoundError(str(stds_path))

            stage = "stats_load"
            means_raw = np.load(means_path)
            stds_raw = np.load(stds_path)
            means, stds, stats_meta = prepare_fourcastnet_stats(
                means_raw,
                stds_raw,
                policy=args.STATS_CHANNEL_POLICY,
            )
            report.update(stats_meta)

            stage = "stats_normalize"
            norm = normalize_fourcastnet_tensor(tensor, means, stds)
            report["normalized_channel_stats"] = _channel_stats(norm)
            report["stats_ok"] = True
            report["normalization_ok"] = True

        report["ok"] = True
        _write_json(output_report, report)
        return 0
    except Exception as exc:
        report["ok"] = False
        report["error_stage"] = stage
        report["error_message"] = str(exc)
        if report.get("stats_ok") is None and (args.GLOBAL_MEANS or args.GLOBAL_STDS):
            report["stats_ok"] = False
        _write_json(output_report, report)
        return 1


if __name__ == "__main__":
    sys.exit(main())
