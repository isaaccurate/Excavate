import hashlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import scripts.aws_api_proxy as proxy

FUNCTION_URL = "https://abc123.lambda-url.us-east-2.on.aws/"
ABSTENTION = {"status": "insufficient_evidence", "answer": None, "citations": []}


class FakeLambda:
    """Records each forwarded request and replies with a configurable response."""

    def __init__(self):
        self.requests = []
        self.reply = httpx.Response(200, json=ABSTENTION)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture
def upstream(monkeypatch):
    monkeypatch.setenv("EXCAVATE_LAMBDA_URL", FUNCTION_URL)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIDEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "session-token")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    fake = FakeLambda()
    client = httpx.Client

    def fake_client(**kwargs):
        return client(transport=httpx.MockTransport(fake), **kwargs)

    monkeypatch.setattr(proxy.httpx, "Client", fake_client)
    return fake


@pytest.fixture
def local(upstream):
    with TestClient(proxy.app, base_url="http://127.0.0.1") as client:
        yield client


def test_signs_and_forwards_a_normalized_question(local, upstream):
    response = local.post("/answer", json={"question": "  Which search?  "})

    assert response.status_code == 200
    assert response.json() == ABSTENTION
    [request] = upstream.requests
    assert str(request.url) == FUNCTION_URL.rstrip("/") + "/answer"
    assert request.content == b'{"question":"Which search?"}'
    assert request.headers["x-amz-content-sha256"] == (
        hashlib.sha256(request.content).hexdigest()
    )
    assert "/us-east-2/lambda/aws4_request" in request.headers["authorization"]
    assert request.headers["x-amz-security-token"] == "session-token"


def test_signs_health_checks_with_an_empty_body(local, upstream):
    upstream.reply = httpx.Response(200, json={"status": "ok"})

    assert local.get("/health").json() == {"status": "ok"}
    [request] = upstream.requests
    assert request.method == "GET"
    assert request.headers["x-amz-content-sha256"] == hashlib.sha256(b"").hexdigest()


def test_rejects_invalid_questions_without_calling_lambda(local, upstream):
    assert local.post("/answer", json={"question": "   "}).status_code == 422
    assert upstream.requests == []


def test_passes_api_errors_through(local, upstream):
    detail = {"detail": "answer provider failed"}
    upstream.reply = httpx.Response(502, json=detail)

    response = local.post("/answer", json={"question": "Which search?"})

    assert (response.status_code, response.json()) == (502, detail)


@pytest.mark.parametrize("status", [401, 403])
def test_reports_rejected_credentials_as_unavailable(local, upstream, status):
    upstream.reply = httpx.Response(status, json={"Message": "Forbidden"})

    response = local.post("/answer", json={"question": "Which search?"})

    assert response.status_code == 503
    assert "credentials" in response.json()["detail"]


@pytest.mark.parametrize(
    "reply",
    [
        httpx.Response(200, text="<html>", headers={"content-type": "text/html"}),
        httpx.ConnectError("unreachable"),
    ],
)
def test_reports_unusable_upstream_replies_as_bad_gateway(local, upstream, reply):
    upstream.reply = reply

    response = local.post("/answer", json={"question": "Which search?"})

    assert response.status_code == 502


def test_refuses_requests_for_other_hosts(local):
    assert local.get("/health", headers={"host": "attacker.example"}).status_code == 400


@pytest.mark.parametrize(
    "url", ["", "https://example.com/", "http://abc.lambda-url.us-east-2.on.aws/"]
)
def test_requires_a_lambda_function_url(upstream, monkeypatch, url):
    monkeypatch.setenv("EXCAVATE_LAMBDA_URL", url)

    with pytest.raises(RuntimeError, match="EXCAVATE_LAMBDA_URL"):
        with TestClient(proxy.app, base_url="http://127.0.0.1"):
            pass


def test_answer_bodies_are_json(local, upstream):
    local.post("/answer", json={"question": "Which search?"})

    [request] = upstream.requests
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {"question": "Which search?"}
