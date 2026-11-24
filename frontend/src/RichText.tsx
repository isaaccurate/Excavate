import "katex/dist/katex.min.css";

import Markdown, { type Components, type Options } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { normalizeMath } from "./math";

const components: Components = {
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
  // Images in notes are usually vault attachments that would not load here, and
  // fetching a URL from untrusted text would leak the reader's visit. Show the caption.
  img: ({ alt }) => (alt ? <span className="prose__image">{alt}</span> : null),
};

const REHYPE: Options["rehypePlugins"] = [
  [rehypeKatex, { throwOnError: false, strict: "ignore", errorColor: "#fb6b70" }],
];

/**
 * Markdown with typeset math, for answers and cited excerpts alike. Raw HTML
 * stays disabled: both quote note text, which is untrusted.
 */
export function RichText({
  text,
  className,
  keepLineBreaks = false,
}: {
  text: string;
  className?: string;
  /** Render single line breaks as breaks, as Obsidian does by default. */
  keepLineBreaks?: boolean;
}) {
  return (
    <div className={className ? `prose ${className}` : "prose"}>
      <Markdown
        remarkPlugins={keepLineBreaks ? [remarkGfm, remarkMath, remarkBreaks] : [remarkGfm, remarkMath]}
        rehypePlugins={REHYPE}
        components={components}
      >
        {normalizeMath(text)}
      </Markdown>
    </div>
  );
}
