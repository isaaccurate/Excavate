import { useState } from "react";

/** Markdown pieces and common letters that a strike can knock loose. */
export const NOTE_BITS = ["#", "##", "[[", "]]", "*", "-", ">", "`", "|", "!", "a", "e", "s", "t", "n", "r"];

/** Three different bits for one strike. */
export function pickBits(random: () => number = Math.random): string[] {
  const pool = [...NOTE_BITS];
  const picked: string[] = [];
  for (let i = 0; i < 3; i += 1) {
    picked.push(pool.splice(Math.floor(random() * pool.length), 1)[0]);
  }
  return picked;
}

/**
 * A pickaxe swinging down and chipping bits of a note out of the air. Each
 * strike knocks loose three new ones, swapped in while they are hidden.
 */
export function Digging() {
  const [bits, setBits] = useState(() => pickBits());
  return (
    <svg className="digging" aria-hidden="true" viewBox="0 0 48 32" width="48" height="32" fill="currentColor">
      <g className="digging__chunks">
        <text className="digging__chunk digging__chunk--1" x="15" y="24">{bits[0]}</text>
        <text className="digging__chunk digging__chunk--2" x="18.5" y="24.5">{bits[1]}</text>
        <text className="digging__chunk digging__chunk--3" x="10.5" y="24">{bits[2]}</text>
      </g>
      <g className="digging__pick" onAnimationIteration={() => setBits(pickBits())}>
        <path d="M23.55 15.15 42 30.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
        <path d="M19.84 25.08Q19.56 12.56 31.62 10.21Q23.83 16 19.84 25.08Z" />
      </g>
    </svg>
  );
}
