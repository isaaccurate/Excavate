from hashlib import sha256
from pathlib import PurePosixPath

from pydantic import BaseModel, FiniteFloat

from knowledge_assistant.contracts import Document


class CachedEmbedding(BaseModel):
    input_digest: str
    vector: list[FiniteFloat]


class EmbeddedDocument(Document):
    """A note version with vectors published in the same immutable payload."""

    embedding_namespace: str
    embeddings: dict[str, CachedEmbedding]


def embedding_inputs(document: Document) -> dict[str, str]:
    title = PurePosixPath(document.path).stem
    return {
        chunk.id: "\n".join((title, *chunk.heading, chunk.text))
        for chunk in document.chunks
    }


def input_digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def matching_embeddings(
    document: Document, namespace: str, digests: dict[str, str]
) -> dict[str, CachedEmbedding]:
    if not isinstance(document, EmbeddedDocument):
        return {}
    if document.embedding_namespace != namespace:
        return {}
    return {
        key: entry
        for key, entry in document.embeddings.items()
        if digests.get(key) == entry.input_digest
    }
