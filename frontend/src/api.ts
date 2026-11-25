// Mirrors knowledge_assistant.answering.AnswerResult, whose citations are
// knowledge_assistant.contracts.Passage values.

export const MAX_QUESTION_CHARS = 1_000;

export type Citation = {
  /** Internal chunk ID: used as a key, never shown. */
  id: string;
  path: string;
  /** Heading trail from the top of the note down to the cited section. */
  heading: string[];
  /** The cited excerpt. Older backends send no text. */
  text?: string;
};

export type AnswerResult =
  | { status: "answered"; answer: string; citations: Citation[] }
  | { status: "insufficient_evidence"; answer: null; citations: [] };

/** Every way a request can fail, so the page can say what to do about it. */
export type FailureKind =
  | "offline"
  | "invalid"
  | "unconfigured"
  | "provider"
  | "retrieval"
  | "rate_limited"
  | "malformed"
  | "unexpected";

export class AskFailure extends Error {
  readonly kind: FailureKind;

  constructor(kind: FailureKind) {
    super(kind);
    this.name = "AskFailure";
    this.kind = kind;
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/** Reads one citation, keeping only known fields. Returns null if it is malformed. */
export function parseCitation(value: unknown): Citation | null {
  if (typeof value !== "object" || value === null) return null;
  const candidate = value as Record<string, unknown>;
  const { id, path, heading, text } = candidate;
  if (typeof id !== "string" || typeof path !== "string") return null;
  if (!Array.isArray(heading) || !heading.every((part) => typeof part === "string")) {
    return null;
  }
  // An absent text field (an older backend) is fine; any other non-string is not.
  if (text !== undefined && typeof text !== "string") return null;
  return text === undefined ? { id, path, heading } : { id, path, heading, text };
}

export function parseResult(payload: unknown): AnswerResult {
  if (typeof payload !== "object" || payload === null) {
    throw new AskFailure("malformed");
  }
  const candidate = payload as Record<string, unknown>;
  const status = candidate.status;
  const answer = candidate.answer;
  const citations = candidate.citations;

  if (!Array.isArray(citations)) throw new AskFailure("malformed");
  if (status === "insufficient_evidence" && answer === null && citations.length === 0) {
    return { status, answer, citations: [] };
  }
  if (status !== "answered" || typeof answer !== "string" || !answer.trim() || !citations.length) {
    throw new AskFailure("malformed");
  }
  const parsed = citations.map((value: unknown) => {
    const citation = parseCitation(value);
    if (!citation) throw new AskFailure("malformed");
    return citation;
  });
  return { status, answer, citations: parsed };
}

/**
 * Statuses the dev proxy itself produces when the backend is not listening.
 * FastAPI answers these with its own JSON body, so a missing body means the
 * request never reached the API.
 */
const UNREACHED = new Set([500, 502, 503, 504]);

/** Returns the API's error detail, or null when the body is not its JSON. */
async function readDetail(response: Response): Promise<string | null> {
  try {
    const parsed: unknown = JSON.parse(await response.text());
    if (typeof parsed !== "object" || parsed === null) return null;
    if (!("detail" in parsed)) return null;
    const detail = (parsed as { detail: unknown }).detail;
    return typeof detail === "string" ? detail : "";
  } catch {
    return null;
  }
}

function kindForStatus(status: number): FailureKind {
  if (status === 422) return "invalid";
  if (status === 429) return "rate_limited";
  if (status === 503) return "unconfigured";
  if (status === 502) return "provider";
  if (status === 500) return "retrieval";
  return "unexpected";
}

/** Posts a question to the same-origin API. */
export async function askQuestion(
  question: string,
  signal: AbortSignal,
): Promise<AnswerResult> {
  let response: Response;
  try {
    const body = JSON.stringify({ question });
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (import.meta.env.VITE_SIGNED_LAMBDA_ORIGIN === "true") {
      // CloudFront signs the origin request using the hash of these exact bytes.
      const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(body));
      headers["X-Amz-Content-Sha256"] = Array.from(new Uint8Array(hash), (byte) =>
        byte.toString(16).padStart(2, "0"),
      ).join("");
    }
    response = await fetch("/answer", {
      method: "POST",
      headers,
      body,
      signal,
    });
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new AskFailure("offline");
  }

  if (!response.ok) {
    const detail = await readDetail(response);
    if (detail === null && UNREACHED.has(response.status)) {
      throw new AskFailure("offline");
    }
    throw new AskFailure(kindForStatus(response.status));
  }

  try {
    return parseResult(await response.json());
  } catch (error) {
    if (error instanceof AskFailure || isAbort(error)) throw error;
    throw new AskFailure("malformed");
  }
}
