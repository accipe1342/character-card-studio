import { useEffect, useState } from "react";

const THINKING_LINES = [
  "Analyzing source data...",
  "Constructing character profile...",
  "Calibrating personality matrix...",
  "Cross-referencing canon data...",
  "Synthesizing behavioral patterns...",
  "Compiling character history...",
  "Processing relationship data...",
  "Generating dialogue samples...",
  "Finalizing character schema...",
  "Running consistency checks...",
];

const LORE_THINKING_LINES = [
  "Parsing wiki content...",
  "Identifying lore entities...",
  "Extracting key relationships...",
  "Classifying entry types...",
  "Generating trigger keywords...",
  "Writing lore entries...",
  "Cross-referencing factions...",
  "Mapping world connections...",
  "Finalizing lorebook schema...",
  "Validating entry content...",
];

export default function MainJobStatus({ job, mode = "character" }) {
  const [thinkIdx, setThinkIdx] = useState(0);
  const [smoothProgress, setSmoothProgress] = useState(0);

  const isThinking = job?.stage === "requesting_model" &&
    job?.status !== "done" && job?.status !== "failed";
  const isFailed = job?.status === "failed";
  const isDone = job?.status === "done";

  const lines = mode === "lore" ? LORE_THINKING_LINES : THINKING_LINES;

  // Cycle thinking text
  useEffect(() => {
    if (!isThinking) return;
    const id = setInterval(() => setThinkIdx(p => (p + 1) % lines.length), 2200);
    return () => clearInterval(id);
  }, [isThinking, lines.length]);

  // Sync to real progress — only move forward, cap at 89 until truly done
  useEffect(() => {
    if (!job) return;
    const id = setTimeout(() => {
      setSmoothProgress(prev => {
        if (isDone) return 100;
        if (isFailed) return prev;
        const target = Math.min(job.progress || 0, 75);
        return Math.max(prev, target);
      });
    }, 0);
    return () => clearTimeout(id);
  }, [job?.progress, isDone, isFailed]);

  // Creep during model processing — slow crawl, cap at 88
  useEffect(() => {
    if (!isThinking) return;
    const id = setInterval(() => {
      setSmoothProgress(prev => {
        if (prev >= 75) return prev;
        return prev + 0.12;
      });
    }, 100);
    return () => clearInterval(id);
  }, [isThinking]);

  if (!job) return null;

  const stageLabel = formatStage(job.stage);
  const mainMessage = isThinking
    ? lines[thinkIdx]
    : (isDone ? (job.message || "Complete") : (job.message || "Working..."));

  return (
    <div style={{
      border: "1px solid var(--nier-border)",
      background: "var(--nier-bg-panel)",
      padding: "10px 14px",
      marginBottom: 12,
    }}>
      {/* Message */}
      <div style={{
        marginBottom: 8,
        textAlign: "center",
        fontSize: 14,
        fontWeight: isDone ? 600 : 400,
        color: isFailed ? "#c84a3a" : "var(--nier-text)",
        letterSpacing: "0.04em",
        minHeight: 20,
      }}>
        {mainMessage}
      </div>

      {/* Progress bar */}
      <div style={{
        width: "100%",
        height: 6,
        background: "rgba(0,0,0,0.12)",
        position: "relative",
        overflow: "hidden",
        margin: "6px 0",
      }}>
        {isFailed ? (
          <div style={{ width: "100%", height: "100%", background: "#c84a3a" }} />
        ) : isDone ? (
          <div style={{ width: "100%", height: "100%", background: "var(--nier-btn-active-bg)", transition: "width 0.4s ease" }} />
        ) : (
          <div className="nier-bar-running" />
        )}

      </div>

      {/* Stage info */}
      <div style={{
        marginTop: 5,
        fontSize: 10,
        color: "var(--nier-text-dim)",
        textAlign: "center",
        letterSpacing: "0.1em",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        gap: 8,
      }}>
        <span style={{ opacity: 0.4 }}>::</span>
        <span>{stageLabel}</span>
        {!isThinking && !isDone && (
          <>
            <span style={{ opacity: 0.4 }}>·</span>
            <span>{Math.round(smoothProgress)}%</span>
          </>
        )}
        {isDone && (
          <>
            <span style={{ opacity: 0.4 }}>·</span>
            <span style={{ color: "var(--nier-text)" }}>✓</span>
          </>
        )}
        <span style={{ opacity: 0.4 }}>::</span>
      </div>
    </div>
  );
}

function formatStage(stage) {
  const map = {
    queued:           "queued",
    fetching_page:    "fetching page",
    saving_source:    "saving source",
    loading_source:   "loading source",
    building_prompt:  "building prompt",
    requesting_model: "model processing",
    saving_card:      "saving card",
    failed:           "failed",
    done:             "complete",
  };
  return map[stage] || stage || "working";
}
