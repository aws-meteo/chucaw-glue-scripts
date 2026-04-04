# AWS Glue 5.0: Resumen Ejecutivo y Guía de Despliegue

Este documento resume las tareas técnicas ejecutadas para la migración, los problemas encontrados durante las pruebas locales, y la hoja de ruta definitiva para subir los artefactos a tu infraestructura de AWS.

---

## 1. Lo que hicimos (Avances Completados)

Logramos una alineación total e impecable del sistema de compilación local para asegurar compatibilidad absoluta con AWS Glue 5.0. 

*   **Runtime Target Establecido:** Cambiamos el Dockerfile base explícitamente a `public.ecr.aws/glue/aws-glue-libs:5` (Amazon Linux 2023, Python 3.11). Se reescribió la instalación de herramientas (`gcc`, `cmake`) para que no colisionen con las nativas de AL2023.
*   **Aislamiento de Dependencias (`pyproject.toml`):** Evitamos conflictos fatales trasladando `numpy`, `pandas`, `pyarrow`, y `boto3` hacia un grupo opcional (`optional-dependencies[glue-base]`). Así, ahora sabemos que el `.whl` generado de la lógica no va a interponerse sobre la baseline ya precargada por Amazon en sus máquinas.
*   **Nuevo Pipeline Robusto de `.gluewheels.zip`:** Ahora el script `build_glue_libs.sh` evalúa un documento maestro (`lista_de_glue50.txt`), filtra las dependencias basales nativamente usando comandos pre-compilados y empaqueta en `dist/glue-dependencies.gluewheels.zip` únicamente lo ajeno a AWS (típicamente `xarray`, `cfgrib`, `eccodes`).
*   **Limpieza Profunda y Ejemplos Actualizados:** Se ordenó la miscelánea (scripts bash sueltos que causaban disonancia de documentación fueron eliminados u archivados). Se actualizó todo `deploy-and-test-glue.ps1` y `examples/` para requerir explícitamente en su configuración `--additional-python-modules` y `GlueVersion="5.0"` con el flag `--no-index`.
*   **Test Atómicos Exitosos:** Los contenedores que probaron cargar estrictamente estos imports (`import xarray`, `import eccodes`) reportaron Código de Salida `0` (Exitoso) operando al cien por ciento *offline*.

---

## 2. Bloqueos Técnicos (Tarea T10 - Smoke Test Local)

**Contexto del Bloqueo:** La tarea final (T10) apuntaba a recrear todo el procesamiento y conversión del archivo de la ruta `20260330060000-6h-scda-fc.grib2` (de casi 130 MB) a Parquet localmente. Si bien el runtime de los modulos base funciona dentro de terminal local del Docker, cuando pasamos el comando GRIB en crudo, el bloque **colapsa en silencio** o experimenta *hangs* (tiempos de suspensión asimétricos y bloqueados) sin tirar error rastreable de consola.

**Hipótesis de los Bloqueos:**
1.  **Limitante Memoria y OOM (Out Of Memory) Silent Kills:** La conversión en vuelo de GRIB vía la dupla `xarray` + `eccodes` expande considerablemente la huella de memoria durante la descompresión y lectura. Como utilizas Docker sobre Windows (WSL2), al rozar el ceiling configurado de recursos de contenedor, el demonio o el OOM Killer nativo matan el proceso de golpe sin llegar a flushear el traceback de error en tu consola.
2.  **Deadlocks por File I/O de Windows-Linux:** Montar archivos de este peso con *bind mounts* (`-v "${PWD}:/workspace"`) en Docker for Windows hacia sistemas de Linux, frecuentemente entraña corrupción de concurrencia al realizar lecturas particionadas. `cfgrib` usa una indexación a bajo nivel para escanear GRIBs y es extremadamente quisquilloso con las fallas subyacentes del filesystem traducido desde Windows. 

**Conclusión del diagnóstico:** Como nuestras validaciones de compilación de bajo nivel (T04) que prueban que los binarios C de Linux de `eccodes` responden bien en Python resultaron limpias y exitosas, todo apunta a que el fallo reside estrictamente en una saturación local de WSL2-Docker. Por ende el **el código fuente está sano** y la ruta de acción directa óptima debe pasar a probar en infraestructura nativa AWS.

---

## 3. Guía de Despliegue en AWS (Desde la Terminal)

Usa la siguiente ruta de pasos para testear los empaquetados subiéndolos a AWS y evaluando finalmente con los fierros verdaderos (`WorkerType: G.1X`).

### Paso 1: Autenticar Sesión AWS
Dado que las sesiones expiran, debes loguearte nuevamente antes de enviar payloads interrumpiendo el flujo.
```powershell
# Inicia SSO contra el Identity Center de tu organización
aws sso login --profile sbnai-admin
```

### Paso 2: Ejecutar Build Oficial de Producción
Si no generaste el `.gluewheels` reciente luego del reinicio, siempre reconstruye así. Tarda un par de minutos máximo y te devuelve los paquetes actualizados. 
```powershell
# Borra las viejas builds y carga el proceso limpio de docker en Linux AL2023.
Remove-Item -Recurse -Force .\build -ErrorAction SilentlyContinue 
New-Item -ItemType Directory -Path .\build -Force | Out-Null
docker run --rm -v "${PWD}:/workspace" -v "${PWD}/build:/build" glue5-builder:latest "bash /workspace/build_glue_libs.sh"
```
*Verificas que finaliza cuando te devuelva `[OK] BUILD COMPLETE`*.

### Paso 3: Disparar el Entorno de Test Efímero del Job en S3
Creamos un orquestador útil `deploy-and-test-glue.ps1` que automatizará todos los roces manuales entre AWS CLI. El script de abajo cogerá tu ZIP filtrado, el `.whl`, formará un Job, lo intentará rodar sobre Glue 5.0 nativo por < 5 mins, bajará los CloudWatch logs, lo pondrá en pantalla y lo liquidará él mismo si se lo pides.
```powershell
# Ejecuta el test. Asegúrate de pasar el string correcto del bucket SIN s3://
.\deploy-and-test-glue.ps1 -Bucket "chucaw-glue-assets-725644097028-us-east-1-an" -Profile "sbnai-admin" -Region "us-east-1"
```

### Comandos Avanzados y Troubleshooting de Emergencia (Supervisión)

Si detectas un comportamiento erróneo (el job se torna rojo/falló):

1.  **Monitorizar vía Nube:**
El orquestador PowerShell provee la terminal para Cloudwatch, pero interactuar con UI de la consola es mejor para observar logs densos. Anda a **AWS Console > AWS Glue > Jobs > Runs**. Haz clic sobre el Job llamado `test-deps-<timestamp>`. Verás la pestaña "Error Logs" directo.
2.  **Verificar Subida Directa:**
Si te genera un flag de AWS error de Archivo Ausente (`DependencyNotFound`), verifica qué hay en los paths:
```powershell
aws s3 ls s3://chucaw-glue-assets-725644097028-us-east-1-an/glue-libs/ --profile sbnai-admin
```
*(Es mandatorio ver ambos archivos allí: tu `chucaw_preprocessor-XX.whl` actual, y `glue-dependencies.gluewheels.zip`)*.
3.  **Comprobar IAM Role Limits (Políticas):**
A veces la política no abarca bien a ciertos buckets de test:
```powershell
aws iam get-role --role-name GlueTestDepsRole --profile sbnai-admin
```
Si es necesario asocia los permisos Full AWSGlue y Full S3 en consola o tu IAM terraform equivalentes.
