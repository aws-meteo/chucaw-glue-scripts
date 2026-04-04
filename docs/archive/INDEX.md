# 📚 AWS Glue Build System - Índice de Documentación

Sistema completo para compilar dependencias Python para AWS Glue 5.0 desde Windows usando Docker.

---

## 🚀 Inicio Rápido (Elige tu camino)

### Opción A: Solo quiero compilar (5 min)

```powershell
# 1. Test (opcional)
.\test-glue-build.ps1

# 2. Build
.\build-glue-deps.ps1

# 3. Upload
aws s3 cp build\glue-dependencies.zip s3://tu-bucket/glue-libs/
```

📖 **Leer**: [GLUE_BUILD_QUICKSTART.md](GLUE_BUILD_QUICKSTART.md)

### Opción B: Quiero entender todo primero (15 min)

1. Lee la arquitectura: [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md)
2. Sigue el checklist: [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md)
3. Ejecuta el build: `.\build-glue-deps.ps1`

### Opción C: Solo necesito ejemplos de código

📁 **Ver**: [examples/](examples/) → Job definitions + Python scripts

---

## 📂 Estructura de Documentación

### Nivel 1: Quick Reference

| Archivo | Propósito | Tiempo Lectura |
|---------|-----------|----------------|
| [GLUE_BUILD_QUICKSTART.md](GLUE_BUILD_QUICKSTART.md) | Comandos básicos + troubleshooting rápido | 3 min |
| [WORKFLOW_DIAGRAM.txt](WORKFLOW_DIAGRAM.txt) | Diagrama visual del flujo completo | 5 min |

### Nivel 2: Implementation Guides

| Archivo | Propósito | Tiempo Lectura |
|---------|-----------|----------------|
| [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) | Checklist paso a paso desde setup hasta deploy | 10 min |
| [BUILD_SYSTEM_SUMMARY.txt](BUILD_SYSTEM_SUMMARY.txt) | Resumen ejecutivo del sistema completo | 8 min |

### Nivel 3: Comprehensive Documentation

| Archivo | Propósito | Tiempo Lectura |
|---------|-----------|----------------|
| [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) | Arquitectura, troubleshooting, security, deployment | 15 min |
| [examples/README.md](examples/README.md) | Guía completa de ejemplos de Glue Jobs | 5 min |

---

## 🔧 Archivos del Sistema

### Core Build System

| Archivo | Descripción |
|---------|-------------|
| **build-glue-deps.ps1** | 🚀 Orquestador principal (EJECUTAR ESTE) |
| **Dockerfile.glue-builder** | 🐳 Entorno de compilación (AWS Glue 5.0 + toolchain) |
| **build_glue_libs.sh** | ⚙️ Script de compilación y empaquetado |
| **verify_glue_deps.py** | ✅ Validador de imports (REPL loop) |
| **test-glue-build.ps1** | 🧪 Pre-flight check (opcional) |

### Configuration

| Archivo | Descripción |
|---------|-------------|
| **requirements-glue.txt** | 📝 Tus dependencias Python |
| **.gitattributes** | 🔧 Line endings (LF para .sh) |
| **.gitignore** | 🚫 Excluye build artifacts |

### Examples

| Archivo | Descripción |
|---------|-------------|
| **examples/glue-job-example.json** | 📋 Job definition template |
| **examples/glue-job-example.py** | 🐍 Glue ETL script example |
| **examples/README.md** | 📖 Guía de ejemplos |

---

## 🎯 Casos de Uso

### 1️⃣ Primera vez usando el sistema

**Ruta recomendada**:
1. Leer: [GLUE_BUILD_QUICKSTART.md](GLUE_BUILD_QUICKSTART.md)
2. Ejecutar: `.\test-glue-build.ps1`
3. Ejecutar: `.\build-glue-deps.ps1`
4. Revisar output en `build/`

### 2️⃣ Ya buildé, ahora necesito deploy a AWS

**Ruta recomendada**:
1. Leer: [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) → Fase 3
2. Upload S3: `aws s3 cp build\glue-dependencies.zip s3://...`
3. Configurar job usando [examples/glue-job-example.json](examples/glue-job-example.json)

### 3️⃣ Build falló, necesito troubleshooting

