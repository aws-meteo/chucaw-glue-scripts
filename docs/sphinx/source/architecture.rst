Architecture
============

Objetivo
--------

Procesar GRIB en Bronze y publicarlo en Platinum en formato Parquet, manteniendo
la base de limpieza/merge sobre ``xarray`` y ``cfgrib``.

Piezas principales
------------------

- ``src/chucaw_preprocessor/ecmwf.py``: funciones base de lectura, merge y serializacion.
- ``scripts/glue_jobs/bronze_to_platinum_parquet.py``: job Glue Python Shell principal.
- ``glue/job-definitions/*.json``: definiciones listas para crear/actualizar el job.
- ``glue/job-runs/*.json``: ejemplos listos para ejecutar corridas.

Particionado
------------

La salida Parquet se publica con las particiones:

- ``year``
- ``month``
- ``day``
- ``run``

Nota sobre DynamicFrame
-----------------------

Este flujo usa Glue Python Shell, por lo que el procesamiento corre con Python puro
(``xarray/pandas/pyarrow``). ``DynamicFrame`` aplica a jobs Spark ``glueetl``.
