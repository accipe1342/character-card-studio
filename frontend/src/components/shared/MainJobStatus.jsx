/**
 * MainJobStatus.jsx — Job progress display
 * ==========================================
 * Displays the status of a background job (scrape, generate, crawl).
 * Shows a progress bar, stage label, and message. Polls via the
 * pollJob() function passed as a prop.
 *
 * PROPS
 * -----
 * job     Job object: { status, stage, progress, message, error }
 *         status: "queued" | "running" | "done" | "failed"
 *
 * PROGRESS BAR
 * ------------
 * Uses a pure CSS indeterminate simulation animation (signal-progress-sim)
 * while the job is running — not tied to the actual job progress
 * percentage, since backend progress estimates are unreliable.
 * Shows solid fill on done, red on failed.
 *
 * HOW TO EXTEND
 * -------------
 * - Show actual percentage: replace signal-progress-sim with a
 *   signal-progress-filled div and set width to job.progress + "%".
 * - Add stage-specific messages: map job.stage to custom display
 *   strings using a lookup object.
 */

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
  const [elapsed, setElapsed] = useState(0);
  const [finalElapsed, setFinalElapsed] = useState(null);

  const THINKING_STAGES = new Set(["requesting_model", "building_prompt", "generating"]);
  const isThinking = THINKING_STAGES.has(job?.stage) &&
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

  // Live elapsed timer — starts when job starts, freezes on done/failed
  useEffect(() => {
    if (!job || isDone || isFailed) return;
    setElapsed(0);
    const id = setInterval(() => setElapsed(s => s + 1), 1000);
    return () => clearInterval(id);
  }, [job?.status]);

  // Freeze elapsed on completion
  useEffect(() => {
    if (isDone || isFailed) setFinalElapsed(elapsed);
  }, [isDone, isFailed]);

  if (!job) return null;

  const stageLabel = formatStage(job.stage);
  const mainMessage = isThinking
    ? lines[thinkIdx]
    : (isDone ? (job.message || "Complete") : (job.message || "Working..."));

  return (
    <div style={{
      border: "1px solid var(--signal-border)",
      background: "var(--signal-bg-panel)",
      padding: "10px 14px",
      marginBottom: 12,
    }}>
      {/* Message */}
      <div style={{
        marginBottom: 8,
        textAlign: "center",
        fontSize: 14,
        fontWeight: isDone ? 600 : 400,
        color: isFailed ? "#c84a3a" : "var(--signal-text)",
        letterSpacing: "0.04em",
        minHeight: 20,
      }}>
        {mainMessage}
      </div>

      {/* Progress bar — pure simulation */}
      <div className="signal-progress-track" style={{ margin: "6px 0" }}>
        {isFailed
          ? <div className="signal-progress-failed" />
          : isDone
          ? <div className="signal-progress-done" />
          : <div className="signal-progress-sim" />
        }
      </div>

      {/* Stage info */}
      <div style={{
        marginTop: 5,
        fontSize: 10,
        color: "var(--signal-text-dim)",
        textAlign: "center",
        letterSpacing: "0.1em",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        gap: 8,
      }}>
        <span style={{ opacity: 0.4 }}>::</span>
        <span>{stageLabel}</span>
        <span style={{ opacity: 0.4 }}>·</span>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {isDone || isFailed
            ? `${finalElapsed ?? elapsed}s`
            : `${elapsed}s`}
        </span>

        {isDone && (
          <>
            <span style={{ opacity: 0.4 }}>·</span>
            <span style={{ color: job?.message?.startsWith("Skipped") ? "var(--signal-text-dim)" : "var(--signal-text)" }}>
              {job?.message?.startsWith("Skipped") ? "—" : "OK"}
            </span>
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
    starting:         "starting",
    fetching_page:    "fetching page",
    saving_source:    "saving source",
    loading_source:   "loading source",
    building_prompt:  "building prompt",
    requesting_model: "model processing",
    generating:       "generating",
    saving_card:      "saving",
    crawling:         "crawling pages",
    scraping:         "scraping",
    failed:           "failed",
    done:             "complete",
  };
  return map[stage] || (stage ? stage.replace(/_/g, " ") : "working");
}
