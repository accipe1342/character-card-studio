/**
 * main.jsx — React entry point
 * =============================
 * Mounts the React app into the #root div in index.html.
 * Imports global CSS files in order:
 *   1. index.css    — CSS resets and font imports
 *   2. App.css      — Layout and structural styles
 *   3. signal-ui.css — Signal UI design system (all component styles)
 *
 * Nothing else lives here. All application logic starts in App.jsx.
 */

import { StrictMode } from 'react'

// Restore theme before first render to avoid flash
let savedTheme = 'light'
try { savedTheme = localStorage.getItem('signal-theme') || 'light' } catch { /* storage blocked (private window): light theme */ }
document.documentElement.setAttribute('data-theme', savedTheme)
import { createRoot } from 'react-dom/client'
import '@fontsource/noto-sans-jp/300.css'   // NieR-style type, bundled so it works offline
import '@fontsource/noto-sans-jp/400.css'
import '@fontsource/noto-sans-jp/500.css'
import '@fontsource/noto-sans-jp/700.css'
import './index.css'
import './signal-ui.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
