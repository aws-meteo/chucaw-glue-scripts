# FourCastNet Preprocessing Fast Audit

## Status Summary
- **Preprocessor Status:** Existing in `scripts/glue_jobs/platinum_parquet_to_fourcastnet.py` and `src/chucaw_preprocessor/fourcastnet.py`.
- **Glue Execution:** Latest runs for `2026/05/10/06z` FAILED.
- **Reason for Failure:** Missing required channels: `sp`, `r` (500, 850 hPa), and `tcwv`. Standard Platinum Parquet does not contain these variables.
- **S3 Tensors:** Only the baseline `input_tensor.npy` exists in the `v0/input` folder. No generated tensors exist for recent dates.
- **RAM Risk:** Each snapshot Parquet file contains ~71.6M rows, requiring ~4GB in memory. Local concatenation of multiple files (Audit script) can exceed 20GB RAM, leading to OOM/Reboots on local machines.

## Detailed Answers

1. **Does the preprocessor already exist?**
   Yes, the logic is implemented in the `chucaw_preprocessor` package and the Glue job script.

2. **What is the exact entrypoint?**
   AWS Glue Job: `platinum_parquet_to_fourcastnet`.

3. **Did the Glue job run successfully?**
   No. It failed with `RuntimeError: Validation failed... missing required channels/columns`.

4. **Where did the Glue job write outputs?**
   Validation reports were written to: `s3://chucaw-data-platinum-processed-725644097028-us-east-1-an/ecmwf/fourcastnet/year=2026/month=05/day=10/hour=06z/`.
   No tensors were written due to validation failure.

5. **Are there already generated tensors in S3 besides the baseline?**
   No. The `generated-inputs` prefix is empty.

6. **Which date/run can be used next?**
   `2026/05/10/06z` and `2026/05/11/06z` have Parquet data, but they are incomplete.

7. **Is the correct next step to use existing output, rerun Glue, or fix the script?**
   The script needs to be updated to support "compatibility mode" (deriving `r` from `q` and `t`, and using proxies for `sp` and `tcwv`) similar to `scripts/dev/make_fourcastnet_compatibility_fixture.py`.

8. **What command should the human run next?**
   Run a local compatibility fixture for one file to verify the derivation logic on real data:
   ```powershell
   $env:PYTHONPATH='src'
   python scripts/dev/make_fourcastnet_compatibility_fixture.py --INPUT_PARQUET tmp/audit_one.parquet --OUTPUT_DIR tmp/audit_compat_test --MODE compatibility_fixture --LATITUDE_POLICY drop_south_pole
   ```

9. **What command should not be run locally due to RAM risk?**
   Do not run `scripts/glue_jobs/audit_platinum_partition.py` on a full partition (multiple files) unless the machine has 32GB+ RAM.

10. **What should be shown in the meeting:**
    - The `validation_report.json` showing the 69 variable-level combinations and the 4 missing channels.
    - The success of a local compatibility fixture (once run).

## Evidence
- **S3 Validation Report:** `ecmwf/fourcastnet/year=2026/month=05/day=10/hour=06z/20260510060000-0h-scda-fc_validation_report.json`
- **Available Variables:** `msl`, `q`, `t`, `t2m`, `u`, `u10`, `v`, `v10`, `z`.
- **Missing Variables:** `sp`, `r`, `tcwv`.
