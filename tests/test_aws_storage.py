import sys
from contextlib import closing
from hashlib import sha256
from io import BytesIO
from uuid import UUID

import pytest

boto3 = pytest.importorskip("boto3")
from botocore.response import StreamingBody  # noqa: E402
from botocore.stub import Stubber  # noqa: E402

from knowledge_assistant.aws_storage import (  # noqa: E402
    RECOVERY_SECONDS,
    AWSDocumentStore,
    StoredNote,
)
from knowledge_assistant.cli import main  # noqa: E402
from knowledge_assistant.contracts import Chunk, Document  # noqa: E402


@pytest.fixture
def aws():
    session = boto3.Session(
        aws_access_key_id="fake", aws_secret_access_key="fake", region_name="us-west-2"
    )
    with (
        closing(session.client("s3")) as s3,
        closing(session.client("dynamodb")) as dynamodb,
    ):
        with Stubber(s3) as blobs, Stubber(dynamodb) as pointers:
            yield (
                AWSDocumentStore(s3, dynamodb, bucket="excavate-test", table="notes"),
                blobs,
                pointers,
            )
            blobs.assert_no_pending_responses()
            pointers.assert_no_pending_responses()


PATH = "Graphs/note.md"
NOW = 1_800_000_000
BUCKET = {"Bucket": "excavate-test"}
TABLE = {"TableName": "notes"}
KEY = {"document_id": {"S": sha256(PATH.encode()).hexdigest()}}
READ = TABLE | {"Key": KEY, "ConsistentRead": True}
SCAN = TABLE | {"ConsistentRead": True}


def item(note, revision):
    return KEY | {
        "note": {"S": note.model_dump_json()},
        "revision": {"S": UUID(int=revision).hex},
    }


def condition(revision):
    return {
        "ConditionExpression": "revision = :old",
        "ExpressionAttributeValues": {":old": {"S": UUID(int=revision).hex}},
    }


@pytest.fixture
def clock(monkeypatch):
    now = [NOW]
    uuids = iter(UUID(int=n) for n in range(1, 100))
    monkeypatch.setattr("knowledge_assistant.aws_storage.time.time", lambda: now[0])
    monkeypatch.setattr("knowledge_assistant.aws_storage.uuid4", lambda: next(uuids))
    return now


def test_ingest_delete_restore(aws, clock):
    store, blobs, pointers = aws
    document = Document(
        path=PATH,
        digest="digest",
        chunks=(Chunk(id="chunk", heading=("Heading",), text="Body"),),
    )
    payload = document.model_dump_json().encode()
    note = StoredNote(
        path=PATH,
        version=sha256(payload).hexdigest(),
        object_key=f"documents/{KEY['document_id']['S']}/{UUID(int=1).hex}.json",
    )
    active = item(note, 2)
    pointers.add_response("get_item", {}, READ)
    blobs.add_response(
        "put_object",
        {},
        BUCKET
        | {
            "Key": note.object_key,
            "Body": payload,
            "ContentType": "application/json",
            "IfNoneMatch": "*",
        },
    )
    pointers.add_response(
        "put_item",
        {},
        TABLE
        | {"Item": active, "ConditionExpression": "attribute_not_exists(document_id)"},
    )
    assert store.put(document)
    pointers.add_response("get_item", {"Item": active}, READ)
    assert not store.put(document)

    note.recover_until = NOW + RECOVERY_SECONDS
    deleted = item(note, 3)
    pointers.add_response("get_item", {"Item": active}, READ)
    pointers.add_response("put_item", {}, TABLE | {"Item": deleted} | condition(2))
    assert store.delete(PATH)
    pointers.add_response("get_item", {"Item": deleted}, READ)
    assert not store.delete(PATH)
    pointers.add_response("get_item", {"Item": deleted}, READ)
    assert store.get(PATH) is None
    pointers.add_response("scan", {"Items": [deleted]}, SCAN)
    assert store.list_documents() == ()

    clock[0] = note.recover_until - 1
    note.recover_until = None
    restored = item(note, 4)
    pointers.add_response("get_item", {"Item": deleted}, READ)
    pointers.add_response("put_item", {}, TABLE | {"Item": restored} | condition(3))
    assert store.restore(PATH)

    pointers.add_response("scan", {"Items": [], "LastEvaluatedKey": KEY}, SCAN)
    pointers.add_response(
        "scan", {"Items": [restored]}, SCAN | {"ExclusiveStartKey": KEY}
    )
    blobs.add_response(
        "get_object",
        {"Body": StreamingBody(BytesIO(payload), len(payload))},
        BUCKET | {"Key": note.object_key},
    )
    assert store.list_documents() == (document,)


