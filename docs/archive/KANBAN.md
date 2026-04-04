# 🏗️ Migración a AWS Glue 5.0 — Estado del Proyecto

> **Última actualización:** 2026-04-04T12:50 (Chile)  
> **Fuente de verdad:** `boulder.json`  
> **Objetivo:** Migrar build system a Glue 5.0 (Python 3.11, Amazon Linux 2023), eliminar contradicciones 4.0/5.0, deploy offline con .gluewheels.zip

---

## 📊 Estado Kanban

### ✅ Done
_Nada aún — comenzando ejecución._

### 🔨 In Progress
_Nada aún._

### 📋 To Do

| ID | Tarea | Workstream | Deps | Tiempo |
|----|-------|-----------|------|--------|
| **T01** | Actualizar Dockerfile.glue-builder a Glue 5.0 | WS1 | — | 15 min |
| **T05** | Alinear pyproject.toml a Python 3.11 | WS2 | — | 5 min |
| **T06** | Limpiar build scripts redundantes | WS1 | — | 5 min |
| **T02** | Compilar wheels en container Glue 5.0 | WS4 | T01 | 20 min |
| **T03** | Crear .gluewheels.zip + wheel del proyecto | WS4 | T02 | 10 min |
| **T04** | Test atómico: import verification offline | WS4 | T03 | 5 min |
| **T07** | Actualizar deploy-and-test-glue.ps1 | WS5 | T04 | 10 min |
| **T08** | Actualizar examples/ para Glue 5.0 | WS5 | T07 | 5 min |
| **T09** | Consolidar documentación | WS5 | T08 | 15 min |
| **T10** | Smoke test E2E con GRIB real | WS5 | T04,T05 | 10 min |

---

## 🎯 Runtime Target

```
Docker Image:  public.ecr.aws/glue/aws-glue-libs:5
OS:            Amazon Linux 2023
Python:        3.11
Spark:         3.5.4
User:          hadoop (NOT glue_user)
Deploy:        --additional-python-modules .gluewheels.zip + --no-index
Internet:      ❌ NO (offline wheel install)
```

## 📦 Dependencias a Empaquetar (extras no incluidas en Glue)

| Paquete | Versión | Tipo |
|---------|---------|------|
| xarray | 2024.2.0 | pure Python wheel |
| cfgrib | 0.9.14.1 | pure Python wheel |
| eccodes | 2.42.0 | Python bindings |
| eccodeslib | 2.42.0 | native .so compiled |

**NO empaquetar** (ya en Glue baseline): numpy, pandas, pyarrow, boto3, packaging, attrs

## 🚀 Secuencia de Validación

```
T01 → Docker image Glue 5.0 con eccodes compilado
  ↓
T05 → pyproject.toml alineado (paralelo)
  ↓
T02 → Wheels compilados cp311/linux
  ↓
T03 → .gluewheels.zip sin paquetes duplicados
  ↓
T04 → Import verification OFFLINE en container
  ↓
T10 → Smoke test con GRIB real
  ↓
T07-T09 → Deploy scripts + docs actualizados
```

## 📁 Archivos a Limpiar

### Eliminar (scripts redundantes de iteraciones pasadas):
- `build_glue_complete.sh`
- `build_glue_libs_compat.sh`
- `build_glue_libs_fixed.sh`
- `build_package.sh`

### Archivar a `docs/archive/` (docs obsoletas/contradictorias):
- `PLAN_SONNET.md` — dice "Glue 5.0 NO existe" (falso)
- `BUILD_SYSTEM_SUMMARY.txt` — referencia Glue 4.0
- `GLUE_BUILD_QUICKSTART.md` — referencia --extra-py-files
- `WORKFLOW_DIAGRAM.txt`
- `IMPLEMENTATION_CHECKLIST.md`
- `0404_upload_guide.md` — dice "Glue 4.0"
- `START_HERE.txt`
- `CONVERSION_ISSUES_RESOLVED.md`

## ⚠️ Contradicciones Encontradas y Resueltas

| Contradicción | Antes | Ahora |
|---------------|-------|-------|
| Docker image | `amazon/aws-glue-libs:glue_libs_4.0.0_image_01` | `public.ecr.aws/glue/aws-glue-libs:5` |
| Python version | 3.9 / 3.10 / 3.11 / 3.12 mezclados | **3.11** (único) |
| Deploy mechanism | `--extra-py-files` ZIP flat | `--additional-python-modules` .gluewheels.zip |
| eccodes version | 1.7.0 vs 2.42.0 | **2.42.0** (único) |
| cfgrib version | 0.9.12.0 vs 0.9.14.1 | **0.9.14.1** (único) |
| Build scripts | 6 scripts .sh distintos | **1** script canónico |
| Docs contradictorias | 8+ archivos en raíz | README.md como fuente de verdad |

---

## 🧭 Para el siguiente LLM/developer

1. **Lee `boulder.json`** — Tiene el plan completo con tareas SMART
2. **Las tareas van en orden** — T01 primero, luego T05 (paralelo), luego T02→T03→T04
3. **El test de cada tarea está en su definición** — ejecuta el campo `test` para verificar
4. **Actualiza este archivo** — Mueve tareas de "To Do" a "In Progress" / "Done"
5. **No toques la lógica ETL** (`ecmwf.py`, `bronze_to_platinum_parquet.py`) — está fuera de scope
