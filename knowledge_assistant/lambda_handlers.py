import os
from contextlib import closing

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from mangum import Mangum

from knowledge_assistant.answer_service import AnswerConfigurationError
from knowledge_assistant.answering import AnswerResult
from knowledge_assistant.api import answer_from_environment, create_app
from knowledge_assistant.store_config import open_aws_document_store


def cloud_answer(question: str) -> AnswerResult:
    secret_arn = os.environ.get("KNOWLEDGE_ASSISTANT_OPENAI_SECRET_ARN")
    if not secret_arn:
        return answer_from_environment(question)
    try:
        with closing(boto3.client("secretsmanager")) as client:
            secret = client.get_secret_value(SecretId=secret_arn).get("SecretString")
    except (BotoCoreError, ClientError):
        raise AnswerConfigurationError("could not read the model credential") from None
    if not secret or not secret.strip():
        raise AnswerConfigurationError("the model credential must be a nonblank string")
    return answer_from_environment(question, api_key=secret)


api_handler = Mangum(create_app(cloud_answer), lifespan="off")


def cleanup_handler(event: dict, context: object) -> dict[str, int]:
    with open_aws_document_store() as store:
        purged = store.cleanup()
    print(f"Cleanup completed. Purged notes: {purged}")
    return {"purged_notes": purged}