**Ruta recomendada**:
1. Ver logs: `build/temp/pip_*.log`
2. Leer: [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) → Troubleshooting
3. Leer: [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Troubleshooting
4. Ejecutar con clean: `.\build-glue-deps.ps1 -CleanBuild`

### 4️⃣ Job de Glue falla con ImportError

**Ruta recomendada**:
1. Verificar CloudWatch logs: `/aws-glue/jobs/output`
2. Leer: [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Security Notes → Shared Libraries
3. Verificar job configuration: `--extra-py-files` path correcto
4. Re-verificar local: `.\build-glue-deps.ps1` (debe pasar verify)

### 5️⃣ Quiero agregar más dependencias

**Ruta recomendada**:
1. Editar: `requirements-glue.txt`
2. Rebuild: `.\build-glue-deps.ps1`
3. Verificar: `build/manifest.txt`
4. Re-deploy: `aws s3 cp build\glue-dependencies.zip ...`

### 6️⃣ Quiero entender la arquitectura

**Ruta recomendada**:
1. Leer: [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Architecture
2. Ver diagrama: [WORKFLOW_DIAGRAM.txt](WORKFLOW_DIAGRAM.txt)
3. Explorar: `Dockerfile.glue-builder` y `build_glue_libs.sh`

---

## 🔍 Búsqueda Rápida

### ¿Cómo hacer X?

| Pregunta | Respuesta |
|----------|-----------|
| ¿Cómo instalo Docker? | [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) → Pre-requisitos |
| ¿Cómo funciona el REPL loop? | [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → verify_glue_deps.py |
| ¿Cómo optimizo el tamaño del ZIP? | [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Troubleshooting → ZIP too large |
| ¿Cómo agrego eccodes shared libraries? | [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Security Notes → Shared Libraries |
| ¿Cómo configuro un Glue Job? | [examples/README.md](examples/README.md) → Usage |
| ¿Cómo subo a S3? | [GLUE_BUILD_QUICKSTART.md](GLUE_BUILD_QUICKSTART.md) → Deploy to AWS |
| ¿Cuánto tarda el build? | [WORKFLOW_DIAGRAM.txt](WORKFLOW_DIAGRAM.txt) → TIEMPOS ESTIMADOS |
| ¿Qué paquetes se incluyen? | `build/manifest.txt` (después de build) |

### ¿Qué significa X?

| Término | Explicación |
|---------|-------------|
| REPL loop | [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → verify_glue_deps.py |
| Binary compatibility | [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Architecture |
| Fail fast | [BUILD_SYSTEM_SUMMARY.txt](BUILD_SYSTEM_SUMMARY.txt) → CONCEPTOS CLAVE |
| Manylinux | [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → build_glue_libs.sh |
| --extra-py-files | [examples/README.md](examples/README.md) → Usage |

---

## 📊 Flujos de Trabajo Comunes

### Flujo 1: Desarrollo Iterativo

```
1. Editar código de Glue Job local
2. Actualizar requirements-glue.txt (si hay nuevas deps)
3. .\build-glue-deps.ps1 -SkipBuild  (rápido si no cambió deps)
4. aws s3 cp build\glue-dependencies.zip s3://...
5. aws glue start-job-run --job-name my-job
6. Revisar CloudWatch logs
7. GOTO 1
```

### Flujo 2: Primera Implementación

```
1. Leer GLUE_BUILD_QUICKSTART.md
2. Preparar requirements-glue.txt
3. .\test-glue-build.ps1
4. .\build-glue-deps.ps1
5. aws s3 cp build\glue-dependencies.zip s3://...
6. Editar examples/glue-job-example.json
7. aws glue create-job --cli-input-json file://examples/glue-job-example.json
8. aws glue start-job-run --job-name my-job
9. Verificar CloudWatch logs
```

### Flujo 3: Troubleshooting

```
1. Identificar error (build vs runtime)
   
   Si error en build:
   2a. Ver build/temp/pip_*.log
   3a. Leer IMPLEMENTATION_CHECKLIST.md → Troubleshooting
   4a. .\build-glue-deps.ps1 -CleanBuild
   
   Si error en Glue:
   2b. Ver CloudWatch /aws-glue/jobs/output
   3b. Verificar --extra-py-files path
   4b. Verificar local verify pasó
   5b. Leer docs/GLUE_DEPENDENCY_BUILD.md → Security Notes
```

---

## 🎓 Recursos de Aprendizaje

### Para Principiantes

1. **¿Qué es AWS Glue?**
   - [AWS Glue Documentation](https://docs.aws.amazon.com/glue/)
   - [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Overview

2. **¿Por qué necesito Docker?**
   - [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → The Problem
   - [BUILD_SYSTEM_SUMMARY.txt](BUILD_SYSTEM_SUMMARY.txt) → PROBLEMA RESUELTO

3. **¿Cómo empiezo?**
   - [GLUE_BUILD_QUICKSTART.md](GLUE_BUILD_QUICKSTART.md)
   - [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md)

### Para Usuarios Avanzados

1. **Arquitectura del Sistema**
   - [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Architecture
   - `Dockerfile.glue-builder` (código fuente)
   - `build_glue_libs.sh` (código fuente)

2. **Optimización y Seguridad**
   - [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Security Notes
   - [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Expected Package Sizes

3. **Customización**
   - Modificar `Dockerfile.glue-builder` para otras librerías
   - Ajustar `build_glue_libs.sh` para optimización específica
   - Extender `verify_glue_deps.py` con tests custom

---

## 🆘 Obtener Ayuda

### Problemas Comunes

| Problema | Solución Rápida | Doc Completa |
|----------|-----------------|--------------|
| Docker not running | Iniciar Docker Desktop | [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) → Troubleshooting |
| eccodes compilation fails | Aumentar memoria Docker a 4GB+ | [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Troubleshooting |
| Import fails pre-optimization | Ver `build/temp/pip_*.log` | [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) → Troubleshooting |
| libeccodes.so not found | Copiar shared libs al ZIP | [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Security Notes |
| ZIP too large | Más optimización en build script | [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) → Troubleshooting |

### Debugging Steps

1. **Build Issues**: Ver `build/temp/pip_*.log`
2. **Runtime Issues**: Ver CloudWatch `/aws-glue/jobs/output`
3. **Verificación Local**: Ejecutar `verify_glue_deps.py` standalone
4. **Clean Build**: `.\build-glue-deps.ps1 -CleanBuild`

---

## 📋 Checklist de Validación

Antes de considerar el sistema "funcionando":

- [ ] `.\test-glue-build.ps1` pasa todos los checks
- [ ] `.\build-glue-deps.ps1` completa sin errores
- [ ] `build/glue-dependencies.zip` existe (~40-50 MB)
- [ ] `build/manifest.txt` lista paquetes esperados
- [ ] Verification logs muestran todos ✓
- [ ] ZIP subido a S3 exitosamente
- [ ] Glue Job configurado con `--extra-py-files`
- [ ] Job test ejecuta sin `ImportError`
- [ ] CloudWatch logs confirman imports exitosos

---

## 🚀 Siguientes Pasos

Después de tener el sistema funcionando:

1. **Implementar lógica ETL**
   - Ver [examples/glue-job-example.py](examples/glue-job-example.py)
   - Procesar GRIB files con xarray/cfgrib
   - Convertir a Parquet

2. **Configurar automatización**
   - AWS Glue Triggers (schedules, event-based)
   - AWS Step Functions (orchestration)
   - CloudWatch Events

3. **Optimizar performance**
   - Ajustar workers, memory, capacity
   - Partitioning de datos
   - Caching de dependencias

4. **Monitoreo**
   - CloudWatch Metrics
   - Glue Job Metrics Dashboard
   - Alertas de errores

---

## 📚 Todos los Archivos de Documentación

```
📦 chucaw-glue-scripts/
├─ 📄 INDEX.md                          ← ESTÁS AQUÍ
├─ 📄 GLUE_BUILD_QUICKSTART.md          ← Quick start (3 min)
├─ 📄 IMPLEMENTATION_CHECKLIST.md       ← Checklist paso a paso
├─ 📄 BUILD_SYSTEM_SUMMARY.txt          ← Resumen ejecutivo
├─ 📄 WORKFLOW_DIAGRAM.txt              ← Diagrama visual del flujo
├─ 📁 docs/
│  └─ 📄 GLUE_DEPENDENCY_BUILD.md       ← Documentación completa
└─ 📁 examples/
   ├─ 📄 README.md                      ← Guía de ejemplos
   ├─ 📄 glue-job-example.json          ← Job definition
   └─ 📄 glue-job-example.py            ← Glue script
```

---

**Última actualización**: 2026-04-03  
**Sistema**: AWS Glue 5.0 Dependency Build System  
**Versión**: 1.0

---

**¿Listo para empezar?** 👉 [GLUE_BUILD_QUICKSTART.md](GLUE_BUILD_QUICKSTART.md)
