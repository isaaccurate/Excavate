# Design decisions

See the [architecture](architecture.md) for the path from a selected note to a cited answer.

## File selection and section identity

The caller supplies a trusted vault root and one relative Markdown path. POSIX directory-relative opens reject symlinks at the root entry and below it. The root’s ancestors are trusted.

Each SQLite row holds a note and its sections. A conditional upsert compares both the source digest and parsed sections so a parser change can refresh an unchanged file.

A section ID depends on its path, heading ancestry, body, and occurrence among identical sections. Editing another section preserves its ID. Heading-only sections remain searchable, and headings inside fenced code stay in the body.

## Search and cache consistency

Rebuilding BM25 and FAISS from one snapshot keeps search results and citations consistent after edits and deletions. The tradeoff is index construction time on every request.

SQLite caches float32 vectors by section ID, provider configuration (including the model), and a digest of the exact embedding input. Provider calls run outside the write transaction. Before saving a validated batch, the cache checks that each note still matches the snapshot. Simultaneous misses can duplicate work. An older request cannot restore vectors for a changed or deleted note.

## Answer limits

The model receives up to five passages, with up to 2,000 body characters each and a 12,000-character budget for the full evidence array. A relevant detail beyond that cutoff can be lost. Embeddings use full sections, so very long sections can also exceed the embedding provider’s input limit.

Questions and source fields are sent as data, separately from trusted instructions. Citation validation checks that IDs refer to supplied passages. Whether the passage supports the claim requires reviewing its text.

## AWS writes and recovery

Each upload gets a unique S3 key. DynamoDB publishes the pointer and checksum after upload. If publication fails, the previous version stays readable, but the new object can remain untracked.

Deletion hides a note immediately. Its latest version is recoverable for seven days. Replaced versions expire seven days after replacement. A purge skips the recovery window. Cleanup claims the record before deleting tracked objects and retains it until deletion succeeds so a retry can finish. This design requires an unversioned bucket.

The API has read access to notes. Ingestion writes payloads and pointers. A separate cleanup role erases expired content.
