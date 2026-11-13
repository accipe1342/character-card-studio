/**
 * ProseScan.jsx — the Critic's instant prose scan (no model call): stock "AI-sounding" phrases, overused words,
 * filler, adverbs, dialogue tags, repeated sentence starts and habits models fall into ("not X, but Y", narrating
 * what doesn't happen, echoing the other speaker, em-dashes, paragraphs opening the same way), whole text and per chapter.
 */
import { useState } from "react";
import { btnTool, hint, panelStyle, headingStyle } from "./textUi";

const H3 = ({ children }) => <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.12em", margin: "16px 0 6px" }}>{children}</div>;
const chip = { display: "inline-block", border: "1px solid var(--signal-border)", padding: "2px 7px", margin: "0 4px 4px 0", fontSize: 12 };

function Examples({ list }) {
  return list.map((x, i) => <div key={i} style={{ fontSize: 12, opacity: 0.85, marginTop: 2 }}>{x.label && <span style={hint}>{x.label}: </span>}{x.excerpt}</div>);
}

function Habit({ title, why, count, extra, examples }) {
  return (
    <div style={{ border: "1px solid var(--signal-border)", padding: "6px 8px", marginBottom: 6 }}>
      <b>{title}</b> <span style={hint}>×{count}{extra ? ` · ${extra}` : ""}</span>
      <div style={{ ...hint, marginTop: 2 }}>{why}</div>
      {examples && <Examples list={examples} />}
    </div>
  );
}

