import struct
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import JSON, URL, LargeBinary, create_engine, delete, or_, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from knowledge_assistant.contracts import Chunk, Document


class Base(DeclarativeBase):
    pass


class DocumentRow(Base):
    __tablename__ = "documents"

    path: Mapped[str] = mapped_column(primary_key=True)
    digest: Mapped[str]
    # Chunks share the document row so a replacement or delete covers both.
    chunks: Mapped[list[dict]] = mapped_column(JSON)


class EmbeddingRow(Base):
    __tablename__ = "embeddings"

    namespace: Mapped[str] = mapped_column(primary_key=True)
    chunk_id: Mapped[str] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(index=True)
    input_digest: Mapped[str]
    vector: Mapped[bytes] = mapped_column(LargeBinary)


class SQLiteDocumentStore:
    def __init__(self, database: Path) -> None:
        self.engine = create_engine(URL.create("sqlite", database=str(database)))
        Base.metadata.create_all(self.engine)

    def get(self, path: str) -> Document | None:
        with Session(self.engine) as session:
            row = session.get(DocumentRow, path)
            if row is None:
                return None
            return self._to_document(row)

    def list_documents(self) -> tuple[Document, ...]:
        with Session(self.engine) as session:
            rows = session.scalars(select(DocumentRow).order_by(DocumentRow.path))
            return tuple(self._to_document(row) for row in rows)

    @staticmethod
    def _to_document(row: DocumentRow) -> Document:
        return Document(
            path=row.path,
            digest=row.digest,
            chunks=tuple(Chunk.model_validate(chunk) for chunk in row.chunks),
        )

    def put(self, document: Document) -> bool:
        statement = insert(DocumentRow).values(
            path=document.path,
            digest=document.digest,
            chunks=[chunk.model_dump(mode="json") for chunk in document.chunks],
        )
        # Compare inside the write to avoid a read/update race. Chunk comparison
        # also refreshes records created by an older parser with the same source digest.
        statement = statement.on_conflict_do_update(
            index_elements=[DocumentRow.path],
            set_={
                "digest": statement.excluded.digest,
                "chunks": statement.excluded.chunks,
            },
            where=or_(
                DocumentRow.digest != statement.excluded.digest,
                DocumentRow.chunks != statement.excluded.chunks,
            ),
        )
        with self.engine.begin() as connection:
            changed = connection.execute(statement).rowcount == 1
            connection.execute(
                delete(EmbeddingRow).where(
                    EmbeddingRow.path == document.path,
                    EmbeddingRow.chunk_id.not_in(
                        [chunk.id for chunk in document.chunks]
                    ),
                )
            )
            return changed

    def delete(self, path: str) -> bool:
        with self.engine.begin() as connection:
            connection.execute(delete(EmbeddingRow).where(EmbeddingRow.path == path))
            statement = delete(DocumentRow).where(DocumentRow.path == path)
            return connection.execute(statement).rowcount == 1

    def read_embeddings(
        self, namespace: str, input_digests: dict[str, str]
    ) -> dict[str, Sequence[float]]:
        found = {}
        ids = list(input_digests)
        with Session(self.engine) as session:
            # Bound IN clauses for older SQLite builds.
            for offset in range(0, len(ids), 500):
                rows = session.scalars(
                    select(EmbeddingRow).where(
                        EmbeddingRow.namespace == namespace,
                        EmbeddingRow.chunk_id.in_(ids[offset : offset + 500]),
                    )
                )
                for row in rows:
                    if row.input_digest != input_digests[row.chunk_id]:
                        continue
                    if not row.vector or len(row.vector) % 4:
                        raise ValueError("invalid cached embedding bytes")
                    found[row.chunk_id] = struct.unpack(
                        f"<{len(row.vector) // 4}f", row.vector
                    )
        return found

    def write_embeddings(
        self,
        namespace: str,
        documents: Sequence[Document],
        entries: dict[str, tuple[str, Sequence[float]]],
    ) -> None:
        with self.engine.connect() as connection:
            # Serialize the snapshot check and publication with note updates/deletes.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                current_documents = {}
                paths = [document.path for document in documents]
                for offset in range(0, len(paths), 500):
                    current_documents.update(
                        {
                            row.path: row
                            for row in connection.execute(
                                select(
                                    DocumentRow.path,
                                    DocumentRow.digest,
                                    DocumentRow.chunks,
                                ).where(
                                    DocumentRow.path.in_(paths[offset : offset + 500])
                                )
                            )
                        }
                    )
                rows = []
                for document in documents:
                    current = current_documents.get(document.path)
                    if current is None or (
                        current.digest != document.digest
                        or current.chunks
                        != [c.model_dump(mode="json") for c in document.chunks]
                    ):
                        continue
                    rows.extend(
                        {
                            "namespace": namespace,
                            "chunk_id": chunk.id,
                            "path": document.path,
                            "input_digest": entries[chunk.id][0],
                            "vector": struct.pack(
                                f"<{len(entries[chunk.id][1])}f", *entries[chunk.id][1]
                            ),
                        }
                        for chunk in document.chunks
                        if chunk.id in entries
                    )
                for offset in range(0, len(rows), 100):
                    statement = insert(EmbeddingRow).values(rows[offset : offset + 100])
                    connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[
                                EmbeddingRow.namespace,
                                EmbeddingRow.chunk_id,
                            ],
                            set_={
                                "input_digest": statement.excluded.input_digest,
                                "vector": statement.excluded.vector,
                            },
                        )
                    )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
