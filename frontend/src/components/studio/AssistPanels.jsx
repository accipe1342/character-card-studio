/**
 * AssistPanels.jsx — v2.5 helpers shared by the studios:
 *   ResendPreviewModal   what "UPDATE IN LORE" would change, entry by entry, with a before/after diff and tick boxes
 *   TrimButton           shorten a lore entry or card field to a target size, shown next to the original first
 *   InterviewPanel       ask a character questions to test its voice, then check the answers against its notes
 *   QuickRepliesButton   a SillyTavern Quick Reply set from a TEXT or LORE project: preview, download, or send
 *   StoryExportsButton   story bible (Markdown / printable page) and the SillyTavern Data Bank pack
 */
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { getQuickReplySet, interviewCharacter, previewCommit, pushQuickRepliesToST, trimText } from "../../lib/api";
import { btn, btnPrimary, btnTool, headingStyle, hint, input, panelStyle } from "./textUi";

const red = "#c84a3a";
const overlay = { position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 300, display: "flex",
  alignItems: "flex-start", justifyContent: "center", padding: "40px 16px", overflowY: "auto" };
const dialog = { ...panelStyle, width: "min(900px, 100%)", padding: 20, boxShadow: "0 8px 32px rgba(0,0,0,0.3)", fontSize: 13 };
const pre = { whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, lineHeight: 1.5, margin: 0 };
const tok = (s) => Math.ceil((s || "").length / 4);
// dialogs go to <body> so a panel with a transform or overflow can't clip them
const Portal = ({ children }) => createPortal(children, document.body);

/** Word-level diff (LCS), capped so huge entries stay fast. Returns [[op, text]] with op "=", "-" or "+". */
export function wordDiff(a, b) {
  const words = (x) => (x || "").match(/\s*\S+\s*/g) || [];   // each word keeps its spaces, so changes never glue words together
  const A = words(a), B = words(b);
  if (A.length * B.length > 400000) return [["-", a], ["+", b]];
  const m = A.length, n = B.length;
  const L = Array.from({ length: m + 1 }, () => new Uint16Array(n + 1));
  for (let i = m - 1; i >= 0; i--) for (let j = n - 1; j >= 0; j--)
    L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = [];
  const push = (op, t) => { if (out.length && out[out.length - 1][0] === op) out[out.length - 1][1] += t; else out.push([op, t]); };
  let i = 0, j = 0;
  while (i < m && j < n) {
    if (A[i] === B[j]) { push("=", A[i]); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) push("-", A[i++]);
    else push("+", B[j++]);
  }
  while (i < m) push("-", A[i++]);
  while (j < n) push("+", B[j++]);
  return out;
}

function Diff({ before, after }) {
  return (
    <p style={pre}>
      {wordDiff(before, after).map(([op, t], k) => op === "=" ? <span key={k}>{t}</span>
        : op === "-" ? <del key={k} style={{ color: red, opacity: 0.85 }}>{t}</del>
        : <ins key={k} style={{ background: "rgba(90,140,80,0.22)", textDecoration: "none" }}>{t}</ins>)}
    </p>
  );
}

const GROUPS = [
  ["refresh", "REFRESHED", "Text changed in TEXT since the last send"],
  ["add", "NEW", "Not in the LORE project yet"],
  ["trash", "GOING TO THE LORE TRASH", "Sent before, no longer kept (restorable in LORE)"],
  ["keep_edited", "KEPT AS YOU EDITED THEM IN LORE", "Your LORE edits win; TEXT changes are not applied"],
  ["keep_deleted", "STAYING DELETED", "You deleted these in LORE"],
];
const TICKABLE = new Set(["refresh", "add", "trash"]);

