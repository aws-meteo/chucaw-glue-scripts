
import pyarrow as pa
import pyarrow.parquet as pq

def serialize_parquet_chunked(ds, output_dir: str, date_str: str, run_str: str) -> tuple[str, str]:
    """Serialize GRIB xarray dataset directly to partitioned PyArrow Parquet chunks.
    This resolves memory OOMs by dropping large single-dataframe allocations.
    """
    import os
    from pathlib import Path
    os.makedirs(output_dir, exist_ok=True)
    surface_path = str(Path(output_dir) / "surface.parquet")
    upper_path = str(Path(output_dir) / "upper.parquet")

    surface_writer = None
    for var in _SURFACE_VARS:
        if var not in ds.data_vars:
            continue
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
        
    if surface_writer:
        surface_writer.close()

    upper_writer = None
    ds_pl = ds.sel(isobaricInhPa=EXPECTED_PRESSURE_LEVELS)
    
    if "gh" in ds_pl.data_vars:
        z_array = ds_pl["gh"] * _GRAVITY
        z_array.name = "z"
        ds_var = z_array.to_dataframe().reset_index()
        ds_var = ds_var.rename(columns={"z": "value"})
        ds_var["variable"] = "z"
        ds_var["value"] = ds_var["value"].astype("float32")
        ds_var["date"] = date_str
        ds_var["run"] = run_str
        
        cols = ["isobaricInhPa", "latitude", "longitude", "variable", "value", "date", "run"]
        table = pa.Table.from_pandas(ds_var[cols])
        if upper_writer is None:
            upper_writer = pq.ParquetWriter(upper_path, table.schema, compression="snappy")
        upper_writer.write_table(table)

    for var in _UPPER_VARS:
        if var not in ds_pl.data_vars:
            continue
        ds_var = ds_pl[[var]].to_dataframe().reset_index()
        ds_var = ds_var.rename(columns={var: "value"})
        ds_var["variable"] = var
        ds_var["value"] = ds_var["value"].astype("float32")
        ds_var["date"] = date_str
        ds_var["run"] = run_str
        
        cols = ["isobaricInhPa", "latitude", "longitude", "variable", "value", "date", "run"]
        table = pa.Table.from_pandas(ds_var[cols])
        if upper_writer is None:
            upper_writer = pq.ParquetWriter(upper_path, table.schema, compression="snappy")
        upper_writer.write_table(table)

    if upper_writer:
        upper_writer.close()

    return surface_path, upper_path
