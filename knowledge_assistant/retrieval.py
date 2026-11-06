import re
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from contextlib import closing
from pathlib import PurePosixPath

from knowledge_assistant.contracts import CorpusReader

QUERY_TERMS = re.compile(r"[^\W_]+", re.UNICODE)


def search_lexical(corpus: CorpusReader, query: str, *, limit: int) -> tuple[str, ...]:
    """Rank matching chunks from the current corpus with SQLite FTS5 BM25."""
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    terms = dict.fromkeys(QUERY_TERMS.findall(query))
    if not terms or limit == 0:
        return ()

    # Quote extracted terms so query text cannot become FTS operators.
    expression = " OR ".join(f'"{term}"' for term in terms)
    with closing(sqlite3.connect(":memory:")) as index:
        index.execute(
            "CREATE VIRTUAL TABLE passages USING fts5(id UNINDEXED, title, heading, body)"
        )
        index.executemany(
            "INSERT INTO passages VALUES (?, ?, ?, ?)",
            (
                (
                    chunk.id,
                    PurePosixPath(document.path).stem,
                    " ".join(chunk.heading),
                    chunk.text,
                )
                for document in corpus.list_documents()
                for chunk in document.chunks
            ),
        )
        # FTS5 BM25 uses lower scores for stronger matches.
        matches = index.execute(
            "SELECT id FROM passages WHERE passages MATCH ? "
            "ORDER BY bm25(passages), id LIMIT ?",
            (expression, limit),
        )
        return tuple(chunk_id for (chunk_id,) in matches)


def reciprocal_rank_fusion(
    *rankings: Sequence[str], limit: int, rank_constant: int = 60
) -> tuple[str, ...]:
    """Combine chunk rankings using one-based ranks and deterministic ties."""
    if limit < 0 or rank_constant < 0:
        raise ValueError("limit and rank_constant must be nonnegative")
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        # A source contributes at most once per chunk.
        for rank, chunk_id in enumerate(dict.fromkeys(ranking), start=1):
            scores[chunk_id] += 1 / (rank_constant + rank)
    return tuple(
        sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:limit]
    )
