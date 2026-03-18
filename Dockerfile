FROM public.ecr.aws/lambda/python:3.13

# 1. Instalar eccodes (Amazon Linux usa dnf, no apt-get)
RUN dnf install -y eccodes && dnf clean all

# 2. Copiar e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copiar tu código al directorio raíz de Lambda
COPY src/ ${LAMBDA_TASK_ROOT}/src/

# 4. Handler: carpeta.archivo.función
CMD [ "src.pangu_prep_pipeline.lambda_handler" ]