/**
 * HelperPanel.jsx — SCRIBE-01, the helper console of the CHARACTER, LORE and TEXT studios.
 *
 * Chat with it to create or edit cards and lorebook entries, or to ask about SillyTavern. Every change it makes is
 * saved at once and listed on the right with OPEN / KEEP / UNDO (UNDO refuses if the item was edited again since).
 * The open studio publishes what is on screen through helperBus, saves pending edits before the helper reads, and
 * reloads what the helper changed.
 *
 * Layout (NieR system-message style): docked along the bottom (drag the top edge to resize), HIDE shrinks it to a
 * bar, FLOAT turns it into a window you can drag and resize. Ctrl+/ (or the footer hint) shows / hides it. Where it
 * sits and how big it is are remembered in this browser.
 */
import { useEffect, useRef, useState } from "react";
import { helperChat, helperChatLoad, helperChats, helperKeep, helperUndo } from "../lib/api";
import { emitHelperChange, flushHelperStudio, getHelperContext, onHelperContext, onHelperToggle } from "../lib/helperBus";

const INK = "#dad6c3";                     // the console is dark in both themes, like NieR's system messages
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
const small = { padding: "3px 9px", fontSize: 11, border: "1px solid transparent", cursor: "pointer", letterSpacing: "0.12em", fontFamily: "inherit" };

