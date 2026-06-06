from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from chucaw_preprocessor.fourcastnet import (
    FOURCASTNET_CONTRACT_VERSION,
    FOURCASTNET_STATS_CHANNEL_POLICY,
    normalize_fourcastnet_tensor,
    prepare_fourcastnet_stats,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Direct tensor smoke attempt for FourCastNet-like backends")
    p.add_argument("--INPUT_TENSOR", required=True)
    p.add_argument("--GLOBAL_MEANS", required=True)
    p.add_argument("--GLOBAL_STDS", required=True)
    p.add_argument("--CHECKPOINT", required=True)
    p.add_argument("--MODEL_BACKEND", choices=["auto", "nvlabs", "earth2studio", "physicsnemo", "dry_random"], default="auto")
    p.add_argument("--OUTPUT_REPORT", required=True)
    p.add_argument("--DEVICE", choices=["auto", "cpu", "cuda"], default="auto")
    p.add_argument("--ALLOW_RANDOM_MODEL", default="false")
    p.add_argument("--LOCAL_REPO", default=None)
    p.add_argument("--ALLOW_TEST_GRID", action="store_true")
    p.add_argument("--STATS_CHANNEL_POLICY", default=FOURCASTNET_STATS_CHANNEL_POLICY)
    return p.parse_args()


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _reshape_stats(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float32)
    if arr.shape == (20,):
        return arr.reshape(1, 20, 1, 1)
    if arr.shape == (1, 20, 1, 1):
        return arr
    if arr.ndim == 4 and arr.shape[1] == 20:
        return arr
    raise ValueError(f"Unsupported stats shape: {arr.shape}")


def _load_tensor(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix == ".npy":
        return np.load(path).astype(np.float32, copy=False)
    if suffix == ".pt":
        import torch

        loaded = torch.load(path, map_location="cpu")
        if hasattr(loaded, "detach"):
            return loaded.detach().cpu().numpy().astype(np.float32, copy=False)
        return np.asarray(loaded, dtype=np.float32)
    raise ValueError(f"Unsupported tensor extension: {suffix}. Expected .npy or .pt")


def _resolve_device(requested: str) -> str:
    import torch

    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but not available")
        return "cuda"
    return "cuda" if torch.cuda.is_available() else "cpu"


def _load_manifest_flags(input_tensor: Path) -> tuple[Any, Any]:
    manifest_path = input_tensor.parent / "tensor_manifest.json"
    if not manifest_path.exists():
        return None, None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    return payload.get("scientific_validity"), payload.get("compatibility_fixture")


def _extract_state_dict(ckpt: Any) -> dict[str, Any]:
    if isinstance(ckpt, dict):
        for key in ["model_state", "state_dict", "module"]:
            v = ckpt.get(key)
            if isinstance(v, dict):
                return v
        if all(isinstance(k, str) for k in ckpt.keys()):
            return ckpt
    raise RuntimeError("Could not extract state dict from checkpoint payload")


def _run_nvlabs_backend(
    x_norm: "torch.Tensor",
    checkpoint_path: Path,
    local_repo: Path | None,
) -> tuple["torch.Tensor", dict[str, Any]]:
    import importlib

    import torch

    if local_repo is None:
        for candidate in [Path("FourCastNet"), Path("external/FourCastNet")]:
            if candidate.exists():
                local_repo = candidate.resolve()
                break
    if local_repo is None or not local_repo.exists():
        raise RuntimeError("NVlabs backend requires --LOCAL_REPO or a discoverable local FourCastNet checkout")

    sys.path.insert(0, str(local_repo))
    sys.path.insert(0, str(local_repo / "networks"))

    model_class = None
    import_errors = []
    for module_name in ["networks.afnonet", "afnonet"]:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "AFNONet"):
                model_class = getattr(module, "AFNONet")
                break
        except Exception as exc:
            import_errors.append(f"{module_name}: {exc}")
    if model_class is None:
        raise RuntimeError("Could not import AFNONet: " + " | ".join(import_errors))

    init_errors = []
    model = None
    candidate_kwargs = [
        {"img_size": (x_norm.shape[2], x_norm.shape[3]), "in_chans": 20, "out_chans": 20},
        {"in_chans": 20, "out_chans": 20},
        {},
    ]
    for kwargs in candidate_kwargs:
        try:
            model = model_class(**kwargs)
            break
        except Exception as exc:
            init_errors.append(f"kwargs={kwargs}: {exc}")
    if model is None:
        raise RuntimeError("AFNONet initialization failed: " + " | ".join(init_errors))

    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    state_dict = _extract_state_dict(checkpoint)
    load_res = model.load_state_dict(state_dict, strict=False)
    model.eval()
    model = model.to(x_norm.device)
    with torch.no_grad():
        y_norm = model(x_norm)
    meta = {
        "backend": "nvlabs",
        "repo_path": str(local_repo),
        "missing_keys_count": len(getattr(load_res, "missing_keys", [])),
        "unexpected_keys_count": len(getattr(load_res, "unexpected_keys", [])),
    }
    return y_norm, meta


def _run_earth2studio_backend(_: "torch.Tensor", __: Path) -> tuple["torch.Tensor", dict[str, Any]]:
    raise RuntimeError("earth2studio backend import/forward is not configured in this repository")


def _run_physicsnemo_backend(_: "torch.Tensor", __: Path) -> tuple["torch.Tensor", dict[str, Any]]:
    raise RuntimeError("physicsnemo backend import/forward is not configured in this repository")


def _run_dry_random_backend(x_norm: "torch.Tensor") -> tuple["torch.Tensor", dict[str, Any]]:
    import torch

    class _RandomModel(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.proj = torch.nn.Conv2d(20, 20, kernel_size=1, bias=True)

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            return self.proj(x)

    model = _RandomModel().to(x_norm.device)
    model.eval()
    with torch.no_grad():
        y_norm = model(x_norm)
    return y_norm, {"backend": "dry_random"}


def main() -> int:
    args = _parse_args()
    input_tensor = Path(args.INPUT_TENSOR)
    means_path = Path(args.GLOBAL_MEANS)
    stds_path = Path(args.GLOBAL_STDS)
    checkpoint_path = Path(args.CHECKPOINT)
    output_report = Path(args.OUTPUT_REPORT)
    local_repo = Path(args.LOCAL_REPO).resolve() if args.LOCAL_REPO else None

    report: dict[str, Any] = {
        "ok": False,
        "contract_version": FOURCASTNET_CONTRACT_VERSION,
        "tensor_ok": False,
        "stats_ok": False,
        "normalization_ok": False,
        "model_backend_requested": args.MODEL_BACKEND,
        "model_backend_used": None,
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_exists": checkpoint_path.exists(),
        "checkpoint_load_ok": False,
        "model_load_ok": False,
        "inferred_or_expected_channel_count": None,
        "input_channel_count": None,
        "channel_count_match": None,
        "inference_attempted": False,
        "inference_success": False,
        "fourcastnet_proven": False,
        "failure_reason": None,
        "output_shape": None,
        "output_finite": None,
        "device": None,
    }
    scientific_validity, compatibility_fixture = _load_manifest_flags(input_tensor)
    report["scientific_validity"] = scientific_validity
    report["compatibility_fixture"] = compatibility_fixture
    stage = "tensor_load"

    try:
        tensor = _load_tensor(input_tensor)
        if args.ALLOW_TEST_GRID:
            if tensor.ndim != 4 or tensor.shape[0] != 1 or tensor.shape[1] != 20:
                raise RuntimeError(f"Invalid tensor shape for test-grid mode: {tensor.shape}")
        else:
            if tuple(tensor.shape) != (1, 20, 720, 1440):
                raise RuntimeError(f"Invalid tensor shape: {tensor.shape}")
        if not np.isfinite(tensor).all():
            raise RuntimeError("Tensor has non-finite values")
        report["tensor_ok"] = True
        report["input_channel_count"] = int(tensor.shape[1])

        stage = "stats_check"
        if not means_path.exists():
            raise FileNotFoundError(f"Missing GLOBAL_MEANS file: {means_path}")
        if not stds_path.exists():
            raise FileNotFoundError(f"Missing GLOBAL_STDS file: {stds_path}")

        means, stds, stats_meta = prepare_fourcastnet_stats(
            np.load(means_path),
            np.load(stds_path),
            policy=args.STATS_CHANNEL_POLICY,
        )
        report.update(stats_meta)
        x_norm_np = normalize_fourcastnet_tensor(tensor, means, stds)
        report["stats_ok"] = True
        report["normalization_ok"] = True

        stage = "torch_setup"
        import torch

        device = _resolve_device(args.DEVICE)
        report["device"] = device
        x_norm = torch.from_numpy(x_norm_np).to(device)

        stage = "backend"
        requested = args.MODEL_BACKEND
        allow_random = _truthy(args.ALLOW_RANDOM_MODEL)
        backends = [requested] if requested != "auto" else ["nvlabs", "earth2studio", "physicsnemo"]
        backend_errors: list[str] = []
        y_norm = None
        backend_meta: dict[str, Any] = {}

        if requested == "dry_random":
            if not allow_random:
                raise RuntimeError("dry_random backend requires --ALLOW_RANDOM_MODEL true")
            report["inference_attempted"] = True
            y_norm, backend_meta = _run_dry_random_backend(x_norm)
            report["model_backend_used"] = "dry_random"
            report["model_load_ok"] = True
            report["checkpoint_load_ok"] = checkpoint_path.exists()
        else:
            if not checkpoint_path.exists():
                raise FileNotFoundError(f"Missing CHECKPOINT file: {checkpoint_path}")
            for backend in backends:
                report["inference_attempted"] = True
                try:
                    if backend == "nvlabs":
                        y_norm, backend_meta = _run_nvlabs_backend(x_norm, checkpoint_path, local_repo)
                    elif backend == "earth2studio":
                        y_norm, backend_meta = _run_earth2studio_backend(x_norm, checkpoint_path)
                    elif backend == "physicsnemo":
                        y_norm, backend_meta = _run_physicsnemo_backend(x_norm, checkpoint_path)
                    else:
                        raise RuntimeError(f"Unsupported backend in auto flow: {backend}")
                    report["model_backend_used"] = backend
                    report["model_load_ok"] = True
                    report["checkpoint_load_ok"] = True
                    break
                except Exception as exc:
                    backend_errors.append(f"{backend}: {exc}")

            if y_norm is None:
                raise RuntimeError("All backend attempts failed: " + " | ".join(backend_errors))

        stage = "output_checks"
        means_t = torch.from_numpy(means.astype(np.float32)).to(device)
        stds_t = torch.from_numpy(stds.astype(np.float32)).to(device)
        y = y_norm * stds_t + means_t
        y_np = y.detach().cpu().numpy()
        report["output_shape"] = list(y_np.shape)
        report["output_finite"] = bool(np.isfinite(y_np).all())
        report["output_stats"] = {
            "min": float(np.min(y_np)),
            "max": float(np.max(y_np)),
            "mean": float(np.mean(y_np)),
        }
        report["inference_success"] = bool(report["output_finite"])
        report["inferred_or_expected_channel_count"] = 20
        report["channel_count_match"] = report["input_channel_count"] == 20
        report["backend_meta"] = backend_meta

        if report["model_backend_used"] in {"nvlabs", "earth2studio", "physicsnemo"} and report["inference_success"]:
            report["fourcastnet_proven"] = True
        else:
            report["fourcastnet_proven"] = False

        report["ok"] = bool(report["inference_success"])
        if not report["ok"]:
            report["failure_reason"] = "Inference output contains non-finite values"
            _write_json(output_report, report)
            return 1

        _write_json(output_report, report)
        return 0
    except Exception as exc:
        report["ok"] = False
        report["failure_reason"] = str(exc)
        report["error_stage"] = stage
        _write_json(output_report, report)
        return 1


if __name__ == "__main__":
    sys.exit(main())
