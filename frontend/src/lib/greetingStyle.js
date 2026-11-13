/**
 * greetingStyle.js — the point of view, tense and length chosen for first messages and greetings (⚙ Options in
 * CHARACTER). Remembered in this browser and sent with every request that writes a first message or greeting:
 * Generate Card, Batch Generate, field regenerate and alternate greetings. Empty values let the model choose.
 */
const KEY = "ccs.greetingStyle";
const EMPTY = { pov: "", tense: "", length: "" };

export function getGreetingStyle() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || "null");
    return v && typeof v === "object" ? { ...EMPTY, ...v } : { ...EMPTY };
  } catch {
    return { ...EMPTY };
  }
}

export function setGreetingStyle(style) {
  try { localStorage.setItem(KEY, JSON.stringify({ ...EMPTY, ...style })); } catch { /* private window: this session only */ }
}

/** The style to send, or null when nothing is chosen. */
export function greetingStyleToSend() {
  const s = getGreetingStyle();
  return s.pov || s.tense || s.length ? s : null;
}
