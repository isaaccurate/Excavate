import asyncio
import subprocess
import sys

import httpx
import pytest

from knowledge_assistant.api import app
from knowledge_assistant.ingestion import ingest_note, note_key
from knowledge_assistant.storage import SQLiteDocumentStore


def test_health():
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.get("/health")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "selection",
    [
        "../secret.md",
        "notes/../secret.md",
        "/secret.md",
        "C:/secret.md",
        r"notes\secret.md",
        "./secret.md",
        "notes//secret.md",
        "secret.txt",
        "a\0.md",
    ],
)
def test_rejects_unsafe_selections(selection):
    with pytest.raises(ValueError):
        note_key(selection)


@pytest.mark.parametrize("component", ["file", "directory", "root", "internal"])
def test_rejects_symlinks(tmp_path, component):
    root = tmp_path / "notes"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "note.md").write_text("private")
    (root / "real.md").write_text("local")
    selection = "note.md"
    if component == "file":
        (root / selection).symlink_to(outside / selection)
    elif component == "directory":
        (root / "alias").symlink_to(outside, target_is_directory=True)
        selection = "alias/note.md"
    elif component == "root":
        root = tmp_path / "alias"
        root.symlink_to(outside, target_is_directory=True)
    else:
        (root / selection).symlink_to(root / "real.md")
    store = SQLiteDocumentStore(tmp_path / "db.sqlite3")
    with pytest.raises(OSError):
        ingest_note(root, selection, store)
    assert store.get(selection) is None


def test_incremental_ingestion(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "other.md").write_text("unselected")
    note = notes / "note.md"
    note.write_text("# Topic\nfirst\n## Detail\n```md\n# literal\n```\n")
    db = tmp_path / "db.sqlite3"
    store = SQLiteDocumentStore(db)
    assert ingest_note(notes, "note.md", store)
    assert not ingest_note(notes, "note.md", store)
    original = SQLiteDocumentStore(db).get("note.md")
    assert original is not None
    assert original.path == "note.md"
    assert [chunk.heading for chunk in original.chunks] == [
        ("Topic",),
        ("Topic", "Detail"),
    ]
    assert "# literal" in original.chunks[1].text
    assert store.get("other.md") is None

    note.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        ingest_note(notes, "note.md", store)
    assert store.get("note.md") == original

    note.write_text("# Topic\nrevised\n## Detail\n```md\n# literal\n```\n")
    assert ingest_note(notes, "note.md", store)
    updated = store.get("note.md")
    assert updated is not None
    assert updated.chunks[0].id != original.chunks[0].id
    assert updated.chunks[1].id == original.chunks[1].id

    note.unlink()
    assert store.delete("note.md")
    assert not store.delete("note.md")
    assert store.get("note.md") is None


def test_duplicate_sections_have_distinct_ids(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("# Repeat\nsame\n# Repeat\nsame\n")
    store = SQLiteDocumentStore(tmp_path / "db.sqlite3")
    ingest_note(tmp_path, note.name, store)
    document = store.get(note.name)
    assert document is not None
    assert len({chunk.id for chunk in document.chunks}) == 2


def test_cli(tmp_path):
    (tmp_path / "note.md").write_text("# Title\nbody")
    command = [
        sys.executable,
        "-m",
        "knowledge_assistant.cli",
        "--db",
        str(tmp_path / "db.sqlite3"),
    ]
    ingest = ["ingest", "--root", str(tmp_path), "note.md"]
    for arguments, expected in [
        (ingest, "indexed"),
        (ingest, "unchanged"),
        (["delete", "note.md"], "deleted"),
        (["delete", "note.md"], "absent"),
    ]:
        result = subprocess.run(
            command + arguments, check=True, capture_output=True, text=True
        )
        assert result.stdout == f"{expected}: note.md\n"
    rejected = subprocess.run(
        command + ["ingest", "--root", str(tmp_path), "../note.md"],
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 1
    assert "without traversal" in rejected.stderr


def test_reingest_restores_heading_only_content_from_legacy_record(tmp_path):
    from knowledge_assistant.contracts import Document
    from knowledge_assistant.retrieval import search_lexical

    store = SQLiteDocumentStore(tmp_path / "db.sqlite3")
    (tmp_path / "note.md").write_text("# Transactions\n## SQLite\n# FAISS\n")
    ingest_note(tmp_path, "note.md", store)
    document = store.get("note.md")
    assert document is not None

    # Earlier ingestion discarded every heading-only section.
    store.put(Document(path=document.path, digest=document.digest, chunks=()))
    assert ingest_note(tmp_path, "note.md", store)
    restored = store.get("note.md")
    assert restored is not None
    assert [chunk.heading for chunk in restored.chunks] == [
        ("Transactions",),
        ("Transactions", "SQLite"),
        ("FAISS",),
    ]
    assert all(chunk.text == "" for chunk in restored.chunks)
    assert search_lexical(store, "SQLite", limit=1) == (restored.chunks[1].id,)
    assert not ingest_note(tmp_path, "note.md", store)


def test_blank_note_has_no_chunks(tmp_path):
    store = SQLiteDocumentStore(tmp_path / "db.sqlite3")
    (tmp_path / "note.md").write_text("\n  \n")
    ingest_note(tmp_path, "note.md", store)
    document = store.get("note.md")
    assert document is not None
    assert document.chunks == ()
