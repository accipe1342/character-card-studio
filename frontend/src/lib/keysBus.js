/**
 * keysBus.js — one event so anything on the page can ask App to open the "?" key sheet.
 * The footer hint lives far from App's state, so it fires openKeys() instead of threading a prop down.
 */
const EVENT = "ccs:keys";

export function openKeys() {
  window.dispatchEvent(new CustomEvent(EVENT));
}

/** App subscribes; returns the unsubscribe. */
export function onOpenKeys(fn) {
  window.addEventListener(EVENT, fn);
  return () => window.removeEventListener(EVENT, fn);
}
