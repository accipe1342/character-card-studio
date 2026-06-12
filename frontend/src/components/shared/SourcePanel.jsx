import CodeMirror from "@uiw/react-codemirror";
import { json } from "@codemirror/lang-json";
import { EditorView } from "@codemirror/view";

const nierTheme = EditorView.theme({
  "&": {
    backgroundColor: "#e9e2cf",
    color: "var(--nier-text)",
  },
  ".cm-content": {
    fontFamily: '"Georgia", "Times New Roman", serif',
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  ".cm-scroller": {
    overflow: "auto",
    fontFamily: '"Georgia", "Times New Roman", serif',
  },
  ".cm-gutters": {
    backgroundColor: "#ddd4c2",
    color: "#6b6458",
    borderRight: "1px solid var(--nier-border)",
  },
  ".cm-activeLine": {
    backgroundColor: "rgba(60, 52, 40, 0.06)",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "rgba(60, 52, 40, 0.06)",
  },
  ".cm-selectionBackground": {
    backgroundColor: "rgba(80, 70, 55, 0.18) !important",
  },
});

function SourceBlock({ title, value }) {
  if (!value) return null;

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{title}</div>
      <div style={{ color: "#333", whiteSpace: "pre-wrap" }}>{value}</div>
    </div>
  );
}

function SourceList({ title, items }) {
  if (!Array.isArray(items) || items.length === 0) return null;

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{title}</div>
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {items.map((item, i) => (
          <li key={`${title}-${i}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export default function SourcePanel({ source }) {
  const normalized = source?.normalized ?? null;

  return (
    <section
      style={{
        border: "1px solid var(--nier-border)",
        background: "var(--nier-bg-panel)",
        padding: 14,
      }}
    >
      <h2 className="nier-heading" style={{ marginTop: 0 }}>Source</h2>

      {!normalized ? (
        <div style={{ color: "var(--nier-text-dim)" }}>
          Scrape a page to see normalized source data.
        </div>
      ) : (
        <>
          <SourceBlock title="Summary" value={normalized.summary} />
          <SourceList title="Appearance" items={normalized.appearance_list} />
          <SourceList
            title="Personality Traits"
            items={normalized.personality_traits}
          />
          <SourceList title="Abilities" items={normalized.abilities_list} />
          <SourceList title="History" items={normalized.history_list} />

          <details style={{ marginTop: 12 }}>
            <summary style={{ cursor: "pointer", marginBottom: 8 }}>
              Raw normalized JSON
            </summary>

            <div style={{ marginBottom: 8 }}>
              <button
                onClick={() =>
                  navigator.clipboard.writeText(
                    JSON.stringify(normalized, null, 2),
                  )
                }
                style={{
                  fontSize: 12,
                  padding: "4px 8px",
                  border: "1px solid var(--nier-border)",
                  background: "var(--nier-bg-btn)",
                  cursor: "pointer",
                }}
              >
                Copy
              </button>
            </div>

            <CodeMirror
              value={JSON.stringify(normalized, null, 2)}
              height="420px"
              extensions={[json(), EditorView.lineWrapping]}
              editable={false}
              theme={nierTheme}
              basicSetup={{
                lineNumbers: true,
                foldGutter: true,
                highlightActiveLine: false,
                highlightActiveLineGutter: false,
              }}
              style={{
                fontSize: 14,
                border: "1px solid var(--nier-border)",
              }}
            />
          </details>
        </>
      )}
    </section>
  );
}
