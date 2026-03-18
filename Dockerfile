# Usamos una versión ligera y oficial de Python
FROM python:3.12-slim

# 1. Instalar dependencias del sistema operativo (CRÍTICO para cfgrib)
RUN apt-get update && apt-get install -y \
    libeccodes-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Configurar el directorio de trabajo dentro del contenedor
WORKDIR /app

# 3. Copiar solo el archivo de requerimientos primero (optimiza la caché de Docker)
COPY requirements.txt .

# 4. Instalar las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiar nuestro script y código
COPY src/ /app/src/

# 6. Comando por defecto al encender el contenedor
# (Si luego usamos AWS Lambda, cambiaremos esto ligeramente)
CMD ["python", "src/pangu_prep_pipeline.py"]