/**
 * HelperPanel.jsx — SCRIBE-01, the helper side panel of the CHARACTER, LORE and TEXT studios.
 *
 * Chat with it to create or edit cards and lorebook entries, or to ask about SillyTavern. Every change it makes is
 * saved at once and shown here with KEEP / UNDO (UNDO refuses if the item was edited again since). The open studio
 * publishes what is on screen through helperBus, saves pending edits before the helper reads, and reloads what the
 * helper changed.
 */
import { useEffect, useRef, useState } from "react";
import { helperChat, helperChatLoad, helperChats, helperKeep, helperUndo } from "../lib/api";
import { emitHelperChange, flushHelperStudio, getHelperContext, onHelperContext } from "../lib/helperBus";
import { btnPrimary, btnTool, hint, input } from "./studio/textUi";

const red = "#c84a3a";
const KEY_OPEN = "ccs.helper.open";
const KEY_CHAT = "ccs.helper.chat";
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* storage off */ } },
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
const PANEL_W = 420;

function ChangeCard({ c, onKeep, onUndo, onOpen, busy }) {
  const done = c.status !== "open";
  return (
    <div role="group" aria-label={`Change: ${c.label}`} style={{ border: "1px solid var(--signal-border)", borderLeft: `3px solid ${c.status === "undone" ? red : "var(--signal-text)"}`,
      padding: "5px 8px", marginTop: 5, fontSize: 12, opacity: done ? 0.7 : 1, background: "var(--signal-bg-panel)" }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ flex: "1 1 140px", minWidth: 0, overflowWrap: "anywhere" }}>
          {c.status === "undone" ? <s>{c.label}</s> : c.label}
        </span>
        {c.status === "kept" && <span style={hint}>✓ kept</span>}
        {c.status === "undone" && <span style={{ ...hint, color: red }}>↶ undone</span>}
        {c.status !== "undone" && onOpen && (c.kind !== "entry" || c.project_id) && (
          <button className="signal-btn" style={{ ...btnTool, padding: "1px 6px", fontSize: 10 }} onClick={() => onOpen(c)}>OPEN</button>
        )}
        {!done && <>
          <button className="signal-btn" style={{ ...btnTool, padding: "1px 6px", fontSize: 10 }} disabled={busy} onClick={() => onKeep(c)}>KEEP</button>
          <button className="signal-btn" style={{ ...btnTool, padding: "1px 6px", fontSize: 10 }} disabled={busy} onClick={() => onUndo(c)}>UNDO</button>
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

  useEffect(() => { store.set(KEY_OPEN, open ? "1" : null); }, [open]);
  // on a wide screen the studio moves over instead of hiding under the panel
  useEffect(() => {
    const fit = () => { document.body.style.paddingRight = open && window.innerWidth >= 1100 ? `${PANEL_W}px` : ""; };
    fit();
    window.addEventListener("resize", fit);
    return () => { window.removeEventListener("resize", fit); document.body.style.paddingRight = ""; };
  }, [open]);
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

  const where = ctx?.label ? `${STUDIO_NAME[studio]} · ${ctx.label}` : STUDIO_NAME[studio];
  if (!open) {
    return (
      <button className="signal-btn" onClick={() => setOpen(true)} aria-label="Open the helper"
        title="SCRIBE-01: ask for a new card, lorebook entries, or how something in SillyTavern works"
        style={{ position: "fixed", right: 0, top: "42%", zIndex: 240, writingMode: "vertical-rl", padding: "12px 6px",
          border: "1px solid var(--signal-border)", borderRight: "none", background: "var(--signal-bg-panel)",
          color: "var(--signal-text)", fontFamily: "inherit", fontSize: 11, fontWeight: 700, letterSpacing: "0.18em", cursor: "pointer" }}>
        ◇ SCRIBE-01
      </button>
    );
  }
  return (
    <aside aria-label="Helper" className="signal-panel"
      style={{ position: "fixed", top: 0, right: 0, bottom: 0, width: `min(${PANEL_W}px, 100vw)`, zIndex: 250, display: "flex", textAlign: "left",
        flexDirection: "column", background: "var(--signal-bg-panel)", borderLeft: "1px solid var(--signal-border)",
        boxShadow: "-8px 0 24px rgba(0,0,0,0.18)", color: "var(--signal-text)" }}>
      <div style={{ padding: "12px 14px 8px", borderBottom: "1px solid var(--signal-border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <b style={{ letterSpacing: "0.16em", fontSize: 13 }}>◇ SCRIBE-01</b>
          <span style={{ ...hint, marginTop: 0 }}>support unit</span>
          <button className="signal-btn" onClick={() => setOpen(false)} aria-label="Close the helper"
            style={{ marginLeft: "auto", background: "none", border: "none", color: "inherit", cursor: "pointer", fontSize: 16 }}>✕</button>
        </div>
        <div style={{ ...hint, marginTop: 2 }}>
          {where} · {ctx?.provider || "nanogpt"}/{ctx?.model || "default model"}
        </div>
        <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
          <select aria-label="Earlier chats" value={chatId || ""} onChange={(e) => pickChat(Number(e.target.value) || null)}
            style={{ ...input, flex: 1, padding: "4px 6px", fontSize: 12 }}>
            <option value="">New chat</option>
            {chats.map((c) => <option key={c.id} value={c.id}>{c.title || `Chat ${c.id}`}</option>)}
          </select>
          <button className="signal-btn" style={{ ...btnTool, padding: "4px 8px" }} onClick={newChat} disabled={busy}>NEW</button>
        </div>
      </div>

      <div ref={listRef} aria-live="polite" style={{ flex: 1, overflowY: "auto", padding: "10px 14px" }}>
        {!messages.length && (
          <div>
            <div style={{ fontSize: 12.5, lineHeight: 1.55, marginBottom: 10 }}>
              Report: unit online. I can write or edit cards, build lorebooks and their entries, read your stories in TEXT,
              and explain SillyTavern settings. Changes are saved at once; each one shows here with KEEP and UNDO.
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {(STARTERS[studio] || []).map((s) => (
                <button key={s} className="signal-btn" style={{ ...btnTool, textAlign: "left", padding: "6px 8px", fontSize: 12 }}
                  disabled={busy} onClick={() => (s.endsWith("idea") ? setText("Write a new character: ") : send(s))}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => {
          const mine = changes.filter((c) => c.message_id === m.id);
          const openOnes = mine.filter((c) => c.status === "open");
          return (
            <div key={m.id} style={{ marginBottom: 12, display: "flex", flexDirection: "column", alignItems: m.role === "user" ? "flex-end" : "stretch" }}>
              <div style={{ maxWidth: m.role === "user" ? "88%" : "100%", border: "1px solid var(--signal-border)", padding: "7px 9px",
                fontSize: 12.5, lineHeight: 1.55, whiteSpace: "pre-wrap", overflowWrap: "anywhere",
                background: m.role === "user" ? "var(--signal-bg-btn)" : "transparent" }}>
                <div style={{ ...hint, marginTop: 0, fontWeight: 700 }}>{m.role === "user" ? "YOU" : "SCRIBE-01"}</div>
                {m.content}
              </div>
              {mine.map((c) => <ChangeCard key={c.id} c={c} onKeep={keep} onUndo={undo} onOpen={onOpen} busy={busy} />)}
              {openOnes.length > 1 && (
                <div style={{ display: "flex", gap: 6, justifyContent: "flex-end", marginTop: 5 }}>
                  <button className="signal-btn" style={{ ...btnTool, padding: "2px 8px", fontSize: 10 }} disabled={busy}
                    onClick={() => openOnes.forEach(keep)}>KEEP ALL</button>
                  <button className="signal-btn" style={{ ...btnTool, padding: "2px 8px", fontSize: 10 }} disabled={busy}
                    onClick={() => undoAll(openOnes)}>UNDO ALL</button>
                </div>
              )}
            </div>
          );
        })}
        {busy && <div style={{ ...hint, marginTop: 0 }}>Working… {elapsed}s</div>}
        {error && <div role="alert" style={{ color: red, fontSize: 12, marginTop: 6 }}>⊗ {error}</div>}
      </div>

      <div style={{ padding: "8px 14px 12px", borderTop: "1px solid var(--signal-border)" }}>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} aria-label="Message to the helper"
          placeholder="Ask for a card, entries, or how something works…" disabled={busy}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          style={{ ...input, width: "100%", boxSizing: "border-box", resize: "vertical", fontSize: 12.5 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
          <span style={{ ...hint, marginTop: 0, flex: 1 }}>Enter to send · Shift+Enter for a new line</span>
          <button className="signal-btn" style={{ ...btnPrimary, opacity: busy || !text.trim() ? 0.6 : 1 }} disabled={busy || !text.trim()}
            onClick={() => send()}>{busy ? "WORKING…" : "SEND"}</button>
        </div>
      </div>
    </aside>
  );
}
