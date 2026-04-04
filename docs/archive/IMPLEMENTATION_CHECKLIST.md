# ✅ Checklist de Implementación - AWS Glue Build System

Este checklist te guía paso a paso para compilar, verificar y desplegar tus dependencias Python en AWS Glue 5.0.

---

## 📋 Pre-requisitos

- [ ] Docker Desktop instalado y corriendo
- [ ] PowerShell 5.1+ (incluido en Windows 10/11)
- [ ] AWS CLI configurado (para deployment)
- [ ] Acceso a cuenta AWS con permisos Glue + S3

---

## 🛠️ Fase 1: Preparación Local

### 1.1 Verificar Entorno

```powershell
# Verificar Docker
docker --version
docker info

# Verificar PowerShell
$PSVersionTable.PSVersion

# Verificar AWS CLI (opcional, necesario solo para deployment)
aws --version
aws sts get-caller-identity
```

- [ ] Docker funciona correctamente
- [ ] PowerShell disponible
- [ ] AWS CLI configurado (si vas a desplegar)

### 1.2 Revisar Dependencias

Edita `requirements-glue.txt` con tus dependencias:

```
xarray==2024.2.0
cfgrib==0.9.14.1
eccodes==2.42.0
eccodeslib==2.42.0
```

- [ ] `requirements-glue.txt` contiene todas las dependencias necesarias
- [ ] Versiones especificadas (evita `latest`)
- [ ] Solo incluye paquetes NO disponibles en baseline de Glue 5.0

**Tip**: Ver `lista_de_glue50.txt` para paquetes ya incluidos en Glue.

---

## 🐳 Fase 2: Compilación

### 2.1 Test Previo (Opcional)

```powershell
.\test-glue-build.ps1
```

Este script verifica:
- ✓ Docker está corriendo
- ✓ Archivos necesarios existen
- ✓ Base image de AWS Glue disponible

- [ ] Pre-flight check pasó exitosamente
- [ ] Todos los archivos requeridos encontrados

### 2.2 Primera Compilación

```powershell
.\build-glue-deps.ps1
```

**Tiempo estimado**: 5-10 minutos (primera vez)

El script:
1. Construye imagen Docker con AWS Glue 5.0 + toolchain
2. Compila eccodes desde fuente (~3-4 min)
3. Instala dependencias Python
4. **Verifica imports** antes de optimizar
5. Optimiza package (elimina cache, tests)
6. Crea `build/glue-dependencies.zip`
7. **Verifica imports** desde ZIP final

- [ ] Build completó sin errores
- [ ] Archivo `build/glue-dependencies.zip` creado
- [ ] Tamaño del ZIP: ~40-50 MB (verificar razonable)
- [ ] Verificación de imports pasó (todos ✓)

**Si falla**: Ver sección de Troubleshooting más abajo.

### 2.3 Verificar Output

```powershell
# Ver contenido del ZIP
Expand-Archive -Path build\glue-dependencies.zip -DestinationPath build\test-extract
ls build\test-extract

# Ver manifest
cat build\manifest.txt

# Cleanup
Remove-Item -Path build\test-extract -Recurse -Force
```

- [ ] ZIP contiene módulos Python (xarray/, cfgrib/, etc.)
- [ ] Manifest lista todos los paquetes instalados
- [ ] No hay archivos `.pyc`, `__pycache__`, `.dist-info`

---

## 🚀 Fase 3: Deployment a AWS

### 3.1 Upload a S3

```bash
# Crear bucket si no existe
aws s3 mb s3://mi-bucket-glue-artifacts --region us-east-1

# Subir ZIP
aws s3 cp build/glue-dependencies.zip s3://mi-bucket-glue-artifacts/libs/

# Verificar upload
aws s3 ls s3://mi-bucket-glue-artifacts/libs/
```

- [ ] ZIP subido a S3 exitosamente
- [ ] Path S3 anotado: `s3://________________/libs/glue-dependencies.zip`

### 3.2 Crear/Actualizar Glue Job

**Opción A: Consola AWS**

1. AWS Glue → ETL jobs → Create job
2. Configurar:
   - **Glue version**: 5.0
   - **Language**: Python 3
   - **Worker type**: G.1X (o según necesidad)
   - **Script path**: s3://tu-bucket/scripts/tu_script.py
3. **Advanced properties** → **Python library path**:
   - Agregar: `s3://mi-bucket-glue-artifacts/libs/glue-dependencies.zip`

**Opción B: AWS CLI**

```bash
# Editar examples/glue-job-example.json con tus valores
# Luego:
aws glue create-job --cli-input-json file://examples/glue-job-example.json
```

- [ ] Glue Job creado
- [ ] `--extra-py-files` apunta a ZIP en S3
- [ ] Versión Glue: 5.0
- [ ] Script de job cargado

