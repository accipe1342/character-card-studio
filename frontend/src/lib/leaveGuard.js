/**
 * leaveGuard.js — warn before closing the tab while work would be lost.
 * Studios call markBusy("text-job", true/false); App installs one beforeunload handler that checks anyBusy().
 */
const flags = new Set();
export function markBusy(key, on) { if (on) flags.add(key); else flags.delete(key); }
export function anyBusy() { return flags.size > 0; }
