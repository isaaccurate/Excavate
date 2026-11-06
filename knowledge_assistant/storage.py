from pathlib import Path

from sqlalchemy import JSON, URL, create_engine, delete, or_, select
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
            return connection.execute(statement).rowcount == 1

    def delete(self, path: str) -> bool:
        with self.engine.begin() as connection:
            statement = delete(DocumentRow).where(DocumentRow.path == path)
            return connection.execute(statement).rowcount == 1