### 3.3 Test en AWS Glue

Usa el script de ejemplo o crea uno simple:

```python
# test_deps.py
import sys
from awsglue.context import GlueContext
from pyspark.context import SparkContext

sc = SparkContext()
glueContext = GlueContext(sc)
logger = glueContext.get_logger()

# Verificar imports
import xarray as xr
import cfgrib
import eccodes

logger.info(f"✓ xarray {xr.__version__}")
logger.info(f"✓ cfgrib {cfgrib.__version__}")
logger.info(f"✓ eccodes {eccodes.__version__}")

logger.info("SUCCESS: All dependencies loaded!")
```

Ejecutar job:

```bash
aws glue start-job-run --job-name mi-test-job
```

Monitorear logs:

```bash
# Ver runs
aws glue get-job-runs --job-name mi-test-job --max-results 1

# CloudWatch logs
# AWS Console → CloudWatch → Log groups → /aws-glue/jobs/output
```

- [ ] Job ejecutó exitosamente
- [ ] Logs muestran imports exitosos (✓)
- [ ] No hay `ImportError` o `ModuleNotFoundError`

---

## 🔧 Troubleshooting

### ❌ Docker build fails

**Error**: `failed to solve: failed to fetch`

**Solución**:
1. Verificar conexión internet
2. Reiniciar Docker Desktop
3. Retry con `--no-cache`:
   ```powershell
   docker build --no-cache -f Dockerfile.glue-builder -t glue-builder:latest .
   ```

### ❌ eccodes compilation fails

**Error**: `CMake Error` durante build

**Solución**:
1. Verificar que Dockerfile.glue-builder tiene `cmake` instalado
2. Aumentar memoria de Docker (Settings → Resources → Memory: 4GB+)

### ❌ Import verification fails (pre-optimization)

**Error**: `ImportError: No module named 'xarray'`

**Solución**:
1. Verificar `requirements-glue.txt` tiene versiones correctas
2. Ver logs en `build/temp/pip_*.log`
3. Intentar con `--no-binary` para forzar source compilation

### ❌ Import fails en AWS Glue

**Error**: `ImportError: libeccodes.so.0: cannot open shared object file`

**Solución**: eccodes shared libraries no están en ZIP.

1. Modificar `build_glue_libs.sh`:
   ```bash
   # Después de pip install, agregar:
   mkdir -p "${SITE_PACKAGES_DIR}/lib"
   cp /usr/local/lib/libeccodes.so* "${SITE_PACKAGES_DIR}/lib/"
   ```

2. En script de Glue, agregar al inicio:
   ```python
   import os
   os.environ['LD_LIBRARY_PATH'] = '/tmp/lib:' + os.environ.get('LD_LIBRARY_PATH', '')
   ```

3. Rebuild y re-deploy

### ❌ ZIP too large (>250MB)

**Solución**: Optimizar más agresivamente

Editar `build_glue_libs.sh`, agregar:
```bash
# Después de optimización existente
find "${SITE_PACKAGES_DIR}" -name "*.so" -exec strip {} \;
find "${SITE_PACKAGES_DIR}" -type d -name "docs" -exec rm -rf {} +
find "${SITE_PACKAGES_DIR}" -type d -name "examples" -exec rm -rf {} +
```

---

## 📚 Recursos Adicionales

- [GLUE_BUILD_QUICKSTART.md](GLUE_BUILD_QUICKSTART.md) - Inicio rápido
- [docs/GLUE_DEPENDENCY_BUILD.md](docs/GLUE_DEPENDENCY_BUILD.md) - Documentación completa
- [examples/README.md](examples/README.md) - Ejemplos de jobs
- [AWS Glue Python Shell Docs](https://docs.aws.amazon.com/glue/latest/dg/add-job-python.html)

---

## ✅ Resumen Final

Una vez completado este checklist:

- ✅ Dependencias compiladas en entorno compatible con Glue
- ✅ Verificación local pasó (sin necesidad de deploy para testing básico)
- ✅ ZIP optimizado y subido a S3
- ✅ Glue Job configurado y testeado
- ✅ Logs confirman imports exitosos en AWS

**Próximos pasos**:
- Desarrollar lógica de tu ETL (procesar GRIB, conversión, etc.)
- Configurar triggers/schedules para jobs
- Monitorear métricas en CloudWatch
- Optimizar performance (workers, memory, partitioning)

---

**¿Problemas?** Revisa:
1. Logs de build: `build/temp/pip_*.log`
2. CloudWatch logs: `/aws-glue/jobs/output`
3. Documentación: `docs/GLUE_DEPENDENCY_BUILD.md`

**¿Todo funcionando?** 🎉 
¡Tu pipeline de Glue está listo para procesar datos climáticos!
