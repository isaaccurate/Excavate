import time
from contextlib import closing
from hashlib import sha256
from uuid import uuid4

from botocore.client import BaseClient
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field

from knowledge_assistant.contracts import Document

RECOVERY_SECONDS = 7 * 24 * 60 * 60


class StoredNote(BaseModel):
    path: str
    version: str
    object_key: str
    retired: dict[str, int] = Field(default_factory=dict)
    recover_until: int | None = None
    purging: bool = False


class AWSDocumentStore:
    """Store immutable document versions in S3 with current pointers in DynamoDB."""

    def __init__(
        self, s3: BaseClient, dynamodb: BaseClient, *, bucket: str, table: str
    ) -> None:
        self.s3 = s3
        self.dynamodb = dynamodb
        self.bucket = bucket
        self.table = table

    @staticmethod
    def _key(path: str) -> dict:
        return {"document_id": {"S": sha256(path.encode("utf-8")).hexdigest()}}

    def _get_item(self, path: str) -> dict | None:
        return self.dynamodb.get_item(
            TableName=self.table, Key=self._key(path), ConsistentRead=True
        ).get("Item")

    def _items(self):
        pages = self.dynamodb.get_paginator("scan").paginate(
            TableName=self.table, ConsistentRead=True
        )
        for page in pages:
            yield from page.get("Items", ())

    @staticmethod
    def _decode(item: dict) -> StoredNote:
        if "note" in item:
            return StoredNote.model_validate_json(item["note"]["S"])
        # Records written before recovery used a content hash as the S3 key.
        version = item["version"]["S"]
        return StoredNote(
            path=item["path"]["S"],
            version=version,
            object_key=f"documents/{version}.json",
        )

    @staticmethod
    def _condition(item: dict | None) -> dict:
        if item is None:
            return {"ConditionExpression": "attribute_not_exists(document_id)"}
        if "revision" not in item:
            return {
                "ConditionExpression": "attribute_not_exists(revision) AND #version = :old",
                "ExpressionAttributeNames": {"#version": "version"},
                "ExpressionAttributeValues": {":old": item["version"]},
            }
        return {
            "ConditionExpression": "revision = :old",
            "ExpressionAttributeValues": {":old": item["revision"]},
        }

    def _replace(self, note: StoredNote, previous: dict | None) -> dict | None:
        item = self._key(note.path) | {
            "note": {"S": note.model_dump_json()},
            "revision": {"S": uuid4().hex},
        }
        try:
            self.dynamodb.put_item(
                TableName=self.table, Item=item, **self._condition(previous)
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise
        return item

    def get(self, path: str) -> Document | None:
        item = self._get_item(path)
        if item is None:
            return None
        note = self._decode(item)
        if note.recover_until is not None or note.purging:
            return None
        return self._read_document(note)

    def list_documents(self) -> tuple[Document, ...]:
        notes = (self._decode(item) for item in self._items())
        documents = [
            self._read_document(note)
            for note in notes
            if note.recover_until is None and not note.purging
        ]
        return tuple(sorted(documents, key=lambda document: document.path))

    def _read_document(self, note: StoredNote) -> Document:
        response = self.s3.get_object(Bucket=self.bucket, Key=note.object_key)
        with closing(response["Body"]) as stream:
            payload = stream.read()
        if sha256(payload).hexdigest() != note.version:
            raise OSError("stored document checksum does not match")
        document = Document.model_validate_json(payload)
        if document.path != note.path:
            raise OSError("stored document path does not match")
        return document

    def put(self, document: Document) -> bool:
        previous = self._get_item(document.path)
        note = self._decode(previous) if previous else None
        if note and (note.recover_until is not None or note.purging):
            raise OSError(
                "note is deleted; restore it or wait for cleanup before ingesting"
            )
        payload = document.model_dump_json().encode("utf-8")
        version = sha256(payload).hexdigest()
        if note and version == note.version:
            return False

        # Never reuse a retired key, even when the note reverts to older content.
        # A cleanup worker may already have selected that key for deletion.
        document_id = self._key(document.path)["document_id"]["S"]
        object_key = f"documents/{document_id}/{uuid4().hex}.json"
        self.s3.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=payload,
            ContentType="application/json",
            IfNoneMatch="*",
        )
        retired = (
            note.retired | {note.object_key: int(time.time()) + RECOVERY_SECONDS}
            if note
            else {}
        )
        updated = StoredNote(
            path=document.path, version=version, object_key=object_key, retired=retired
        )
        if self._replace(updated, previous) is None:
            raise OSError("note changed during ingestion; retry the command")
        return True

    def delete(self, path: str) -> bool:
        previous = self._get_item(path)
        if previous is None:
            return False
        note = self._decode(previous)
        if note.recover_until is not None or note.purging:
            return False
        note.recover_until = int(time.time()) + RECOVERY_SECONDS
        if self._replace(note, previous) is None:
            raise OSError("note changed during deletion; retry the command")
        return True

    def restore(self, path: str) -> bool:
        previous = self._get_item(path)
        if previous is None:
            return False
        note = self._decode(previous)
        if (
            note.purging
            or note.recover_until is None
            or note.recover_until <= int(time.time())
        ):
            return False
        note.recover_until = None
        if self._replace(note, previous) is None:
            raise OSError("note changed during restore; retry the command")
        return True

    def cleanup(self) -> int:
        """Purge expired notes and retired payloads. Failed work remains retryable."""
        self._require_unversioned_bucket()
        now = int(time.time())
        purged = 0
        for item in self._items():
            note = self._decode(item)
            if note.purging or (
                note.recover_until is not None and note.recover_until <= now
            ):
                purged += self._purge(note, item)
                continue
            expired = {key for key, deadline in note.retired.items() if deadline <= now}
            if expired:
                for key in sorted(expired):
                    self.s3.delete_object(Bucket=self.bucket, Key=key)
                note.retired = {
                    key: deadline
                    for key, deadline in note.retired.items()
                    if key not in expired
                }
                self._replace(note, item)
        return purged

    def purge(self, path: str) -> bool:
        self._require_unversioned_bucket()
        item = self._get_item(path)
        return self._purge(self._decode(item), item) if item else False

    def _require_unversioned_bucket(self) -> None:
        if self.s3.get_bucket_versioning(Bucket=self.bucket).get("Status"):
            raise OSError("cleanup requires an unversioned S3 bucket")

    def _purge(self, note: StoredNote, item: dict) -> bool:
        # Claim the record before deleting its payload. The revision check
        # prevents a stale scan from deleting a note that was just restored.
        if not note.purging:
            note.purging = True
            item = self._replace(note, item)
            if item is None:
                return False
        for key in (*sorted(note.retired), note.object_key):
            self.s3.delete_object(Bucket=self.bucket, Key=key)
        try:
            self.dynamodb.delete_item(
                TableName=self.table, Key=self._key(note.path), **self._condition(item)
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return True
