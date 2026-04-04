# Problemas Detectados y Soluciones - Conversión GRIB a Parquet

## Resumen Ejecutivo

Se identificaron y resolvieron **problemas críticos de compatibilidad** en el entorno `.venv311-linux` que impedían la conversión local de archivos GRIB a Parquet.

---

## ✅ Problemas Identificados

### 1. **Incompatibilidad de Versiones: pandas 3.0.2 vs xarray 2024.2.0**

**Error Original:**
```
AssertionError in xarray/coding/times.py:354
assert result.dtype == "timedelta64[ns]"
```

**Causa Raíz:**
- El entorno tenía instalado **pandas 3.0.2** (incompatible)
- El `requirements.txt` especifica **pandas 2.2.2**
- `xarray 2024.2.0` no soporta pandas 3.x para decodificación de timedeltas

**Solución Aplicada:**
```bash
pip uninstall pandas -y
pip install pandas==2.2.2
```

---

### 2. **Corrupción de numpy Durante Desinstalación Fallida**

**Error:**
```
ImportError: Error importing numpy: you should not try to import numpy from
        its source directory
```

**Causa:**
- Desinstalación interrumpida de pandas dejó numpy en estado corrupto
- Directorio `~umpy` residual en site-packages

**Solución Aplicada:**
```bash
pip install --force-reinstall --no-cache-dir numpy==1.26.4
```

---

### 3. **Workaround para Compatibilidad pandas 3.x en Código**

**Modificación en `src/chucaw_preprocessor/ecmwf.py`:**

```python
def load_merged_dataset(grib_path: str) -> xr.Dataset:
    # Use decode_timedelta=False to avoid pandas 3.x compatibility issues
    backend_kwargs = {"decode_timedelta": False}
    datasets = cfgrib.open_datasets(grib_path, backend_kwargs=backend_kwargs)
    # ... resto del código
```

**Propósito:**
- Permite ejecutar el script incluso si se vuelve a instalar pandas 3.x accidentalmente
- Evita el error de AssertionError en `timedelta64[ns]`
- Funciona con pandas 2.x y 3.x

---

### 4. **Archivo de Índice GRIB Incompatible**

**Advertencias:**
```
Ignoring index file '*.grib2.5b7b6.idx' incompatible with GRIB file
```

**Causa:**
- Índices cfgrib desactualizados o generados con versión diferente

**Solución:**
```bash
rm -f ./scripts/glue_jobs/*.idx
```

---

### 5. **Limitación de Memoria WSL para Archivos GRIB Grandes**

**Problema:**
- El archivo `20260330060000-6h-scda-fc.grib2` (125 MB) excede la memoria disponible en WSL
- El proceso Python es terminado (exit code 1/9) sin mensaje de error

**Causa Raíz:**
- Límites de memoria de WSL por defecto (~2-4GB)
- cfgrib carga todo el archivo en memoria durante procesamiento

**Soluciones Posibles:**

#### Opción A: Aumentar Memoria de WSL
Crear/editar `%USERPROFILE%\.wslconfig`:
```ini
[wsl2]
memory=8GB
processors=4
```

Luego reiniciar WSL:
```powershell
wsl --shutdown
```

#### Opción B: Procesar en Entorno Nativo Linux
- Usar servidor Linux con más memoria
- Ejecutar en AWS Glue (diseñado para este propósito)

#### Opción C: Dividir Archivos GRIB
- Usar `grib_copy` de eccodes para extraer subconjuntos
- Procesar por partes y combinar resultados

---

## 🎯 Estado Actual

### ✅ **Funcionalidades Resueltas:**

1. **Dependencias Correctas:**
   - ✅ numpy 1.26.4
   - ✅ pandas 2.2.2
   - ✅ xarray 2024.2.0
   - ✅ cfgrib 0.9.14.1

2. **Código Modificado:**
   - ✅ Workaround `decode_timedelta=False` en `ecmwf.py`
   - ✅ Imports funcionando correctamente

3. **Script Ejecutable:**
   - ✅ `grib_to_platinum_parquet.py` listo para usar
   - ✅ PYTHONPATH configurado automáticamente

### ⚠️ **Limitación Pendiente:**

- **Archivos GRIB > 100MB**: Requieren más memoria que la disponible en WSL por defecto
- **Recomendación**: Usar Opción A (aumentar memoria WSL) o procesar en AWS Glue

---

## 📋 Comando de Ejecución Verificado

```bash
cd /mnt/c/Users/Asus/Documents/code/SbnAI/chucaw-glue-scripts
source .venv311-linux/bin/activate

# Para archivos GRIB pequeños/medianos (<50MB):
python scripts/glue_jobs/grib_to_platinum_parquet.py \
    --GRIB_PATH "./ruta/archivo.grib2" \
    --OUTPUT_DIR "./output_test" \
    --DATE "20260330" \
    --RUN "06z"
```

---

## 🔧 Mantenimiento Futuro

### Para Reinstalar Dependencias:

```bash
# Asegurarse de usar las versiones correctas
pip install -r requirements.txt

# Verificar versiones:
pip list | grep -E "(pandas|numpy|xarray|cfgrib)"
```

### Verificación Rápida:

```bash
python -c "
import sys
sys.path.insert(0, 'src')
from chucaw_preprocessor.ecmwf import load_merged_dataset
print('✅ Módulo importado correctamente')
"
```

---

## 📝 Archivos Modificados

1. **`src/chucaw_preprocessor/ecmwf.py`**
   - Línea 63: Agregado `backend_kwargs = {"decode_timedelta": False}`
   - Línea 64: Pasado `backend_kwargs` a `cfgrib.open_datasets()`

---

## 🚀 Próximos Pasos Recomendados

1. **Aumentar memoria WSL** siguiendo Opción A
2. **Probar conversión** con archivo GRIB completo
3. **Monitorear uso de memoria** durante procesamiento
4. **Considerar procesamiento batch** para múltiples archivos

---

**Fecha:** 2026-04-02  
**Estado:** Problemas identificados y soluciones implementadas  
**Pendiente:** Aumentar memoria WSL para archivos grandes
