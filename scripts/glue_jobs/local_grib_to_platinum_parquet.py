"""Local GRIB to Platinum Parquet conversion script.

This entrypoint accepts a single local GRIB file path, builds the same
surface and upper-level parquet frames used by the Glue job, and writes the
results to a local output directory.
"""

from datetime import datetime
from pathlib import Path
import re

from chucaw_preprocessor.ecmwf import serialize_parquet_chunked, load_merged_dataset
from chucaw_preprocessor.glue_args import resolve_args


def _normalize_run(run_value: str) -> str:
    run_value = (run_value or "").strip().lower()
    if not run_value:
        return "00z"
    return run_value if run_value.endswith("z") else f"{run_value}z"


def _extract_date_run_from_path(grib_path: str) -> tuple[str, str]:
    path_value = str(grib_path)
    date_match = re.search(r"(20\d{6})", path_value)
    run_match = re.search(r"/(00z|06z|12z|18z)/", path_value.lower())
    date_str = date_match.group(1) if date_match else datetime.utcnow().strftime("%Y%m%d")
    run_str = run_match.group(1) if run_match else "00z"
    return date_str, run_str


def main() -> None:
    """Convert a local GRIB file into parquet outputs."""
    args = resolve_args(required=["GRIB_PATH"], optional=["OUTPUT_DIR", "DATE", "RUN"])

    grib_path = Path(args["GRIB_PATH"]).expanduser()
    if not grib_path.exists():
        raise FileNotFoundError(f"No existe el archivo GRIB local: {grib_path}")

    inferred_date, inferred_run = _extract_date_run_from_path(str(grib_path))
    date_str = (args.get("DATE") or "").strip() or inferred_date
    run_str = _normalize_run((args.get("RUN") or "").strip() or inferred_run)
    output_dir = args.get("OUTPUT_DIR") or str(Path("/tmp") / "parquet")

    ds = load_merged_dataset(str(grib_path))

    output_filename = grib_path.with_suffix('.parquet').name
    output_path = str(Path(output_dir) / output_filename)
    parquet_path = serialize_parquet_chunked(
        ds, output_path=output_path, date_str=date_str, run_str=run_str
    )

    print(
        {
            "status": "ok",
            "grib_path": str(grib_path),
            "output_dir": output_dir,
            "parquet_path": parquet_path,
            "date": date_str,
            "run": run_str,
        }
    )


if __name__ == "__main__":
    main()