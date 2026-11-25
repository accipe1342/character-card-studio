/**
 * HelperPanel.jsx — SCRIBE-01, the helper console of the CHARACTER, LORE and TEXT studios.
 *
 * Chat with it to create or edit cards and lorebook entries, or to ask about SillyTavern. Every change it makes is
 * saved at once and listed on the right, grouped by reply, with Open / Undo (Undo refuses if the item was edited again since).
 * The open studio publishes what is on screen through helperBus, saves pending edits before the helper reads, and
 * reloads what the helper changed.
 *
 * Layout (system-message style): docked along the bottom (drag the top edge to resize), HIDE shrinks it to a
 * bar, FLOAT turns it into a window you can drag and resize. Ctrl+/ (or the footer hint) shows / hides it. Where it
 * sits and how big it is are remembered in this browser.
 */
import { useEffect, useRef, useState } from "react";
import { getPresets, helperChat, helperChatDelete, helperChatLoad, helperChats, helperKeep, helperRun, helperUndo } from "../lib/api";
import { emitHelperChange, flushHelperStudio, getHelperContext, onHelperContext, onHelperToggle } from "../lib/helperBus";
import SignalMenu, { MenuItem, MenuSep } from "./shared/SignalMenu";

const INK = "#dad6c3";                     // the console is dark in both themes, like a system message
const DIM = "rgba(218,214,195,0.72)";
const LINE = "rgba(218,214,195,0.25)";
const CONSOLE_BG = "#3e3b33";
const red = "#e0a08a";
const KEY_OPEN = "ccs.helper.open";
const KEY_CHAT = "ccs.helper.chat";
const KEY_MODE = "ccs.helper.mode";        // "dock" | "float"
const KEY_H = "ccs.helper.h";
const KEY_POS = "ccs.helper.pos";
const BAR_H = 38;
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* storage off */ } },
  json(k, d) { try { return JSON.parse(localStorage.getItem(k)) || d; } catch { return d; } },
};

const STARTERS = {
  character: ["Write a new character from my idea", "Tighten this card's description", "Make a lorebook for this card's world",
    "What makes a good first message?"],
  lore: ["Add entries for the main places in this lorebook", "Check these entries for weak keywords", "Shorten the longest entries",
    "When should an entry be constant?"],
  text: ["Make a card from the selected character", "Build a lorebook from this story's places and factions",
    "What should go in the card and what in the lorebook?"],
};
const STUDIO_NAME = { character: "CHARACTER", lore: "LORE", text: "TEXT" };
const small = {};                           // size and look come from .scribe-btn (same in both themes)

/** One change, as a sentence. The work is already saved, so the only real action is putting it back. */
function ChangeRow({ c, onUndo, onOpen, busy, dim, red, ink, at = 0 }) {
  const d = c.detail || null;
  const parts = (d?.parts || []).filter((p) => p.field);
  const canOpen = c.status !== "undone" && onOpen && (c.kind !== "entry" || c.project_id);
  const act = { display: "inline-flex", alignItems: "center", padding: "2px 8px", font: "400 11px inherit",
    letterSpacing: "0.1em", border: `1px solid ${dim}`, background: "none", cursor: "pointer" };
  return (
    <div role="group" aria-label={`Change: ${c.label}`} className="signal-row-in"
      style={{ animationDelay: `${Math.min(at, 4) * 60}ms`,            // stagger the first five, then all at once
        display: "flex", flexWrap: "wrap", gap: "6px 9px", alignItems: "center", padding: "8px", fontSize: 12.5,
        borderBottom: "1px solid rgba(218,214,195,0.12)", opacity: c.status === "undone" ? 0.6 : 1 }}>
      <span aria-hidden="true" style={{ width: 8, height: 8, flex: "none",
        background: c.created ? ink : "transparent", border: c.created ? "none" : `1px solid ${ink}`, boxSizing: "border-box" }} />
      <span style={{ flex: "1 1 130px", minWidth: 0, overflowWrap: "break-word", textDecoration: c.status === "undone" ? "line-through" : "none" }}>
        {d ? (
          <>
            {d.verb} <span style={{ fontWeight: 500 }}>{d.subject}</span>
            {parts.length ? (
              <span style={{ color: dim }}>
                {" — "}{parts.map((p) => p.field).join(", ")}
                {parts.length === 1 && parts[0].size ? ` · ${parts[0].size}` : ""}
              </span>
            ) : null}
          </>
        ) : c.label}
      </span>
      {c.status === "undone"
        ? <span style={{ color: red, fontSize: 11, letterSpacing: "0.1em", marginLeft: "auto" }}>PUT BACK</span>
        : (
          <span style={{ display: "inline-flex", gap: 5, marginLeft: "auto", flex: "none" }}>
            {canOpen && <button type="button" style={{ ...act, color: ink }} onClick={() => onOpen(c)}>Open</button>}
            {c.status === "open" && (
              <button type="button" style={{ ...act, color: red }} disabled={busy} onClick={() => onUndo(c)}>Undo</button>
            )}
          </span>
        )}
      {c.error && <div style={{ color: red, marginTop: 3, flex: "1 1 100%" }}>⊗ {c.error}</div>}
    </div>
  );
}

