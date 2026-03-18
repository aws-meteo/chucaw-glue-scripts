FROM public.ecr.aws/lambda/python:3.13

# eccodes se instala vía pip — trae la librería C incluida, no necesita dnf
COPY requirements.txt .
RUN pip install --no-cache-dir eccodes -r requirements.txt

COPY src/ ${LAMBDA_TASK_ROOT}/src/

CMD [ "src.pangu_prep_pipeline.lambda_handler" ]