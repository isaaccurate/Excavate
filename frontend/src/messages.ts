import { MAX_QUESTION_CHARS, type FailureKind } from "./api";

export type Message = {
  title: string;
  /** What a visitor sees. */
  detail: string;
  /** Setup advice for whoever runs the backend, shown only by the dev server. */
  devHint?: string;
};

export const FAILURE_MESSAGES: Record<FailureKind, Message> = {
  offline: {
    title: "Excavate isn't responding",
    detail: "The answer service can't be reached right now. Try again in a moment.",
    devHint: "The request didn't reach the backend. Start it with uvicorn knowledge_assistant.api:app.",
  },
  unconfigured: {
    title: "Excavate isn't available right now",
    detail: "The answer service isn't set up to answer yet. Try again later.",
    devHint:
      "The backend needs OPENAI_API_KEY, KNOWLEDGE_ASSISTANT_OPENAI_MODEL, and the retrieval extra installed. Set those and restart it.",
  },
  retrieval: {
    title: "Couldn't search the notes",
    detail: "Something went wrong while searching. Try again in a moment.",
    devHint: "Check that KNOWLEDGE_ASSISTANT_DB points at a database you have ingested notes into.",
  },
  provider: {
    title: "Couldn't write an answer",
    detail: "The answer model didn't return a usable reply. Ask again.",
    devHint: "The generation call failed or returned an invalid answer. Check the uvicorn log.",
  },
  invalid: {
    title: "That question can't be asked",
    detail: `Questions can be up to ${MAX_QUESTION_CHARS} characters.`,
  },
  malformed: {
    title: "Something went wrong",
    detail: "Excavate sent back a reply this page can't read. Try again.",
    devHint: "The response didn't match the expected shape. Check the uvicorn log.",
  },
  unexpected: {
    title: "Something went wrong",
    detail: "The request failed. Try again in a moment.",
    devHint: "Check the uvicorn log for what the API returned.",
  },
};

export const NO_EVIDENCE: Message = {
  title: "Not enough in these notes",
  detail: "None of the notes support an answer to that. Try rephrasing, or ask about another topic.",
  devHint: "If the notes should cover it, ingest the note that does.",
};
