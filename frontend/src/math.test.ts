import { describe, expect, it } from "vitest";

import { normalizeMath } from "./math";

describe("normalizeMath", () => {
  it("turns \\( \\) into inline $ math", () => {
    expect(normalizeMath("Here \\( a = 2 \\) and \\(b\\).")).toBe("Here $a = 2$ and $b$.");
  });

  it("turns \\[ \\] into a $$ block", () => {
    expect(normalizeMath("Total: \\[ 2^j \\cdot n \\]")).toBe("Total: \n$$\n2^j \\cdot n\n$$\n");
  });

  it("leaves Obsidian-style $ math alone", () => {
    expect(normalizeMath("Already $O(n)$ and $$x$$")).toBe("Already $O(n)$ and $$x$$");
  });

  it("leaves code spans and fenced blocks untouched", () => {
    const code = "Use `\\(x\\)` inline.\n```\nre = r\"\\(\\d+\\)\"\n```";
    expect(normalizeMath(code)).toBe(code);
  });
});
