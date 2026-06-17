/**
 * TopNav.jsx — Top navigation bar
 * =================================
 * The app header. Contains the logo, studio tab switcher,
 * language selector, theme toggle, and library button.
 *
 * PROPS
 * -----
 * activeTab            "character" | "lore" | "config"
 * setActiveTab(tab)    Called when a tab is clicked
 * theme                "light" | "dark"
 * setTheme(theme)      Called when theme toggle is clicked
 * language             "en" | "ja" | "zh"
 * setLanguage(lang)    Called when language is changed
 * onOpenLibrary()      Called when the Library button is clicked
 * t                    Translation strings
 *
 * HOW TO EXTEND
 * -------------
 * - Add a new tab: add an entry to the TABS array and handle it
 *   in App.jsx's tab switcher.
 * - Add a new language: add an option to the language selector and
 *   add the translation object to i18n.js.
 * - Add a user menu: replace the library button area with a dropdown.
 */

import { useState, useEffect } from "react";

export default function TopNav({ mode, setMode, onLibrary, lang, setLang, t = {} }) {
  const [dark, setDark] = useState(() => {
    return localStorage.getItem("signal-theme") === "dark";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    localStorage.setItem("signal-theme", dark ? "dark" : "light");
  }, [dark]);

  const buttonStyle = {
    padding: "10px 14px",
    border: "1px solid var(--signal-border, #3a3a3a)",
    background: "var(--signal-btn-active-bg, #2b2b2b)",
    color: "var(--signal-btn-active-text, #f5f1e8)",
    cursor: "pointer",
    fontWeight: 700,
    letterSpacing: "0.08em",
  };

  const activeStyle = {
    ...buttonStyle,
    background: "var(--signal-bg-btn, #dcd6c4)",
    color: "var(--signal-text, #2b2b2b)",
  };

  const iconBtnStyle = {
    padding: "10px 12px",
    border: "1px solid var(--signal-border, #3a3a3a)",
    background: "var(--signal-bg-btn, #dcd6c4)",
    color: "var(--signal-text, #2b2b2b)",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  };

  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
      <button
        className={`signal-btn${mode === "character" ? " signal-btn-active" : ""}`}
        style={mode === "character" ? activeStyle : buttonStyle}
        onClick={() => setMode("character")}
      >
        {/* Signal UI android eye */}
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ marginRight: 6, verticalAlign: "middle" }}>
          <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.2"/>
          <circle cx="8" cy="8" r="4" stroke="currentColor" strokeWidth="1.2"/>
          <circle cx="8" cy="8" r="1.5" fill="currentColor"/>
          <line x1="1" y1="8" x2="4" y2="8" stroke="currentColor" strokeWidth="1.2"/>
          <line x1="12" y1="8" x2="15" y2="8" stroke="currentColor" strokeWidth="1.2"/>
          <line x1="8" y1="1" x2="8" y2="4" stroke="currentColor" strokeWidth="1.2"/>
          <line x1="8" y1="12" x2="8" y2="15" stroke="currentColor" strokeWidth="1.2"/>
        </svg>
        {t.character || "CHARACTER"}
      </button>

      <button
        className={`signal-btn${mode === "lore" ? " signal-btn-active" : ""}`}
        style={mode === "lore" ? activeStyle : buttonStyle}
        onClick={() => setMode("lore")}
      >
        {/* Signal UI codex */}
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ marginRight: 6, verticalAlign: "middle" }}>
          <rect x="2" y="2" width="12" height="12" stroke="currentColor" strokeWidth="1.2"/>
          <line x1="2" y1="5.5" x2="14" y2="5.5" stroke="currentColor" strokeWidth="1"/>
          <line x1="4" y1="8.5" x2="12" y2="8.5" stroke="currentColor" strokeWidth="1"/>
          <line x1="4" y1="11" x2="9" y2="11" stroke="currentColor" strokeWidth="1"/>
          <line x1="10.5" y1="11" x2="12" y2="11" stroke="currentColor" strokeWidth="1"/>
        </svg>
        {t.lore || "LORE"}
      </button>

      <button
        className={`signal-btn${mode === "config" ? " signal-btn-active" : ""}`}
        style={mode === "config" ? activeStyle : buttonStyle}
        onClick={() => setMode("config")}
      >
        {/* Gear icon */}
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ marginRight: 6, verticalAlign: "middle" }}>
          <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.2"/>
          <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
        </svg>
        {t.config || "CONFIG"}
      </button>

      <div style={{ flex: 1 }} />

      {/* Library */}
      <button className="signal-btn" style={buttonStyle} onClick={onLibrary} title="Open saved cards">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ marginRight: 6, verticalAlign: "middle" }}>
          <polygon points="8,1 14,4.5 14,11.5 8,15 2,11.5 2,4.5" stroke="currentColor" strokeWidth="1.2" fill="none"/>
          <polygon points="8,4.5 11,6.25 11,9.75 8,11.5 5,9.75 5,6.25" stroke="currentColor" strokeWidth="1" fill="none"/>
          <circle cx="8" cy="8" r="1.2" fill="currentColor"/>
        </svg>
        {t.library || "LIBRARY"}
      </button>

      {/* Language toggle */}
      <div style={{ display: "flex", border: "1px solid var(--signal-border, #3a3a3a)" }}>
        {[{code: "en", label: "EN"}, {code: "ja", label: "日本語"}, {code: "zh", label: "中文"}].map(({code, label}) => (
          <button
            key={code}
            className={`signal-btn${lang === code ? " signal-btn-active" : ""}`}
            onClick={() => setLang(code)}
            style={{
              padding: "10px 12px",
              fontSize: 13,
              fontWeight: 700,
              letterSpacing: "0.04em",
              border: "none",
              borderRight: code !== "zh" ? "1px solid var(--signal-border, #3a3a3a)" : "none",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Theme toggle */}
      <button
        className="signal-btn"
        style={iconBtnStyle}
        onClick={() => setDark(d => !d)}
        title={dark ? "Switch to light mode" : "Switch to dark mode"}
      >
        {dark ? (
          /* Sun */
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.2"/>
            <line x1="8" y1="1" x2="8" y2="3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="8" y1="13" x2="8" y2="15" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="1" y1="8" x2="3" y2="8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="13" y1="8" x2="15" y2="8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="2.93" y1="2.93" x2="4.34" y2="4.34" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="11.66" y1="11.66" x2="13.07" y2="13.07" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="13.07" y1="2.93" x2="11.66" y2="4.34" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
            <line x1="4.34" y1="11.66" x2="2.93" y2="13.07" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
          </svg>
        ) : (
          /* Moon */
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M13 10A6 6 0 0 1 6 3a6 6 0 1 0 7 7z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
          </svg>
        )}
      </button>
    </div>
  );
}
