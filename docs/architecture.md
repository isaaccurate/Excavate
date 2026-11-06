# Architecture

Excavate indexes selected notes, retrieves relevant sections, and generates answers with citations.

## Index notes

The CLI accepts a vault root and one relative Markdown path. Ingestion validates the path, reads the file, and splits it into sections while preserving heading ancestry.

Local storage uses SQLAlchemy and SQLite. Each row holds a note's path, content digest, and chunks. A conditional write updates the whole row when the source or parsed chunks change.

## Retrieve passages

Each search loads a snapshot of the indexed notes. BM25 ranks matches in note titles, headings, and body text using SQLite FTS5. FAISS searches vectors, and reciprocal rank fusion combines the two rankings.

Both searches and citation lookup use the same snapshot. Indexes are rebuilt for each request. Local token-hash embeddings are the default for testing, with an optional managed embedding provider.

## Generate answers

The CLI and FastAPI share the same answer service. It selects a bounded set of passages and asks the language model to answer from that evidence. The current generation adapter uses the OpenAI Responses API with Structured Outputs.

The application validates the returned structure and checks that every citation refers to a supplied passage. The model decides whether the evidence supports an answer. Questions and note content are passed separately from trusted instructions.

The API returns 422 for invalid input, 503 for missing configuration, and 502 for provider failures or unusable responses. The health endpoint works with the base installation.

## Store notes in AWS

S3 holds parsed notes. DynamoDB tracks the current S3 object, checksum, and recovery state for each note. Uploading the object before publishing its record prevents a failed upload from exposing missing evidence.

Retrieval reads the current documents into a snapshot. Concurrent updates can produce a mix of document versions across a DynamoDB scan.

Deleting a note hides it from retrieval and starts its recovery window. Restore makes it available again. Cleanup claims expired records before removing their objects, then deletes the records after S3 deletion succeeds. This lets failed cleanup operations be retried.

See [decisions](decisions.md) for tradeoffs and limits, or [usage](usage.md) to run the application.
