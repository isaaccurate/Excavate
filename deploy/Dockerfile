FROM public.ecr.aws/lambda/python:3.12

COPY pyproject.toml ${LAMBDA_TASK_ROOT}/
COPY knowledge_assistant ${LAMBDA_TASK_ROOT}/knowledge_assistant
RUN python -m pip install --no-cache-dir --target "${LAMBDA_TASK_ROOT}" '.[aws,retrieval,lambda]'

CMD ["knowledge_assistant.lambda_handlers.api_handler"]