def test_cleanup_resumes_partial_purge(aws, clock):
    from botocore.exceptions import ClientError

    store, blobs, pointers = aws
    note = StoredNote(
        path=PATH,
        version="hash",
        object_key="documents/current.json",
        retired={"documents/retired.json": NOW + 1},
        recover_until=NOW,
    )
    expired = item(note, 9)
    pointers.add_response("get_item", {"Item": expired}, READ)
    assert not store.restore(PATH)
    note.purging = True
    claimed = item(note, 1)

    blobs.add_response("get_bucket_versioning", {}, BUCKET)
    pointers.add_response("scan", {"Items": [expired]}, SCAN)
    pointers.add_response("put_item", {}, TABLE | {"Item": claimed} | condition(9))
    blobs.add_response("delete_object", {}, BUCKET | {"Key": "documents/retired.json"})
    blobs.add_client_error(
        "delete_object",
        "AccessDenied",
        expected_params=BUCKET | {"Key": note.object_key},
    )
    with pytest.raises(ClientError, match="AccessDenied"):
        store.cleanup()

    blobs.add_response("get_bucket_versioning", {}, BUCKET)
    pointers.add_response("scan", {"Items": [claimed]}, SCAN)
    blobs.add_response("delete_object", {}, BUCKET | {"Key": "documents/retired.json"})
    blobs.add_response("delete_object", {}, BUCKET | {"Key": note.object_key})
    pointers.add_response("delete_item", {}, TABLE | {"Key": KEY} | condition(1))
    assert store.cleanup() == 1


def test_cleanup_skips_note_restored_after_scan(aws, clock):
    store, blobs, pointers = aws
    note = StoredNote(
        path=PATH,
        version="hash",
        object_key="documents/current.json",
        recover_until=NOW,
    )
    blobs.add_response("get_bucket_versioning", {}, BUCKET)
    pointers.add_response("scan", {"Items": [item(note, 9)]}, SCAN)
    pointers.add_client_error("put_item", "ConditionalCheckFailedException")
    assert store.cleanup() == 0


def test_cleanup_preserves_current_and_recent_payloads(aws, clock):
    store, blobs, pointers = aws
    note = StoredNote(
        path=PATH,
        version="hash",
        object_key="documents/current.json",
        retired={"documents/expired.json": NOW, "documents/recent.json": NOW + 1},
    )
    before = item(note, 9)
    del note.retired["documents/expired.json"]
    blobs.add_response("get_bucket_versioning", {}, BUCKET)
    pointers.add_response("scan", {"Items": [before]}, SCAN)
    blobs.add_response("delete_object", {}, BUCKET | {"Key": "documents/expired.json"})
    pointers.add_response(
        "put_item", {}, TABLE | {"Item": item(note, 1)} | condition(9)
    )
    assert store.cleanup() == 0


def test_cli_reports_failed_s3_write_without_publishing_pointer(
    aws, monkeypatch, tmp_path, capsys
):
    store, blobs, pointers = aws

    class Session:
        def client(self, name):
            return {"s3": store.s3, "dynamodb": store.dynamodb}[name]

    monkeypatch.setattr(boto3, "Session", Session)
    monkeypatch.setenv("KNOWLEDGE_ASSISTANT_STORAGE", "aws")
    monkeypatch.setenv("KNOWLEDGE_ASSISTANT_S3_BUCKET", "excavate-test")
    monkeypatch.setenv("KNOWLEDGE_ASSISTANT_DYNAMODB_TABLE", "notes")
    (tmp_path / "note.md").write_text("# Heading\nBody")
    monkeypatch.setattr(
        sys,
        "argv",
        ["knowledge-assistant", "ingest", "--root", str(tmp_path), "note.md"],
    )
    pointers.add_response("get_item", {})
    blobs.add_client_error("put_object", "AccessDenied")
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert "AWS document storage operation failed" in capsys.readouterr().err


def test_replacing_legacy_note_tracks_old_payload_for_cleanup(aws, clock):
    store, blobs, pointers = aws
    old = KEY | {"path": {"S": PATH}, "version": {"S": "old-hash"}}
    document = Document(path=PATH, digest="changed", chunks=())
    payload = document.model_dump_json().encode()
    note = StoredNote(
        path=PATH,
        version=sha256(payload).hexdigest(),
        object_key=f"documents/{KEY['document_id']['S']}/{UUID(int=1).hex}.json",
        retired={"documents/old-hash.json": NOW + RECOVERY_SECONDS},
    )
    pointers.add_response("get_item", {"Item": old}, READ)
    blobs.add_response(
        "put_object",
        {},
        BUCKET
        | {
            "Key": note.object_key,
            "Body": payload,
            "ContentType": "application/json",
            "IfNoneMatch": "*",
        },
    )
    pointers.add_response(
        "put_item",
        {},
        TABLE
        | {
            "Item": item(note, 2),
            "ConditionExpression": "attribute_not_exists(revision) AND #version = :old",
            "ExpressionAttributeNames": {"#version": "version"},
            "ExpressionAttributeValues": {":old": {"S": "old-hash"}},
        },
    )
    assert store.put(document)


