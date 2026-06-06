import json
import os
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest

from chucaw_preprocessor.fourcastnet import build_fourcastnet_channel_map, specific_humidity_to_relative_humidity


CHANNELS = build_fourcastnet_channel_map()
REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_small_parquet(path: Path, include_sp_r_tcwv: bool) -> None:
    lats = [90.0, 89.75]
    lons = [0.0, 0.25]
    rows = []
    for idx, (var, lvl) in enumerate(CHANNELS):
        if var in {"sp", "tcwv"} and not include_sp_r_tcwv:
            continue
        out_var = var
        if var == "r" and not include_sp_r_tcwv:
            # Keep q available so compatibility mode can derive r@850/r@500.
            out_var = "q"
        for lat in lats:
            for lon in lons:
                rows.append(
                    {
                        "isobaricInhPa": np.nan if lvl is None else float(lvl),
                        "latitude": lat,
                        "longitude": lon,
                        "variable": out_var,
                        "value": float(idx + lat * 0.001 + lon * 0.001),
                        "date": "20260409",
                        "run": "18z",
                    }
                )
    pd.DataFrame(rows).to_parquet(path, index=False)


def _expected_basename(date: str = "20260409", run: str = "18z") -> str:
    return f"fcn_compat_{date}_{run}.parquet"


