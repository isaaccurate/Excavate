import { describe, expect, it } from "vitest";

import { excerptOf, noteStem, wikilinkTarget } from "./citations";

const base = { id: "c", path: "Greedy Algorithm/Interval Scheduling.md", heading: ["Greedy", "Proof"] };

describe("wikilinkTarget", () => {
  it("links to the deepest heading of the note", () => {
    expect(wikilinkTarget(base)).toBe("Interval Scheduling#Proof");
  });

  it("links to the note itself when there is no heading", () => {
    expect(wikilinkTarget({ ...base, heading: [] })).toBe("Interval Scheduling");
  });

  it("drops folders and the .md extension", () => {
    expect(noteStem("a/b/Stable Matching.MD")).toBe("Stable Matching");
  });
});

describe("excerptOf", () => {
  it("trims blank lines at the edges but keeps inner breaks and indentation", () => {
    expect(excerptOf({ ...base, text: "\n\n  - one\n  - two\n\n" })).toBe("  - one\n  - two");
  });

  it.each([undefined, "", "   \n \n"])("returns null for %j", (text) => {
    expect(excerptOf({ ...base, text })).toBeNull();
  });
});