export function ResendPreviewModal({ projectId, onClose, onApply }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const [skip, setSkip] = useState(() => new Set());
  const [open, setOpen] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  useEffect(() => { previewCommit(projectId).then(setD).catch((e) => setError(e.message)); }, [projectId]);
  const toggle = (set, setter, key) => setter(() => { const n = new Set(set); n.has(key) ? n.delete(key) : n.add(key); return n; });
  const acts = d?.actions || [];
  const changes = acts.filter((x) => TICKABLE.has(x.action));
  const applying = changes.filter((x) => !skip.has(x.title)).length;
  return (<Portal>
    <div style={overlay} onClick={onClose}>
      <div className="signal-panel" role="dialog" aria-label="Update LORE preview" style={dialog} onClick={(e) => e.stopPropagation()}>
        <h2 className="signal-heading" style={headingStyle}>UPDATE LORE · PREVIEW</h2>
        {error && <div style={{ color: red, fontSize: 12 }}>⊗ {error}</div>}
        {!d && !error && <div style={hint}>Comparing with the LORE project…</div>}
        {d && (<>
          <div style={{ ...hint, marginTop: 0 }}>
            Nothing has been written yet. Untick an entry to leave it exactly as it is in LORE. Click a title to see the change
            ({acts.filter((x) => x.action === "same").length} unchanged entries are not listed).
          </div>
          {!changes.length && <div style={{ fontSize: 13, margin: "12px 0" }}>Nothing would change: LORE already matches.</div>}
          {GROUPS.map(([key, title, note]) => {
            const rows = acts.filter((x) => x.action === key);
            if (!rows.length) return null;
            return (
              <div key={key} style={{ marginTop: 14 }}>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em" }}>{title} · {rows.length}</div>
                <div style={{ ...hint, marginTop: 2, marginBottom: 6 }}>{note}</div>
                {rows.map((x) => {
                  const tick = TICKABLE.has(key);
                  const isOpen = open.has(x.title);
                  return (
                    <div key={key + x.title} style={{ border: "1px solid var(--signal-border)", padding: "6px 8px", marginBottom: 6 }}>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        {tick && <input type="checkbox" aria-label={`Apply ${x.title}`} checked={!skip.has(x.title)} onChange={() => toggle(skip, setSkip, x.title)} />}
                        <button onClick={() => toggle(open, setOpen, x.title)} className="signal-btn"
                          style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: "inherit", fontFamily: "inherit", fontWeight: 700, fontSize: 13, textAlign: "left", flex: 1 }}>
                          {isOpen ? "▾" : "▸"} {x.title} <span style={{ ...hint, fontWeight: 400 }}>{x.entry_type}</span>
                        </button>
                        <span style={hint}>
                          {key === "refresh" ? `~${tok(x.old_content)} → ~${tok(x.new_content)} tokens` : key === "add" ? `~${tok(x.new_content)} tokens` : ""}
                        </span>
                      </div>
                      {isOpen && (
                        <div style={{ marginTop: 6 }}>
                          {key === "refresh" && <Diff before={x.old_content} after={x.new_content} />}
                          {key === "add" && <p style={pre}>{x.new_content}</p>}
                          {key === "trash" && <p style={{ ...pre, opacity: 0.7 }}>{x.old_content}</p>}
                          {key.startsWith("keep") && (<>
                            <div style={hint}>In LORE (kept):</div><p style={pre}>{x.old_content}</p>
                            {x.new_content && x.new_content !== x.old_content && (<><div style={{ ...hint, marginTop: 6 }}>TEXT would have sent:</div><p style={{ ...pre, opacity: 0.7 }}>{x.new_content}</p></>)}
                          </>)}
                          {key === "refresh" && JSON.stringify(x.old_keys) !== JSON.stringify(x.new_keys) && (
                            <div style={{ ...hint, marginTop: 4 }}>Keys: {x.old_keys.join(", ") || "none"} → {x.new_keys.join(", ") || "none"}</div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </>)}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16, flexWrap: "wrap" }}>
          <button className="signal-btn" style={btn} onClick={onClose}>CANCEL</button>
          <button className="signal-btn" style={{ ...btnPrimary, opacity: busy || !d ? 0.6 : 1 }} disabled={busy || !d}
            onClick={async () => { setBusy(true); try { await onApply([...skip]); } finally { setBusy(false); } }}>
            {busy ? "UPDATING…" : changes.length ? `APPLY ${applying} CHANGE(S)` : "UPDATE ANYWAY"}
          </button>
        </div>
      </div>
    </div>
  </Portal>);
}

/** Button that trims `text` to about `target` tokens and shows the result next to the original before anything changes. */
export function TrimButton({ text, target = 150, kind = "lore", name, field, provider, model, onAccept, label = "TRIM" }) {
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [goal, setGoal] = useState(target);
  const [showDiff, setShowDiff] = useState(false);
  async function run(t = goal) {
    setBusy(true); setError("");
    try { setRes(await trimText({ text, target_tokens: t, kind, name, field, provider, model })); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return (<>
    <button className="signal-btn" style={{ ...btnTool, padding: "3px 8px", fontSize: 11, marginTop: 4, opacity: busy ? 0.6 : 1 }} disabled={busy}
      title={`Ask ${provider}/${model || "default"} for a version of about ${target} tokens. You see both before anything changes.`}
      onClick={() => { setGoal(target); run(target); }}>
      {busy && !res ? "TRIMMING…" : `✂ ${label} TO ~${target}`}
    </button>
    {error && !res && <span style={{ color: red, fontSize: 11, marginLeft: 6 }}>⊗ {error}</span>}
    {res && (<Portal>
      <div style={overlay} onClick={() => setRes(null)}>
        <div className="signal-panel" role="dialog" aria-label="Trim compare" style={dialog} onClick={(e) => e.stopPropagation()}>
          <h2 className="signal-heading" style={headingStyle}>TRIM · {name || field || "entry"}</h2>
          {res.unchanged
            ? <div style={hint}>Already at or under the target, nothing to trim.</div>
            : <div style={{ ...hint, marginTop: 0 }}>~{res.tokens_before} → ~{res.tokens_after} tokens. Check that no fact you need was dropped.</div>}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginTop: 10 }}>
            <div><div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", marginBottom: 4 }}>ORIGINAL</div><p style={pre}>{text}</p></div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em" }}>TRIMMED</span>
                <label style={{ fontSize: 11, display: "flex", gap: 4, alignItems: "center", marginLeft: "auto" }}>
                  <input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} /> mark changes
                </label>
              </div>
              {showDiff ? <Diff before={text} after={res.text} /> : <p style={pre} data-testid="trimmed-text">{res.text}</p>}
            </div>
          </div>
          {error && <div style={{ color: red, fontSize: 12, marginTop: 8 }}>⊗ {error}</div>}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", alignItems: "center", marginTop: 16, flexWrap: "wrap" }}>
            <span style={hint}>target</span>
            <input type="number" min={30} max={2000} step={10} value={goal} aria-label="Target tokens" onChange={(e) => setGoal(parseInt(e.target.value) || target)}
              style={{ ...input, width: 80, padding: "5px 6px" }} />
            <button className="signal-btn" style={{ ...btn, opacity: busy ? 0.6 : 1 }} disabled={busy} onClick={() => run(goal)}>{busy ? "TRIMMING…" : "TRY AGAIN"}</button>
            <button className="signal-btn" style={btn} onClick={() => setRes(null)}>KEEP ORIGINAL</button>
            <button className="signal-btn" style={btnPrimary} disabled={res.unchanged} onClick={() => { onAccept(res.text); setRes(null); }}>USE TRIMMED</button>
          </div>
        </div>
      </div>
    </Portal>)}
  </>);
}

const STARTERS = [
  "Who are you, in your own words?",
  "What do you want most right now?",
  "Who do you trust, and who don't you?",
  "What would make you lose your temper?",
  "Tell me about the last place you called home.",
];

/** Chat with a character to test its voice. `entityId` (TEXT entry) or `card` (CHARACTER studio). Not saved. */
export function InterviewPanel({ entityId, card, provider, model, name }) {
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [check, setCheck] = useState(null);
  const who = name || card?.name || "the character";
  useEffect(() => { setMsgs([]); setCheck(null); setError(""); }, [entityId]);
  const target = entityId ? { entity_id: entityId } : { card };
  async function ask(text) {
    const question = (text ?? q).trim();
    if (!question || busy) return;
    const next = [...msgs, { role: "user", content: question }];
    setMsgs(next); setQ(""); setBusy(true); setError(""); setCheck(null);
    try {
      const r = await interviewCharacter({ ...target, provider, model, messages: next });
      setMsgs([...next, { role: "char", content: r.reply }]);
    } catch (e) { setError(e.message); setMsgs(msgs); setQ(question); }
    finally { setBusy(false); }
  }
  async function runCheck() {
    setBusy(true); setError("");
    try { setCheck(await interviewCharacter({ ...target, provider, model, messages: msgs, check: true })); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ ...hint, marginTop: 0, marginBottom: 8 }}>
        Ask {who} questions to hear how the notes play. Uses {provider}/{model || "default"}; the chat is not saved.
        When you have a few answers, CHECK compares them with the notes.
      </div>
      {!msgs.length && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 8 }}>
          {STARTERS.map((s) => <button key={s} className="signal-btn" style={{ ...btnTool, padding: "3px 8px", fontSize: 11 }} disabled={busy} onClick={() => ask(s)}>{s}</button>)}
        </div>
      )}
      <div aria-live="polite" style={{ maxHeight: 360, overflowY: "auto" }}>
        {msgs.map((m, i) => (
          <div key={i} style={{ margin: "0 0 8px", display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
            <div style={{ maxWidth: "85%", border: "1px solid var(--signal-border)", padding: "6px 9px", fontSize: 12.5, lineHeight: 1.5,
              background: m.role === "user" ? "var(--signal-bg-btn)" : "transparent", whiteSpace: "pre-wrap" }}>
              <div style={{ ...hint, marginTop: 0, fontWeight: 700 }}>{m.role === "user" ? "YOU" : who.toUpperCase()}</div>
              {m.content}
            </div>
          </div>
        ))}
        {busy && <div style={hint}>…</div>}
      </div>
      {error && <div style={{ color: red, fontSize: 12, margin: "4px 0" }}>⊗ {error}</div>}
      <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
        <input style={{ ...input, flex: 1 }} value={q} placeholder={`Ask ${who} something…`} aria-label="Question"
          onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }} />
        <button className="signal-btn" style={{ ...btnPrimary, opacity: busy || !q.trim() ? 0.6 : 1 }} disabled={busy || !q.trim()} onClick={() => ask()}>ASK</button>
      </div>
      <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
        <button className="signal-btn" style={{ ...btn, flex: 1, opacity: busy || msgs.length < 2 ? 0.6 : 1 }} disabled={busy || msgs.length < 2} onClick={runCheck}
          title="One model call: lists answers that contradict the notes or sound out of character">✓ CHECK AGAINST NOTES</button>
        <button className="signal-btn" style={btn} disabled={busy || !msgs.length} onClick={() => { setMsgs([]); setCheck(null); }}>CLEAR</button>
      </div>
      {check && (
        <div style={{ border: "1px solid var(--signal-border)", padding: "8px 10px", marginTop: 8, fontSize: 12.5 }}>
          <b>{check.verdict || (check.issues.length ? "Some answers drift." : "Consistent with the notes.")}</b>
          {check.issues.map((x, i) => <div key={i} style={{ marginTop: 4, color: red }}>• {x}</div>)}
          {check.issues.length > 0 && <div style={{ ...hint, marginTop: 6 }}>Fix the notes on the EDIT tab, or add a speech sample that shows the right behaviour.</div>}
        </div>
      )}
    </div>
  );
}

/** Opens a preview of the Quick Reply set built from a project, with DOWNLOAD (.json, for SillyTavern's Quick Reply
 *  import) and SEND TO SILLYTAVERN. kind: "text" | "lore". */
export function QuickRepliesButton({ kind, projectId, style, label = "QUICK REPLIES" }) {
  const [set, setSet] = useState(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  async function open() {
    setError(""); setStatus(null);
    try { setSet(await getQuickReplySet(kind, projectId)); } catch (e) { setError(e.message); }
  }
  function download() {
    const blob = new Blob([JSON.stringify(set, null, 4)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(set.name || "quick-replies").replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "-") || "quick-replies"}.json`;
    a.click(); URL.revokeObjectURL(a.href);
  }
  async function send() {
    setBusy(true); setStatus(null);
    try {
      const r = await pushQuickRepliesToST(set);
      setStatus({ ok: true, text: `Saved in SillyTavern as the set "${r.name}" (${r.count} buttons). Reload SillyTavern, then pick it under Extensions → Quick Reply.` });
    } catch (e) { setStatus({ ok: false, text: e.message }); }
    finally { setBusy(false); }
  }
  return (<>
    <button className="signal-btn" style={style} onClick={open} disabled={!projectId}
      title="A SillyTavern Quick Reply set: a button per place and character, plus recap / time skip helpers">
      ▤ {label}
    </button>
    {error && <span style={{ color: red, fontSize: 11, marginLeft: 6 }}>⊗ {error}</span>}
    {set && (<Portal>
      <div style={overlay} onClick={() => setSet(null)}>
        <div className="signal-panel" role="dialog" aria-label="Quick Replies" style={{ ...dialog, width: "min(640px, 100%)" }} onClick={(e) => e.stopPropagation()}>
          <h2 className="signal-heading" style={headingStyle}>QUICK REPLIES · {set.name}</h2>
          <div style={{ ...hint, marginTop: 0 }}>
            Buttons under the SillyTavern chat box. "→" moves the scene and "+" brings someone in (a narrator line, no reply
            is generated); the last ones ask the model for a recap or a scene check. Edit them freely in SillyTavern afterwards.
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, margin: "12px 0" }}>
            {set.qrList.map((q) => <span key={q.id} title={q.message} style={{ border: "1px solid var(--signal-border)", padding: "3px 8px", fontSize: 12 }}>{q.label}</span>)}
          </div>
          {status && <div role="status" style={{ fontSize: 12, color: status.ok ? "var(--signal-text)" : red }}>{status.ok ? "✓" : "⊗"} {status.text}</div>}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14, flexWrap: "wrap" }}>
            <button className="signal-btn" style={btn} onClick={() => setSet(null)}>CLOSE</button>
            <button className="signal-btn" style={btn} onClick={download}>↓ DOWNLOAD .JSON</button>
            <button className="signal-btn" style={{ ...btnPrimary, opacity: busy ? 0.6 : 1 }} disabled={busy} onClick={send}>{busy ? "SENDING…" : "⇢ SEND TO SILLYTAVERN"}</button>
          </div>
        </div>
      </div>
    </Portal>)}
  </>);
}

/** Story bible and Data Bank downloads for a TEXT ("text") or LORE ("lore") project. Plain GET links, no model call. */
export function StoryExportsButton({ kind, projectId, style, label = "STORY BIBLE / DATA BANK" }) {
  const [open, setOpen] = useState(false);
  const base = `/api/${kind === "lore" ? "lore" : "text"}/project/${projectId}`;
  const row = { display: "flex", gap: 12, alignItems: "flex-start", borderTop: "1px solid var(--signal-border)", padding: "10px 0" };
  const link = { ...btn, textDecoration: "none", color: "inherit", whiteSpace: "nowrap", display: "inline-block", minWidth: 150, textAlign: "center" };
  return (<>
    <button className="signal-btn" style={style} disabled={!projectId} onClick={() => setOpen(true)}
      title="Everything this project knows, as a document to read or print, or as notes for SillyTavern's Data Bank">
      ▥ {label}
    </button>
    {open && (<Portal>
      <div style={overlay} onClick={() => setOpen(false)}>
        <div className="signal-panel" role="dialog" aria-label="Story exports" style={{ ...dialog, width: "min(620px, 100%)" }} onClick={(e) => e.stopPropagation()}>
          <h2 className="signal-heading" style={headingStyle}>STORY BIBLE · DATA BANK</h2>
          <div style={{ ...hint, marginTop: 0, marginBottom: 6 }}>
            Built from the same entries that go to LORE{kind === "text" ? " (as of the starting point, if one is set)" : ""}: story so far, timeline,
            characters (main first), factions, places and the rest.
          </div>
          <div style={row}>
            <a className="signal-btn" style={link} href={`${base}/bible?format=html`} target="_blank" rel="noopener noreferrer">PRINTABLE PAGE</a>
            <div style={{ fontSize: 12 }}>Opens in a new tab with portraits. Use its PRINT button to print or save as PDF.</div>
          </div>
          <div style={row}>
            <a className="signal-btn" style={link} href={`${base}/bible?format=md`} download>↓ MARKDOWN (.md)</a>
            <div style={{ fontSize: 12 }}>One file for notes apps, Obsidian, or sharing.</div>
          </div>
          <div style={row}>
            <a className="signal-btn" style={link} href={`${base}/databank`} download>↓ DATA BANK (.zip)</a>
            <div style={{ fontSize: 12 }}>One note per entry for SillyTavern's Data Bank (wand menu → Open Data Bank), found by meaning
              with Vector Storage instead of keywords. Instructions are in the zip.</div>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
            <button className="signal-btn" style={btn} onClick={() => setOpen(false)}>CLOSE</button>
          </div>
        </div>
      </div>
    </Portal>)}
  </>);
}
