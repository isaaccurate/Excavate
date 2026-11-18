import pytest

from scripts.evaluate_labeled import score_ranking


@pytest.mark.parametrize(
    "ranking,relevant,expected",
    [
        (["other", "a", "b"], {"a", "b"}, (1.0, True, True, 0.5)),
        (["a"], {"a", "b"}, (0.5, True, False, 1.0)),
        (["1", "2", "3", "4", "5", "a"], {"a"}, (0.0, False, False, 0.0)),
        ([], {"a"}, (0.0, False, False, 0.0)),
    ],
)
def test_section_metrics_handle_partial_and_missing_evidence(
    ranking, relevant, expected
):
    assert tuple(score_ranking(ranking, relevant).values()) == expected


def test_alternative_sections_count_as_one_evidence_group():
    from scripts.evaluate_labeled import score_evidence

    result = score_evidence(["proof", "theorem"], [{"proof", "theorem"}, {"other"}])
    assert result["evidence_recall_at_5"] == 0.5
    assert result["hit_at_5"]
    assert not result["full_evidence_at_5"]
    assert result["reciprocal_rank_at_5"] == 1.0


def test_rescore_preserves_rankings_and_excludes_ambiguous_question(tmp_path):
    import copy
    import json

    from scripts.evaluate_labeled import MODES, rescore_report

    questions = [
        {
            "id": "excluded",
            "answerable": True,
            "exclude_from_scoring": True,
            "sources": [],
        },
        {
            "id": "scored",
            "answerable": True,
            "sources": [{"path": "note.md", "heading": ["Proof"]}],
        },
        {"id": "unanswerable", "answerable": False, "sources": []},
    ]
    path = tmp_path / "labels.json"
    path.write_text(json.dumps({"questions": questions, "label_revision": 2}))
    ranking = [{"path": "note.md", "heading": ["Proof"], "id": "chunk"}]
    original = {
        "dataset_sha256": "original",
        "results": [
            {
                "id": q["id"],
                "answerable": q["answerable"],
                "rankings": {mode: ranking for mode in MODES},
                "metrics": {},
            }
            for q in questions
        ],
    }
    before = copy.deepcopy(original)
    report = rescore_report(path, original)
    assert original == before
    assert report["scored_questions"] == 1
    assert report["rescore_embedding_http_calls"] == 0
    assert report["original_dataset_sha256"] == "original"
    assert report["results"][0]["metrics"] is None
    assert report["results"][2]["metrics"] is None
    assert report["metrics"]["hybrid"]["full_evidence_at_5"] == 1.0
    assert all(
        new["rankings"] == old["rankings"]
        for new, old in zip(report["results"], original["results"], strict=True)
    )


def test_real_embedding_benchmark_counts_cached_provider_work(tmp_path, monkeypatch):
    import json

    import httpx

    from scripts.evaluate_labeled import benchmark_labeled

    (tmp_path / "note.md").write_text("# Heading\nExample evidence.")
    labels = tmp_path / "labels.json"
    labels.write_text(
        json.dumps(
            {
                "status": "human_reviewed",
                "name": "Test",
                "corpus": {"paths": ["note.md"]},
                "questions": [
                    {"id": "one", "question": "Evidence?"},
                    {"id": "two", "question": "Heading?"},
                ],
            }
        )
    )
    real_client = httpx.Client

    def respond(request):
        batch = json.loads(request.content)["input"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": [1.0, 0.5]} for i in range(len(batch))
                ],
                "usage": {"total_tokens": len(batch)},
            },
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    report = benchmark_labeled(labels, tmp_path, "embedding-test", 1)
    assert report["all_rankings_identical"]
    assert report["summary"]["disabled"]["http_calls"] == 4
    assert report["summary"]["enabled"]["http_calls"] == 2
    assert report["summary"]["enabled"]["document_inputs"] == 0
    assert report["summary"]["enabled"]["query_inputs"] == 2
    assert report["cold_cache_population"][0]["document_inputs"] == 1


def test_answer_evaluation_keeps_labels_out_of_generation(tmp_path, monkeypatch):
    import json

    import httpx

    from scripts.evaluate_labeled import evaluate_answers

    (tmp_path / "note.md").write_text("# Evidence\nThe test code is quartz.")
    labels = tmp_path / "labels.json"
    labels.write_text(
        json.dumps(
            {
                "status": "human_reviewed",
                "name": "Answer test",
                "corpus": {"paths": ["note.md"]},
                "questions": [
                    {
                        "id": "one",
                        "question": "What is the code?",
                        "answerable": True,
                        "expected_answer": "PRIVATE_GROUND_TRUTH",
                    },
                    {
                        "id": "two",
                        "question": "Who invented the moon?",
                        "answerable": False,
                    },
                ],
            }
        )
    )
    real_client = httpx.Client

    def respond(request):
        body = json.loads(request.content)
        assert "PRIVATE_GROUND_TRUTH" not in request.content.decode()
        if request.url.path == "/v1/embeddings":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": i, "embedding": [1.0, 0.5]}
                        for i in range(len(body["input"]))
                    ]
                },
            )
        payload = json.loads(body["input"])
        missing = "moon" in payload["question"]
        answer = {
            "status": "insufficient_evidence" if missing else "answered",
            "answer": None if missing else "The test code is quartz.",
            "citation_ids": [] if missing else [payload["passages"][0]["id"]],
        }
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": json.dumps(answer)}
                        ],
                    }
                ],
            },
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    report = evaluate_answers(labels, tmp_path, "embedding-test", "generation-test")
    assert report["results"][0]["result"]["status"] == "answered"
    assert report["results"][1]["result"]["status"] == "insufficient_evidence"
    assert report["results"][0]["evidence"][0]["text"] == "The test code is quartz."
