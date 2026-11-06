"""Compare retrieval modes on the two explicitly selected course notes."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from knowledge_assistant.embeddings import HashEmbeddings
from knowledge_assistant.hybrid import HybridSearch
from knowledge_assistant.ingestion import ingest_note
from knowledge_assistant.storage import SQLiteDocumentStore

STABLE_MATCHING = "Stable Matching.md"
MASTER_THEOREM = "Divide and Conquer Algorithm/Master Theorem.md"
CASES = (
    (
        "What makes a resident and hospital an unstable pair?",
        STABLE_MATCHING,
        ("Formal Definition",),
    ),
    (
        "Why can’t a hospital and a resident who prefer each other end up apart?",
        STABLE_MATCHING,
        ("Gale Shapley Algorithm", "Proof"),
    ),
    (
        "Why does equal work at every recursion level introduce a logarithmic factor?",
        MASTER_THEOREM,
        ("Intuition",),
    ),
    (
        "When do the leaves dominate the total work of a divide-and-conquer recurrence?",
        MASTER_THEOREM,
        ("Intuition",),
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", type=Path, help="Directory containing the selected notes."
    )
    args = parser.parse_args()

    with TemporaryDirectory() as directory:
        store = SQLiteDocumentStore(Path(directory) / "eval.sqlite3")
        for note in (STABLE_MATCHING, MASTER_THEOREM):
            ingest_note(args.root, note, store)
        search = HybridSearch(store, HashEmbeddings())
        labels = {
            (doc.path, chunk.heading): chunk.id
            for doc in search.snapshot.documents
            for chunk in doc.chunks
        }
        print(f"{len(labels)} passages. Columns: lexical, dense, hybrid.")
        for query, path, heading in CASES:
            target = labels[path, heading]
            ranks = search.search(query, limit=len(labels), candidates=len(labels))
            print(
                [
                    ranking.index(target) + 1 if target in ranking else None
                    for ranking in (ranks.lexical, ranks.dense, ranks.hybrid)
                ],
                query,
            )


if __name__ == "__main__":
    main()