def _run_tensor_export(
    input_parquet: Path,
    output_dir: Path,
    *,
    output_format: str = "npy",
    allow_test_grid: bool = True,
    require_complete: str = "true",
    force: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    cmd = [
        sys.executable,
        "scripts/dev/export_fourcastnet_tensor.py",
        "--INPUT_PARQUET",
        str(input_parquet),
        "--OUTPUT_DIR",
        str(output_dir),
        "--LATITUDE_POLICY",
        "fail",
        "--OUTPUT_FORMAT",
        output_format,
        "--REQUIRE_COMPLETE",
        require_complete,
    ]
    if allow_test_grid:
        cmd.append("--ALLOW_TEST_GRID")
    if force:
        cmd.append("--FORCE")
    return subprocess.run(cmd, cwd=REPO_ROOT, env=env)


def _run_fixture(
    inp: Path,
    out_dir: Path,
    mode: str,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    cmd = [
        sys.executable,
        "scripts/dev/make_fourcastnet_compatibility_fixture.py",
        "--INPUT_PARQUET",
        str(inp),
        "--OUTPUT_DIR",
        str(out_dir),
        "--MODE",
        mode,
        "--LATITUDE_POLICY",
        "fail",
        "--ALLOW_TEST_GRID",
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, cwd=REPO_ROOT, env=env)


def test_rh_derivation_finite_and_bounded() -> None:
    q = np.full((2, 2), 0.005, dtype=np.float32)
    t = np.full((2, 2), 280.0, dtype=np.float32)
    rh, summary = specific_humidity_to_relative_humidity(q, t, 850.0, clip_percent=True)
    assert rh.shape == (2, 2)
    assert np.isfinite(rh).all()
    assert float(rh.min()) >= 0.0
    assert float(rh.max()) <= 100.0
    assert "rh_percent_mean" in summary


def test_strict_mode_refuses_missing_channels(tmp_path: Path) -> None:
    inp = tmp_path / "in.parquet"
    out_dir = tmp_path / "strict"
    _make_small_parquet(inp, include_sp_r_tcwv=False)
    result = _run_fixture(inp, out_dir, "strict")
    assert result.returncode == 0
    report = json.loads((out_dir / "validation_report.json").read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["scientific_validity"] is False
    assert report["all_channels_original"] is False
    assert any(item["variable"] == "sp" for item in report["missing_channels"])
    assert not (out_dir / _expected_basename()).exists()


def test_strict_mode_complete_input_can_be_scientifically_valid(tmp_path: Path) -> None:
    inp = tmp_path / "in.parquet"
    out_dir = tmp_path / "strict_complete"
    _make_small_parquet(inp, include_sp_r_tcwv=True)
    result = _run_fixture(inp, out_dir, "strict")
    assert result.returncode == 0

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((out_dir / "validation_report.json").read_text(encoding="utf-8"))
    provenance = json.loads((out_dir / "channel_provenance.json").read_text(encoding="utf-8"))["channels"]
    out_parquet = out_dir / _expected_basename()
    assert out_parquet.exists()

    assert manifest["compatibility_fixture"] is False
    assert manifest["scientific_validity"] is True
    assert manifest["all_channels_original"] is True
    assert manifest["any_proxy_channels"] is False
    assert manifest["any_derived_channels"] is False

    assert report["scientific_validity"] is True
    assert report["all_channels_original"] is True
    assert report["any_proxy_channels"] is False
    assert report["any_derived_channels"] is False

    assert all(c["status"] == "original" for c in provenance)


def test_compatibility_mode_writes_complete_output_and_provenance(tmp_path: Path) -> None:
    inp = tmp_path / "in.parquet"
    out_dir = tmp_path / "compat"
    _make_small_parquet(inp, include_sp_r_tcwv=False)
    result = _run_fixture(inp, out_dir, "compatibility_fixture")
    assert result.returncode == 0
    out_parquet = out_dir / _expected_basename()
    assert out_parquet.exists()
    prov = json.loads((out_dir / "channel_provenance.json").read_text(encoding="utf-8"))["channels"]
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((out_dir / "validation_report.json").read_text(encoding="utf-8"))
    by_key = {(c["variable"], c["level"]): c for c in prov}
    assert by_key[("sp", None)]["status"] == "proxy"
    assert by_key[("r", 850.0)]["status"] == "derived"
    assert by_key[("tcwv", None)]["status"] == "proxy"
    assert manifest["scientific_validity"] is False
    assert manifest["compatibility_fixture"] is True
    assert manifest["all_channels_original"] is False
    assert manifest["any_proxy_channels"] is True
    assert manifest["any_derived_channels"] is True
    assert report["scientific_validity"] is False
    assert any(c["status"] == "missing" or c["status"] in {"proxy", "derived", "original"} for c in prov)


def test_output_basename_can_be_derived_or_overridden(tmp_path: Path) -> None:
    inp = tmp_path / "in.parquet"
    out_dir = tmp_path / "compat_custom"
    _make_small_parquet(inp, include_sp_r_tcwv=False)

    result = _run_fixture(inp, out_dir, "compatibility_fixture")
    assert result.returncode == 0
    assert (out_dir / _expected_basename()).exists()

    out_dir2 = tmp_path / "compat_override"
    result2 = _run_fixture(
        inp,
        out_dir2,
        "compatibility_fixture",
        extra_args=["--OUTPUT_BASENAME", "my_fixture_name.parquet"],
    )
    assert result2.returncode == 0
    assert (out_dir2 / "my_fixture_name.parquet").exists()


def test_output_basename_fails_if_date_run_not_derivable_without_override(tmp_path: Path) -> None:
    inp = tmp_path / "in.parquet"
    out_dir = tmp_path / "compat_bad_basename"
    _make_small_parquet(inp, include_sp_r_tcwv=False)
    df = pd.read_parquet(inp)
    df["date"] = "not-a-date"
    df["run"] = "runX"
    df.to_parquet(inp, index=False)

    result = _run_fixture(inp, out_dir, "compatibility_fixture")
    assert result.returncode != 0
    assert not (out_dir / _expected_basename()).exists()


def test_h5_export_and_validator_small_grid(tmp_path: Path) -> None:
    inp = tmp_path / "in.parquet"
    mid = tmp_path / "compat"
    _make_small_parquet(inp, include_sp_r_tcwv=False)
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    result = _run_fixture(inp, mid, "compatibility_fixture")
    assert result.returncode == 0

    out_h5 = mid / "x.h5"
    subprocess.run(
        [
            sys.executable,
            "scripts/dev/export_fourcastnet_h5.py",
            "--INPUT_PARQUET",
            str(mid / _expected_basename()),
            "--OUTPUT_H5",
            str(out_h5),
            "--LATITUDE_POLICY",
            "fail",
            "--ALLOW_TEST_GRID",
            "--REQUIRE_COMPLETE",
            "false",
        ],
        check=True,
        cwd=REPO_ROOT,
        env=env,
    )
    with h5py.File(out_h5, "r") as f:
        assert "fields" in f
        assert f["fields"].shape[1] == 20


def test_h5_validator_writes_failure_reports(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    bad1 = tmp_path / "bad_missing.h5"
    with h5py.File(bad1, "w") as f:
        f.create_dataset("not_fields", data=np.zeros((1, 20, 2, 2), dtype=np.float32))
    r1 = tmp_path / "r1.json"
    p1 = subprocess.run(
        [
            sys.executable,
            "scripts/dev/validate_fourcastnet_h5.py",
            "--INPUT_H5",
            str(bad1),
            "--OUTPUT_REPORT",
            str(r1),
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    assert p1.returncode != 0
    rep1 = json.loads(r1.read_text(encoding="utf-8"))
    assert rep1["ok"] is False
    assert rep1["error_stage"] in {"dataset_discovery", "dataset_read"}
    assert "dataset_names" in rep1

    bad2 = tmp_path / "bad_shape.h5"
    with h5py.File(bad2, "w") as f:
        f.create_dataset("fields", data=np.zeros((1, 20, 2, 2), dtype=np.float32))
    r2 = tmp_path / "r2.json"
    p2 = subprocess.run(
        [
            sys.executable,
            "scripts/dev/validate_fourcastnet_h5.py",
            "--INPUT_H5",
            str(bad2),
            "--OUTPUT_REPORT",
            str(r2),
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    assert p2.returncode != 0
    rep2 = json.loads(r2.read_text(encoding="utf-8"))
    assert rep2["ok"] is False
    assert rep2["error_stage"] == "shape_validation"
    assert rep2["shape"] == [1, 20, 2, 2]

    bad3 = tmp_path / "bad_non_finite.h5"
    arr = np.zeros((1, 20, 720, 1440), dtype=np.float32)
    arr[0, 0, 0, 0] = np.nan
    with h5py.File(bad3, "w") as f:
        f.create_dataset("fields", data=arr)
    r3 = tmp_path / "r3.json"
    p3 = subprocess.run(
        [
            sys.executable,
            "scripts/dev/validate_fourcastnet_h5.py",
            "--INPUT_H5",
            str(bad3),
            "--OUTPUT_REPORT",
            str(r3),
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    assert p3.returncode != 0
    rep3 = json.loads(r3.read_text(encoding="utf-8"))
    assert rep3["ok"] is False
    assert rep3["error_stage"] == "finite_validation"
    assert rep3["finite"] is False


def test_channel_order_stable() -> None:
    expected = [
        ("u10", None), ("v10", None), ("t2m", None), ("sp", None), ("msl", None),
        ("t", 850.0), ("u", 1000.0), ("v", 1000.0), ("z", 1000.0), ("u", 850.0),
        ("v", 850.0), ("z", 850.0), ("u", 500.0), ("v", 500.0), ("z", 500.0),
        ("t", 500.0), ("z", 50.0), ("r", 500.0), ("r", 850.0), ("tcwv", None),
    ]
    assert CHANNELS == expected


def test_tensor_export_writes_tensor_and_manifest_small_grid(tmp_path: Path) -> None:
    inp = tmp_path / "in.parquet"
    out_dir = tmp_path / "compat"
    tensor_out = tmp_path / "tensor"
    _make_small_parquet(inp, include_sp_r_tcwv=False)
    result = _run_fixture(inp, out_dir, "compatibility_fixture")
    assert result.returncode == 0

    export = _run_tensor_export(out_dir / _expected_basename(), tensor_out, output_format="npy", allow_test_grid=True)
    assert export.returncode == 0
    assert (tensor_out / "input_tensor.npy").exists()
    assert (tensor_out / "tensor_manifest.json").exists()
    report = json.loads((tensor_out / "tensor_validation_report.json").read_text(encoding="utf-8"))
    assert report["ok"] is True


def test_tensor_export_incomplete_fails_when_require_complete_true(tmp_path: Path) -> None:
    inp = tmp_path / "in.parquet"
    out_dir = tmp_path / "tensor"
    _make_small_parquet(inp, include_sp_r_tcwv=False)
    # Incomplete raw parquet should fail in exporter when REQUIRE_COMPLETE=true.
    result = _run_tensor_export(inp, out_dir, require_complete="true", allow_test_grid=True)
    assert result.returncode != 0
    report = json.loads((out_dir / "tensor_validation_report.json").read_text(encoding="utf-8"))
    assert report["ok"] is False


def test_tensor_validator_passes_and_fails(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    good = tmp_path / "good.npy"
    np.save(good, np.zeros((1, 20, 720, 1440), dtype=np.float32))
    good_report = tmp_path / "good_report.json"
    ok = subprocess.run(
        [
            sys.executable,
            "scripts/dev/validate_fourcastnet_tensor.py",
            "--INPUT_TENSOR",
            str(good),
            "--OUTPUT_REPORT",
            str(good_report),
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    assert ok.returncode == 0
    rep = json.loads(good_report.read_text(encoding="utf-8"))
    assert rep["ok"] is True
    assert rep["tensor_ok"] is True

    bad_shape = tmp_path / "bad_shape.npy"
    np.save(bad_shape, np.zeros((1, 20, 2, 2), dtype=np.float32))
    bad_shape_report = tmp_path / "bad_shape_report.json"
    p_bad_shape = subprocess.run(
        [
            sys.executable,
            "scripts/dev/validate_fourcastnet_tensor.py",
            "--INPUT_TENSOR",
            str(bad_shape),
            "--OUTPUT_REPORT",
            str(bad_shape_report),
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    assert p_bad_shape.returncode != 0
    rep_bad_shape = json.loads(bad_shape_report.read_text(encoding="utf-8"))
    assert rep_bad_shape["ok"] is False

    bad_non_finite = tmp_path / "bad_non_finite.npy"
    arr = np.zeros((1, 20, 720, 1440), dtype=np.float32)
    arr[0, 0, 0, 0] = np.nan
    np.save(bad_non_finite, arr)
    bad_non_finite_report = tmp_path / "bad_non_finite_report.json"
    p_bad_nf = subprocess.run(
        [
            sys.executable,
            "scripts/dev/validate_fourcastnet_tensor.py",
            "--INPUT_TENSOR",
            str(bad_non_finite),
            "--OUTPUT_REPORT",
            str(bad_non_finite_report),
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    assert p_bad_nf.returncode != 0
    rep_bad_nf = json.loads(bad_non_finite_report.read_text(encoding="utf-8"))
    assert rep_bad_nf["ok"] is False
    assert rep_bad_nf["error_stage"] == "tensor_finite"


def test_tensor_validator_stats_broadcast_validation(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    tensor = tmp_path / "x.npy"
    np.save(tensor, np.zeros((1, 20, 720, 1440), dtype=np.float32))
    means = tmp_path / "means.npy"
    stds = tmp_path / "stds.npy"
    np.save(means, np.zeros((21,), dtype=np.float32))
    np.save(stds, np.ones((20,), dtype=np.float32))

    out = tmp_path / "stats_report.json"
    p = subprocess.run(
        [
            sys.executable,
            "scripts/dev/validate_fourcastnet_tensor.py",
            "--INPUT_TENSOR",
            str(tensor),
            "--GLOBAL_MEANS",
            str(means),
            "--GLOBAL_STDS",
            str(stds),
            "--OUTPUT_REPORT",
            str(out),
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    assert p.returncode != 0
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["ok"] is False
    assert rep["stats_ok"] is False


def test_tensor_validator_21_channel_stats_requires_and_reports_policy(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    tensor = tmp_path / "x.npy"
    np.save(tensor, np.zeros((1, 20, 2, 2), dtype=np.float32))
    means = tmp_path / "means.npy"
    stds = tmp_path / "stds.npy"
    np.save(means, np.zeros((21,), dtype=np.float32))
    np.save(stds, np.ones((21,), dtype=np.float32))

    out = tmp_path / "stats_report_ok.json"
    p = subprocess.run(
        [
            sys.executable,
            "scripts/dev/validate_fourcastnet_tensor.py",
            "--INPUT_TENSOR",
            str(tensor),
            "--GLOBAL_MEANS",
            str(means),
            "--GLOBAL_STDS",
            str(stds),
            "--STATS_CHANNEL_POLICY",
            "first_20_channels",
            "--OUTPUT_REPORT",
            str(out),
            "--ALLOW_TEST_GRID",
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    assert p.returncode == 0
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["ok"] is True
    assert rep["tensor_ok"] is True
    assert rep["stats_ok"] is True
    assert rep["normalization_ok"] is True
    assert rep["contract_version"] == "fcn_v0_nvlabs_20ch_first20stats"
    assert rep["stats_channels_original"] == 21
    assert rep["stats_channels_used"] == 20
    assert rep["dropped_stats_channel"] == 20
    assert rep["dropped_stats_channel_name"] == "sst"


def test_direct_tensor_smoke_dry_random_requires_allow_flag(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    tensor = tmp_path / "x.npy"
    np.save(tensor, np.zeros((1, 20, 2, 2), dtype=np.float32))
    means = tmp_path / "means.npy"
    stds = tmp_path / "stds.npy"
    ckpt = tmp_path / "fake.ckpt"
    np.save(means, np.zeros((20,), dtype=np.float32))
    np.save(stds, np.ones((20,), dtype=np.float32))
    ckpt.write_bytes(b"fake")
    out = tmp_path / "dry_random_blocked.json"

    p = subprocess.run(
        [
            sys.executable,
            "scripts/dev/fourcastnet_direct_tensor_smoke.py",
            "--INPUT_TENSOR",
            str(tensor),
            "--GLOBAL_MEANS",
            str(means),
            "--GLOBAL_STDS",
            str(stds),
            "--CHECKPOINT",
            str(ckpt),
            "--MODEL_BACKEND",
            "dry_random",
            "--OUTPUT_REPORT",
            str(out),
            "--ALLOW_TEST_GRID",
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    assert p.returncode != 0
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["fourcastnet_proven"] is False


def test_direct_tensor_smoke_dry_random_plumbing_only(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    tensor = tmp_path / "x.npy"
    np.save(tensor, np.zeros((1, 20, 2, 2), dtype=np.float32))
    means = tmp_path / "means.npy"
    stds = tmp_path / "stds.npy"
    ckpt = tmp_path / "placeholder.ckpt"
    np.save(means, np.zeros((20,), dtype=np.float32))
    np.save(stds, np.ones((20,), dtype=np.float32))
    ckpt.write_bytes(b"placeholder")
    out = tmp_path / "dry_random_ok.json"

    p = subprocess.run(
        [
            sys.executable,
            "scripts/dev/fourcastnet_direct_tensor_smoke.py",
            "--INPUT_TENSOR",
            str(tensor),
            "--GLOBAL_MEANS",
            str(means),
            "--GLOBAL_STDS",
            str(stds),
            "--CHECKPOINT",
            str(ckpt),
            "--MODEL_BACKEND",
            "dry_random",
            "--ALLOW_RANDOM_MODEL",
            "true",
            "--OUTPUT_REPORT",
            str(out),
            "--ALLOW_TEST_GRID",
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    assert p.returncode == 0
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["inference_success"] is True
    assert rep["fourcastnet_proven"] is False


def test_notebook_static_checker_detects_tensor_stage(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    p = subprocess.run(
        [
            sys.executable,
            "scripts/dev/validate_colab_notebook_static.py",
            "--NOTEBOOK",
            "notebooks/fourcastnet_colab_smoke_test.ipynb",
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    assert p.returncode == 0
