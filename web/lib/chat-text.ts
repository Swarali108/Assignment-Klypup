/**
 * Pure text helpers for streamed answers (no imports, so the tier-1 check can run them under plain Node).
 */

/** Cut prose into sentences, keeping every character: a boundary is ., ! or ? followed by whitespace, or a blank line. */
export function sentences(text: string): string[] {
  const out: string[] = [];
  const re = /[.!?]["”)]?\s+|\n{2,}/g;
  let start = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    const end = m.index + m[0].length;
    out.push(text.slice(start, end));
    start = end;
  }
  if (start < text.length) out.push(text.slice(start));
  return out.filter((s) => s.length);
}

/**
 * Deltas carry their own whitespace (v1 words and v2 sentences both do). The one repair: a sentence that ends
 * in . ! or ? followed by a delta starting with a capital letter gets a space. Never before a digit or ₹, so a
 * number split across deltas ("₹468." + "85 Cr") is never changed.
 */
export function joinDelta(text: string, delta: string): string {
  if (!text || !delta) return text + delta;
  if (/[.!?]$/.test(text) && /^[A-Z“*]/.test(delta)) return `${text} ${delta}`;
  return text + delta;
}
