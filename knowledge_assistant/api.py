import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from knowledge_assistant.answer_service import (
    AnswerConfigurationError,
    configured_answer,
)
from knowledge_assistant.answering import AnswerRequest, AnswerResult, GenerationError


class Health(BaseModel):
    status: Literal["ok"] = "ok"


def health() -> Health:
    return Health()


def answer_from_environment(question: str) -> AnswerResult:
    database = os.environ.get("KNOWLEDGE_ASSISTANT_DB")
    if not database:
        raise AnswerConfigurationError("set KNOWLEDGE_ASSISTANT_DB to enable answering")
    return configured_answer(
        question,
        database=Path(database),
        model=os.environ.get("KNOWLEDGE_ASSISTANT_OPENAI_MODEL"),
        embedding_model=os.environ.get("KNOWLEDGE_ASSISTANT_EMBEDDING_MODEL"),
    )


def create_app(
    answer_service: Callable[[str], AnswerResult] = answer_from_environment,
) -> FastAPI:
    app = FastAPI(title="Knowledge Assistant", version="0.1.0")
    app.get("/health")(health)

    @app.post("/answer")
    def answer(request: AnswerRequest) -> AnswerResult:
        try:
            return answer_service(request.question)
        except AnswerConfigurationError as error:
            raise HTTPException(status_code=503, detail=str(error)) from None
        except (OSError, sqlite3.Error, SQLAlchemyError, ValueError):
            raise HTTPException(
                status_code=500, detail="answer retrieval failed"
            ) from None
        except GenerationError:
            raise HTTPException(
                status_code=502, detail="answer provider failed"
            ) from None

    return app


app = create_app()
