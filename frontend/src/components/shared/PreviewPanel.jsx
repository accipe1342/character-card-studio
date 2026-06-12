import { useRef, useState } from "react";

// ── PNG tEXt chunk injector ───────────────────────────────────────────────────
// SillyTavern expects: tEXt chunk with key="chara", value=base64(JSON)
// Must be inserted before the IEND chunk.

function crc32(buf) {
  const table = crc32.table || (crc32.table = (() => {
    const t = new Uint32Array(256);
    for (let i = 0; i < 256; i++) {
      let c = i;
      for (let j = 0; j < 8; j++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      t[i] = c;
    }
    return t;
  })());
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) crc = table[(crc ^ buf[i]) & 0xFF] ^ (crc >>> 8);
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

function makeTEXtChunk(keyword, text) {
  const enc = new TextEncoder();
  const kw = enc.encode(keyword);
  const tx = enc.encode(text);
  const data = new Uint8Array(kw.length + 1 + tx.length);
  data.set(kw);
  data[kw.length] = 0; // null separator
  data.set(tx, kw.length + 1);

  const type = new Uint8Array([116, 69, 88, 116]); // "tEXt"
  const forCrc = new Uint8Array(type.length + data.length);
  forCrc.set(type); forCrc.set(data, type.length);
  const checksum = crc32(forCrc);

  const chunk = new Uint8Array(4 + 4 + data.length + 4);
  const view = new DataView(chunk.buffer);
  view.setUint32(0, data.length, false);
  chunk.set(type, 4);
  chunk.set(data, 8);
  view.setUint32(8 + data.length, checksum, false);
  return chunk;
}

function injectCharaChunk(pngBytes, cardJson) {
  // base64-encode the JSON (SillyTavern spec)
  const b64 = btoa(unescape(encodeURIComponent(JSON.stringify(cardJson))));
  const textChunk = makeTEXtChunk("chara", b64);

  // Find IEND chunk (last 12 bytes of a valid PNG)
  const iend = new Uint8Array([73, 69, 78, 68]); // "IEND"
  let iendPos = -1;
  for (let i = pngBytes.length - 12; i >= 0; i--) {
    if (pngBytes[i+4] === iend[0] && pngBytes[i+5] === iend[1] &&
        pngBytes[i+6] === iend[2] && pngBytes[i+7] === iend[3]) {
      iendPos = i;
      break;
    }
  }
  if (iendPos === -1) throw new Error("Could not find IEND chunk in PNG");

  const out = new Uint8Array(pngBytes.length + textChunk.length);
  out.set(pngBytes.slice(0, iendPos));
  out.set(textChunk, iendPos);
  out.set(pngBytes.slice(iendPos), iendPos + textChunk.length);
  return out;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function PreviewPanel({ imageFile, imageUrl, onImageChange, card, t = {} }) {
  const canvasRef = useRef(null);
  const [includeFields, setIncludeFields] = useState(false);
  const [viewMode, setViewMode] = useState("natural");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");

  async function handleExportPng() {
    if (!card) return;
    setExporting(true);
    setExportError("");

    try {
      const canvas = canvasRef.current;
      const ctx = canvas.getContext("2d");
      const W = 600;
      const PADDING = 28;
      const LINE_H = 22;

      // ── collect fields if requested ──────────────────────
      const sections = [];
      if (includeFields) {
        if (viewMode === "natural") {
          for (const f of ["description","personality","scenario","first_mes","mes_example"]) {
            const v = card[f];
            if (v?.trim()) sections.push({ label: f.replaceAll("_"," ").toUpperCase(), value: String(v) });
          }
          if (card.tags?.length) sections.push({ label: "TAGS", value: card.tags.join(" · ") });
        } else {
          const sp = card.structured_profile || {};
          const order = ["age","sex","gender","species","race","pronouns","sexual_attraction",
            "job_occupation","height","weight","relationship_status","relationship_to_user",
            "backstory","personality_traits","appearance","clothing","accessories",
            "speech","likes","dislikes","loves","hates","kinks"];
          for (const k of order) {
            const v = sp[k];
            if (!v || (Array.isArray(v) && !v.length)) continue;
            const d = Array.isArray(v) ? v.join(", ") : String(v);
            if (d.trim()) sections.push({ label: k.replaceAll("_"," ").toUpperCase(), value: d });
          }
        }
      }

      // ── measure text height ──────────────────────────────
      const IMG_H = 800;
      const textW = W - PADDING * 2;

      function measureWrapped(ctx, text, maxW, lineH) {
        const words = text.split(/\s+/);
        let lines = 1, line = "";
        for (const w of words) {
          const t = line ? line + " " + w : w;
          if (ctx.measureText(t).width > maxW && line) { lines++; line = w; }
          else line = t;
        }
        return lines * lineH;
      }

      // Temp canvas to measure
      const tmp = document.createElement("canvas");
      tmp.width = W;
      const tmpCtx = tmp.getContext("2d");

      let textH = 0;
      if (sections.length) {
        textH += PADDING + 36 + 14; // name + underline
        for (const s of sections) {
          tmpCtx.font = `${14}px Arial`;
          textH += LINE_H + measureWrapped(tmpCtx, s.value, textW, LINE_H) + 18;
        }
        textH += PADDING;
      }

      const TOTAL_H = IMG_H + textH;
      canvas.width = W;
      canvas.height = TOTAL_H;

      // ── background ──────────────────────────────────────
      ctx.fillStyle = "#efe8d8";
      ctx.fillRect(0, 0, W, TOTAL_H);

      // ── image ───────────────────────────────────────────
      let actualImgH = IMG_H;
      if (imageUrl) {
        const img = new Image();
        img.crossOrigin = "anonymous";
        await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = imageUrl; });
        // Scale image to fill width, preserving aspect ratio (no cropping)
        const scale = W / img.naturalWidth;
        const sw = W;
        const sh = img.naturalHeight * scale;
        actualImgH = Math.round(sh);
        canvas.height = actualImgH + textH;
        // Redraw background for new height
        ctx.fillStyle = "#efe8d8";
        ctx.fillRect(0, 0, W, actualImgH + textH);
        ctx.drawImage(img, 0, 0, sw, sh);
      } else {
        ctx.fillStyle = "#ddd4c2";
        ctx.fillRect(0, 0, W, IMG_H);
        ctx.fillStyle = "#888"; ctx.font = "16px Arial"; ctx.textAlign = "center";
        ctx.fillText("No image", W / 2, IMG_H / 2);
      }

      // ── gradient fade into text ──────────────────────────
      if (textH > 0) {
        const fadeH = Math.min(120, actualImgH * 0.2);
        const g = ctx.createLinearGradient(0, actualImgH - fadeH, 0, actualImgH);
        g.addColorStop(0, "rgba(239,232,216,0)");
        g.addColorStop(1, "rgba(239,232,216,1)");
        ctx.fillStyle = g;
        ctx.fillRect(0, actualImgH - fadeH, W, fadeH);
      }

      // ── text ─────────────────────────────────────────────
      if (sections.length) {
        let y = actualImgH + PADDING;
        ctx.textAlign = "left";

        ctx.font = "bold 26px Arial"; ctx.fillStyle = "#2b2b2b";
        ctx.fillText(card.name || "Character", PADDING, y + 22); y += 32;
        ctx.strokeStyle = "#3a3a3a"; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(PADDING, y); ctx.lineTo(W - PADDING, y); ctx.stroke();
        y += 14;

        for (const { label, value } of sections) {
          ctx.font = `bold 11px Arial`; ctx.fillStyle = "#888";
          ctx.fillText(label, PADDING, y); y += LINE_H;
          ctx.font = "14px Arial"; ctx.fillStyle = "#2b2b2b";
          const words = value.split(/\s+/);
          let line = "";
          for (const w of words) {
            const t = line ? line + " " + w : w;
            if (ctx.measureText(t).width > textW && line) {
              ctx.fillText(line, PADDING, y); y += LINE_H; line = w;
            } else line = t;
          }
          if (line) { ctx.fillText(line, PADDING, y); y += LINE_H; }
          y += 18;
        }
      }

      // ── border ───────────────────────────────────────────
      ctx.strokeStyle = "#3a3a3a"; ctx.lineWidth = 1.5;
      ctx.strokeRect(1, 1, W - 2, actualImgH + textH - 2);

      // ── embed chara JSON metadata & download ─────────────
      const dataUrl = canvas.toDataURL("image/png");
      const base64 = dataUrl.split(",")[1];
      const binary = atob(base64);
      const pngBytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) pngBytes[i] = binary.charCodeAt(i);

      const withMeta = injectCharaChunk(pngBytes, card);
      const blob = new Blob([withMeta], { type: "image/png" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(card.name || "card").replace(/\s+/g, "_")}.card.png`;
      a.click();
      URL.revokeObjectURL(url);

    } catch (e) {
      setExportError(e.message);
    } finally {
      setExporting(false);
    }
  }

  const btnStyle = {
    padding: "9px 14px",
    border: "1px solid var(--nier-border)",
    background: "var(--nier-bg-btn)",
    color: "var(--nier-text)",
    cursor: "pointer",
    fontFamily: "inherit",
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: "0.06em",
  };

  return (
    <section className="nier-panel nier-screen-panel" style={{ border: "1px solid var(--nier-border)", background: "var(--nier-bg-panel)", padding: 14, position: "relative" }}>
      <h2 className="nier-heading" style={{ marginTop: 0 }}>{t.preview || "Preview"}</h2>

      <label style={{
        display: "grid", placeItems: "center", minHeight: 48,
        border: "1px dashed #3a3a3a", marginBottom: 12,
        cursor: "pointer", background: "var(--nier-bg-field)",
      }}>
        <input type="file" accept="image/*" onChange={onImageChange} style={{ display: "none" }} />
        <span>{t.uploadImage || "Upload character image"}</span>
      </label>

      <div
        style={{
          width: "100%", aspectRatio: "3 / 4",
          border: "1px solid var(--nier-border)", background: "var(--nier-bg-mid)",
          overflow: "hidden", marginBottom: 10,
          transition: "opacity 0.25s ease",
          cursor: "default",
        }}
        onMouseEnter={(e) => e.currentTarget.style.opacity = "0.72"}
        onMouseLeave={(e) => e.currentTarget.style.opacity = "1"}
      >
        {imageUrl ? (
          <img src={imageUrl} alt={imageFile?.name || t.preview || "Preview"}
            style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <div style={{ width: "100%", height: "100%", display: "grid", placeItems: "center", color: "var(--nier-text-dim)" }}>
            {t.noImage || "No image uploaded yet"}
          </div>
        )}
      </div>

      <div style={{ color: "var(--nier-text-dim)", fontSize: 13, marginBottom: 12 }}>
        {imageFile ? `Selected: ${imageFile.name}` : (t.uploadHint || "Upload art, portrait, or cover image.")}
      </div>

      {/* Export error */}
      {exportError && (
        <div style={{
          border: "1px solid #7f1d1d", background: "#2a0a0a",
          color: "#fca5a5", padding: "10px 12px", marginBottom: 10, fontSize: 13,
          display: "flex", gap: 8, alignItems: "flex-start",
        }}>
          <span style={{ fontSize: 16, lineHeight: 1 }}>⊗</span>
          <div>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>Export Failed</div>
            <div>{exportError}</div>
          </div>
        </div>
      )}

      {card && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "center" }}>

          {/* Optional fields toggle */}
          <label style={{
            display: "flex", alignItems: "center", gap: 8,
            cursor: "pointer", fontSize: 13, color: "var(--nier-text)", userSelect: "none",
            justifyContent: "center",
          }}>
            <span style={{
              width: 16, height: 16, flexShrink: 0,
              border: "1.5px solid #3a3a3a",
              background: includeFields ? "#2b2b2b" : "#f7f2e7",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              {includeFields && (
                <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                  <path d="M1 3.5L3.5 6.5L9 1" stroke="#f5f1e8" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              )}
            </span>
            <input type="checkbox" checked={includeFields}
              onChange={e => setIncludeFields(e.target.checked)} style={{ display: "none" }} />
            {t.includeFields || "Include fields in image"}
          </label>

          {/* View mode toggle (only shown if fields included) */}
          {includeFields && (
            <div style={{ display: "flex", gap: 6 }}>
              {["natural", "structured"].map(m => (
                <button key={m}
                  className={viewMode === m ? "nier-btn nier-btn-active" : "nier-btn"}
                  onClick={() => setViewMode(m)}
                  style={{ ...btnStyle, padding: "6px 10px", fontSize: 12 }}>
                  {m.toUpperCase()}
                </button>
              ))}
            </div>
          )}

          {/* Export button */}
          <button className="nier-btn" onClick={handleExportPng} disabled={exporting}
            style={{
              ...btnStyle,
              width: "100%",
              background: "var(--nier-btn-active-bg)", color: "var(--nier-text-inv)",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              opacity: exporting ? 0.6 : 1,
              cursor: exporting ? "not-allowed" : "pointer",
            }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="1" y="1" width="12" height="12" stroke="currentColor" strokeWidth="1.2"/>
              <line x1="7" y1="3" x2="7" y2="9" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
              <polyline points="4.5,6.5 7,9.5 9.5,6.5" stroke="currentColor" strokeWidth="1.2"
                strokeLinecap="round" strokeLinejoin="round" fill="none"/>
              <line x1="3.5" y1="11" x2="10.5" y2="11" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
            </svg>
            {exporting ? (t.exporting || "EXPORTING…") : (t.exportPng || "EXPORT AS .CARD.PNG")}
          </button>
        </div>
      )}

      <canvas ref={canvasRef} style={{ display: "none" }} />
    </section>
  );
}