function ChangeCard({ c, onKeep, onUndo, onOpen, busy }) {
  const done = c.status !== "open";
  return (
    <div role="group" aria-label={`Change: ${c.label}`} style={{ background: "rgba(218,214,195,0.08)", padding: "5px 8px", fontSize: 12,
      opacity: done ? 0.7 : 1, borderLeft: `3px solid ${c.status === "undone" ? red : INK}` }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ flex: "1 1 120px", minWidth: 0, overflowWrap: "anywhere" }}>{c.status === "undone" ? <s>{c.label}</s> : c.label}</span>
        {c.status === "kept" && <span style={{ color: DIM }}>✓ kept</span>}
        {c.status === "undone" && <span style={{ color: red }}>↶ undone</span>}
        {c.status !== "undone" && onOpen && (c.kind !== "entry" || c.project_id) && (
          <button className="signal-btn" style={small} onClick={() => onOpen(c)}>OPEN</button>
        )}
        {!done && <>
          <button className="signal-btn" style={small} disabled={busy} onClick={() => onKeep(c)}>KEEP</button>
          <button className="signal-btn" style={small} disabled={busy} onClick={() => onUndo(c)}>UNDO</button>
        </>}
      </div>
      {c.error && <div style={{ color: red, marginTop: 3 }}>⊗ {c.error}</div>}
    </div>
  );
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
  const [error, setError] = useState("");
  const [ctx, setCtx] = useState(() => getHelperContext(studio));
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
  useEffect(() => {                                   // reopen the last chat
    if (!open || !chatId || messages.length) return;
    helperChatLoad(chatId).then((d) => { setMessages(d.messages); setChanges(d.changes); })
      .catch(() => setChatId(null));
  }, [open, chatId]);   // only when the panel opens or the chat changes
  useEffect(() => { if (open) helperChats().then(setChats).catch(() => {}); }, [open, chatId]);
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
    setBusy(true); setError(""); setText("");
    setMessages((m) => [...m, { id: `tmp${Date.now()}`, role: "user", content: message }]);
    try {
      await flushHelperStudio(studio);                 // the helper must read what is on screen, saved
      const c = getHelperContext(studio) || {};
      const { provider, model, ...context } = c;
      const r = await helperChat({ message, chat_id: chatId, context: { studio, ...context }, provider, model });
      setChatId(r.chat_id);
      setMessages((m) => [...m, { id: r.message_id, role: "helper", content: r.reply }]);
      setChanges((cs) => [...cs, ...r.changes]);
      emitHelperChange(r.touched);
    } catch (e) {
      setError(e.message);
      setText(message);
      setMessages((m) => m.filter((x) => !(typeof x.id === "string" && x.content === message && x.role === "user")));
    } finally {
      setBusy(false);
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
  function newChat() { setChatId(null); setMessages([]); setChanges([]); setError(""); }
  async function pickChat(id) {
    if (!id) return newChat();
    try { const d = await helperChatLoad(id); setChatId(id); setMessages(d.messages); setChanges(d.changes); setError(""); }
    catch (e) { setError(e.message); }
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
  const where = ctx?.label ? `${STUDIO_NAME[studio]} / ${ctx.label}` : STUDIO_NAME[studio];
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} aria-label="Open the helper"
        title="SCRIBE-01: ask for a new card, lorebook entries, or how something in SillyTavern works (Ctrl+/)"
        style={{ position: "fixed", left: 24, right: 24, bottom: 6, height: BAR_H - 6, zIndex: 240, display: "flex", alignItems: "center", gap: 12,
          padding: "0 16px", background: CONSOLE_BG, color: INK, border: "1px solid transparent", fontFamily: "inherit",
          fontSize: 12, letterSpacing: "0.22em", cursor: "pointer", textAlign: "left" }}>
        <span className="nier-diamond" aria-hidden="true" />
        <span style={{ fontWeight: 500 }}>SCRIBE-01</span>
        <span style={{ opacity: 0.72 }}>:: ASK FOR A CARD, ENTRIES OR ADVICE</span>
        <span style={{ marginLeft: "auto", opacity: 0.72 }}>{openCount ? `${openCount} OPEN CHANGE${openCount > 1 ? "S" : ""} · ` : ""}CTRL+/ ▴</span>
      </button>
    );
  }

  const floating = mode === "float";
  const fp = pos || { x: Math.max(0, window.innerWidth - 700), y: Math.max(0, window.innerHeight - 520), w: 660, h: 460 };
  const frame = floating
    ? { left: fp.x, top: fp.y, width: Math.min(fp.w, window.innerWidth), height: Math.min(fp.h, window.innerHeight) }
    : { left: 24, right: 24, bottom: 6, height };
  const groups = messages.filter((m) => m.role === "helper").map((m) => ({ m, list: changes.filter((c) => c.message_id === m.id) }))
    .filter((g) => g.list.length);
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
        <span className="nier-diamond" aria-hidden="true" />
        <b style={{ fontWeight: 500, letterSpacing: "0.3em", fontSize: 13 }}>SCRIBE-01</b>
        <span style={{ fontSize: 11, letterSpacing: "0.16em", color: DIM, textTransform: "uppercase", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 420 }}>
          :: {where} · {ctx?.provider || "nanogpt"}/{ctx?.model || "default model"}
        </span>
        <div style={{ flex: 1 }} />
        <select aria-label="Earlier chats" value={chatId || ""} onChange={(e) => pickChat(Number(e.target.value) || null)}
          style={{ background: "rgba(218,214,195,0.1)", color: INK, border: `1px solid ${LINE}`, fontFamily: "inherit", fontSize: 11, padding: "3px 6px", maxWidth: 200 }}>
          <option value="">New chat</option>
          {chats.map((c) => <option key={c.id} value={c.id}>{c.title || `Chat ${c.id}`}</option>)}
        </select>
        <button className="signal-btn" style={small} onClick={newChat} disabled={busy}>NEW</button>
        <button className="signal-btn" style={small} onClick={() => setMode(floating ? "dock" : "float")}
          aria-label={floating ? "Dock at the bottom" : "Float as a window"}>{floating ? "⇊ DOCK" : "⧉ FLOAT"}</button>
        <button className="signal-btn" style={small} onClick={() => setOpen(false)} aria-label="Close the helper">▾ HIDE</button>
      </div>

      <div style={{ flex: 1, display: "flex", minHeight: 0, flexWrap: floating && fp.w < 560 ? "wrap" : "nowrap" }}>
        <div style={{ flex: "1 1 360px", display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
          <div ref={listRef} aria-live="polite" style={{ flex: 1, overflowY: "auto", padding: "8px 14px", fontSize: 13, lineHeight: 1.7 }}>
            {!messages.length && (
              <div>
                <div style={{ marginBottom: 8 }}><span style={{ color: DIM, letterSpacing: "0.14em" }}>SCRIBE-01 ::</span> Report: unit online. I can write or edit
                  cards, build lorebooks and their entries, read your stories in TEXT, and explain SillyTavern settings. Each change
                  is saved at once and listed on the right with KEEP and UNDO.</div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {(STARTERS[studio] || []).map((s) => (
                    <button key={s} className="signal-btn" style={{ ...small, letterSpacing: "0.04em", fontSize: 12, padding: "5px 10px" }}
                      disabled={busy} onClick={() => (s.endsWith("idea") ? setText("Write a new character: ") : send(s))}>{s}</button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", marginBottom: 4 }}>
                <span style={{ color: DIM, letterSpacing: "0.14em" }}>{m.role === "user" ? "YOU ::" : "SCRIBE-01 ::"}</span> {m.content}
              </div>
            ))}
            {busy && <div style={{ color: DIM }}>SCRIBE-01 :: working… {elapsed}s<span className="signal-typing-cursor" aria-hidden="true" /></div>}
            {error && <div role="alert" style={{ color: red, fontSize: 12, marginTop: 6 }}>⊗ {error}</div>}
          </div>
          <div style={{ display: "flex", gap: 8, padding: "6px 14px 10px", alignItems: "flex-end", flex: "none" }}>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} aria-label="Message to the helper"
              placeholder="Ask SCRIBE-01 ::  Enter to send · Shift+Enter for a new line" disabled={busy}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              style={{ flex: 1, boxSizing: "border-box", resize: "none", fontSize: 13, fontFamily: "inherit", padding: "7px 10px",
                background: "rgba(218,214,195,0.1)", color: INK, border: "none", boxShadow: `inset 0 0 0 1px ${LINE}` }} />
            <button className="signal-btn signal-btn-active" style={{ ...small, padding: "9px 16px", fontSize: 12 }} disabled={busy || !text.trim()}
              onClick={() => send()}>{busy ? "WORKING…" : "SEND"}</button>
          </div>
        </div>
        <div style={{ flex: "0 1 360px", borderLeft: `1px solid ${LINE}`, padding: "8px 14px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
          <div style={{ letterSpacing: "0.24em", fontWeight: 500, fontSize: 12 }}>CHANGES · {openCount} OPEN</div>
          {!groups.length && <div style={{ color: DIM, fontSize: 12 }}>What SCRIBE-01 changes shows up here, with OPEN, KEEP and UNDO.</div>}
          {groups.map(({ m, list }) => {
            const openOnes = list.filter((c) => c.status === "open");
            return (
              <div key={m.id} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {list.map((c) => <ChangeCard key={c.id} c={c} onKeep={keep} onUndo={undo} onOpen={onOpen} busy={busy} />)}
                {openOnes.length > 1 && (
                  <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                    <button className="signal-btn" style={small} disabled={busy} onClick={() => openOnes.forEach(keep)}>KEEP ALL</button>
                    <button className="signal-btn" style={small} disabled={busy} onClick={() => undoAll(openOnes)}>UNDO ALL</button>
                  </div>
                )}
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