def test_cleanup_cli_uses_configured_aws_store(aws, monkeypatch, capsys):
    store, blobs, pointers = aws

    class Session:
        def client(self, name):
            return {"s3": store.s3, "dynamodb": store.dynamodb}[name]

    monkeypatch.setattr(boto3, "Session", Session)
    monkeypatch.setenv("KNOWLEDGE_ASSISTANT_STORAGE", "aws")
    monkeypatch.setenv("KNOWLEDGE_ASSISTANT_S3_BUCKET", "excavate-test")
    monkeypatch.setenv("KNOWLEDGE_ASSISTANT_DYNAMODB_TABLE", "notes")
    monkeypatch.setattr(sys, "argv", ["knowledge-assistant", "cleanup"])
    blobs.add_response("get_bucket_versioning", {}, BUCKET)
    pointers.add_response("scan", {"Items": []}, SCAN)
    main()
    assert capsys.readouterr().out == "purged notes: 0\n"


def test_purge_rejects_a_versioned_bucket(aws):
    store, blobs, _ = aws
    blobs.add_response("get_bucket_versioning", {"Status": "Enabled"}, BUCKET)
    with pytest.raises(OSError, match="unversioned"):
        store.purge(PATH)


def test_concurrent_publication_reports_conflict(aws, clock):
    store, blobs, pointers = aws
    document = Document(path=PATH, digest="changed", chunks=())
    pointers.add_response("get_item", {}, READ)
    blobs.add_response("put_object", {})
    pointers.add_client_error("put_item", "ConditionalCheckFailedException")
    with pytest.raises(OSError, match="changed during ingestion"):
        store.put(document)


def test_read_rejects_corrupt_payload(aws):
    store, blobs, pointers = aws
    note = StoredNote(
        path=PATH, version="expected-checksum", object_key="documents/current.json"
    )
    pointers.add_response("get_item", {"Item": item(note, 1)}, READ)
    blobs.add_response(
        "get_object",
        {"Body": StreamingBody(BytesIO(b"corrupt"), 7)},
        BUCKET | {"Key": note.object_key},
    )
    with pytest.raises(OSError, match="checksum"):
        store.get(PATH)


def test_answer_api_reads_aws_without_a_sqlite_database(aws, monkeypatch):
    import asyncio
    import json
    from functools import partial

    import httpx

    from knowledge_assistant.api import app

    store, blobs, pointers = aws

    class Session:
        def client(self, name):
            return {"s3": store.s3, "dynamodb": store.dynamodb}[name]

    monkeypatch.setattr(boto3, "Session", Session)
    monkeypatch.setenv("KNOWLEDGE_ASSISTANT_STORAGE", "aws")
    monkeypatch.setenv("KNOWLEDGE_ASSISTANT_S3_BUCKET", "excavate-test")
    monkeypatch.setenv("KNOWLEDGE_ASSISTANT_DYNAMODB_TABLE", "notes")
    monkeypatch.delenv("KNOWLEDGE_ASSISTANT_DB", raising=False)
    monkeypatch.delenv("KNOWLEDGE_ASSISTANT_EMBEDDING_MODEL", raising=False)
    monkeypatch.setenv("KNOWLEDGE_ASSISTANT_OPENAI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "fake")

    document = Document(
        path=PATH,
        digest="digest",
        chunks=(
            Chunk(id="citation", heading=("Storage",), text="Notes use S3 storage."),
        ),
    )
    payload = document.model_dump_json().encode()
    note = StoredNote(
        path=PATH,
        version=sha256(payload).hexdigest(),
        object_key="documents/current.json",
    )
    pointers.add_response("scan", {"Items": [item(note, 1)]}, SCAN)
    blobs.add_response(
        "get_object",
        {"Body": StreamingBody(BytesIO(payload), len(payload))},
        BUCKET | {"Key": note.object_key},
    )

    def generate(request):
        data = json.loads(request.content)
        evidence = json.loads(data["input"])["passages"]
        assert evidence[0]["path"] == PATH
        assert evidence[0]["text"] == document.chunks[0].text
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "status": "answered",
                                        "answer": "S3.",
                                        "citation_ids": ["citation"],
                                    }
                                ),
                            }
                        ],
                    }
                ],
            },
        )

    monkeypatch.setattr(
        httpx, "Client", partial(httpx.Client, transport=httpx.MockTransport(generate))
    )

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                "/answer", json={"question": "Where are notes stored?"}
            )

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.json()["citations"] == [
        {"id": "citation", "path": PATH, "heading": ["Storage"]}
    ]
