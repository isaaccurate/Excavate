import hashlib
import json
import os
import re
import stat
from collections import Counter
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path, PureWindowsPath

from knowledge_assistant.contracts import (
    MAX_PASSAGE_CHARS,
    Chunk,
    Document,
    DocumentStore,
)

HEADING = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*)|$)")
FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")


def note_key(selection: str) -> str:
    """Validate a selection and preserve its spelling as the storage key."""
    parts = selection.split("/")
    if (
        any(part in {"", ".", ".."} for part in parts)
        or "\\" in selection
        or "\0" in selection
        or PureWindowsPath(selection).drive
        or Path(selection).suffix.lower() != ".md"
    ):
        raise ValueError("select a root-relative Markdown file without traversal")
    return selection


def read_note(root: Path, key: str) -> bytes:
    """Open each component relative to a pinned directory, without following links."""
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        raise OSError("secure note ingestion requires POSIX directory-relative opens")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    *directories, filename = note_key(key).split("/")
    # Check each component as it is opened so a symlink swap cannot redirect
    # a later open after an earlier path validation.
    with ExitStack() as stack:
        directory = os.open(root, directory_flags)
        stack.callback(os.close, directory)
        for component in directories:
            directory = os.open(component, directory_flags, dir_fd=directory)
            stack.callback(os.close, directory)
        # A FIFO could block during open, before fstat can reject it.
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        descriptor = os.open(filename, flags, dir_fd=directory)
        with os.fdopen(descriptor, "rb") as note:
            if not stat.S_ISREG(os.fstat(note.fileno()).st_mode):
                raise ValueError("selected note must be a regular file")
            return note.read()


def sections(markdown: str) -> Iterator[tuple[tuple[str, ...], str]]:
    """Yield ATX heading ancestry and section text, including any preamble."""
    headings: list[tuple[int, str]] = []
    body: list[str] = []
    fence: str | None = None
    for line in markdown.splitlines():
        marker = FENCE.fullmatch(line)
        if fence:
            # A closing fence uses the same marker and is at least as long.
            if marker and marker[1].startswith(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
        elif heading := HEADING.fullmatch(line):
            yield tuple(title for _, title in headings), "\n".join(body).strip()
            body = []
            level = len(heading[1])
            while headings and headings[-1][0] >= level:
                headings.pop()
            title = re.sub(r"(?:^|[ \t]+)#+[ \t]*$", "", heading[2] or "")
            headings.append((level, title.strip()))
            continue
        body.append(line)
    yield tuple(title for _, title in headings), "\n".join(body).strip()


def split_section(body: str) -> Iterator[str]:
    """Fit passages into the answer budget while retaining nearby context."""
    overlap_chars = 500
    while len(body) > MAX_PASSAGE_CHARS:
        # Balance the last two passages so a short continuation has enough
        # context to rank for the section's topic.
        cut = min(MAX_PASSAGE_CHARS, (len(body) + overlap_chars) // 2)
        for separator in ("\n\n", "\n", " "):
            boundary = body.rfind(separator, MAX_PASSAGE_CHARS // 2, cut)
            if boundary != -1:
                cut = boundary
                break
        yield body[:cut].rstrip()
        # Repeat a complete preceding paragraph when it fits in the overlap.
        # This carries the setup into a continuation without duplicating pages.
        overlap = body.rfind("\n\n", cut - overlap_chars, cut)
        body = body[overlap + 2 if overlap != -1 else cut :].lstrip()
    yield body


def ingest_note(root: Path, selection: str, store: DocumentStore) -> bool:
    """Ingest one selected note and return whether its stored content changed."""
    key = note_key(selection)
    raw = read_note(root, key)
    # Count identical sections separately so unrelated insertions preserve IDs.
    occurrences: Counter[tuple[tuple[str, ...], str]] = Counter()
    chunks = []
    for heading, body in sections(raw.decode("utf-8-sig")):
        # Headings can carry facts even when the section has no body.
        if not body and not any(heading):
            continue
        for passage in split_section(body):
            identity = (heading, passage)
            ordinal = occurrences[identity]
            occurrences[identity] += 1
            payload = json.dumps([key, heading, passage, ordinal]).encode()
            chunks.append(
                Chunk(
                    id=hashlib.sha256(payload).hexdigest(),
                    heading=heading,
                    text=passage,
                )
            )
    return store.put(
        Document(path=key, digest=hashlib.sha256(raw).hexdigest(), chunks=tuple(chunks))
    )
