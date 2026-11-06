from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, Field

from knowledge_assistant.answering import GeneratedAnswer, GenerationError


class TextOutput(BaseModel):
    type: Literal["output_text"]
    text: str


class Refusal(BaseModel):
    type: Literal["refusal"]


class Message(BaseModel):
    type: Literal["message"]
    role: Literal["assistant"]
    status: Literal["completed"]
    content: list[TextOutput | Refusal]


class Reasoning(BaseModel):
    type: Literal["reasoning"]


class ResponseEnvelope(BaseModel):
    status: Literal["completed"]
    output: list[Annotated[Message | Reasoning, Field(discriminator="type")]]


class OpenAIGeneration:
    def __init__(self, client: httpx.Client, *, api_key: str, model: str) -> None:
        self.client = client
        self.api_key = api_key
        self.model = model

    def generate(self, *, instructions: str, input_text: str) -> str:
        try:
            response = self.client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "instructions": instructions,
                    "input": input_text,
                    "store": False,
                    "max_output_tokens": 2_048,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "grounded_answer",
                            "schema": GeneratedAnswer.model_json_schema(),
                            "strict": True,
                        }
                    },
                },
                timeout=30.0,
                follow_redirects=False,
            )
            response.raise_for_status()
            output = ResponseEnvelope.model_validate_json(response.content).output
        except (httpx.HTTPError, ValueError):
            raise GenerationError("OpenAI generation request failed") from None

        messages = [item for item in output if isinstance(item, Message)]
        if len(messages) == 1:
            content = messages[0].content
            if len(content) == 1 and isinstance(content[0], TextOutput):
                return content[0].text
        raise GenerationError("OpenAI did not return a usable answer")
