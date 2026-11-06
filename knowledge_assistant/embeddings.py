import hashlib
import re
from collections.abc import Sequence

import httpx
from pydantic import BaseModel, FiniteFloat, StrictInt


class EmbeddingError(RuntimeError):
    """The embedding provider failed to produce a usable batch."""


class EmbeddingRow(BaseModel):
    index: StrictInt
    embedding: list[FiniteFloat]


class EmbeddingResponse(BaseModel):
    data: list[EmbeddingRow]


class OpenAIEmbeddings:
    def __init__(self, client: httpx.Client, *, api_key: str, model: str) -> None:
        self.client = client
        self.api_key = api_key
        self.model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        # Keep request batches bounded. The provider enforces token limits.
        for start in range(0, len(texts), 32):
            batch = list(texts[start : start + 32])
            try:
                response = self.client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "input": batch,
                        "model": self.model,
                        "encoding_format": "float",
                    },
                    timeout=30.0,
                    follow_redirects=False,
                )
                response.raise_for_status()
                rows = sorted(
                    EmbeddingResponse.model_validate_json(response.content).data,
                    key=lambda row: row.index,
                )
            except (httpx.HTTPError, ValueError):
                raise EmbeddingError("OpenAI embedding request failed") from None
            if [row.index for row in rows] != list(range(len(batch))):
                raise EmbeddingError("OpenAI returned invalid embedding indices")
            vectors.extend(row.embedding for row in rows)
        return vectors


class HashEmbeddings:
    """Deterministic token-count vectors for offline tests and plumbing checks."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * 512
            for token in re.findall(r"\w+", text.casefold()):
                digest = hashlib.blake2b(token.encode(), digest_size=4).digest()
                vector[int.from_bytes(digest, "big") % len(vector)] += 1.0
            vectors.append(vector)
        return vectors
