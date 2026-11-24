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

export type AnswerResult = {
  status: "answered" | "insufficient_evidence";
  answer: string | null;
  citations: Citation[];
};

/** Every way a request can fail, so the page can say what to do about it. */
export type FailureKind =
  | "offline"
  | "invalid"
  | "unconfigured"
  | "provider"
  | "retrieval"
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

  const statusIsKnown =
    status === "answered" || status === "insufficient_evidence";
  const answerIsValid = typeof answer === "string" || answer === null;
  if (!statusIsKnown || !answerIsValid || !Array.isArray(citations)) {
    throw new AskFailure("malformed");
  }
  const parsed = citations.map(parseCitation);
  if (parsed.some((citation) => citation === null)) throw new AskFailure("malformed");
  if (status === "answered" && typeof answer !== "string") {
    throw new AskFailure("malformed");
  }

  return { status, answer, citations: parsed as Citation[] };
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
  if (status === 503) return "unconfigured";
  if (status === 502) return "provider";
  if (status === 500) return "retrieval";
  return "unexpected";
}

/**
 * Posts to the local API through the dev proxy. The request carries no
 * credentials: the backend reads OPENAI_API_KEY and any AWS settings itself.
 */
export async function askQuestion(
  question: string,
  signal: AbortSignal,
): Promise<AnswerResult> {
  let response: Response;
  try {
    response = await fetch("/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
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
