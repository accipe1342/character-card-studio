/**
 * CriticPanel.jsx — the TEXT studio's critic, on its own (own model, own jobs; never touches extraction or lore).
 *   RUN CRITIQUE     verdict, scores, ranked problems, step-by-step plan, line fixes (whole text or one chapter)
 *   CHAPTER SWEEP    every part scored on its own, so the weakest chapters stand out
 *   SCORE HISTORY    average score of each critique over time
 *   REWRITE          a line fix or a sweep problem -> the paragraph rewritten with the fix applied
 */
import { useEffect, useState } from "react";
import { startCritique, listCritiques, getCritique, deleteCritique, startSweep, rewritePassage, getJob, getPresets } from "../../lib/api";
import { markBusy } from "../../lib/leaveGuard";
import { DEFAULT_MODELS, Divider, btnPrimary, btnTool, headingStyle, hint, input, label, panelStyle, toolbarGrid } from "./textUi";

function ScoreBar({ s }) {
  const v = Math.max(0, Math.min(10, Number(s.score) || 0));
  const col = v >= 8 ? "var(--signal-text)" : v >= 5 ? "#b8860b" : "#c84a3a";
  return (
    <div style={{ marginBottom: 6 }} title={s.why}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
        <span>{s.category}</span><b>{v}/10</b>
      </div>
      <div style={{ height: 6, border: "1px solid var(--signal-border)", background: "var(--signal-bg-input)" }}>
        <div style={{ width: `${v * 10}%`, height: "100%", background: col }} />
      </div>
    </div>
  );
}

const scoreColor = (v) => (v >= 8 ? "var(--signal-text)" : v >= 5 ? "#b8860b" : "#c84a3a");

/** Average score per critique, oldest to newest. */
function ScoreHistory({ critiques, onOpen, currentId }) {
  const pts = [...critiques].reverse().filter((c) => c.avg != null);
  if (pts.length < 2) return null;
  const w = 100 / Math.max(1, pts.length);
  return (
    <div style={{ marginTop: 10 }} aria-label="Score history">
      <div style={label}>SCORE HISTORY</div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 64, borderBottom: "1px solid var(--signal-border)" }}>
        {pts.map((c) => (
          <button key={c.id} type="button" onClick={() => onOpen(c.id)}
            title={`${c.scope}${c.focus ? ` · ${c.focus}` : ""} · ${String(c.created_at).slice(0, 16)} · ${c.avg}/10`}
            aria-label={`${c.scope} ${c.avg} out of 10`}
            style={{ flex: `0 1 ${w}%`, minWidth: 6, height: `${Math.max(6, c.avg * 10)}%`, padding: 0, cursor: "pointer",
              border: currentId === c.id ? "2px solid var(--signal-text)" : "1px solid var(--signal-border)",
              background: scoreColor(c.avg), opacity: c.kind === "sweep" ? 0.65 : 1 }} />
        ))}
      </div>
      <div style={{ ...hint, display: "flex", justifyContent: "space-between" }}>
        <span>first {pts[0].avg}</span><span>latest {pts[pts.length - 1].avg}{pts.length > 1 && ` (${pts[pts.length - 1].avg - pts[0].avg >= 0 ? "+" : ""}${(pts[pts.length - 1].avg - pts[0].avg).toFixed(1)})`}</span>
      </div>
    </div>
  );
}

