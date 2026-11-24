import type { Citation } from "./api";

export function noteName(path: string): string {
  const segments = path.split("/");
  return segments[segments.length - 1] || path;
}

export function noteStem(path: string): string {
  return noteName(path).replace(/\.md$/i, "");
}

/** The link you would type in a note to reach this section. */
export function wikilinkTarget(citation: Citation): string {
  const leaf = citation.heading[citation.heading.length - 1];
  return leaf ? `${noteStem(citation.path)}#${leaf}` : noteStem(citation.path);
}

/** The excerpt to show, without blank lines at its edges, or null if there is none. */
export function excerptOf(citation: Citation): string | null {
  const text = citation.text?.replace(/^(?:[ \t]*\r?\n)+|(?:\r?\n[ \t]*)+$/g, "");
  return text && text.trim().length > 0 ? text : null;
}
