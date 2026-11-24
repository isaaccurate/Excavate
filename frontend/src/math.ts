/** Code spans and fenced blocks, which math conversion must leave alone. */
const CODE = /(```[\s\S]*?```|`[^`\n]*`)/;

/**
 * Models often write math with LaTeX's \(...\) and \[...\] delimiters, while
 * remark-math (like Obsidian) reads $...$ and $$...$$. Convert outside code.
 */
export function normalizeMath(text: string): string {
  return text
    .split(CODE)
    .map((part, index) => {
      if (index % 2 === 1) return part;
      return part
        .replace(/\\\[([\s\S]+?)\\\]/g, (_, body: string) => `\n$$\n${body.trim()}\n$$\n`)
        .replace(/\\\(([\s\S]+?)\\\)/g, (_, body: string) => `$${body.trim()}$`);
    })
    .join("");
}