export default function ProseScanModal({ res, name, onClose }) {
  const [sort, setSort] = useState("story");
  if (!res) return null;
  const per = [...(res.per_chunk || [])].sort((a, b) => (sort === "worst"
    ? (b.cliches_per1k + b.adverbs_per1k / 10 + b.filler_per1k / 10) - (a.cliches_per1k + a.adverbs_per1k / 10 + a.filler_per1k / 10)
    : a.idx - b.idx));
  const maxC = Math.max(0.01, ...per.map((p) => p.cliches_per1k));
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 300,
      display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "40px 16px", overflowY: "auto" }}>
      <div onClick={(e) => e.stopPropagation()} className="signal-panel" role="dialog" aria-label="Prose scan"
        style={{ ...panelStyle, width: "min(860px, 100%)", padding: 20, boxShadow: "0 8px 32px rgba(0,0,0,0.3)", fontSize: 13 }}>
        <h2 className="signal-heading" style={headingStyle}>PROSE SCAN · {name}</h2>
        <div style={{ ...hint, marginTop: 0 }}>
          Instant checks, no model call. These are things to look at, not rules: dialogue-heavy chapters naturally have more tags,
          and some genres use certain phrases on purpose. The phrase list is <code>backend/config/ai_cliches.txt</code>; edit it to taste.
        </div>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", margin: "12px 0", fontSize: 13 }}>
          <span><b>{res.words.toLocaleString()}</b> words</span>
          <span><b>{res.cliche_count}</b> stock phrases</span>
          <span><b>{res.adverbs.per1k}</b> -ly adverbs / 1k words</span>
          <span><b>{res.filler_per1k}</b> filler words / 1k</span>
          <span title="Share of dialogue tags that are not said/asked"><b>{Math.round(res.tags.fancy_share * 100)}%</b> fancy dialogue tags</span>
        </div>

        <H3>STOCK PHRASES</H3>
        {!res.cliches.length && <div style={hint}>None found.</div>}
        {res.cliches.map((c) => (
          <div key={c.phrase} style={{ border: "1px solid var(--signal-border)", padding: "6px 8px", marginBottom: 6 }}>
            <b>“{c.phrase.replaceAll("*", "…")}”</b> <span style={hint}>×{c.count}</span>
            {c.examples.map((x, i) => <div key={i} style={{ fontSize: 12, opacity: 0.85 }}>{x.label && <span style={hint}>{x.label}: </span>}{x.excerpt}</div>)}
          </div>
        ))}

        <H3>OVERUSED WORDS</H3>
        {!res.overused.length ? <div style={hint}>Nothing stands out.</div>
          : <div>{res.overused.map((w) => <span key={w.word} style={chip} title={`${w.per10k} per 10,000 words`}>{w.word} ×{w.count}</span>)}</div>}

        <H3>FILLER WORDS</H3>
        {!Object.keys(res.filler).length ? <div style={hint}>None.</div>
          : <div>{Object.entries(res.filler).map(([w, c]) => <span key={w} style={chip}>{w} ×{c}</span>)}</div>}

        <H3>ADVERBS</H3>
        <div>{res.adverbs.top.map((w) => <span key={w.word} style={chip}>{w.word} ×{w.count}</span>)}</div>

        <H3>DIALOGUE TAGS</H3>
        <div style={{ fontSize: 12 }}>
          said / asked: {res.tags.plain} · other tags: {res.tags.fancy}
          {res.tags.fancy_share > 0.5 && " · more than half are fancy tags: plain said lets the dialogue carry the emotion"}
        </div>
        {res.tags.top_fancy.length > 0 && <div style={{ marginTop: 4 }}>{res.tags.top_fancy.map((w) => <span key={w.word} style={chip}>{w.word} ×{w.count}</span>)}</div>}

        <H3>REPEATED SENTENCE STARTS</H3>
        {!res.repeated_starts.length && <div style={hint}>None.</div>}
        {res.repeated_starts.map((r, i) => (
          <div key={i} style={{ fontSize: 12, marginBottom: 4 }}>
            <b>{r.run}× “{r.word}”</b>{r.label && <span style={hint}> · {r.label}</span>}: {r.excerpt}
          </div>
        ))}

        {res.patterns && (() => {
          const p = res.patterns;
          const any = p.not_but.count || p.negations.count || p.echoes.count || p.dashes.per1k > 8 || p.para_starts.length;
          return (<>
            <H3>HABITS</H3>
            {!any && <div style={hint}>None stand out.</div>}
            {p.not_but.count > 0 && <Habit title="“Not X, but Y”" count={p.not_but.count} examples={p.not_but.examples}
              why="Emphasis by saying what something isn't (“It wasn't anger. It was something colder.”). Once is a choice; often is a habit. Say the thing directly." />}
            {p.negations.count > 0 && <Habit title="What doesn't happen" count={p.negations.count} extra={`${p.negations.per1k} / 1k`} examples={p.negations.examples}
              why="Narration of non-events (“she doesn't move”, “he didn't answer”). Say what they do instead: “she stays still”, “he looks at the floor”." />}
            {p.echoes.count > 0 && <Habit title="Echoed lines" count={p.echoes.count} examples={p.echoes.examples}
              why="A reply that repeats the other speaker's words as a question (“Are you new?” / “New?”). React to what was said instead." />}
            {p.dashes.per1k > 8 && <Habit title="Em-dashes" count={p.dashes.count} extra={`${p.dashes.per1k} / 1k words`}
              why="A few are fine; many in a row read as machine-written. Commas, full stops and parentheses do most of the same jobs." />}
            {p.para_starts.map((x, i) => <Habit key={i} title={`Paragraphs opening with “${x.word}”`} count={x.count} extra={`of ${x.of}${x.label ? ` · ${x.label}` : ""}`}
              why="Most paragraphs start the same way. Vary the openings: a line of dialogue, a place, a sound, someone else." />)}
          </>);
        })()}

        {per.length > 1 && (<>
          <H3>BY CHAPTER</H3>
          <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
            {[["story", "STORY ORDER"], ["worst", "WORST FIRST"]].map(([k, t]) => (
              <button key={k} className={sort === k ? "signal-btn signal-btn-active" : "signal-btn"} style={{ ...btnTool, padding: "4px 8px" }} onClick={() => setSort(k)}>{t}</button>
            ))}
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
              <thead><tr>{["Chapter", "Words", "Stock phrases", "/1k", "Adverbs /1k", "Filler /1k", "Fancy tags", "Repeated starts", "Not X, but Y", "Non-events", "Echoes", "Dashes /1k"].map((h) => (
                <th key={h} style={{ textAlign: h === "Chapter" ? "left" : "right", padding: "4px 6px", borderBottom: "1px solid var(--signal-border)" }}>{h}</th>))}</tr></thead>
              <tbody>{per.map((p) => (
                <tr key={p.idx}>
                  <td style={{ padding: "4px 6px", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.idx + 1}. {p.label}</td>
                  <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.words.toLocaleString()}</td>
                  <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.cliches}</td>
                  <td style={{ padding: "4px 6px", textAlign: "right" }}>
                    <span style={{ display: "inline-block", width: 40, height: 6, border: "1px solid var(--signal-border)", marginRight: 4, verticalAlign: "middle" }}>
                      <span style={{ display: "block", height: "100%", width: `${(p.cliches_per1k / maxC) * 100}%`, background: p.cliches_per1k > 1 ? "var(--signal-accent)" : "var(--signal-text)" }} />
                    </span>{p.cliches_per1k}
                  </td>
                  <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.adverbs_per1k}</td>
                  <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.filler_per1k}</td>
                  <td style={{ padding: "4px 6px", textAlign: "right" }}>{Math.round(p.fancy_tag_share * 100)}%</td>
                  <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.repeated_starts}</td>
                  <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.not_but ?? ""}</td>
                  <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.negations ?? ""}</td>
                  <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.echoes ?? ""}</td>
                  <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.dashes_per1k ?? ""}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </>)}
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
          <button className="signal-btn" style={btnTool} onClick={onClose}>CLOSE</button>
        </div>
      </div>
    </div>
  );
}
