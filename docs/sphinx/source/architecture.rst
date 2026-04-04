Architecture
============

Objetivo
--------

Procesar GRIB en Bronze y publicarlo en Platinum en formato Parquet, manteniendo
la base de limpieza/merge sobre ``xarray`` y ``cfgrib``.

Piezas principales
------------------

- ``src/chucaw_preprocessor/ecmwf.py``: funciones base de lectura, merge y serializacion.
- ``scripts/glue_jobs/bronze_to_platinum_parquet.py``: job Glue principal (runtime ``glueetl`` en Glue 5.0).
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

Este flujo se ejecuta en ``glueetl`` para Glue 5.0 (Python 3.11), pero la transformacion
del script sigue en Python puro (``xarray/pandas/pyarrow``) sin ``DynamicFrame``.
