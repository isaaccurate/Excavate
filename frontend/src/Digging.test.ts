import { describe, expect, it } from "vitest";

import { NOTE_BITS, pickBits } from "./Digging";

describe("pickBits", () => {
  it("picks three different bits from the set", () => {
    for (let run = 0; run < 200; run += 1) {
      const bits = pickBits();
      expect(bits).toHaveLength(3);
      expect(new Set(bits).size).toBe(3);
      for (const bit of bits) expect(NOTE_BITS).toContain(bit);
    }
  });

  it("is driven by the random source", () => {
    expect(pickBits(() => 0)).toEqual(NOTE_BITS.slice(0, 3));
  });
});
