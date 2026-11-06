from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

import faiss
import numpy as np
from numpy.typing import NDArray

from knowledge_assistant.contracts import (
    CorpusReader,
    Document,
    EmbeddingProvider,
    Passage,
    VectorSearch,
)
from knowledge_assistant.embeddings import EmbeddingError
from knowledge_assistant.retrieval import reciprocal_rank_fusion, search_lexical


def normalized_vectors(
    vectors: Sequence[Sequence[float]], *, count: int
) -> NDArray[np.float32]:
    try:
        matrix = np.array(vectors, dtype=np.float32)
    except (TypeError, ValueError, OverflowError):
        raise EmbeddingError("expected a rectangular embedding matrix") from None
    if (
        matrix.ndim != 2
        or matrix.shape[0] != count
        or matrix.shape[1] == 0
        or not np.isfinite(matrix).all()
    ):
        raise EmbeddingError("invalid embedding count, dimensions, or values")
    norms = np.linalg.norm(matrix.astype(np.float64), axis=1, keepdims=True)
    # Tokenless passages can produce zero vectors in the offline provider.
    return (matrix / np.where(norms == 0, 1, norms)).astype(np.float32)


class FaissVectorSearch:
    def __init__(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        self.ids = tuple(ids)
        matrix = normalized_vectors(vectors, count=len(ids))
        self.index = faiss.IndexFlatIP(matrix.shape[1])
        self.index.add(matrix)

    def search(self, vector: Sequence[float], *, limit: int) -> tuple[str, ...]:
        if limit < 0:
            raise ValueError("limit must be nonnegative")
        if limit == 0:
            return ()
        query = normalized_vectors([vector], count=1)
        if query.shape[1] != self.index.d:
            raise EmbeddingError("query and index embedding dimensions differ")
        if not query.any():
            return ()
        # Score the small snapshot exactly and break ties before truncating.
        scores, positions = self.index.search(query, len(self.ids))
        ranked = sorted(
            (-float(score), self.ids[position])
            for score, position in zip(scores[0], positions[0], strict=True)
        )
        return tuple(chunk_id for _, chunk_id in ranked[:limit])


@dataclass(frozen=True)
class Snapshot:
    documents: tuple[Document, ...]

    def list_documents(self) -> tuple[Document, ...]:
        return self.documents


@dataclass(frozen=True)
class Rankings:
    lexical: tuple[str, ...] = ()
    dense: tuple[str, ...] = ()
    hybrid: tuple[str, ...] = ()


class HybridSearch:
    """Build a consistent retrieval snapshot and reuse its vectors across queries."""

    def __init__(self, corpus: CorpusReader, provider: EmbeddingProvider) -> None:
        self.snapshot = Snapshot(tuple(corpus.list_documents()))
        self.provider = provider
        chunks = [
            chunk for document in self.snapshot.documents for chunk in document.chunks
        ]
        self.vector_index: VectorSearch | None = (
            FaissVectorSearch(
                [chunk.id for chunk in chunks],
                provider.embed(
                    [
                        "\n".join(
                            (
                                PurePosixPath(document.path).stem,
                                *chunk.heading,
                                chunk.text,
                            )
                        )
                        for document in self.snapshot.documents
                        for chunk in document.chunks
                    ]
                ),
            )
            if chunks
            else None
        )

    def search(self, query: str, *, limit: int = 5, candidates: int = 20) -> Rankings:
        if limit < 0 or candidates < limit:
            raise ValueError("require 0 <= limit <= candidates")
        if not query.strip() or self.vector_index is None or limit == 0:
            return Rankings()
        lexical = search_lexical(self.snapshot, query, limit=candidates)
        vectors = self.provider.embed([query])
        if len(vectors) != 1:
            raise EmbeddingError("expected one query embedding")
        dense = self.vector_index.search(vectors[0], limit=candidates)
        return Rankings(
            lexical=lexical[:limit],
            dense=dense[:limit],
            hybrid=reciprocal_rank_fusion(lexical, dense, limit=limit),
        )

    def retrieve(self, query: str, *, limit: int) -> tuple[Passage, ...]:
        ranks = self.search(query, limit=limit, candidates=max(20, limit))
        passages = {
            chunk.id: Passage(
                id=chunk.id, path=document.path, heading=chunk.heading, text=chunk.text
            )
            for document in self.snapshot.documents
            for chunk in document.chunks
            if chunk.id in ranks.hybrid
        }
        return tuple(passages[chunk_id] for chunk_id in ranks.hybrid)
