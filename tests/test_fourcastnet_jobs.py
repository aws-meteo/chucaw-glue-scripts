import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.glue_jobs.audit_platinum_partition import _partition_prefix as audit_partition_prefix
from scripts.glue_jobs.audit_platinum_partition import _normalize_hour_arg as normalize_hour_audit
from scripts.glue_jobs.platinum_parquet_to_fourcastnet import _partition_prefix as glue_partition_prefix
from scripts.glue_jobs.platinum_parquet_to_fourcastnet import _normalize_hour_arg as normalize_hour_glue


def test_normalize_hour_accepts_hour_with_or_without_z() -> None:
    assert normalize_hour_glue("6") == ("06z", "06z")
    assert normalize_hour_glue("06") == ("06z", "06z")
    assert normalize_hour_glue("06z") == ("06z", "06z")
    assert normalize_hour_audit("06") == ("06", "06z")
    assert normalize_hour_audit("06z") == ("06", "06z")


def test_partition_prefix_uses_validated_fourcastnet_hour_with_z() -> None:
    out = glue_partition_prefix("ecmwf/parquet", "2026", "06", "02", "06z")
    assert out.endswith("year=2026/month=06/day=02/hour=06z")
    out2 = audit_partition_prefix("ecmwf/parquet", "2026", "06", "02", "06")
    assert out2.endswith("year=2026/month=06/day=02/hour=06")


def _make_incomplete_local_parquet(path: Path) -> None:
    df = pd.DataFrame(
        {
            "isobaricInhPa": [np.nan] * 4,
            "latitude": [90.0, 90.0, 89.75, 89.75],
            "longitude": [-180.0, -179.75, -180.0, -179.75],
            "variable": ["u10", "v10", "t2m", "msl"],
            "value": [1.0, 2.0, 3.0, 4.0],
            "date": ["20260410"] * 4,
            "run": ["00z"] * 4,
        }
    )
    df.to_parquet(path, index=False)


def test_local_cli_default_latitude_policy_fail(tmp_path: Path) -> None:
    parquet_path = tmp_path / "incomplete.parquet"
    out_dir = tmp_path / "out_default"
    _make_incomplete_local_parquet(parquet_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    cmd = [
        sys.executable,
        "scripts/glue_jobs/local_parquet_to_fourcastnet.py",
        "--PARQUET_PATH",
        str(parquet_path),
        "--OUTPUT_DIR",
        str(out_dir),
        "--ALLOW_INCOMPLETE",
        "true",
    ]
    subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[1], env=env)
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["latitude_policy"] == "fail"
    assert manifest["tensor_written"] is False
    assert not (out_dir / "input_fourcastnet.npy").exists()


def test_local_cli_accepts_latitude_policy_arg(tmp_path: Path) -> None:
    parquet_path = tmp_path / "incomplete.parquet"
    out_dir = tmp_path / "out_drop"
    _make_incomplete_local_parquet(parquet_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    cmd = [
        sys.executable,
        "scripts/glue_jobs/local_parquet_to_fourcastnet.py",
        "--PARQUET_PATH",
        str(parquet_path),
        "--OUTPUT_DIR",
        str(out_dir),
        "--ALLOW_INCOMPLETE",
        "true",
        "--LATITUDE_POLICY",
        "drop_south_pole",
    ]
    subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[1], env=env)
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["latitude_policy"] == "drop_south_pole"
    assert manifest["tensor_written"] is False
    assert not (out_dir / "input_fourcastnet.npy").exists()


def test_glue_job_uses_contract_default_latitude_policy() -> None:
    import scripts.glue_jobs.platinum_parquet_to_fourcastnet as job

    calls: list[str] = []
    df = pd.DataFrame(
        {
            "isobaricInhPa": [np.nan],
            "latitude": [90.0],
            "longitude": [0.0],
            "variable": ["u10"],
            "value": [1.0],
            "date": ["20260410"],
            "run": ["00z"],
        }
    )

    def fake_read(*_args, **_kwargs):
        return df, {"rows_after_pair_filter": len(df)}

    def fake_validation(_df, latitude_policy="fail"):
        calls.append(latitude_policy)
        return {"ok": False}

    job._list_partition_parquet_keys = lambda *_args, **_kwargs: ["dummy.parquet"]
    job._download_s3_keys = lambda *_args, **_kwargs: ["tmp/test_glue_lat_policy/dummy.parquet"]
    job._read_fourcastnet_relevant_parquet = fake_read
    job.build_validation_report = fake_validation
    job._upload_file = lambda *_args, **_kwargs: None

    result = job.run_job(
        {
            "YEAR": "2026",
            "MONTH": "06",
            "DAY": "02",
            "HOUR": "06z",
            "ALLOW_INCOMPLETE": "true",
            "TMP_DIR": "tmp/test_glue_lat_policy",
        }
    )
    assert calls == ["drop_south_pole"]
    assert result["latitude_policy"] == "drop_south_pole"
    assert result["source_partition"].endswith("year=2026/month=06/day=02/hour=06z")


def test_glue_job_accepts_latitude_policy_arg() -> None:
    import scripts.glue_jobs.platinum_parquet_to_fourcastnet as job

    calls: list[str] = []
    df = pd.DataFrame(
        {
            "isobaricInhPa": [np.nan],
            "latitude": [90.0],
            "longitude": [0.0],
            "variable": ["u10"],
            "value": [1.0],
            "date": ["20260410"],
            "run": ["00z"],
        }
    )

    def fake_read(*_args, **_kwargs):
        return df, {"rows_after_pair_filter": len(df)}

    def fake_validation(_df, latitude_policy="fail"):
        calls.append(latitude_policy)
        return {"ok": False}

    job._list_partition_parquet_keys = lambda *_args, **_kwargs: ["dummy.parquet"]
    job._download_s3_keys = lambda *_args, **_kwargs: ["tmp/test_glue_lat_policy_arg/dummy.parquet"]
    job._read_fourcastnet_relevant_parquet = fake_read
    job.build_validation_report = fake_validation
    job._upload_file = lambda *_args, **_kwargs: None

    result = job.run_job(
        {
            "YEAR": "2026",
            "MONTH": "06",
            "DAY": "02",
            "HOUR": "06z",
            "ALLOW_INCOMPLETE": "true",
            "LATITUDE_POLICY": "drop_north_pole",
            "TMP_DIR": "tmp/test_glue_lat_policy_arg",
        }
    )
    assert calls == ["drop_north_pole"]
    assert result["latitude_policy"] == "drop_north_pole"
