/**
 * helperBus.js — how the studios and the helper side panel talk to each other.
 *
 *   setHelperContext(studio, ctx)   a studio says what is open (card_id, lore_project_id, ...) and its provider/model
 *   registerHelperFlush(studio, fn) a studio's "save what isn't saved yet", run before the helper reads anything
 *   onHelperChange(fn)              a studio hears which items the helper (or an undo) changed, to reload them
 */
const contexts = {};
const flushers = {};
const listeners = new Set();
const ctxListeners = new Set();

export function setHelperContext(studio, ctx) {
  contexts[studio] = ctx;
  ctxListeners.forEach((fn) => fn(studio, ctx));
}
export function getHelperContext(studio) {
  return contexts[studio] || null;
}
export function onHelperContext(fn) {
  ctxListeners.add(fn);
  return () => ctxListeners.delete(fn);
}

export function registerHelperFlush(studio, fn) {
  flushers[studio] = fn;
  return () => { if (flushers[studio] === fn) delete flushers[studio]; };
}
export async function flushHelperStudio(studio) {
  const fn = flushers[studio];
  if (fn) await fn();
}

/** touched: [{kind: "card" | "entry" | "project", id, project_id?}] */
export function emitHelperChange(touched) {
  if (!touched || !touched.length) return;
  listeners.forEach((fn) => { try { fn(touched); } catch { /* one studio failing to reload must not stop the others */ } });
}
export function onHelperChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
