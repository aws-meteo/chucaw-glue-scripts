from pathlib import Path

from chucaw_preprocessor.ecmwf import (
    build_parquet_frames,
    download_grib_from_s3,
    load_merged_dataset,
    upload_file_to_s3,
    write_parquet_frames,
)
from chucaw_preprocessor.glue_args import resolve_args
from chucaw_preprocessor.job_common import partition_prefix


def main() -> None:
    args = resolve_args(
        required=["BRONZE_BUCKET", "BRONZE_KEY", "SILVER_BUCKET", "SILVER_PREFIX", "DATE", "RUN"],
        optional=["TMP_DIR"],
    )
    tmp_dir = args.get("TMP_DIR") or "/tmp"
    grib_path = download_grib_from_s3(args["BRONZE_BUCKET"], args["BRONZE_KEY"], download_dir=tmp_dir)
    ds = load_merged_dataset(grib_path)
    surface_df, upper_df = build_parquet_frames(ds)

    output_dir = str(Path(tmp_dir) / "parquet")
    surface_path, upper_path = write_parquet_frames(surface_df, upper_df, output_dir=output_dir)
    target_prefix = partition_prefix(args["SILVER_PREFIX"], args["DATE"], args["RUN"])

    upload_file_to_s3(surface_path, args["SILVER_BUCKET"], f"{target_prefix}/dataset=surface/part-000.parquet")
    upload_file_to_s3(upper_path, args["SILVER_BUCKET"], f"{target_prefix}/dataset=upper/part-000.parquet")

    print(
        {
            "status": "ok",
            "silver_bucket": args["SILVER_BUCKET"],
            "prefix": target_prefix,
            "artifacts": ["dataset=surface/part-000.parquet", "dataset=upper/part-000.parquet"],
        }
    )


if __name__ == "__main__":
    main()
