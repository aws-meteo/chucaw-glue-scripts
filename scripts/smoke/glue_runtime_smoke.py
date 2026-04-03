"""Smoke test for Glue runtime module resolution and version sanity.

This script validates:
1. Python runtime version (expected 3.11 by default).
2. Required module imports for this project.
3. Optional version alignment against Glue baseline list.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path


BASELINE_CHECK_PKGS = ("boto3", "numpy", "pandas", "pyarrow")
MODULE_TO_DIST = {
    "pyarrow": "pyarrow",
    "numpy": "numpy",
    "pandas": "pandas",
    "boto3": "boto3",
    "xarray": "xarray",
    "cfgrib": "cfgrib",
    "eccodes": "eccodes",
    "eccodeslib": "eccodeslib",
    "chucaw_preprocessor": "chucaw-preprocessor",
}


@dataclass
class ModuleStatus:
    module: str
    import_ok: bool
    distribution: str | None
    version: str | None
    error: str | None
    baseline_expected: str | None = None
    baseline_match: bool | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Glue runtime smoke test")
    parser.add_argument(
        "--expect-python",
        default="3.11",
        help="Expected major.minor Python version (default: 3.11)",
    )
    parser.add_argument(
        "--required-modules",
        nargs="+",
        default=[
            "boto3",
            "numpy",
            "pandas",
            "pyarrow",
            "xarray",
            "cfgrib",
            "eccodes",
            "eccodeslib",
            "chucaw_preprocessor",
        ],
        help="Modules that must be importable.",
    )
    parser.add_argument(
        "--glue-baseline",
        default="lista_de_glue50.txt",
        help="Path to Glue baseline package/version file.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when checks fail.",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional path to write JSON report.",
    )
    return parser.parse_args()


def read_baseline(path: str) -> dict[str, str]:
    baseline_path = Path(path)
    if not baseline_path.exists():
        return {}
    baseline: dict[str, str] = {}
    for line in baseline_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Za-z0-9_.-]+)==([^\s]+)\s*$", line)
        if match:
            pkg = match.group(1).lower().replace("_", "-")
            baseline[pkg] = match.group(2)
    return baseline


def current_python() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def check_module(module_name: str, baseline: dict[str, str]) -> ModuleStatus:
    dist = MODULE_TO_DIST.get(module_name, module_name).lower().replace("_", "-")
    expected = baseline.get(dist) if dist in BASELINE_CHECK_PKGS else None
    try:
        importlib.import_module(module_name)
        try:
            version = metadata.version(dist)
        except metadata.PackageNotFoundError:
            version = None
        baseline_match = None
        if expected is not None and version is not None:
            baseline_match = version == expected
        return ModuleStatus(
            module=module_name,
            import_ok=True,
            distribution=dist,
            version=version,
            error=None,
            baseline_expected=expected,
            baseline_match=baseline_match,
        )
    except Exception as exc:  # noqa: BLE001
        return ModuleStatus(
            module=module_name,
            import_ok=False,
            distribution=dist,
            version=None,
            error=f"{type(exc).__name__}: {exc}",
            baseline_expected=expected,
            baseline_match=False if expected is not None else None,
        )


def main() -> int:
    args = parse_args()
    baseline = read_baseline(args.glue_baseline)
    py_now = current_python()
    py_ok = py_now == args.expect_python

    checks = [check_module(mod, baseline) for mod in args.required_modules]
    imports_ok = all(item.import_ok for item in checks)
    baseline_ok = all(
        item.baseline_match in (True, None)
        for item in checks
    )

    summary = {
        "python": {
            "current": py_now,
            "expected": args.expect_python,
            "ok": py_ok,
        },
        "imports_ok": imports_ok,
        "baseline_ok": baseline_ok,
        "strict": args.strict,
        "checks": [asdict(item) for item in checks],
    }

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(summary, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

    print(json.dumps(summary, indent=2, ensure_ascii=True))

    if not args.strict:
        return 0
    if py_ok and imports_ok and baseline_ok:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
