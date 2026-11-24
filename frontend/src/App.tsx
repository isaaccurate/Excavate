import { lazy, Suspense, useEffect, useRef, useState } from "react";

import {
  AskFailure,
  MAX_QUESTION_CHARS,
  askQuestion,
  type AnswerResult,
  type FailureKind,
} from "./api";
import { Callout } from "./Callout";
import { Digging } from "./Digging";
import { ArrowUpIcon, FailureIcon, PencilIcon, WarningIcon } from "./icons";
import { FAILURE_MESSAGES, NO_EVIDENCE } from "./messages";
import { SUGGESTIONS } from "./suggestions";

/** One question at a time: a new question replaces the current exchange. */
type Exchange =
  | { phase: "searching"; question: string }
  | { phase: "result"; question: string; result: AnswerResult }
  | { phase: "failed"; question: string; kind: FailureKind };

const AnswerContent = lazy(() => import("./AnswerContent"));

const MAX_COMPOSER_HEIGHT = 200;

export default function App() {
  const [draft, setDraft] = useState("");
  const [exchange, setExchange] = useState<Exchange | null>(null);
  const pending = useRef<AbortController | null>(null);
  const composer = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => () => pending.current?.abort(), []);

  // Grow the composer with its text, up to a few lines.
  useEffect(() => {
    const field = composer.current;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, MAX_COMPOSER_HEIGHT)}px`;
  }, [draft]);

  const searching = exchange?.phase === "searching";
  const trimmed = draft.trim();
  const canAsk = trimmed.length > 0 && !searching;
  const remaining = MAX_QUESTION_CHARS - draft.length;

  async function ask(question: string) {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setExchange({ phase: "searching", question });

    try {
      const result = await askQuestion(question, controller.signal);
      if (!controller.signal.aborted) setExchange({ phase: "result", question, result });
    } catch (error) {
      if (controller.signal.aborted) return;
      const kind = error instanceof AskFailure ? error.kind : "unexpected";
      setExchange({ phase: "failed", question, kind });
    }
  }

  function submitDraft() {
    if (!canAsk) return;
    setDraft("");
    void ask(trimmed);
  }

  function startOver() {
    pending.current?.abort();
    pending.current = null;
    setExchange(null);
    composer.current?.focus();
  }

  return (
    <div className="app">
      <header className="titlebar">
        <span className="titlebar__name">Excavate</span>
        <button
          className="titlebar__action"
          type="button"
          onClick={startOver}
          disabled={exchange === null}
        >
          <PencilIcon />
          New question
        </button>
      </header>

      <main className="stage" aria-live="polite">
        {exchange === null ? (
          <div className="welcome">
            <h1 className="welcome__title">Ask your notes.</h1>
            <p className="welcome__lede">
              Answers come only from the notes you have indexed, and every answer lists the
              sections it was drawn from.
            </p>
            {SUGGESTIONS.length > 0 ? (
              <div className="suggestions">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    className="suggestions__item"
                    type="button"
                    key={suggestion}
                    onClick={() => void ask(suggestion)}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="exchange">
            <p className="question">{exchange.question}</p>

            <article className="reply" aria-busy={exchange.phase === "searching"}>
              <div className="reply__head">
                <span className="reply__speaker">Excavate</span>
                {exchange.phase === "searching" ? (
                  <>
                    <Digging />
                    <span className="reply__searching-text">Searching your notes</span>
                  </>
                ) : null}
              </div>

              {exchange.phase === "result" && exchange.result.status === "answered" ? (
                <Suspense fallback={<p className="reply__answer">{exchange.result.answer}</p>}>
                  <AnswerContent answer={exchange.result.answer} citations={exchange.result.citations} />
                </Suspense>
              ) : null}

              {exchange.phase === "result" &&
              exchange.result.status === "insufficient_evidence" ? (
                <Callout tone="warning" icon={<WarningIcon />} message={NO_EVIDENCE} />
              ) : null}

              {exchange.phase === "failed" ? (
                <Callout
                  tone="danger"
                  icon={<FailureIcon />}
                  message={FAILURE_MESSAGES[exchange.kind]}
                >
                  <button
                    className="callout__retry"
                    type="button"
                    onClick={() => void ask(exchange.question)}
                  >
                    Ask again
                  </button>
                </Callout>
              ) : null}
            </article>
          </div>
        )}
      </main>

      <footer className="dock">
        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            submitDraft();
          }}
        >
          <label className="visually-hidden" htmlFor="question">
            Ask a question
          </label>
          <div className="composer__box">
            <textarea
              id="question"
              ref={composer}
              className="composer__field"
              placeholder="Ask about your notes"
              value={draft}
              maxLength={MAX_QUESTION_CHARS}
              rows={1}
              autoFocus
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  submitDraft();
                }
              }}
            />
            <button className="composer__send" type="submit" aria-label="Ask" disabled={!canAsk}>
              <ArrowUpIcon />
            </button>
          </div>
          <p className="composer__hint">
            {remaining <= 200
              ? `${remaining} characters left`
              : "A new question replaces the current answer. Enter to ask, Shift + Enter for a new line."}
          </p>
        </form>
      </footer>
    </div>
  );
}
