/**
 * Starter questions for the opening screen. Edit them to match the notes in
 * the index the backend serves, and update them when those notes change.
 * The page shows up to four; an empty list shows none.
 *
 * Friendly framing ("in simple words", "walk me through") can get clearer
 * answers, but it is part of the search query too, so re-check retrieval after
 * rewording. Each of these retrieved its topic's main section from
 * data/cse421.sqlite3 in a local check; re-check them with the embedding and
 * answer models the deployed backend uses before relying on them.
 */
export const SUGGESTIONS: readonly string[] = [
  "In simple words, what is the proof of correctness for greedy interval scheduling?",
  "Walk me through how the Gale-Shapley algorithm finds a stable matching.",
  "In plain terms, how can you test whether a graph is bipartite?",
].slice(0, 4);
