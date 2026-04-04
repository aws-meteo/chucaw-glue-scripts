import sys

with open("src/chucaw_preprocessor/ecmwf.py", "r") as f:
    content = f.read()

# Create a new version of serialize_parquet_chunked that loops over isobaricInhPa
new_method = """
def serialize_parquet_chunked(ds: xr.Dataset, output_dir: str, date_str: str, run_str: str) -> tuple[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    surface_path = str(Path(output_dir) / "surface.parquet")
    upper_path = str(Path(output_dir) / "upper.parquet")

    surface_writer = None
    for var in _SURFACE_VARS:
        if var not in ds.data_vars: continue
        ds_var = ds[[var]].to_dataframe().reset_index()
        ds_var = ds_var.rename(columns={var: "value"})
        ds_var["variable"] = var
        ds_var["value"] = ds_var["value"].astype("float32")
        ds_var["date"] = date_str
        ds_var["run"] = run_str
        cols = ["latitude", "longitude", "variable", "value", "date", "run"]
        table = pa.Table.from_pandas(ds_var[cols])
        if surface_writer is None:
            surface_writer = pq.ParquetWriter(surface_path, table.schema, compression="snappy")
        surface_writer.write_table(table)
    if surface_writer: surface_writer.close()

    upper_writer = None
    ds_pl = ds.sel(isobaricInhPa=EXPECTED_PRESSURE_LEVELS)
    
    if "gh" in ds_pl.data_vars:
        for p_level in ds_pl.isobaricInhPa.values:
            ds_sub = ds_pl[["gh"]].sel(isobaricInhPa=p_level)
            z_array = ds_sub["gh"] * _GRAVITY
            z_array.name = "z"
            ds_var = z_array.to_dataframe().reset_index()
            ds_var = ds_var.rename(columns={"z": "value"})
            ds_var["variable"] = "z"
            ds_var["value"] = ds_var["value"].astype("float32")
            ds_var["date"] = date_str
            ds_var["run"] = run_str
            # Add missing coordinate because .sel dropped it
            ds_var["isobaricInhPa"] = p_level
            cols = ["isobaricInhPa", "latitude", "longitude", "variable", "value", "date", "run"]
            table = pa.Table.from_pandas(ds_var[cols])
            if upper_writer is None:
                upper_writer = pq.ParquetWriter(upper_path, table.schema, compression="snappy")
            upper_writer.write_table(table)

    for var in _UPPER_VARS:
        if var not in ds_pl.data_vars: continue
        for p_level in ds_pl.isobaricInhPa.values:
            ds_sub = ds_pl[[var]].sel(isobaricInhPa=p_level)
            ds_var = ds_sub.to_dataframe().reset_index()
            ds_var = ds_var.rename(columns={var: "value"})
            ds_var["variable"] = var
            ds_var["value"] = ds_var["value"].astype("float32")
            ds_var["date"] = date_str
            ds_var["run"] = run_str
            ds_var["isobaricInhPa"] = p_level
            cols = ["isobaricInhPa", "latitude", "longitude", "variable", "value", "date", "run"]
            table = pa.Table.from_pandas(ds_var[cols])
            if upper_writer is None:
                upper_writer = pq.ParquetWriter(upper_path, table.schema, compression="snappy")
            upper_writer.write_table(table)

    if upper_writer: upper_writer.close()
    return surface_path, upper_path
"""

# Strip out old serialize_parquet_chunked
start_idx = content.find("def serialize_parquet_chunked")
if start_idx != -1:
    content = content[:start_idx]

content += new_method

with open("src/chucaw_preprocessor/ecmwf.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patched ecmwf.py successfully.")
