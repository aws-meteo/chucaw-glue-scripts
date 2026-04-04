# Archivo de Artefactos Agénticos

Los archivos contenidos en este directorio son el subproducto de iteraciones intensivas de pruebas, automatización y scripting ad-hoc durante el proceso de migración de dependencias local y validación de `pyarrow` con AWS Glue 5.0.

Fueron guardados aquí (archivados) en lugar de eliminarse por si en el futuro se necesita referenciar algún "snippet" de cómo se emuló WSL, se corrieron batches experimentales o se extrajeron planes preliminares de trabajo.

## Tipos de archivos archivados:
- **Scripts de Monkey Patch (`fixer*.py`, `patch*.py`)**: Automatizaciones rápidas para buscar/reemplazar contenidos en medio de migraciones sin abrir editores.
- **Runners Ad-hoc (`*test.sh`, `runner*.sh`, `*.py` basura)**: Ejecutores para validar iteraciones de dependencias offline de manera rápida en contenedores separados del CI.
- **Logs y Planes Provisionales**: Archivos `.txt` y `.md` capturando el output de terminal o resumiendo planes transitorios (`0404_RESUMEN_MIGRACION`, `boulder.json`) para el agente.

Estos archivos **no son esenciales** para el funcionamiento del código de preprocesamiento, de las de definiciones estáticas de Glue ni de la arquitectura fundamental del proyecto de datos. Su uso a futuro está desaconsejado, sirven meramente como bitácora histórica.
