# FourCastNet V0 Preprocessing (Platinum Parquet -> Snapshot NPY)

## Objective

V0 adds a minimal and explicit preprocessing path that reads one Platinum Parquet partition and emits one FourCastNet-ready snapshot tensor.

This phase emits `.npy` only. Yearly HDF5 assembly is a future phase.

Normalization is specified separately in
[`normalization_contract.md`](normalization_contract.md). The `.npy` tensor is
raw; normalize with the declared global mean/std contract before model input.

## Input contract

Expected schema columns in Platinum Parquet rows:

- `isobaricInhPa` or `isobaricinhpa`
- `latitude`
- `longitude`
- `variable`
- `value`
- `date`
- `run`

Expected partitioning:

- `year`
- `month`
- `day`
- `hour`

Defaults:

- Platinum bucket: `chucaw-data-platinum-processed-725644097028-us-east-1-an`
- Platinum parquet prefix: `ecmwf/parquet`
- FourCastNet output prefix: `ecmwf/fourcastnet`

## Output artifacts per partition

- `input_fourcastnet.npy`
- `manifest.json`
- `validation_report.json`

S3 path pattern:

- `s3://<PLATINUM_BUCKET>/<FOURCASTNET_PREFIX>/year=YYYY/month=MM/day=DD/hour=HH/input_fourcastnet.npy`
- `s3://<PLATINUM_BUCKET>/<FOURCASTNET_PREFIX>/year=YYYY/month=MM/day=DD/hour=HH/manifest.json`
- `s3://<PLATINUM_BUCKET>/<FOURCASTNET_PREFIX>/year=YYYY/month=MM/day=DD/hour=HH/validation_report.json`

## Tensor contract

- Shape: `(1, 20, 720, 1440)`
- Dtype: `float32`
- Latitude order: descending `90 -> -89.75`
- Longitude order: ascending `0 -> 359.75`
- Normalization contract: `fcn_v0_nvlabs_20ch_first20stats`
- Stats policy for 21-channel NVlabs stats: `first_20_channels` (drop legacy `sst`)

Channel order:

1. `u10` surface
2. `v10` surface
3. `t2m` surface
4. `sp` surface
5. `msl` surface
6. `t` 850 hPa
7. `u` 1000 hPa
8. `v` 1000 hPa
9. `z` 1000 hPa
10. `u` 850 hPa
11. `v` 850 hPa
12. `z` 850 hPa
13. `u` 500 hPa
14. `v` 500 hPa
15. `z` 500 hPa
16. `t` 500 hPa
17. `z` 50 hPa
18. `r` 500 hPa
19. `r` 850 hPa
20. `tcwv` integrated/surface

## Missing channels behavior

V0 never synthesizes missing meteorological channels.

If required channels are missing:

- `manifest.json` and `validation_report.json` are still written.
- `input_fourcastnet.npy` is not written.
- Job fails by default unless `--ALLOW_INCOMPLETE=true`.
- If latitude count is 721 and `LATITUDE_POLICY=fail`, validation remains incomplete and tensor is not written.

Likely missing from current upstream Parquet pipeline:

- `sp`
- `r`
- `tcwv`

## Glue job

Script:

- `scripts/glue_jobs/platinum_parquet_to_fourcastnet.py`

Arguments:

- `--PLATINUM_BUCKET`
- `--PLATINUM_PARQUET_PREFIX`
- `--FOURCASTNET_PREFIX`
- `--YEAR`
- `--MONTH`
- `--DAY`
- `--HOUR`
- `--TMP_DIR`
- `--ALLOW_INCOMPLETE=false`
- `--LATITUDE_POLICY=fail` (`fail|drop_south_pole|drop_north_pole`)

`HOUR` accepts both `06` and `06z`.
For S3 partition paths it is normalized to `HH` (example `hour=06`).
For run metadata labels it is normalized to `HHz` (example `06z`).

Example:

```text
--PLATINUM_BUCKET chucaw-data-platinum-processed-725644097028-us-east-1-an
--PLATINUM_PARQUET_PREFIX ecmwf/parquet
--FOURCASTNET_PREFIX ecmwf/fourcastnet
--YEAR 2026
--MONTH 04
--DAY 03
--HOUR 00
--TMP_DIR /tmp
--ALLOW_INCOMPLETE false
```

## Local dry-run

Script:

- `scripts/glue_jobs/local/local_parquet_to_fourcastnet.py`

Positive smoke (complete channels, writes tensor):

```powershell
$env:PYTHONPATH='src'
python scripts/dev/generate_fourcastnet_synthetic_parquet.py --OUTPUT_PATH tmp/fourcastnet_complete.parquet --COMPLETE true
python scripts/glue_jobs/local/local_parquet_to_fourcastnet.py --PARQUET_PATH tmp/fourcastnet_complete.parquet --OUTPUT_DIR tmp/fourcastnet_complete_out --ALLOW_TEST_GRID true
```

Incomplete smoke (writes reports, skips tensor):

```powershell
$env:PYTHONPATH='src'
python scripts/dev/generate_fourcastnet_synthetic_parquet.py --OUTPUT_PATH tmp/fourcastnet_incomplete.parquet --COMPLETE false
python scripts/glue_jobs/local/local_parquet_to_fourcastnet.py --PARQUET_PATH tmp/fourcastnet_incomplete.parquet --OUTPUT_DIR tmp/fourcastnet_incomplete_out --ALLOW_INCOMPLETE true --ALLOW_TEST_GRID true
```

Local audit command for a real S3 partition (no tensor required):

```powershell
python scripts/glue_jobs/audit_platinum_partition.py `
  --PLATINUM_BUCKET chucaw-data-platinum-processed-725644097028-us-east-1-an `
  --PLATINUM_PARQUET_PREFIX ecmwf/parquet `
  --YEAR 2026 `
  --MONTH 04 `
  --DAY 03 `
  --HOUR 06 `
  --OUTPUT_DIR tmp/fourcastnet_real_audit_2026_04_03_06
```

Audit artifacts:

- `available_variables.json`
- `available_variable_levels.csv`
- `validation_report.json`
- `manifest.json`

## Future option: deriving relative humidity r from q

- Current Platinum contains `q` but not `r`.
- FourCastNet expects `r` at 850 and 500 hPa.
- Deriving `r` from `q` is a physical transformation, not a simple rename.
- It requires an explicit formula, unit assumptions, pressure-level handling (Pa or hPa), temperature in K, and validation against a trusted reference.
- Until implemented and validated, `r` remains a missing channel.

## Upstream variables required for FourCastNet

- Current representative local Parquet has `msl`, `q`, `t`, `t2m`, `u`, `u10`, `v`, `v10`, `z`.
- FourCastNet additionally requires `sp`, `r`, `tcwv`.
- `sp` and `tcwv` likely need upstream inclusion during GRIB ingestion when source messages provide them.
- `r` must be ingested directly or derived from `q` with an explicit validated formula.
- Current V0 behavior must remain fail-safe: no tensor write until required channels exist or are explicitly derived and validated.
