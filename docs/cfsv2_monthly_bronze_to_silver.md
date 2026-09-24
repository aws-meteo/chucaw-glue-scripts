# CFSv2 Monthly Bronze -> Silver

Glue Python Shell job: `scripts/glue_jobs/cfsv2_monthly_bronze_to_silver.py`
Core logic: `src/chucaw_preprocessor/cfsv2.py`

Processes one NOAA CFSv2 monthly forecast GRIB object at a time. Kept fully
separate from the ECMWF job/partition scheme — do not share helpers that
assume ECMWF's `year=/month=/day=/hour=` layout.

## Input

- `--BRONZE_KEY` (required): exact Bronze S3 key, e.g.
  `climate_long_range/provider=noaa/product=cfsv2/version=v0/run_date=20260629/
  cycle=00/member=01/product_kind=pgbf/valid_month=202609/raw/
  pgbf.01.2026062900.202609.avrg.grib.grb2`
- `--BRONZE_BUCKET` (default `chucaw-data-bronze-raw-725644097028-us-east-1-an`)
- `--SILVER_BUCKET` (default `chucaw-data-platinum-processed-725644097028-us-east-1-an`)
- `--SILVER_PREFIX` (default `climate_long_range/cfsv2_monthly_chile_long_v0`)
- `--TMP_DIR` (default `/tmp`)
- `--BBOX_NORTH` / `--BBOX_SOUTH` / `--BBOX_WEST` / `--BBOX_EAST`
  (default Chile bbox: north=-17, south=-56, west=-76, east=-66)
- `--WRITE_MANIFEST` (`true`/`1`/`yes` to also upload a small JSON manifest)

## Output

One Parquet file per Bronze key:

```
<SILVER_PREFIX>/run_date=YYYYMMDD/cycle=HH/member=XX/product_kind=KIND/
  valid_month=YYYYMM/avg_kind=KIND/part-000.parquet
```

Columns: `provider, product, version, run_date, cycle, member, product_kind,
valid_month, lead_month, avg_kind, latitude, longitude, variable, level_type,
level_value, value, unit, grib_short_name, grib_name, grib_param_id,
grib_discipline, grib_parameter_category, grib_parameter_number,
grib_type_of_level, grib_step_type, source_s3_uri`.

- `lead_month` is the calendar-month offset from `run_date`'s month to `valid_month`.
- `avg_kind` is `daily` by default, `6hourly` when the source filename ends in
  `.avrg.grib.00Z.grb2`.
- `level_type` is `surface` (with `level_value=null`) for variables without an
  extra vertical dimension, otherwise the GRIB level coordinate name (e.g.
  `isobaricInhPa`) with `level_value` set per row.
- `grib_*` columns preserve GRIB identity metadata used to map NOAA local CFSv2
  parameters such as PEVPR `(0,1,200)` and HPBL `(0,3,196)`.

## Processing notes

- Opens GRIB with `cfgrib.open_datasets(..., backend_kwargs={"decode_timedelta": False,
  "read_keys": ["discipline", "parameterCategory", "parameterNumber"]})` and converts
  each returned dataset independently — messages are not force-merged. It also opens
  explicit CFSv2 local-parameter filters for PEVPR and HPBL, then deduplicates after
  variables are identified.
- Bbox subsetting tolerates both -180..180 and 0..360 longitude conventions and
  is applied before any conversion to pandas, to keep memory bounded.
- Fails fast (`ValueError`) if the key can't be parsed or the bbox selects no data.

## Local dry run

```bash
python scripts/glue_jobs/cfsv2_monthly_bronze_to_silver.py \
  --BRONZE_KEY "climate_long_range/provider=noaa/product=cfsv2/version=v0/run_date=20260629/cycle=00/member=01/product_kind=pgbf/valid_month=202609/raw/pgbf.01.2026062900.202609.avrg.grib.grb2" \
  --TMP_DIR ./tmp
```

## Tests

```bash
python -m pytest tests/test_cfsv2_*.py
```

Synthetic-dataset only, no AWS/network calls.