/** SQLite stores UTC without a marker; show it as the reader's own clock. */
function clockTime(ts) {
  if (!ts) return "";
  const d = new Date(String(ts).includes("T") ? ts : `${String(ts).replace(" ", "T")}Z`);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** What an answer cost: time, tokens in and out, the model that wrote it, and how many steps it took. */
function MessageMeta({ m, dim }) {
  const t2 = clockTime(m.created_at);
  const x = m.meta;
  const bits = [t2];
  if (x) {
    if (x.seconds) bits.push(`${x.seconds}s`);
    if (x.prompt_tokens || x.completion_tokens) bits.push(`${(x.prompt_tokens || 0).toLocaleString()} → ${(x.completion_tokens || 0).toLocaleString()} tok`);
    if (x.model) bits.push(`${x.provider || ""}/${x.model}`.replace(/^\//, ""));
    if (x.steps > 1) bits.push(`${x.steps} steps`);
  }
  const line = bits.filter(Boolean).join(" · ");
  return line ? <div style={{ color: dim, fontSize: 10.5, letterSpacing: "0.06em", marginTop: 1 }}>{line}</div> : null;
}

export default function HelperPanel({ studio, onOpen }) {
  const [open, setOpen] = useState(() => store.get(KEY_OPEN) === "1");
  const [chatId, setChatId] = useState(() => Number(store.get(KEY_CHAT)) || null);
  const [messages, setMessages] = useState([]);
  const [changes, setChanges] = useState([]);
  const [chats, setChats] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [run, setRun] = useState(null);           // what the backend says this run is doing
  const [error, setError] = useState("");
  const [confirmDel, setConfirmDel] = useState(false);   // DELETE asks once, like the studios do
  const [ctx, setCtx] = useState(() => getHelperContext(studio));
  const [preset, setPreset] = useState(null);        // CONFIG -> Model presets -> SCRIBE-01, if one is set
  useEffect(() => { getPresets().then((p) => setPreset(p?.helper?.model ? p.helper : null)).catch(() => {}); }, []);
  const listRef = useRef(null);
  const [mode, setMode] = useState(() => (store.get(KEY_MODE) === "float" ? "float" : "dock"));
  const [height, setHeight] = useState(() => Math.min(640, Math.max(180, Number(store.get(KEY_H)) || 280)));
  const [pos, setPos] = useState(() => store.json(KEY_POS, null));

  useEffect(() => { store.set(KEY_OPEN, open ? "1" : null); }, [open]);
  useEffect(() => { store.set(KEY_MODE, mode); }, [mode]);
  useEffect(() => { store.set(KEY_H, String(height)); }, [height]);
  useEffect(() => { if (pos) store.set(KEY_POS, JSON.stringify(pos)); }, [pos]);
  // the page leaves room at the bottom so nothing hides under the console (or its bar)
  useEffect(() => {
    document.body.style.paddingBottom = `${(open && mode === "dock" ? height : BAR_H) + 8}px`;
    return () => { document.body.style.paddingBottom = ""; };
  }, [open, mode, height]);
  // Ctrl+/ and the footer hint show / hide it
  useEffect(() => {
    const key = (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "/") { e.preventDefault(); setOpen((v) => !v); } };
    window.addEventListener("keydown", key);
    const off = onHelperToggle(() => setOpen((v) => !v));
    return () => { window.removeEventListener("keydown", key); off(); };
  }, []);
  useEffect(() => { store.set(KEY_CHAT, chatId ? String(chatId) : null); }, [chatId]);
  useEffect(() => {
    setCtx(getHelperContext(studio));
    return onHelperContext((s, c) => { if (s === studio) setCtx(c); });
  }, [studio]);
  // reopen the last chat; while the server is still starting, try again instead of forgetting the chat
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!open || !chatId || messages.length) return undefined;
    let t;
    helperChatLoad(chatId).then((d) => { setMessages(d.messages); setChanges(d.changes); })
      .catch((e) => { if (e.notFound) setChatId(null); else if (retry < 20) t = setTimeout(() => setRetry((n) => n + 1), 1500); });
    return () => clearTimeout(t);
  }, [open, chatId, retry]);   // only when the panel opens, the chat changes, or a retry is due
  useEffect(() => { if (open) helperChats().then(setChats).catch(() => {}); }, [open, chatId, retry]);
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, changes, busy]);
  useEffect(() => {
    if (!busy) { setElapsed(0); return; }
    const t0 = Date.now();
    const iv = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(iv);
  }, [busy]);

  async function send(msg) {
    const message = (msg ?? text).trim();
    if (!message || busy) return;
    // the backend reports each step against this id while the request is still open
    const runId = (crypto.randomUUID ? crypto.randomUUID() : `r${Date.now()}${Math.random()}`).slice(0, 64);
    const poll = setInterval(() => {
      helperRun(runId).then((r) => { if (!r.waiting) setRun(r); }).catch(() => {});
    }, 700);
    setBusy(true); setError(""); setText(""); setRun(null);
    setMessages((m) => [...m, { id: `tmp${Date.now()}`, role: "user", content: message, created_at: new Date().toISOString() }]);
    try {
      await flushHelperStudio(studio);                 // the helper must read what is on screen, saved
      const c = getHelperContext(studio) || {};
      const { provider: sp, model: sm, ...context } = c;
      // her own model when CONFIG sets one, otherwise whatever the studio on screen is using
      const provider = preset?.provider || preset?.model ? (preset.provider || sp) : sp;
      const model = preset?.model || sm;
      const r = await helperChat({ message, chat_id: chatId, context: { studio, ...context }, provider, model, run_id: runId });
      setChatId(r.chat_id);
      setMessages((m) => [...m, { id: r.message_id, role: "helper", content: r.reply, meta: r.meta, created_at: r.created_at }]);
      setChanges((cs) => [...cs, ...r.changes]);
      emitHelperChange(r.touched);
    } catch (e) {
      setError(e.message);
      setText(message);
      setMessages((m) => m.filter((x) => !(typeof x.id === "string" && x.content === message && x.role === "user")));
    } finally {
      clearInterval(poll);
      setBusy(false);
      setRun(null);
    }
  }

  const patch = (id, p) => setChanges((cs) => cs.map((c) => (c.id === id ? { ...c, ...p } : c)));
  async function keep(c) {
    try { await helperKeep(c.id); patch(c.id, { status: "kept", error: "" }); } catch (e) { patch(c.id, { error: e.message }); }
  }
  async function undo(c) {
    try {
      await flushHelperStudio(studio);
      await helperUndo(c.id);
      patch(c.id, { status: "undone", error: "" });
      emitHelperChange([{ kind: c.kind, id: c.target_id, project_id: c.project_id }]);
      return true;
    } catch (e) { patch(c.id, { error: e.message }); return false; }
  }
  async function undoAll(list) {
    for (const c of [...list].reverse()) {           // newest first: entries before the lorebook that holds them
      if (!(await undo(c))) break;
    }
  }
  const chatTitle = (c) => {
    const t2 = (c.title || `Chat ${c.id}`).trim();
    return t2.length > 38 ? `${t2.slice(0, 37)}\u2026` : t2;      // long first messages become the title
  };
  const chatLabel = chatId ? chatTitle(chats.find((c) => c.id === chatId) || { id: chatId, title: "" }) : "New chat";

  function newChat() { setChatId(null); setMessages([]); setChanges([]); setError(""); setConfirmDel(false); }
  async function pickChat(id) {
    setConfirmDel(false);
    if (!id) return newChat();
    try { const d = await helperChatLoad(id); setChatId(id); setMessages(d.messages); setChanges(d.changes); setError(""); }
    catch (e) { setError(e.message); }
  }
  /** Press once to ask, again to delete. What the chat made (cards, entries) stays. */
  async function deleteChat() {
    if (!chatId) return;
    if (!confirmDel) { setConfirmDel(true); setTimeout(() => setConfirmDel(false), 4000); return; }
    setConfirmDel(false);
    try {
      await helperChatDelete(chatId);
      newChat();
      helperChats().then(setChats).catch(() => {});
    } catch (e) { setError(e.message); }
  }

  // drag the top edge (docked) or the title bar / corner (floating)
  function drag(e, kind) {
    e.preventDefault();
    const sx = e.clientX, sy = e.clientY, h0 = height;
    const p0 = pos || { x: window.innerWidth - 700, y: window.innerHeight - 520, w: 660, h: 460 };
    const move = (ev) => {
      const dx = ev.clientX - sx, dy = ev.clientY - sy;
      if (kind === "edge") setHeight(Math.min(window.innerHeight - 120, Math.max(160, h0 - dy)));
      if (kind === "move") setPos({ ...p0, x: Math.min(window.innerWidth - 120, Math.max(0, p0.x + dx)), y: Math.min(window.innerHeight - 60, Math.max(0, p0.y + dy)) });
      if (kind === "size") setPos({ ...p0, w: Math.max(420, p0.w + dx), h: Math.max(260, p0.h + dy) });
    };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  const openCount = changes.filter((c) => c.status === "open").length;
  const madeCount = changes.filter((c) => c.status !== "undone").length;
  const where = ctx?.label ? `${STUDIO_NAME[studio]} / ${ctx.label}` : STUDIO_NAME[studio];
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} aria-label="Open the helper"
        title="SCRIBE-01: ask for a new card, lorebook entries, or how something in SillyTavern works (Ctrl+/)"
        style={{ position: "fixed", left: 24, right: 24, bottom: 6, height: BAR_H - 6, zIndex: 240, display: "flex", alignItems: "center", gap: 12,
          padding: "0 16px", background: CONSOLE_BG, color: INK, border: "1px solid transparent", fontFamily: "inherit",
          fontSize: 12, letterSpacing: "0.22em", cursor: "pointer", textAlign: "left" }}>
        <span className="sui-diamond" aria-hidden="true" />
        <span style={{ fontWeight: 500 }}>SCRIBE-01</span>
        <span style={{ opacity: 0.72 }}>:: ASK FOR A CARD, ENTRIES OR ADVICE</span>
        <span style={{ marginLeft: "auto", opacity: 0.72 }}>{openCount ? `${openCount} CHANGE${openCount > 1 ? "S" : ""} · ` : ""}CTRL+/ ▴</span>
      </button>
    );
  }

  const floating = mode === "float";
  const fp = pos || { x: Math.max(0, window.innerWidth - 700), y: Math.max(0, window.innerHeight - 520), w: 660, h: 460 };
  // a window saved on a bigger screen must still be reachable: keep its title bar inside the viewport
  const fw = Math.min(fp.w, window.innerWidth), fh = Math.min(fp.h, window.innerHeight);
  const frame = floating
    ? { left: Math.min(Math.max(0, fp.x), Math.max(0, window.innerWidth - fw)),
        top: Math.min(Math.max(0, fp.y), Math.max(0, window.innerHeight - fh)), width: fw, height: fh }
    : { left: 24, right: 24, bottom: 6, height: Math.min(height, Math.max(160, window.innerHeight - 120)) };
  // one group per reply, newest first; "cleared" ones drop out and everything put back collects at the end
  const undoneOnes = changes.filter((c) => c.status === "undone");
  const groups = messages.filter((m) => m.role === "helper")
    .map((m) => ({ m, list: changes.filter((c) => c.message_id === m.id && c.status === "open") }))
    .filter((g) => g.list.length).reverse();
  if (undoneOnes.length) groups.push({ m: { id: "undone" }, list: undoneOnes, undone: true });
  return (
    <aside aria-label="Helper" style={{ position: "fixed", ...frame, zIndex: 250, display: "flex", flexDirection: "column", textAlign: "left",
      background: CONSOLE_BG, color: INK, boxShadow: "5px 5px 0 rgba(78,75,66,0.3), 0 10px 30px rgba(0,0,0,0.25)" }}>
      {!floating && <div aria-hidden="true" onPointerDown={(e) => drag(e, "edge")} title="Drag to resize"
        style={{ height: 7, cursor: "ns-resize", display: "flex", justifyContent: "center", alignItems: "center", flex: "none" }}>
        <div style={{ width: 60, height: 2, background: DIM }} />
      </div>}
      <div onPointerDown={floating ? (e) => { if (!e.target.closest("button, select, input, textarea")) drag(e, "move"); } : undefined}
        style={{ display: "flex", alignItems: "center", gap: 10, padding: floating ? "8px 14px" : "2px 14px 7px", borderBottom: `1px solid ${LINE}`,
          cursor: floating ? "move" : "default", flexWrap: "wrap", flex: "none" }}>
        <span className="sui-diamond" aria-hidden="true" />
        <b style={{ fontWeight: 500, letterSpacing: "0.3em", fontSize: 13 }}>SCRIBE-01</b>
        <span style={{ fontSize: 11, letterSpacing: "0.16em", color: DIM, textTransform: "uppercase", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 420 }}>
          :: {where} · {(preset?.provider || ctx?.provider) || "nanogpt"}/{(preset?.model || ctx?.model) || "default model"}{preset?.model ? " · set in CONFIG" : ""}
        </span>
        <div style={{ flex: 1 }} />
        <SignalMenu label={chatLabel} align="right" width={300} title="Earlier chats" btnClass="scribe-btn" menuClass="is-console"
          style={{ padding: "3px 9px", fontSize: 11, letterSpacing: "0.12em", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", display: "inline-block" }}>
          <MenuItem onClick={() => pickChat(null)}>New chat</MenuItem>
          {chats.length > 0 && <MenuSep />}
          {chats.map((c) => (
            <MenuItem key={c.id} onClick={() => pickChat(c.id)}>
              {chatTitle(c)}{c.id === chatId ? "  \u2713" : ""}
            </MenuItem>
          ))}
        </SignalMenu>
        <button className="scribe-btn" style={small} onClick={newChat} disabled={busy}>NEW</button>
        <button className="scribe-btn" style={small} onClick={deleteChat} disabled={busy || !chatId}
          title="Delete this conversation. The cards and entries it made stay.">{confirmDel ? "DELETE?" : "\u2715 CHAT"}</button>
        <a className="scribe-btn" href="/api/helper/card" download="SCRIBE-01.png" style={{ textDecoration: "none" }}
          title="SCRIBE-01 as a SillyTavern character card, to talk with her there (the glossary comes along as her lorebook)">⇩ CARD</a>
        <button className="scribe-btn" style={small} onClick={() => setMode(floating ? "dock" : "float")}
          aria-label={floating ? "Dock at the bottom" : "Float as a window"}>{floating ? "⇊ DOCK" : "⧉ FLOAT"}</button>
        <button className="scribe-btn" style={small} onClick={() => setOpen(false)} aria-label="Close the helper">▾ HIDE</button>
      </div>

      <div style={{ flex: 1, display: "flex", minHeight: 0, flexWrap: floating && fp.w < 560 ? "wrap" : "nowrap" }}>
        <div style={{ flex: "1 1 360px", display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
          <div ref={listRef} aria-live="polite" tabIndex={0} aria-label="Conversation" className="scribe-scroll"
            style={{ flex: 1, minHeight: 0, overflowY: "auto", overscrollBehavior: "contain", padding: "8px 14px", fontSize: 13, lineHeight: 1.7, outline: "none" }}>
            {!messages.length && (
              <div>
                <div style={{ marginBottom: 8 }}><span style={{ color: DIM, letterSpacing: "0.14em" }}>SCRIBE-01 ::</span> Report: unit online. I can write or edit
                  cards, build lorebooks and their entries, read your stories in TEXT, and explain SillyTavern settings. Each change
                  is saved as I make it and listed on the right, so you can see what changed or put any of it back.</div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {(STARTERS[studio] || []).map((s) => (
                    <button key={s} className="scribe-btn" style={{ ...small, letterSpacing: "0.04em", fontSize: 12, padding: "5px 10px" }}
                      disabled={busy} onClick={() => (s.endsWith("idea") ? setText("Write a new character: ") : send(s))}>{s}</button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", marginBottom: 6 }}>
                <span style={{ color: DIM, letterSpacing: "0.14em" }}>{m.role === "user" ? "YOU ::" : "SCRIBE-01 ::"}</span> {m.content}
                <MessageMeta m={m} dim={DIM} />
              </div>
            ))}
            {busy && (
              <div style={{ color: DIM }}>
                SCRIBE-01 :: {run?.message || "working"}
                {run?.step ? ` · step ${run.step} of ${run.of}` : ""}
                {run?.changes ? ` · ${run.changes} change${run.changes === 1 ? "" : "s"} so far` : ""}
                {` · ${elapsed}s`}
                <span className="signal-typing-cursor" aria-hidden="true" />
              </div>
            )}
            {error && <div role="alert" style={{ color: red, fontSize: 12, marginTop: 6 }}>⊗ {error}</div>}
          </div>
          <div style={{ display: "flex", gap: 8, padding: "6px 14px 10px", alignItems: "flex-end", flex: "none" }}>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} aria-label="Message to the helper"
              placeholder="Ask SCRIBE-01 ::  Enter to send · Shift+Enter for a new line" disabled={busy}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              style={{ flex: 1, boxSizing: "border-box", resize: "none", fontSize: 13, fontFamily: "inherit", padding: "7px 10px",
                background: "rgba(218,214,195,0.1)", color: INK, border: "none", boxShadow: `inset 0 0 0 1px ${LINE}` }} />
            <button className="scribe-btn is-primary" style={{ ...small, padding: "9px 16px", fontSize: 12 }} disabled={busy || !text.trim()}
              onClick={() => send()}>{busy ? "WORKING…" : "SEND"}</button>
          </div>
        </div>
        <div className="scribe-scroll" style={{ flex: "0 1 360px", borderLeft: `1px solid ${LINE}`, padding: "8px 14px", overflowY: "auto", overscrollBehavior: "contain", display: "flex", flexDirection: "column", gap: 6, minWidth: 0, minHeight: 0 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span style={{ letterSpacing: "0.24em", fontWeight: 500, fontSize: 12 }}>CHANGES</span>
            {!!madeCount && <span style={{ color: DIM, fontSize: 11, letterSpacing: "0.14em" }}>:: {madeCount} MADE, ALL SAVED</span>}
          </div>
          {!groups.length
            ? <div style={{ color: DIM, fontSize: 12 }}>What SCRIBE-01 changes shows up here. Each one is saved as she makes it.</div>
            : <div style={{ color: DIM, fontSize: 11, lineHeight: 1.5, margin: "4px 0 8px" }}>
                Everything here is already in your cards and lorebooks. Undo puts one back the way it was.
              </div>}
          {groups.map(({ m, list, undone }) => {
            const openOnes = list.filter((c) => c.status === "open");
            const newest = groups[0].m.id === m.id;
            const label = undone ? `PUT BACK EARLIER · ${list.length}`
              : `${newest ? "THIS REPLY" : "EARLIER REPLY"} · ${list.length} CHANGE${list.length > 1 ? "S" : ""}`;
            return (
              <div key={undone ? "undone" : m.id} style={{ border: `1px solid ${LINE}`, marginBottom: 10 }}>
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "5px 8px", padding: "7px 8px", background: "rgba(218,214,195,0.1)" }}>
                  <span style={{ fontSize: 11, fontWeight: 500, letterSpacing: "0.18em", color: DIM }}>{label}</span>
                  <span style={{ flex: 1 }} />
                  {openOnes.length > 1 && (
                    <>
                      <button type="button" className="scribe-btn" style={small} disabled={busy}
                        onClick={() => undoAll(openOnes)}>Undo all</button>
                      <button type="button" className="scribe-btn" style={small} disabled={busy}
                        aria-label="Clear these from the list" title="Clear these from the list — the work stays exactly as it is"
                        onClick={() => openOnes.forEach(keep)}>Clear</button>
                    </>
                  )}
                </div>
                {list.map((c, i) => <ChangeRow key={c.id} at={i} c={c} onUndo={undo} onOpen={onOpen} busy={busy} dim={DIM} red={red} ink={INK} />)}
              </div>
            );
          })}
        </div>
      </div>
      {floating && <div aria-hidden="true" onPointerDown={(e) => drag(e, "size")} title="Drag to resize"
        style={{ position: "absolute", right: 2, bottom: 2, width: 12, height: 12, cursor: "nwse-resize", borderRight: `2px solid ${DIM}`, borderBottom: `2px solid ${DIM}` }} />}
    </aside>
  );
}