function RewriteBox({ projectId, quote, fix, provider, model }) {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [error, setError] = useState("");
  async function go() {
    setBusy(true); setError("");
    try { setRes(await rewritePassage(projectId, { quote, fix, provider, model })); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return (
    <div style={{ marginTop: 4 }}>
      {!res && (
        <button className="signal-btn" style={{ ...btnTool, padding: "4px 8px", fontSize: 10 }} disabled={busy} onClick={go}
          title="Find this line in the text and rewrite its paragraph with the fix applied. Your text is not changed.">
          {busy ? "REWRITING…" : "✎ REWRITE THE PASSAGE"}
        </button>
      )}
      {error && <div style={{ color: "#c84a3a", fontSize: 11 }}>⊗ {error}</div>}
      {res && (
        <div style={{ borderLeft: "3px solid var(--signal-text)", padding: "4px 8px", marginTop: 4, fontSize: 12 }}>
          <div style={{ ...hint, marginTop: 0 }}>{res.found ? `From ${res.label}` : "Line not found in the text: rewrote the quote alone"}{res.notes ? ` · ${res.notes}` : ""}</div>
          <details><summary style={{ cursor: "pointer", fontSize: 11 }}>Original</summary>
            <div style={{ whiteSpace: "pre-wrap", opacity: 0.75 }}>{res.original}</div></details>
          <div style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>{res.rewrite}</div>
          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <button className="signal-btn" style={{ ...btnTool, padding: "4px 8px", fontSize: 10 }}
              onClick={() => navigator.clipboard?.writeText(res.rewrite)}>COPY</button>
            <button className="signal-btn" style={{ ...btnTool, padding: "4px 8px", fontSize: 10 }} onClick={() => setRes(null)}>AGAIN</button>
          </div>
        </div>
      )}
    </div>
  );
}

function SweepTable({ rows, projectId, provider, model }) {
  const [sort, setSort] = useState("story");
  const list = [...rows].sort((a, b) => (sort === "worst" ? (a.score || 99) - (b.score || 99) : a.idx - b.idx));
  return (
    <div>
      <div style={{ display: "flex", gap: 6, margin: "8px 0" }}>
        {[["story", "STORY ORDER"], ["worst", "WEAKEST FIRST"]].map(([k, t]) => (
          <button key={k} className={sort === k ? "signal-btn signal-btn-active" : "signal-btn"} style={{ ...btnTool, padding: "4px 8px" }} onClick={() => setSort(k)}>{t}</button>
        ))}
      </div>
      {list.map((r) => (
        <div key={r.idx} style={{ border: "1px solid var(--signal-border)", padding: "6px 8px", marginBottom: 6 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <b style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.idx + 1}. {r.label}</b>
            {r.score ? <span style={{ fontWeight: 700, color: scoreColor(r.score) }}>{r.score}/10</span> : <span style={hint}>not scored</span>}
          </div>
          {r.score > 0 && (
            <div style={{ height: 4, border: "1px solid var(--signal-border)", margin: "4px 0" }}>
              <div style={{ width: `${r.score * 10}%`, height: "100%", background: scoreColor(r.score) }} />
            </div>
          )}
          {r.error && <div style={{ fontSize: 11, color: "#c84a3a" }}>⊗ {r.error}</div>}
          {r.summary && <div style={{ fontSize: 12 }}>{r.summary}</div>}
          {r.worst && <div style={{ fontSize: 12 }}><b>Worst:</b> {r.worst}{r.quote && <i style={{ opacity: 0.8 }}> “{r.quote}”</i>}</div>}
          {r.fix && <div style={{ fontSize: 12 }}><b>Fix:</b> {r.fix}</div>}
          {r.best && <div style={{ fontSize: 12, color: "var(--signal-text-dim)" }}><b>Best:</b> {r.best}</div>}
          {r.quote && <RewriteBox projectId={projectId} quote={r.quote} fix={`${r.worst}. ${r.fix}`} provider={provider} model={model} />}
        </div>
      ))}
    </div>
  );
}

function CritiqueBody({ c, full, projectId, provider, model }) {
  const r = c.result || {};
  const H3 = ({ children }) => <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", margin: "14px 0 6px" }}>{children}</div>;
  const avg = (r.scores || []).length ? ((r.scores.reduce((a, x) => a + (Number(x.score) || 0), 0)) / r.scores.length).toFixed(1) : null;
  return (
    <div style={{ fontSize: 13, lineHeight: 1.55, textAlign: "left" }}>
      <div style={{ fontSize: 11, color: "var(--signal-text-dim)" }}>{c.scope}{c.focus ? ` · focus: ${c.focus}` : ""} · {c.created_at}</div>
      <H3>VERDICT {avg && <span style={{ fontWeight: 400 }}>· average {avg}/10</span>}</H3>
      <div>{r.verdict}</div>
      {(r.scores || []).length > 0 && (<><H3>SCORES</H3>{r.scores.map((x, i) => <ScoreBar key={i} s={x} />)}</>)}
      {full && r.sweep && (<><H3>PART BY PART</H3><SweepTable rows={r.sweep} projectId={projectId} provider={provider} model={model} /></>)}
      {full && (<>
        {(r.strengths || []).length > 0 && (<><H3>WHAT ACTUALLY WORKS</H3><ul style={{ margin: 0, paddingLeft: 18 }}>{r.strengths.map((x, i) => <li key={i}>{x}</li>)}</ul></>)}
        {(r.problems || []).length > 0 && (<><H3>THE BIGGEST PROBLEMS</H3>
          <ol style={{ margin: 0, paddingLeft: 20 }}>{r.problems.map((x, i) => (
            <li key={i} style={{ marginBottom: 8 }}><b>{x.title}</b>
              {x.evidence && <div style={{ fontStyle: "italic", opacity: 0.85 }}>“{x.evidence}”</div>}
              {x.why && <div>{x.why}</div>}
              {x.fix && <div><b>Fix:</b> {x.fix}</div>}
              {x.evidence && <RewriteBox projectId={projectId} quote={x.evidence} fix={`${x.title}. ${x.fix || ""}`} provider={provider} model={model} />}
            </li>))}</ol></>)}
        {(r.plan || []).length > 0 && (<><H3>STEP-BY-STEP IMPROVEMENT PLAN</H3>
          <ol style={{ margin: 0, paddingLeft: 20 }}>{r.plan.map((x, i) => <li key={i} style={{ marginBottom: 6 }}><b>{x.step}</b>: {x.how}</li>)}</ol></>)}
        {(r.line_fixes || []).length > 0 && (<><H3>LINE-LEVEL FIXES</H3>
          {r.line_fixes.map((x, i) => (
            <div key={i} style={{ border: "1px solid var(--signal-border)", padding: "6px 8px", marginBottom: 6 }}>
              <div style={{ textDecoration: "line-through", opacity: 0.7 }}>{x.original}</div>
              <div><b>→</b> {x.rewrite}</div>
              {x.why && <div style={{ fontSize: 11, color: "var(--signal-text-dim)" }}>{x.why}</div>}
              <RewriteBox projectId={projectId} quote={x.original} fix={`Apply this kind of fix to the whole paragraph: "${x.rewrite}". ${x.why || ""}`} provider={provider} model={model} />
            </div>))}</>)}
        {(r.top3 || []).length > 0 && (<><H3>IF YOU ONLY FIX THREE THINGS</H3>
          <ol style={{ margin: 0, paddingLeft: 20 }}>{r.top3.map((x, i) => <li key={i}>{x}</li>)}</ol></>)}
      </>)}
    </div>
  );
}

export default function CriticPanel({ project, parallel = 3, showToast, setError, t = {} }) {
  const [critScope, setCritScope] = useState("all");
  const [critFocus, setCritFocus] = useState("");
  const [critProvider, setCritProvider] = useState("nanogpt");
  const [critModel, setCritModel] = useState(DEFAULT_MODELS.nanogpt);
  const [critJobId, setCritJobId] = useState(null);
  const [critJob, setCritJob] = useState(null);
  const [critiques, setCritiques] = useState([]);
  const [critView, setCritView] = useState(null);
  const [critOpen, setCritOpen] = useState(false);

  useEffect(() => { markBusy("critic", !!critJobId); return () => markBusy("critic", false); }, [critJobId]);
  useEffect(() => {
    getPresets().then((p) => { if (p?.critic?.model) { setCritProvider(p.critic.provider || "nanogpt"); setCritModel(p.critic.model); } }).catch(() => {});
  }, []);
  useEffect(() => {
    setCritView(null); setCritOpen(false); setCritScope("all");
    if (project?.id) loadCritiques(project.id, true); else setCritiques([]);
  }, [project?.id]);

  async function loadCritiques(id, openLatest = false) {
    try {
      const list = await listCritiques(id);
      setCritiques(list);
      if (openLatest) setCritView(list.length ? await getCritique(list[0].id) : null);
    } catch { setCritiques([]); }
  }

  // job poller (independent of the extraction job)
  useEffect(() => {
    if (!critJobId) return;
    const iv = setInterval(async () => {
      try {
        const j = await getJob(critJobId);
        setCritJob(j);
        if (j.status === "done" || j.status === "failed") {
          clearInterval(iv);
          setCritJobId(null);
          if (j.status === "failed") setError(`Critic: ${j.error || j.message || "failed"}`);
          else if (project) {
            await loadCritiques(project.id);
            setCritView(await getCritique(j.result.critique_id)); setCritOpen(true);
          }
        }
      } catch { /* keep polling */ }
    }, 1000);
    return () => clearInterval(iv);
  }, [critJobId]);

  function chapterGroups() {
    const g = [];
    for (const c of project?.chunks || []) {
      const key = c.label.split(" (part ")[0];
      const last = g[g.length - 1];
      if (last && last.key === key) last.idx.push(c.idx); else g.push({ key, idx: [c.idx] });
    }
    return g;
  }
  async function runCritique() {
    if (!project) return;
    setError("");
    const g = critScope === "all" ? null : chapterGroups()[parseInt(critScope, 10)];
    try {
      const res = await startCritique(project.id, {
        provider: critProvider, model: critModel, focus: critFocus, parallel,
        chunks: g ? g.idx : [], scope_label: g ? g.key : "Whole text",
      });
      setCritJob({ status: "running", progress: 2, message: "Starting the critic..." });
      setCritJobId(res.job_id);
    } catch (e) { setError(e.message); }
  }
  async function runSweep() {
    if (!project) return;
    if (!window.confirm(`Score all ${project.chunks.length} parts one by one? One model call per part.`)) return;
    setError("");
    try {
      const res = await startSweep(project.id, { provider: critProvider, model: critModel, parallel });
      setCritJob({ status: "running", progress: 2, message: "Starting the sweep..." });
      setCritJobId(res.job_id);
    } catch (e) { setError(e.message); }
  }
  async function removeCritique(id) {
    try {
      await deleteCritique(id);
      if (critView?.id === id) { setCritView(null); setCritOpen(false); }
      await loadCritiques(project.id);
    } catch (e) { setError(e.message); }
  }
  function downloadCritique() {
    if (!critView) return;
    const blob = new Blob([critView.result.markdown || ""], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `critique-${(project?.name || "text").replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "-")}-${critView.id}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <>
      <section className="signal-panel signal-panel-delay-2" style={panelStyle}>
        <h2 className="signal-heading" style={headingStyle}>CRITIC</h2>
        {!project && (
          <div style={{ color: "var(--signal-text-dim)", fontSize: 12, textAlign: "center", padding: "6px 0" }}>
            Pick a text above to have it torn apart, then rebuilt step by step.
          </div>
        )}
        {project && (<>
          <div style={{ ...hint, marginTop: 0 }}>
            A brutally honest editor: verdict, scores, ranked problems with quotes, a step-by-step plan and line rewrites.
            Runs on its own; it does not touch extraction or the lorebook.
          </div>
          <div style={label}>SCOPE</div>
          <select style={input} value={critScope} onChange={(e) => setCritScope(e.target.value)} aria-label="Critique scope">
            <option value="all">Whole text ({project.chunks.length} parts)</option>
            {chapterGroups().map((g, i) => <option key={i} value={i}>{g.key}{g.idx.length > 1 ? ` (${g.idx.length} parts)` : ""}</option>)}
          </select>
          <div style={label}>FOCUS</div>
          <select style={input} value={critFocus} onChange={(e) => setCritFocus(e.target.value)} aria-label="Critique focus">
            <option value="">Everything</option>
            <option value="prose and style">Prose & style</option>
            <option value="dialogue and character voice">Dialogue & voice</option>
            <option value="characterization and canon accuracy">Characters & canon</option>
            <option value="plot, structure and pacing">Plot & pacing</option>
            <option value="grammar, spelling, punctuation and formatting">Grammar & mechanics</option>
          </select>
          <div style={label}>MODEL</div>
          <div style={{ display: "flex", gap: 6 }}>
            <select style={{ ...input, width: "auto" }} value={critProvider} aria-label="Critic provider"
              onChange={(e) => { setCritProvider(e.target.value); setCritModel(DEFAULT_MODELS[e.target.value] || ""); }}>
              <option value="nanogpt">NanoGPT</option>
              <option value="openrouter">OpenRouter</option>
              <option value="local">Local</option>
            </select>
            <input style={{ ...input, flex: 1, minWidth: 0 }} list="text-models" value={critModel} onChange={(e) => setCritModel(e.target.value)} placeholder="Model" aria-label="Critic model" />
          </div>
          <div style={hint}>A stronger model gives sharper critique; the whole text takes one call per part plus one.</div>
          <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <button className="signal-btn" style={{ ...btnPrimary, flex: "2 1 150px", opacity: critJobId ? 0.6 : 1 }} disabled={!!critJobId} onClick={runCritique}>
              {critJobId ? "CRITIC AT WORK…" : `☠ ${(t.runCritique || "Run critique").toUpperCase()}`}
            </button>
            <button className="signal-btn" style={{ ...btnTool, flex: "1 1 130px", opacity: critJobId ? 0.6 : 1 }} disabled={!!critJobId} onClick={runSweep}
              title="Score every part on its own, so the weakest chapters stand out">
              ▤ {(t.chapterSweep || "Chapter sweep").toUpperCase()}
            </button>
          </div>
          {critJobId && critJob && (
            <div style={{ marginTop: 8 }}>
              <div style={{ height: 4, border: "1px solid var(--signal-border)" }}>
                <div style={{ width: `${critJob.progress || 0}%`, height: "100%", background: "var(--signal-text)", transition: "width .3s" }} />
              </div>
              <div style={{ ...hint, marginTop: 4 }}>{critJob.message}</div>
            </div>
          )}

          {critView && (<>
            <Divider label="LATEST VERDICT" style={{ marginTop: 14 }} />
            <CritiqueBody c={critView} full={false} projectId={project.id} provider={critProvider} model={critModel} />
            <div style={{ ...toolbarGrid, marginTop: 8 }}>
              <button className="signal-btn" style={btnTool} onClick={() => setCritOpen(true)}>OPEN FULL {critView.result?.sweep ? "SWEEP" : "CRITIQUE"}</button>
              <button className="signal-btn" style={btnTool} onClick={downloadCritique}>↓ .MD</button>
            </div>
          </>)}
          <ScoreHistory critiques={critiques} currentId={critView?.id} onOpen={async (id) => setCritView(await getCritique(id))} />
          {critiques.length > 1 && (<>
            <div style={label}>EARLIER CRITIQUES</div>
            <div style={{ maxHeight: 140, overflowY: "auto", border: "1px solid var(--signal-border)" }}>
              {critiques.map((c) => (
                <div key={c.id} style={{ display: "flex", gap: 6, alignItems: "center", padding: "5px 8px", fontSize: 11,
                  borderBottom: "1px solid var(--signal-border)", cursor: "pointer",
                  background: critView?.id === c.id ? "var(--signal-btn-active-bg)" : "transparent",
                  color: critView?.id === c.id ? "var(--signal-btn-active-text)" : "var(--signal-text)" }}
                  onClick={async () => setCritView(await getCritique(c.id))}>
                  <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {c.scope}{c.focus ? ` · ${c.focus}` : ""} · {String(c.created_at).slice(0, 16)}{c.avg != null ? ` · ${c.avg}/10` : ""}
                  </span>
                  <button className="signal-btn" onClick={(ev) => { ev.stopPropagation(); removeCritique(c.id); }} aria-label="Delete critique"
                    style={{ background: "none", border: "none", color: "#c84a3a", padding: "0 4px", cursor: "pointer", fontFamily: "inherit" }} title="Delete">✕</button>
                </div>
              ))}
            </div>
          </>)}
        </>)}
      </section>

      {critOpen && critView && (
        <div onClick={() => setCritOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 300,
          display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "40px 16px", overflowY: "auto" }}>
          <div onClick={(e) => e.stopPropagation()} className="signal-panel" role="dialog" aria-label="Critique"
            style={{ ...panelStyle, width: "min(860px, 100%)", padding: 20, boxShadow: "0 8px 32px rgba(0,0,0,0.3)" }}>
            <h2 className="signal-heading" style={headingStyle}>{critView.result?.sweep ? "CHAPTER SWEEP" : "CRITIQUE"} · {project?.name}</h2>
            <CritiqueBody c={critView} full projectId={project.id} provider={critProvider} model={critModel} />
            <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end", flexWrap: "wrap" }}>
              <button className="signal-btn" style={btnTool} onClick={() => { navigator.clipboard?.writeText(critView.result.markdown || ""); showToast && showToast("Critique copied"); }}>COPY</button>
              <button className="signal-btn" style={btnTool} onClick={downloadCritique}>↓ DOWNLOAD .MD</button>
              <button className="signal-btn" style={btnTool} onClick={() => setCritOpen(false)}>CLOSE</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
