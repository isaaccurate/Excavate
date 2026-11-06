import os
from pathlib import Path

from knowledge_assistant.answering import (
    AnswerRequest,
    AnswerResult,
    GenerationError,
    answer_question,
)


class AnswerConfigurationError(RuntimeError):
    """Answering requires an existing database and explicit provider settings."""


def configured_answer(
    question: str,
    *,
    database: Path | None,
    model: str | None,
    embedding_model: str | None = None,
) -> AnswerResult:
    question = AnswerRequest(question=question).question
    if not model or not model.strip():
        raise AnswerConfigurationError("configure an OpenAI generation model")
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise AnswerConfigurationError("set OPENAI_API_KEY to enable answering")
    if embedding_model is not None and not embedding_model.strip():
        raise AnswerConfigurationError("embedding model must be nonblank")

    # Health and ingestion can run without the optional retrieval dependencies.
    try:
        import httpx

        from knowledge_assistant.embeddings import (
            EmbeddingError,
            HashEmbeddings,
            OpenAIEmbeddings,
        )
        from knowledge_assistant.generation import OpenAIGeneration
        from knowledge_assistant.hybrid import HybridSearch
    except ImportError:
        raise AnswerConfigurationError(
            "install the retrieval extra to enable answering"
        ) from None

    from knowledge_assistant.store_config import (
        StorageConfigurationError,
        open_document_store,
    )

    try:
        with open_document_store(database) as store, httpx.Client() as client:
            embeddings = (
                HashEmbeddings()
                if embedding_model is None
                else OpenAIEmbeddings(client, api_key=api_key, model=embedding_model)
            )
            generation = OpenAIGeneration(client, api_key=api_key, model=model)
            try:
                search = HybridSearch(store, embeddings)
                return answer_question(question, search, generation)
            except EmbeddingError:
                raise GenerationError("answer embedding failed") from None
    except StorageConfigurationError as error:
        raise AnswerConfigurationError(str(error)) from None
