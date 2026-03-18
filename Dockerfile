FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install --no-cache-dir eccodes -r requirements.txt

COPY src/ ${LAMBDA_TASK_ROOT}/src/

CMD [ "src.pangu_prep_pipeline.lambda_handler" ]