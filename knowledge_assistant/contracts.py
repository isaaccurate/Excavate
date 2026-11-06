from typing import Protocol, Sequence

from pydantic import BaseModel, ConfigDict


class Chunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    heading: tuple[str, ...]
    text: str


class Document(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    digest: str
    chunks: tuple[Chunk, ...]


class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    path: str
    heading: tuple[str, ...]


class Passage(Citation):
    text: str


class CorpusReader(Protocol):
    def list_documents(self) -> Sequence[Document]:
        """Read a snapshot of the stored corpus."""
        ...


class DocumentStore(Protocol):
    def get(self, path: str) -> Document | None: ...

    def put(self, document: Document) -> bool:
        """Replace one document atomically. Return whether it changed."""
        ...

    def delete(self, path: str) -> bool:
        """Delete the stored document and return whether it existed."""
        ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one embedding per input text in input order."""
        ...


class VectorSearch(Protocol):
    def search(self, vector: Sequence[float], *, limit: int) -> Sequence[str]:
        """Return chunk IDs in ranked order."""
        ...


class PassageSearch(Protocol):
    def retrieve(self, query: str, *, limit: int) -> Sequence[Passage]: ...


class GenerationProvider(Protocol):
    def generate(self, *, instructions: str, input_text: str) -> str:
        """Return the raw structured answer for validation by the caller."""
        ...
