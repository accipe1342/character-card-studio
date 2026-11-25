/**
 * tokens.js — the app's rough token estimate (no tokenizer): one token per word, plus one for every four letters
 * past the fourth. Used for the per-field and whole-card counts.
 */
export function countTokens(text) {
  if (!text) return 0;
  const str = Array.isArray(text) ? text.join(" ") : String(text);
  const words = str.trim().split(/\s+/).filter(Boolean);
  let tokens = 0;
  for (const w of words) {
    tokens += 1 + Math.floor(Math.max(0, w.length - 4) / 4);
  }
  return tokens;
}
