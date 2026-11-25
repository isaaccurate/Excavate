"""Forward local frontend requests to an IAM-authenticated Lambda Function URL."""

import hashlib
import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException, Request, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from knowledge_assistant.answering import AnswerRequest

logger = logging.getLogger(__name__)
FUNCTION_URL = re.compile(r"https://[a-z0-9]+\.lambda-url\.([a-z0-9-]+)\.on\.aws/?")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[dict]:
    function_url = os.environ.get("EXCAVATE_LAMBDA_URL", "").strip()
    match = FUNCTION_URL.fullmatch(function_url)
    if match is None:
        raise RuntimeError("Set EXCAVATE_LAMBDA_URL to the HTTPS Lambda Function URL")

    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise RuntimeError("AWS credentials are required to sign requests to Lambda")

    with httpx.Client(timeout=httpx.Timeout(95.0, connect=5.0)) as client:
        yield {
            "function_url": function_url.rstrip("/"),
            "region": match[1],
            "credentials": credentials,
            "client": client,
        }


app = FastAPI(title="Excavate AWS proxy", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])


def forward(request: Request, method: str, path: str, body: bytes = b"") -> Response:
    state = request.state
    url = f"{state.function_url}{path}"
    # Sign the same bytes sent to Lambda, including an empty body for GET.
    headers = {"X-Amz-Content-Sha256": hashlib.sha256(body).hexdigest()}
    if body:
        headers["Content-Type"] = "application/json"
    outbound = AWSRequest(method=method, url=url, data=body, headers=headers)

    try:
        credentials = state.credentials.get_frozen_credentials()
        SigV4Auth(credentials, "lambda", state.region).add_auth(outbound)
        upstream = state.client.request(
            method, url, headers=dict(outbound.headers), content=body
        )
    except (BotoCoreError, ClientError, httpx.RequestError, RuntimeError) as error:
        logger.warning("Lambda proxy request failed (%s)", type(error).__name__)
        raise HTTPException(502, "Could not reach the deployed API") from None

    content_type = upstream.headers.get("content-type", "").split(";", 1)[0].strip()
    if upstream.status_code in (401, 403):
        # A configuration problem on this machine, not an answer failure.
        logger.warning(
            "Lambda rejected the signed request (HTTP %s)", upstream.status_code
        )
        raise HTTPException(
            503, "The deployed API rejected the proxy's AWS credentials"
        )
    if content_type != "application/json":
        logger.warning(
            "Unexpected Lambda proxy response (HTTP %s)", upstream.status_code
        )
        raise HTTPException(502, "The deployed API returned an unexpected response")

    return Response(
        upstream.content,
        status_code=upstream.status_code,
        media_type="application/json",
    )


@app.get("/health")
def health(request: Request) -> Response:
    return forward(request, "GET", "/health")


@app.post("/answer")
def answer(request: Request, payload: AnswerRequest) -> Response:
    return forward(
        request, "POST", "/answer", payload.model_dump_json().encode("utf-8")
    )
