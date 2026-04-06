#!/usr/bin/env python3
"""
Example AWS Glue Job Script
============================
Demonstrates usage of custom dependencies (xarray, cfgrib) compiled with
the Docker build system (build-glue-deps.ps1).

Prerequisites:
1. Build dependencies: docker build -f Dockerfile.glue-builder -t glue5-builder:latest . && docker run --rm -v ".:/workspace" -v "./build:/build" glue5-builder:latest "bash /workspace/build_glue_libs.sh"
2. Upload to S3: aws s3 cp build/glue-dependencies.gluewheels.zip s3://your-bucket/libs/ && aws s3 cp build/chucaw_preprocessor-*.whl s3://your-bucket/libs/
3. Configure job with: --additional-python-modules s3://your-bucket/libs/glue-dependencies.gluewheels.zip,s3://your-bucket/libs/chucaw_preprocessor-0.1.0-py3-none-any.whl and --python-modules-installer-option --no-index
"""

import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job

# Initialize Glue context
args = getResolvedOptions(sys.argv, ['JOB_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)
logger = glueContext.get_logger()

# ============================================================================
# VERIFY CUSTOM DEPENDENCIES
# ============================================================================
logger.info("=" * 80)
logger.info("Verifying custom dependencies from .gluewheels.zip")
logger.info("=" * 80)

try:
    import xarray as xr
    import cfgrib
    import eccodes
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    
    logger.info(f"✓ xarray {xr.__version__}")
    logger.info(f"✓ cfgrib {cfgrib.__version__}")
    logger.info(f"✓ eccodes {eccodes.__version__}")
    logger.info(f"✓ numpy {np.__version__}")
    logger.info(f"✓ pandas {pd.__version__}")
    logger.info(f"✓ pyarrow {pa.__version__}")
    
except ImportError as e:
    logger.error(f"Failed to import dependency: {e}")
    logger.error("Ensure --additional-python-modules points to glue-dependencies.gluewheels.zip and chucaw_preprocessor wheel")
    raise

logger.info("=" * 80)
logger.info("All dependencies loaded successfully!")
logger.info("=" * 80)

# ============================================================================
# EXAMPLE: Process GRIB files from S3 with xarray/cfgrib
# ============================================================================

# Example S3 path to GRIB file
# grib_s3_path = "s3://your-bucket/bronze/ecmwf/2024/01/01/data.grib"

# Download GRIB to local temp storage (Glue workers have /tmp)
# import boto3
# s3 = boto3.client('s3')
# local_grib = "/tmp/input.grib"
# s3.download_file(bucket, key, local_grib)

# Open with xarray + cfgrib engine
# logger.info(f"Opening GRIB file: {local_grib}")
# ds = xr.open_dataset(local_grib, engine='cfgrib')
# logger.info(f"Dataset variables: {list(ds.data_vars)}")

# Process data
# df = ds.to_dataframe().reset_index()
# spark_df = spark.createDataFrame(df)

# Write to S3 as Parquet
# output_path = "s3://your-bucket/platinum/ecmwf/2024/01/01/"
# spark_df.write.mode('overwrite').parquet(output_path)
# logger.info(f"Written Parquet to: {output_path}")

# ============================================================================
# EXAMPLE: Use Glue DynamicFrame for catalog integration
# ============================================================================

# Read from Glue Data Catalog
# dyf = glueContext.create_dynamic_frame.from_catalog(
#     database = "your_database",
#     table_name = "your_table"
# )

# Transform
# dyf_transformed = ApplyMapping.apply(
#     frame = dyf,
#     mappings = [
#         ("old_col", "string", "new_col", "string"),
#         ("timestamp", "long", "timestamp", "timestamp")
#     ]
# )

# Write to S3 + update catalog
# glueContext.write_dynamic_frame.from_options(
#     frame = dyf_transformed,
#     connection_type = "s3",
#     connection_options = {"path": "s3://your-bucket/output/"},
#     format = "parquet"
# )

logger.info("Job completed successfully")
job.commit()
