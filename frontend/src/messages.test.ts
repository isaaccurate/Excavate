import { describe, expect, it } from "vitest";

import { FAILURE_MESSAGES, NO_EVIDENCE } from "./messages";

// Visitors to a deployed page cannot act on setup advice.
const SETUP_TERMS = /uvicorn|KNOWLEDGE_ASSISTANT|OPENAI|ingest|backend|log\b/i;

describe("visitor-facing messages", () => {
  it.each(Object.entries({ ...FAILURE_MESSAGES, NO_EVIDENCE }))("%s keeps setup advice out of what visitors see", (_kind, message) => {
    expect(message.title).not.toMatch(SETUP_TERMS);
    expect(message.detail).not.toMatch(SETUP_TERMS);
  });
});
