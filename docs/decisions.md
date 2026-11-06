# Design decisions

These choices explain the current behavior and the tradeoffs behind it. See [architecture](architecture.md) for the overall flow.

## Ingestion and storage

- The caller supplies a trusted root and a single root-relative Markdown path. Ingestion opens path components relative to directory descriptors and rejects symlinks at the root entry and below it. The supplied root's ancestors are part of the trusted configuration. Secure opens require POSIX support.
- Store each note and its chunks in one SQLite row. The relative path is the document key. The raw byte digest and derived chunks detect repeated ingestion and the conditional upsert keeps document metadata and chunks consistent. Overlapping updates use the last committed content.
- Chunk by ATX heading sections and preserve heading ancestry. Fenced code stays in the section body. IDs hash the path, heading ancestry, body, and occurrence among identical sections. Edits to unrelated sections preserve IDs. Renames or changes to a section's heading or text change its ID.
## Retrieval

- Keep vector search and embedding contracts small until concrete adapters need additional operations. The S3 and DynamoDB adapters use the current storage interfaces. Managed vector search can extend its interface when concrete requirements emerge.
- Build the lexical index from a SQLite corpus snapshot per query. This keeps updates and deletions visible without a separate index synchronization mechanism. It requires SQLite with FTS5 and incurs a full rebuild per query.
- Keep FAISS in memory for the local milestone. Dense and lexical rankings use the same corpus snapshot. Each search or answer request rebuilds from current data and embeddings. This avoids stale index state and repeats embedding work across requests.
- Preserve heading-only sections with empty bodies. Re-ingestion can refresh older records even when source bytes are unchanged. Filename stems participate in both lexical and dense search while heading ancestry remains structured metadata.
## Answers and citations

- Answer using up to five hybrid-ranked passages. The application sends the first 2,000 characters of each passage body and bounds the serialized evidence array to 12,000 characters, including paths and headings. It skips passages that exceed the remaining evidence budget. A trimmed question may contain up to 1,000 characters. These character caps are approximate controls for model context. Full passages still go to the embedding provider when managed embeddings are enabled, so long sections may exceed its token limit. The generation request has a 2,048-token output cap and validated answer text has a 4,000-character cap.
- Keep question and evidence in a JSON input separate from trusted instructions. Treat source fields as untrusted. Return insufficient evidence when no passage fits or the provider returns a valid abstention. Treat malformed responses, refusals, incomplete outputs, and citations outside the supplied evidence as provider failures. Citation validation establishes source membership. Semantic support and resistance to embedded instructions depend on the model.
## AWS writes

- Give each S3 upload a unique key and store its SHA-256 checksum in DynamoDB. DynamoDB uses a bounded hash of the note path as its partition key and tracks the current payload and retired keys. Unique keys prevent cleanup from racing with re-ingestion of previously seen content. Conditional writes preserve repeated-ingest behavior and detect changes to parsed chunks even when the source digest stays the same. Upload before publishing the pointer so a failed upload cannot expose missing evidence. Unpublished payloads remain in S3 pending reconciliation. [S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html) · [DynamoDB PutItem](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_PutItem.html)

## AWS note retention and access

- Keep a superseded note payload for seven days from replacement. Keep the current payload for as long as the note is indexed. Cleanup must verify that a payload is still unreferenced before erasing it.
- A normal delete removes the note from retrieval immediately and keeps its latest payload recoverable for seven days from deletion. Restore republishes that version. Once the recovery window ends, cleanup erases the deleted note's remaining payloads. Older superseded versions retain their original expiration dates.
- A permanent-delete request overrides both seven-day windows. Remove the note from retrieval immediately and erase all copies under Excavate's control, including historical payloads and any persistent index entries once those exist. Report completion only after cleanup succeeds. The original Obsidian file is outside this operation. The current cleanup implementation requires an unversioned bucket. [Deleting S3 object versions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html)
- Keep the bucket private. Give search and answering read access scoped to the document prefix and table. Give ingestion permission to upload payloads and update pointers. Use a separate cleanup role to erase payloads.
- Use conditional revisions for deletion, restore, and cleanup. A purge claims the record before erasing payloads and keeps the record until deletion succeeds so a retry can finish the work. Set up the cleanup schedule and verify it with synthetic notes before uploading real notes.
