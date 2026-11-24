import { afterEach, describe, expect, it, vi } from "vitest";

import { AskFailure, askQuestion, parseResult } from "./api";

const CITATION = { id: "c1", path: "Notes/Graphs.md", heading: ["Graphs", "DFS"], text: "Depth first." };

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(result: Response | Error) {
  const fetch = vi.fn(async () => {
    if (result instanceof Error) throw result;
    return result;
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

async function failureKind(promise: Promise<unknown>): Promise<string> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof AskFailure) return error.kind;
    throw error;
  }
  throw new Error("expected the request to fail");
}

const ask = () => askQuestion("Which search?", new AbortController().signal);

afterEach(() => vi.unstubAllGlobals());

describe("askQuestion", () => {
  it("posts the question to /answer and returns the parsed result", async () => {
    const fetch = stubFetch(json(200, { status: "answered", answer: "Hybrid.", citations: [CITATION] }));
    await expect(ask()).resolves.toEqual({
      status: "answered",
      answer: "Hybrid.",
      citations: [CITATION],
    });
    expect(fetch).toHaveBeenCalledWith(
      "/answer",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ question: "Which search?" }) }),
    );
  });

  it.each([
    [422, "invalid", { detail: [{ msg: "too long" }] }],
    [503, "unconfigured", { detail: "configure an OpenAI generation model" }],
    [502, "provider", { detail: "answer provider failed" }],
    [500, "retrieval", { detail: "answer retrieval failed" }],
    [404, "unexpected", { detail: "Not Found" }],
  ])("maps an API %i to %s", async (status, kind, body) => {
    stubFetch(json(status, body));
    expect(await failureKind(ask())).toBe(kind);
  });

  // The dev proxy answers for a backend that is not listening, without FastAPI's JSON.
  it.each([500, 502, 503, 504])("treats a %i without the API's JSON as unreachable", async (status) => {
    stubFetch(new Response("", { status }));
    expect(await failureKind(ask())).toBe("offline");
  });

  it("treats a network error as unreachable", async () => {
    stubFetch(new TypeError("Failed to fetch"));
    expect(await failureKind(ask())).toBe("offline");
  });

  it("rethrows cancellation instead of reporting a failure", async () => {
    stubFetch(new DOMException("aborted", "AbortError"));
    await expect(ask()).rejects.toMatchObject({ name: "AbortError" });
  });

  it("reports a non-JSON success body as malformed", async () => {
    stubFetch(new Response("<html>", { status: 200 }));
    expect(await failureKind(ask())).toBe("malformed");
  });
});

describe("parseResult", () => {
  it("accepts a citation without text, for older backends", () => {
    const { text: _text, ...legacy } = CITATION;
    expect(parseResult({ status: "answered", answer: "A.", citations: [legacy] }).citations).toEqual([legacy]);
  });

  it("keeps only the fields the page uses", () => {
    const result = parseResult({ status: "answered", answer: "A.", citations: [{ ...CITATION, score: 0.9 }] });
    expect(result.citations[0]).toEqual(CITATION);
  });

  it("accepts an abstention with no answer", () => {
    expect(parseResult({ status: "insufficient_evidence", answer: null, citations: [] }).status).toBe(
      "insufficient_evidence",
    );
  });

  it.each([
    ["a non-string excerpt", { status: "answered", answer: "A.", citations: [{ ...CITATION, text: 5 }] }],
    ["a heading that is not a list of strings", { status: "answered", answer: "A.", citations: [{ ...CITATION, heading: "DFS" }] }],
    ["an answered result with no answer", { status: "answered", answer: null, citations: [] }],
    ["an unknown status", { status: "maybe", answer: "A.", citations: [] }],
    ["a missing citation list", { status: "answered", answer: "A." }],
  ])("rejects %s", (_label, payload) => {
    expect(() => parseResult(payload)).toThrow(AskFailure);
  });
});
