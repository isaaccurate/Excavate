import os
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from knowledge_assistant.contracts import CorpusStore
from knowledge_assistant.storage import SQLiteDocumentStore

if TYPE_CHECKING:
    from knowledge_assistant.aws_storage import AWSDocumentStore


class StorageConfigurationError(ValueError):
    """The selected backend needs additional configuration."""


@contextmanager
def open_document_store(
    database: Path | None, *, create: bool = False
) -> Iterator[CorpusStore]:
    backend = os.environ.get("KNOWLEDGE_ASSISTANT_STORAGE", "sqlite")
    if backend == "sqlite":
        if database is None:
            raise StorageConfigurationError(
                "set KNOWLEDGE_ASSISTANT_DB to enable answering"
            )
        if not create and not database.is_file():
            raise StorageConfigurationError("database does not exist")
        store = SQLiteDocumentStore(database)
        try:
            yield store
        finally:
            store.engine.dispose()
        return

    if backend != "aws":
        raise StorageConfigurationError(
            "KNOWLEDGE_ASSISTANT_STORAGE must be sqlite or aws"
        )
    with open_aws_document_store() as store:
        yield store


@contextmanager
def open_aws_document_store() -> Iterator["AWSDocumentStore"]:
    if os.environ.get("KNOWLEDGE_ASSISTANT_STORAGE") != "aws":
        raise StorageConfigurationError(
            "this command requires KNOWLEDGE_ASSISTANT_STORAGE=aws"
        )
    bucket = os.environ.get("KNOWLEDGE_ASSISTANT_S3_BUCKET", "").strip()
    table = os.environ.get("KNOWLEDGE_ASSISTANT_DYNAMODB_TABLE", "").strip()
    if not bucket or not table:
        raise StorageConfigurationError(
            "set KNOWLEDGE_ASSISTANT_S3_BUCKET and KNOWLEDGE_ASSISTANT_DYNAMODB_TABLE"
        )
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        from knowledge_assistant.aws_storage import AWSDocumentStore
    except ImportError:
        raise StorageConfigurationError(
            "install the aws extra to use AWS storage"
        ) from None

    try:
        session = boto3.Session()
        with (
            closing(session.client("s3")) as s3,
            closing(session.client("dynamodb")) as ddb,
        ):
            yield AWSDocumentStore(s3, ddb, bucket=bucket, table=table)
    except (BotoCoreError, ClientError):
        raise OSError("AWS document storage operation failed") from None
