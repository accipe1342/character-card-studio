# Signal UI — design system

A calm, "systematic and sterile, but beautiful" interface language inspired by the menus of NieR:Automata: warm
beige paper, warm dark grey ink, hairlines borrowed from musical scores, and almost no color. This document is
self-contained: copy it into any project and build to it. The drop-in stylesheet in section 14 implements
everything described here; section 15 has React versions of the components that need behavior.

Reference implementation: Character Card Studio (`frontend/src/signal-ui.css`, `StudioHeader.jsx`,
`HelperPanel.jsx`, `shared/NierMenu.jsx`).

---

## Contents

1. Principles
2. Quick start
3. Color
4. Typography
5. Spacing and layout
6. Surfaces and depth
7. Ornaments
8. Components
9. Motion
10. Voice and copy
11. Accessibility
12. Dark mode
13. Do and don't
14. Drop-in stylesheet
15. React components
16. Checklist for a new screen

---

## 1. Principles

1. **Paper, not glass.** Everything sits on a warm beige ground with a faint grid. No gradients, no glassmorphism,
   no blur except a menu's soft drop shadow.
2. **Ink, not black.** Text and "dark" elements use a warm grey-brown (`#4e4b42`), never `#000`. Contrast comes
   from weight and darkness, not from hue.
3. **One accent, used rarely.** A single drab red-orange marks danger, errors and secrets. If you reach for a second
   color, use weight, size, a square marker or an inverted block instead.
4. **Square everything.** Border radius is always 0. Shapes are rectangles, squares and one 45° diamond.
5. **Depth by offset, not blur.** Raised things cast a hard shadow 3–5 px down and right, like a printed block
   slightly lifted off the page.
6. **Selected means inverted.** The selected tab, the hovered menu item, the active list row and the primary button
   all flip to dark ink with beige text. There is no "blue highlight".
7. **Score marks as structure.** Staff lines frame the page, `::` introduces a subtitle or a speaker, `||` ends a
   rule, a small filled square marks list items. Decoration is thin, repeated and quiet.
8. **Wide letter-spacing, light weights.** Titles are large and thin (weight 300) with very wide tracking; labels are
   small capitals with wide tracking. Body text stays normal.
9. **Fluid, never stiff.** Motion uses one spring curve: fast start, soft landing. Lines draw first, content rises
   after them. Nothing flashes or bounces.
10. **Few visible actions.** A toolbar shows the 3–5 things people do most; everything else lives in a menu
    (`NEW ▾`, `TOOLS ▾`, `EXPORT ▾`). Sections inside a panel become tabs before they become a long scroll.

---

## 2. Quick start

1. Install the font (works offline): `npm i @fontsource/noto-sans-jp` and import weights 300, 400, 500, 700
   (`import '@fontsource/noto-sans-jp/300.css'` and so on). Without a bundler, use Google Fonts
   `family=Noto+Sans+JP:wght@300;400;500;700`. Fallback: `system-ui, 'Segoe UI', Roboto, sans-serif`.
2. Paste the stylesheet from section 14 into `signal.css` and load it after your reset.
3. Set the theme on `<html>`: `data-theme="light"` (default) or `data-theme="dark"`.
4. Build pages from this skeleton:

```html
<body class="sui">
  <div class="sui-page">
    <div class="sui-staff" aria-hidden="true"><i></i><b></b><i></i></div>
    <nav class="sui-tabs">
      <button class="sui-btn is-active">CHARACTER</button><button class="sui-btn">LORE</button>
      <span class="sui-grow"></span>
      <button class="sui-btn" aria-label="Search">⌕</button>
    </nav>
    <header class="sui-header">
      <div><h1 class="sui-title">LORE</h1><div class="sui-sub">:: World entries · factions · places</div></div>
      <div class="sui-rule" aria-hidden="true"><span class="sui-diamond"></span><span class="sui-line"></span><span>||</span></div>
      <div class="sui-ctx">RAIN PORT<br>OLD HARBOR</div>
    </header>
    <main> … panels … </main>
    <footer class="sui-footer">
      <div class="sui-staff thin" aria-hidden="true"><i></i><i></i></div>
      <div class="sui-keys"><span class="sui-grow">APP NAME</span><span>CTRL+K :: SEARCH</span></div>
    </footer>
  </div>
</body>
```

---

## 3. Color

### 3.1 Tokens

All colors are CSS custom properties. Components only ever reference tokens.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--sui-bg` | `#d1cdb7` | `#1a1814` | Page ground |
| `--sui-panel` | `#dad6c3` | `#201e1a` | Panels, menus, dialogs |
| `--sui-field` | `#e4e0cf` | `#272420` | Inputs, textareas, selects |
| `--sui-btn` | `#c4bea8` | `#2e2b26` | Resting buttons, tabs, chips |
| `--sui-mid` | `#c9c3ad` | `#2a2720` | Secondary fills (picture wells, track of a progress bar) |
| `--sui-ink` | `#4e4b42` | `#c8c0a8` | Body text, icons, hairlines, staff lines |
| `--sui-ink-dim` | `#58544a` | `#a0967f` | Secondary text, hints, labels, footer |
| `--sui-sel-bg` | `#4e4b42` | `#c8c0a8` | Selected / primary / hovered block |
| `--sui-sel-ink` | `#dad6c3` | `#1a1814` | Text on a selected block |
| `--sui-hover` | `#58544a` | `#3a3630` | Button hover fill |
| `--sui-line` | `#6e695b` | `#4a4540` | Input borders, dividers (non-text) |
| `--sui-accent` | `#863a29` | `#d98a6e` | Danger, errors, secrets, "undone". The only hue |
| `--sui-warn` | `#66501e` | `#c9a65a` | "Look at this" (soft warnings). Use sparingly |
| `--sui-ok` | `#4a8a4a` | `#7fb07f` | Only for the brief "saved" flash. Never for text |
| `--sui-shadow` | `rgba(78,75,66,.25)` | `rgba(0,0,0,.45)` | Offset shadows |
| `--sui-grid` | `rgba(78,75,66,.06)` | `rgba(200,192,168,.04)` | Background grid lines |
| Console bg | `#3e3b33` | `#3e3b33` | The system-log console is dark in both themes |
| Console ink | `#dad6c3` | `#dad6c3` | Text in the console |
| Console dim | `rgba(218,214,195,.72)` | same | Speaker prefixes, meta text in the console |
| Console line | `rgba(218,214,195,.25)` | same | Hairlines inside the console |

### 3.2 Rules

- **Hierarchy by darkness and weight.** Primary text `--sui-ink`, secondary `--sui-ink-dim`, emphasis by weight 500,
  selection by inversion. Do not introduce blue links, green buttons or colored icons.
- **The accent is a signal, not a theme.** Use it for: delete and destructive actions, error lines (`⊗ …`), the
  "undone" state, secret or restricted items, a failing score. Never as a large fill, never on more than a few
  elements per screen.
- **Warnings** (`--sui-warn`) are for "you may want to check this" (a long field, a weak keyword). If it can break
  something, it is the accent instead.
- **Success is quiet.** Show `✓ saved` in dim ink; a 0.8 s green ring on the saved field is the only use of green.
- **Translucency only on the console and menus' shadow.** Everything else is opaque.
- **Inline colors are forbidden.** If a component needs a new color, add a token here first.

### 3.3 Background texture

- Grid: two 1 px linear gradients in `--sui-grid`, 32 px cell.
- Screen edge (the "convex monitor"): a fixed overlay with
  `radial-gradient(ellipse at center, transparent 55%, rgba(60,56,46,.16) 100%)` plus
  `box-shadow: inset 0 0 160px rgba(60,56,46,.22)`, `pointer-events: none`. In dark mode use black at 35%.

---

## 4. Typography

Font: **Noto Sans JP** (closest open font to the original's Japanese gothic), fallback `system-ui`. It covers
Latin, Japanese and most Chinese, so mixed-language UIs stay consistent.

| Role | Size / weight | Tracking | Case | Line height | Notes |
|---|---|---|---|---|---|
| Display title (page) | 46 px / 300 | 0.32em | UPPER | 1.0 | One per page, left aligned |
| Page subtitle | 13 px / 400 | 0.24em | UPPER | 1.4 | Starts with `:: `, items joined with ` · ` |
| Context (top right) | 12 px / 400 | 0.14em | UPPER | 1.6 | What is open, one item per line, right aligned, dim |
| Panel strip | 12 px / 500 | 0.22em | UPPER | 1.3 | Inside the dark header strip |
| Tab / nav | 13 px / 500 | 0.20em | UPPER | 1 | |
| Button | 13 px / 500 | 0.06–0.14em | Title or UPPER | 1 | Menus and primary actions in UPPER |
| Menu item | 13 px / 400 | 0.04em | Sentence | 1.3 | |
| Field label | 11 px / 500 | 0.20em | UPPER | 1.3 | Dim ink |
| Body | 13–14 px / 400 | normal | Sentence | 1.6–1.7 | Long text 14 px / 1.7 |
| Hint / meta | 11–12 px / 400 | 0.04–0.16em | Sentence or UPPER | 1.5 | Dim ink |
| Entity title (editor) | 18 px / 600–700 | normal | As written | 1.3 | e.g. the name of the open item |
| Console | 13 px / 400 | normal | Sentence | 1.7 | Speaker prefix in dim with 0.14em tracking |

Rules:

- Two weights do most of the work: 400 and 500. 300 is only for the display title; 700 only for short emphasis
  inside body text.
- Wide tracking is for UPPERCASE text only. Never track lowercase body text.
- Numbers that change (counts, tokens, timers) use `font-variant-numeric: tabular-nums`.
- Separator inside a line is ` · ` (middle dot with spaces). Lists in a subtitle use the same.
- No italics in UI chrome. Italics are reserved for quoted content.
- Truncate long names with an ellipsis rather than wrapping inside buttons and strips.

---

## 5. Spacing and layout

### 5.1 Scale

Base unit 4 px. Use only: **4, 6, 8, 10, 12, 16, 18, 24, 32, 40**.

| Use | Value |
|---|---|
| Gap between buttons in a toolbar | 8 |
| Gap between chips / small buttons | 4–6 |
| Gap between panels | 12–16 |
| Panel padding | 12 (dense) / 14–16 (editor) |
| Panel strip to content | 12 |
| Header margin top / bottom | 18 / 18 |
| Section break inside a panel | 12–16 |
| Page gutter | 24 desktop, 16 phone |

### 5.2 Page structure (top to bottom)

1. Staff band (14 px tall).
2. Tab row: studio / section tabs on the left, utilities (search, library, language, theme) on the right,
   12 px below the staff.
3. Header: display title + subtitle (left), a rule with a diamond and `||` (fills the middle), context (right).
4. Inputs row (if the page has a main input such as a URL and a model picker).
5. Action toolbar: 3–5 visible buttons on the left, a flexible spacer, status text, then menus on the right.
6. Content: panels in a grid.
7. Footer: thin staff (two hairlines), then the key-hint line.
8. Docked console (fixed to the bottom; the page gets `padding-bottom` equal to its height + 8).

### 5.3 Content grids

- Master / detail: `220px | 280px | 1fr` (collection, list, editor). Collapse the editor under the list below
  1180 px; collapse everything to one column below 760 px.
- Two-pane editor: `330px | 1fr` (preview, editor). One column below 700 px.
- Three columns of equal weight: one column below 1100 px.
- Content width: center at 1076–1126 px for tool pages; full width (with 24 px gutters) for dense workbenches.

### 5.4 Phone

- 16 px gutters, no horizontal scroll ever (`scrollWidth <= viewport`).
- Toolbars wrap; menus open full width if they would overflow.
- Tab row wraps; utilities may collapse to icons.
- The console docks full width and starts hidden as its bar.
- Touch targets at least 44 × 44 px (pad small buttons).

---

## 6. Surfaces and depth

| Level | What | Shadow |
|---|---|---|
| 0 | Page ground | none (grid + edge vignette) |
| 1 | Buttons, tabs, chips | `3px 3px 0 var(--sui-shadow)` |
| 1+ | Hovered button | `4px 4px 0 var(--sui-shadow)` |
| 2 | Panels | `4px 4px 0 var(--sui-shadow)` |
| 3 | Menus | `4px 4px 0 var(--sui-shadow), 0 8px 24px rgba(0,0,0,.18)` |
| 4 | Console, floating window | `5px 5px 0 rgba(78,75,66,.3), 0 10px 30px rgba(0,0,0,.25)` |
| 5 | Dialogs | backdrop `rgba(0,0,0,.45)` + level-4 shadow |

- `border-radius: 0` everywhere.
- Buttons have **no border** (transparent 1 px border to keep sizes stable).
- Panels have a 1 px hairline in `--sui-line` plus the offset shadow. A 1 px top line draws in when a panel appears.
- Inputs use a 1 px `--sui-line` border (or an inset 1 px box-shadow) on `--sui-field`.
- Disabled things lose their shadow and drop to 55% opacity.

---

## 7. Ornaments

Use them to frame, never to fill. Each has one job.

| Ornament | Markup / CSS | Where |
|---|---|---|
| **Staff band** | two 1 px hairlines with a row of 4 × 4 px squares every 12 px between them, 14 px tall, 55% ink | Top of every page |
| **Thin staff** | two hairlines 7 px apart | Footer, above key hints |
| **Diamond** | 8 × 8 px box, 1 px border, rotated 45° | Start of the header rule, before a console title |
| **Header rule** | diamond + flexible 1 px line at 50% + `||` | Between title and context |
| **`::` prefix** | literal `:: ` before text | Page subtitle, speaker labels in the console, headings in dialogs |
| **`||` double bar** | literal `||`, 11 px, 0.2em tracking | End of a rule; both ends of a labeled divider |
| **Square marker** | 7 × 7 px filled square (`currentColor`) | Before a panel strip title, before list items and menu items (menu at 6 px / 50%) |
| **Cursor** | a small right-pointing triangle (10 × 10 px) left of the selected list item | Lists where keyboard selection matters |
| **Labeled divider** | `|| ─── LABEL ─── ||`, label 10 px / 700 / 0.16em caps | Separating sections inside a panel |
| **Corner brackets** | 10 px L-shapes in the corners, 1.5 px | Framing a featured block (an open record); at most one per screen |
| **Block cursor** | 8 × 14 px block, blinking 0.7 s `steps(1)` | End of the last console line while working |

---

## 8. Components

Every component below is implemented in the stylesheet (section 14). Class names start with `sui-`.

### 8.1 Tab bar (`.sui-tabs` + `.sui-btn`)

- Buttons 9 × 18 px padding, 13 px / 500, 0.2em tracking, UPPER, optional 16 px stroke icon before the label.
- Selected tab: `.is-active` (inverted). Exactly one is selected.
- Utilities on the right are the same buttons (icon-only ones get an `aria-label`).
- A segmented group (language switch) shares one outline and has no gaps.

### 8.2 Page header (`.sui-header`)

- Display title, then `:: subtitle` under it, left aligned.
- The rule fills the remaining width (`flex: 1 1 120px`) and sits on the subtitle's baseline.
- Context on the right: what is open (collection / item), UPPER, dim, one item per line. When nothing is open,
  say so ("NOTHING OPEN").

### 8.3 Buttons (`.sui-btn`)

| State | Look |
|---|---|
| Resting | `--sui-btn` fill, ink text, 3 px offset shadow |
| Hover | `--sui-hover` fill, beige text, 4 px shadow, a 1 px line sweeps under the label (0.4 s) |
| Pressed | `transform: scale(.97)` |
| Primary / selected (`.is-primary`, `.is-active`) | inverted: `--sui-sel-bg` fill, `--sui-sel-ink` text |
| Danger (`.is-danger`) | resting look, accent text; on hover accent fill with beige text |
| Disabled | 55% opacity, no shadow, no hover |
| Focus (keyboard) | 2 px ink outline, 2 px offset |

Sizes: default 10 × 14 px padding; small `.sm` 4 × 9 px, 11 px text; icon `.icon` 10 × 12 px.
At most **one primary** per toolbar. Menus open with a trailing ` ▾`.

### 8.4 Menu (`.sui-menu`)

- Trigger: a `.sui-btn` with ` ▾`; it shows as selected while open. `aria-haspopup="menu"`, `aria-expanded`.
- Popup: `--sui-panel`, 4 px padding top/bottom, min-width 240 px, level-3 shadow, 6 px below the trigger,
  aligned left (or right for menus at the right end of a toolbar).
- Items: full-width buttons, 9 × 14 px padding, 13 px / 400, a 6 px square marker at 50% before the label.
  Hover / keyboard focus: inverted. Disabled: 50% opacity.
- Group label: 11 px / 500 / 0.2em caps, dim. Separator: 1 px line at 40%.
- A checkbox option is a `<label>` row inside the menu; clicking it does not close the menu.
- Closes on a pick, a click outside or Escape. Items that open their own dialog stay mounted while the menu is
  closed (render the popup with `display: none`).
- Standard menus: `NEW ▾` (blank, import), `TOOLS ▾` (checks, analyses), `EXPORT ▾` (every output format and
  "send to…" action), `GENERATE ▾` (ways to create content).

### 8.5 Panel (`.sui-panel` + `.sui-strip`)

- `--sui-panel` fill, 1 px hairline, level-2 shadow, 12–16 px padding.
- First child is the **strip**: a full-width dark bar (`--sui-sel-bg` / `--sui-sel-ink`), 7 × 12 px padding,
  12 px / 500 / 0.22em caps, a 7 px square marker before the text. Optional right-aligned status in the strip
  ("✓ SAVED").
- Empty state: one centered dim sentence that says what to do next ("Load a text on the left, or pick a saved one").
- Panels appear with the line-draw + rise animation (section 9), staggered 80 ms.

### 8.6 List item (`.sui-item`)

- Row: 9 × 12 px padding, 13 px, a square marker (60% opacity) then the label, meta right-aligned in 11 px caps.
  Rows are separated by a hairline at 18%.
- Selected: inverted fill, full-opacity marker, a 3 px offset shadow, and the triangle cursor 16 px to the left.
- Secret / restricted rows: accent marker and an accent meta word ("SECRET").
- Keyboard: `J` / `K` move, Enter opens, `X` deletes, `U` undoes. Show these in the footer.

### 8.7 Inputs (`.sui-field`)

- `--sui-field` fill, 1 px `--sui-line` border, no radius, 10–12 px padding, ink text, dim placeholder.
- Label above in field-label style (11 px caps, dim). Optional "(optional)" in lowercase.
- Focus: 2 px ink outline at offset 0 (or a 2 px inset bar on the left for large text areas).
- Text areas resize vertically only. Long text 14 px / 1.7.
- Selects look like fields with a `▾`.
- Chips (keywords, tags): `.sui-chip` 5 × 9 px, field fill, hairline, `×` in accent to remove.

### 8.8 Tabs inside a panel (`.sui-tabs.inner`)

- Small `.sui-btn` (6 × 12 px, 12 px, 0.16em) in a row; the selected one is inverted.
- A count can follow the label: `KEYS · 2`.
- Hidden tab panels stay mounted (use the `hidden` attribute) so unsaved input survives switching.
- `role="tablist"`, `role="tab"` with `aria-selected`, `role="tabpanel"`.

### 8.9 Labeled divider (`.sui-divider`)

`|| ── LABEL ── ||`: two short marks, flexible hairlines, a 10 px / 700 / 0.16em caps label. Use between sections
inside one panel when tabs would be overkill.

### 8.10 Console / system log (`.sui-console`)

The assistant, log or job output lives here, styled like the game's system messages.

- Docked: fixed to the bottom, 24 px from the sides, default 280 px tall, resizable from a 7 px top edge
  (a 60 × 2 px grip in the middle). The page gets matching `padding-bottom`.
- Colors: console bg / ink / dim / line tokens (dark in both themes). Level-4 shadow.
- Header row: diamond, `NAME` (13 px / 500 / 0.3em), `:: CONTEXT` (11 px caps dim), spacer, history select,
  small buttons (`NEW`, `⧉ FLOAT` / `⇊ DOCK`, `▾ HIDE`).
- Body: two columns. Left: the log, each line prefixed `YOU ::` / `NAME ::` in dim tracked caps; the input at the
  bottom (2 rows, Enter sends, Shift+Enter new line) with an inverted `SEND`. Right (360 px): a list of what changed,
  with per-item actions.
- Working: a dim `NAME :: working… 12s` line with the blinking block cursor.
- Hidden: collapses to a 32 px bar along the bottom: diamond, `NAME`, `:: what it does`, and on the right open
  counts and the shortcut (`CTRL+/ ▴`). The whole bar is the button.
- Floating: same content in a window (default 660 × 460) that drags by its header (anywhere that is not a control)
  and resizes from a 12 px corner mark. Position and size are remembered.
- Shortcut: `Ctrl+/` (or ⌘/) toggles it from anywhere.

### 8.11 Change record (`.sui-change`)

For anything automated that edits user data, show each change as a row the user can act on.

- Row: translucent fill (8% beige on the console), a 3 px left bar (ink; accent when undone), label, actions
  `OPEN` / `KEEP` / `UNDO` as small buttons.
- States: open (actions shown), `✓ kept` (dim), `↶ undone` (accent, label struck through).
- When one reply made several changes, add `KEEP ALL` / `UNDO ALL` under the group (undo newest first).
- An undo that would overwrite newer work is refused with a plain sentence, never applied silently.

### 8.12 Dialog (`.sui-dialog`)

- Backdrop `rgba(0,0,0,.45)`, click outside closes. Panel width `min(640px, 100%)`, 20 px padding.
- Title as a heading `NAME · CONTEXT` in strip style or 16 px / 700 with `::` marks.
- Actions bottom right: secondary first, primary last (inverted). `CLOSE` is always present.
- `role="dialog"`, `aria-label`, focus the first control, Escape closes.

### 8.13 Toast (`.sui-toast`)

Bottom center, 24 px up (above the console bar), inverted block, 13 px / 700 / 0.08em, `✓ message`, 2–3 s,
`pointer-events: none`.

### 8.14 Progress (`.sui-progress`)

- Track 6 px tall in 12% ink. Indeterminate: a 35–55% block sweeping left to right in 1.6 s.
- Determinate: inverted fill growing with a 0.4 s ease. Failure: the bar turns accent.
- Always pair with text: `Writing the card (2/3)… 14s`.

### 8.15 Key-hint footer (`.sui-keys`)

- Thin staff, then one line: app name on the left, hints on the right, 11 px / 400 / 0.16em caps, dim, 22 px gaps.
- Format: `KEY :: ACTION` (`CTRL+K :: SEARCH`). A hint may be a button (the console shortcut).
- List only what works on the current page.

### 8.16 Status text

Right side of a toolbar or a strip, 12 px caps dim: `✓ SAVED`, `● EDITING (AUTOSAVES)`, `9 ENTRIES · ~640 TOK`.
Errors inline: `⊗ message` in accent.

---

## 9. Motion

### 9.1 Curves and durations

| Token | Value | Use |
|---|---|---|
| `--sui-spring` | `cubic-bezier(0.16, 1, 0.3, 1)` | Anything entering or moving |
| `--sui-soft` | `cubic-bezier(0.25, 0.46, 0.45, 0.94)` | Color and opacity changes, sweeps |
| `--sui-snappy` | `cubic-bezier(0.4, 0, 0.2, 1)` | Lines drawing, presses, progress |

| Pattern | Spec |
|---|---|
| Panel enter | top hairline draws left→right (`scaleX 0→1`, 0.35 s snappy), content rises 10 px + fades in (0.55 s spring) |
| Stagger | 80 ms between sibling panels; never animate everything at once |
| Page / section switch | slide 16 px from the direction of travel + fade, 0.38 s spring |
| Title enter | tracking −0.02em → 0.12em → final, opacity 0 → 1, 0.9 s spring |
| Button hover | fill 0.18 s soft; 1 px underline sweeps in 0.4 s and fades |
| Button press | `scale(.97)` 0.1 s snappy |
| Menu open | instant, or 120 ms fade; no scale |
| Vignette | fades in over 1.8 s on load |
| Saved flash | 0.8 s ring on the saved field |
| Delete flash | brief accent tint on the removed row before it leaves |
| Cursor blink | 0.7 s `steps(1)` |

Rules: animate `transform` and `opacity` only; no bounces, no overshoot, no flicker; the "glitch" effect is for
one-off moments (a name appearing after generation), never a loop on content. Honor `prefers-reduced-motion`:
drop slides and rises, keep instant state changes.

---

## 10. Voice and copy

- **Labels** are short, UPPERCASE, nouns or verbs: `EXPORT`, `NEW ENTRY`, `TEST ACTIVATION`.
- **Subtitles** start with `:: ` and list what the page holds, joined by ` · `.
- **System voice** (assistants, logs) is terse and prefixed: `Report: 3 entries added.`,
  `Proposal: a courier card and a small lorebook.`, `Unit online.` One idea per line, no exclamation marks, no
  emoji, no apologies beyond one plain sentence.
- **Speakers** in logs: `YOU ::` and `NAME ::`.
- **Empty states** tell the next step in one sentence.
- **Errors** say what happened and what to do: `⊗ The model returned no greeting. Try again or pick another model.`
- **Confirmations** for destructive actions name the thing and the count: `Move all 12 entries in "Rain Port" to
  the trash?`
- **Symbols**: `✓` done/kept, `⊗` error, `↶` undone, `●` unsaved, `▾` menu, `▴` expand, `⧉` float, `⇊` dock,
  `⇢` send to another app, `↓` download, `♻` trash, `◇` the assistant / something special, `⚙` options.

---

## 11. Accessibility

Measured contrast (WCAG 2.x). Body and small text need 4.5:1; large text and UI parts need 3:1.

| Pair | Ratio |
|---|---|
| Ink `#4e4b42` on bg `#d1cdb7` | 5.45 |
| Ink on panel `#dad6c3` | 5.97 |
| Ink on field `#e4e0cf` | 6.58 |
| Ink on button `#c4bea8` | 4.68 |
| Dim `#58544a` on bg | 4.72 |
| Selected ink `#dad6c3` on `#4e4b42` | 5.97 |
| Beige on hover `#58544a` | 5.17 |
| Accent `#863a29` on bg / panel | 4.95 / 5.43 |
| Warn `#66501e` on bg | 4.81 |
| Line `#6e695b` on bg (non-text) | 3.42 |
| Console ink `#dad6c3` on `#3e3b33` | 7.66 |
| Dark: ink `#c8c0a8` on `#1a1814` | 9.76 |
| Dark: dim `#a0967f` on `#1a1814` / button `#2e2b26` | 6.05 / 4.81 |
| Dark: accent `#d98a6e` on `#1a1814` | 6.59 |
| Dark: selected `#1a1814` on `#c8c0a8` | 9.76 |

Rules:

- Keyboard focus is always visible: `outline: 2px solid var(--sui-ink); outline-offset: 2px` on every control
  (`:focus-visible`, so mouse clicks don't show it).
- Real elements: `<button>`, `<a href>`, `<input>` with a `<label>`. Never a clickable `<div>`.
- Icon-only buttons have `aria-label`. Decorative ornaments have `aria-hidden="true"`.
- Menus: `aria-haspopup="menu"`, `aria-expanded`, `role="menu"`, `role="menuitem"`; Escape closes.
- Tabs: `role="tablist"` / `tab` (`aria-selected`) / `tabpanel`.
- Change rows: `role="group"` with `aria-label="Change: <label>"`.
- Live areas (logs, job status): `aria-live="polite"`; errors `role="alert"`.
- Never use color alone: the accent always comes with a word or symbol (`⊗`, `SECRET`, `↶ undone`).
- Touch targets ≥ 44 px on phones.

---

## 12. Dark mode

Same rules, inverted ground:

- Ground `#1a1814`, panels `#201e1a`, ink `#c8c0a8`.
- **Selected stays "the strongest contrast":** a light block (`#c8c0a8`) with dark text (`#1a1814`). Panel strips,
  hovered menu items, the primary button and the selected tab all use this.
- Buttons: `#2e2b26` fill, ink text, black offset shadow at 45%.
- Accent and warn get lighter (`#d98a6e`, `#c9a65a`) to keep contrast.
- The console keeps its own dark palette (it reads as a separate device).
- Vignette uses black instead of warm brown. Grid lines drop to 4%.
- Switch with `data-theme` on `<html>`; remember the choice; set it before first paint to avoid a flash.

---

## 13. Do and don't

| Do | Don't |
|---|---|
| Warm grey ink | Pure black or pure white |
| Invert to show selection | Blue highlights, colored outlines |
| One accent for danger | Red, green, blue and orange buttons side by side |
| Square corners | Any border radius |
| Hard offset shadow | Soft drop shadows on buttons and panels |
| 3–5 visible actions + menus | 15 buttons in three rows |
| Tabs for long editors | A form that scrolls through five sections |
| `::` and `||` sparingly | Ornaments on every element |
| Thin 46 px display title, left | Centered bold page titles |
| UPPERCASE + tracking for labels | Tracking on body text |
| Dim sentence for empty states | Big illustrations |
| Bundle the font | Depend on a font CDN for an offline tool |
| Tokens in CSS | Hex values in components |

---

## 14. Drop-in stylesheet

Self-contained. Load it after a reset. Prefix `sui-`.

```css
/* ================= Signal UI ================= */
:root {
  --sui-bg: #d1cdb7; --sui-panel: #dad6c3; --sui-field: #e4e0cf; --sui-btn: #c4bea8; --sui-mid: #c9c3ad;
  --sui-ink: #4e4b42; --sui-ink-dim: #58544a; --sui-sel-bg: #4e4b42; --sui-sel-ink: #dad6c3; --sui-hover: #58544a;
  --sui-line: #6e695b; --sui-accent: #863a29; --sui-warn: #66501e; --sui-ok: #4a8a4a;
  --sui-shadow: rgba(78, 75, 66, .25); --sui-grid: rgba(78, 75, 66, .06); --sui-edge: rgba(60, 56, 46, .22);
  --sui-con-bg: #3e3b33; --sui-con-ink: #dad6c3; --sui-con-dim: rgba(218, 214, 195, .72); --sui-con-line: rgba(218, 214, 195, .25);
  --sui-font: 'Noto Sans JP', system-ui, 'Segoe UI', Roboto, sans-serif;
  --sui-spring: cubic-bezier(.16, 1, .3, 1); --sui-soft: cubic-bezier(.25, .46, .45, .94); --sui-snappy: cubic-bezier(.4, 0, .2, 1);
}
[data-theme="dark"] {
  --sui-bg: #1a1814; --sui-panel: #201e1a; --sui-field: #272420; --sui-btn: #2e2b26; --sui-mid: #2a2720;
  --sui-ink: #c8c0a8; --sui-ink-dim: #a0967f; --sui-sel-bg: #c8c0a8; --sui-sel-ink: #1a1814; --sui-hover: #3a3630;
  --sui-line: #4a4540; --sui-accent: #d98a6e; --sui-warn: #c9a65a; --sui-ok: #7fb07f;
  --sui-shadow: rgba(0, 0, 0, .45); --sui-grid: rgba(200, 192, 168, .04); --sui-edge: rgba(0, 0, 0, .35);
}

/* ground */
.sui { margin: 0; background: var(--sui-bg); color: var(--sui-ink); font: 400 14px/1.6 var(--sui-font);
  background-image: linear-gradient(var(--sui-grid) 1px, transparent 1px), linear-gradient(90deg, var(--sui-grid) 1px, transparent 1px);
  background-size: 32px 32px; -webkit-font-smoothing: antialiased; }
.sui::after { content: ''; position: fixed; inset: 0; pointer-events: none; z-index: 9999;
  background: radial-gradient(ellipse at center, transparent 55%, var(--sui-edge) 100%); box-shadow: inset 0 0 160px var(--sui-edge);
  animation: sui-fade 1.8s var(--sui-soft) both; }
.sui *, .sui *::before, .sui *::after { box-sizing: border-box; border-radius: 0; }
.sui button, .sui input, .sui select, .sui textarea { font-family: inherit; }
.sui-page { max-width: 1126px; margin: 0 auto; padding: 24px; }
.sui-grow { flex: 1; }
@media (max-width: 700px) { .sui-page { padding: 16px; } }

/* ornaments */
.sui-staff { height: 14px; display: flex; flex-direction: column; justify-content: space-between; }
.sui-staff > i { display: block; height: 1px; background: var(--sui-ink); opacity: .55; }
.sui-staff > b { display: block; height: 4px; opacity: .55; background-image: repeating-linear-gradient(90deg, var(--sui-ink) 0 4px, transparent 4px 12px); }
.sui-staff.thin { height: 7px; }
.sui-diamond { width: 8px; height: 8px; border: 1px solid currentColor; transform: rotate(45deg); flex: none; display: inline-block; }
.sui-sq { width: 7px; height: 7px; background: currentColor; display: inline-block; flex: none; }

/* header */
.sui-tabs { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
.sui-header { display: flex; align-items: flex-end; gap: 24px; margin: 18px 0; flex-wrap: wrap; text-align: left; }
.sui-title { font: 300 46px/1 var(--sui-font); letter-spacing: .32em; margin: 0; animation: sui-title .9s var(--sui-spring) both; }
.sui-sub { font: 400 13px var(--sui-font); letter-spacing: .24em; color: var(--sui-ink-dim); margin-top: 8px; text-transform: uppercase; }
.sui-rule { flex: 1 1 120px; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; font-size: 11px; letter-spacing: .2em; }
.sui-rule .sui-line { flex: 1; height: 1px; background: var(--sui-ink); opacity: .5; }
.sui-ctx { font: 400 12px/1.6 var(--sui-font); letter-spacing: .14em; color: var(--sui-ink-dim); text-align: right; text-transform: uppercase; margin-bottom: 4px; }
@media (max-width: 700px) { .sui-title { font-size: 32px; letter-spacing: .24em; } .sui-ctx { text-align: left; } }

/* buttons */
.sui-btn { position: relative; overflow: hidden; display: inline-flex; align-items: center; gap: 8px; white-space: nowrap; cursor: pointer;
  padding: 10px 14px; border: 1px solid transparent; background: var(--sui-btn); color: var(--sui-ink);
  font: 500 13px var(--sui-font); letter-spacing: .08em; box-shadow: 3px 3px 0 var(--sui-shadow);
  transition: background .18s var(--sui-soft), color .18s var(--sui-soft), box-shadow .18s var(--sui-soft), transform .1s var(--sui-snappy); }
.sui-tabs > .sui-btn { padding: 9px 18px; letter-spacing: .2em; }
.sui-btn::after { content: ''; position: absolute; left: 0; right: 0; bottom: 2px; height: 1px; background: currentColor; opacity: 0; transform: scaleX(0); transform-origin: left; }
.sui-btn:hover:not(:disabled) { background: var(--sui-hover); color: var(--sui-sel-ink); box-shadow: 4px 4px 0 var(--sui-shadow); }
[data-theme="dark"] .sui-btn:hover:not(:disabled) { color: var(--sui-ink); }
.sui-btn:hover:not(:disabled)::after { animation: sui-sweep .4s var(--sui-soft) forwards; }
.sui-btn:active:not(:disabled) { transform: scale(.97); }
.sui-btn.is-primary, .sui-btn.is-active, .sui-btn[aria-expanded="true"] { background: var(--sui-sel-bg); color: var(--sui-sel-ink); }
.sui-btn.is-danger { color: var(--sui-accent); }
.sui-btn.is-danger:hover:not(:disabled) { background: var(--sui-accent); color: var(--sui-sel-ink); }
.sui-btn:disabled { opacity: .55; box-shadow: none; cursor: default; }
.sui-btn.sm { padding: 4px 9px; font-size: 11px; letter-spacing: .12em; }
.sui-btn.icon { padding: 10px 12px; }
.sui-seg { display: inline-flex; box-shadow: 3px 3px 0 var(--sui-shadow); }
.sui-seg > .sui-btn { box-shadow: none; }
.sui :focus-visible { outline: 2px solid var(--sui-ink); outline-offset: 2px; }

/* toolbar + menus */
.sui-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
.sui-status { font-size: 12px; letter-spacing: .14em; color: var(--sui-ink-dim); text-transform: uppercase; }
.sui-menu-wrap { position: relative; display: inline-flex; }
.sui-menu { position: absolute; top: calc(100% + 6px); left: 0; z-index: 120; min-width: 240px; padding: 4px 0; text-align: left;
  background: var(--sui-panel); box-shadow: 4px 4px 0 var(--sui-shadow), 0 8px 24px rgba(0, 0, 0, .18); }
.sui-menu.right { left: auto; right: 0; }
.sui-menu-item { display: flex; align-items: center; gap: 10px; width: 100%; border: none; background: transparent; cursor: pointer;
  color: var(--sui-ink); font: 400 13px var(--sui-font); letter-spacing: .04em; padding: 9px 14px; text-align: left; }
.sui-menu-item::before { content: ''; width: 6px; height: 6px; background: currentColor; opacity: .5; flex: none; }
.sui-menu-item:hover:not(:disabled), .sui-menu-item:focus-visible { background: var(--sui-sel-bg); color: var(--sui-sel-ink); outline: none; }
.sui-menu-item:disabled { opacity: .5; cursor: default; }
.sui-menu-label { font: 500 11px var(--sui-font); letter-spacing: .2em; color: var(--sui-ink-dim); padding: 8px 14px 4px; text-transform: uppercase; }
.sui-menu-sep { height: 1px; background: var(--sui-line); opacity: .4; margin: 4px 0; }
.sui-menu-check { display: flex; align-items: center; gap: 8px; padding: 9px 14px; font-size: 13px; cursor: pointer; }

/* panels */
.sui-panel { position: relative; background: var(--sui-panel); border: 1px solid var(--sui-line); padding: 14px;
  box-shadow: 4px 4px 0 var(--sui-shadow); animation: sui-rise .55s var(--sui-spring) both; }
.sui-panel::before { content: ''; position: absolute; top: -1px; left: -1px; right: -1px; height: 1px; background: var(--sui-ink);
  transform-origin: left; animation: sui-draw .35s var(--sui-snappy) both; }
.sui-panel:nth-child(2) { animation-delay: .08s; } .sui-panel:nth-child(3) { animation-delay: .16s; } .sui-panel:nth-child(4) { animation-delay: .24s; }
.sui-strip { display: flex; align-items: center; gap: 10px; margin: 0 0 12px; padding: 7px 12px; background: var(--sui-sel-bg); color: var(--sui-sel-ink);
  font: 500 12px var(--sui-font); letter-spacing: .22em; text-transform: uppercase; }
.sui-strip::before { content: ''; width: 7px; height: 7px; background: currentColor; flex: none; }
.sui-strip .end { margin-left: auto; opacity: .8; }
.sui-empty { text-align: center; color: var(--sui-ink-dim); font-size: 13px; padding: 16px 8px; }
.sui-grid { display: grid; gap: 16px; }
.sui-grid.md { grid-template-columns: 220px 280px minmax(0, 1fr); }
@media (max-width: 1180px) { .sui-grid.md { grid-template-columns: 220px minmax(0, 1fr); } .sui-grid.md > :last-child { grid-column: 1 / -1; } }
@media (max-width: 760px) { .sui-grid.md { grid-template-columns: 1fr; } }

/* lists */
.sui-list { position: relative; }
.sui-item { position: relative; display: flex; align-items: center; gap: 10px; padding: 9px 12px; font-size: 13px; cursor: pointer;
  border-bottom: 1px solid rgba(78, 75, 66, .18); background: transparent; border-left: none; border-right: none; border-top: none;
  width: 100%; text-align: left; color: inherit; font-family: inherit; }
.sui-item::before { content: ''; width: 7px; height: 7px; background: currentColor; opacity: .6; flex: none; }
.sui-item .meta { margin-left: auto; font-size: 11px; letter-spacing: .1em; text-transform: uppercase; }
.sui-item.is-selected, .sui-item[aria-selected="true"] { background: var(--sui-sel-bg); color: var(--sui-sel-ink); box-shadow: 3px 3px 0 var(--sui-shadow); }
.sui-item.is-selected::before, .sui-item[aria-selected="true"]::before { opacity: 1; }
.sui-item.is-selected::after, .sui-item[aria-selected="true"]::after { content: ''; position: absolute; left: -16px; top: 50%; margin-top: -5px;
  width: 10px; height: 10px; background: var(--sui-ink); clip-path: polygon(0 0, 100% 50%, 0 100%); }
.sui-item.is-secret::before { background: var(--sui-accent); opacity: 1; }
.sui-item.is-secret .meta { color: var(--sui-accent); }

/* fields */
.sui-label { display: block; font: 500 11px var(--sui-font); letter-spacing: .2em; color: var(--sui-ink-dim); text-transform: uppercase; margin-bottom: 4px; }
.sui-field { width: 100%; background: var(--sui-field); color: var(--sui-ink); border: 1px solid var(--sui-line); padding: 10px 12px; font: 400 14px/1.6 var(--sui-font); }
.sui-field::placeholder { color: var(--sui-ink-dim); opacity: .8; }
textarea.sui-field { resize: vertical; line-height: 1.7; }
.sui-chip { display: inline-flex; align-items: center; gap: 6px; padding: 5px 9px; font-size: 12px; background: var(--sui-field); border: 1px solid var(--sui-line); letter-spacing: .06em; }
.sui-chip button { border: none; background: none; color: var(--sui-accent); cursor: pointer; padding: 0; font: inherit; }
.sui-divider { display: flex; align-items: center; gap: 8px; margin: 12px 0; }
.sui-divider::before, .sui-divider::after { content: '||'; font-size: 10px; letter-spacing: .1em; opacity: .7; }
.sui-divider > i { flex: 1; height: 1px; background: var(--sui-line); }
.sui-divider > span { font: 700 10px var(--sui-font); letter-spacing: .16em; text-transform: uppercase; }

/* tabs inside a panel */
.sui-tabs.inner { margin: 0 0 12px; gap: 4px; }
.sui-tabs.inner > .sui-btn { padding: 6px 12px; font-size: 12px; letter-spacing: .16em; }
.sui-tabs.inner > .sui-btn[aria-selected="true"] { background: var(--sui-sel-bg); color: var(--sui-sel-ink); }

/* console (system log) */
.sui-console { position: fixed; left: 24px; right: 24px; bottom: 6px; height: 280px; z-index: 250; display: flex; flex-direction: column;
  background: var(--sui-con-bg); color: var(--sui-con-ink); box-shadow: 5px 5px 0 rgba(78, 75, 66, .3), 0 10px 30px rgba(0, 0, 0, .25); }
.sui-console.is-float { left: auto; right: auto; bottom: auto; }
.sui-console-grip { height: 7px; cursor: ns-resize; display: flex; justify-content: center; align-items: center; flex: none; }
.sui-console-grip::after { content: ''; width: 60px; height: 2px; background: var(--sui-con-dim); }
.sui-console-head { display: flex; align-items: center; gap: 10px; padding: 2px 14px 7px; border-bottom: 1px solid var(--sui-con-line); flex-wrap: wrap; flex: none; }
.sui-console.is-float .sui-console-head { padding: 8px 14px; cursor: move; }
.sui-console-name { font-weight: 500; letter-spacing: .3em; font-size: 13px; }
.sui-console-ctx { font-size: 11px; letter-spacing: .16em; color: var(--sui-con-dim); text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sui-console-body { flex: 1; display: flex; min-height: 0; }
.sui-console-log { flex: 1 1 360px; overflow-y: auto; padding: 8px 14px; font-size: 13px; line-height: 1.7; }
.sui-console-log .who { color: var(--sui-con-dim); letter-spacing: .14em; }
.sui-console-side { flex: 0 1 360px; border-left: 1px solid var(--sui-con-line); padding: 8px 14px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
.sui-console-input { display: flex; gap: 8px; padding: 6px 14px 10px; align-items: flex-end; }
.sui-console-input textarea { flex: 1; resize: none; font: 400 13px var(--sui-font); padding: 7px 10px; color: var(--sui-con-ink);
  background: rgba(218, 214, 195, .1); border: none; box-shadow: inset 0 0 0 1px var(--sui-con-line); }
.sui-console .sui-btn { background: #c4bea8; color: #4e4b42; }
.sui-console .sui-btn.is-primary { background: var(--sui-con-ink); color: var(--sui-con-bg); }
.sui-console-bar { position: fixed; left: 24px; right: 24px; bottom: 6px; height: 32px; z-index: 240; display: flex; align-items: center; gap: 12px;
  padding: 0 16px; border: none; cursor: pointer; text-align: left; background: var(--sui-con-bg); color: var(--sui-con-ink);
  font: 400 12px var(--sui-font); letter-spacing: .22em; }
.sui-console-bar .dim { color: var(--sui-con-dim); }
.sui-console-bar .end { margin-left: auto; color: var(--sui-con-dim); }
.sui-cursor { display: inline-block; width: 8px; height: 14px; margin-left: 4px; vertical-align: -2px; background: currentColor; animation: sui-blink .7s steps(1) infinite; }
.sui-change { padding: 5px 8px; font-size: 12px; background: rgba(218, 214, 195, .08); border-left: 3px solid var(--sui-con-ink); display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.sui-change .label { flex: 1 1 120px; min-width: 0; overflow-wrap: anywhere; }
.sui-change.is-undone { border-left-color: #e0a08a; opacity: .7; } .sui-change.is-undone .label { text-decoration: line-through; }
.sui-change.is-kept { opacity: .7; }

/* dialog, toast, progress, footer */
.sui-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, .45); z-index: 300; display: flex; align-items: flex-start; justify-content: center; padding: 40px 16px; overflow-y: auto; }
.sui-dialog { width: min(640px, 100%); background: var(--sui-panel); padding: 20px; box-shadow: 5px 5px 0 rgba(78, 75, 66, .3), 0 10px 30px rgba(0, 0, 0, .25); }
.sui-dialog-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; flex-wrap: wrap; }
.sui-toast { position: fixed; left: 50%; bottom: 48px; transform: translateX(-50%); z-index: 9998; pointer-events: none; padding: 10px 24px;
  background: var(--sui-sel-bg); color: var(--sui-sel-ink); font: 700 13px var(--sui-font); letter-spacing: .08em; box-shadow: 4px 4px 0 var(--sui-shadow); }
.sui-progress { position: relative; height: 6px; background: rgba(0, 0, 0, .12); overflow: hidden; }
.sui-progress > i { position: absolute; top: 0; height: 100%; background: var(--sui-sel-bg); animation: sui-progress 1.6s var(--sui-snappy) infinite; }
.sui-progress.is-failed > i { animation: none; left: 0; width: 100%; background: var(--sui-accent); }
.sui-footer { margin-top: 28px; padding-bottom: 6px; }
.sui-keys { display: flex; gap: 22px; justify-content: flex-end; flex-wrap: wrap; margin-top: 5px; font: 400 11px var(--sui-font); letter-spacing: .16em; color: var(--sui-ink-dim); text-transform: uppercase; }
.sui-keys button { background: none; border: none; padding: 0; font: inherit; letter-spacing: inherit; color: inherit; cursor: pointer; }
.sui-error { color: var(--sui-accent); font-size: 12px; } .sui-error::before { content: '⊗ '; }
.sui-ok { color: var(--sui-ink-dim); font-size: 12px; } .sui-ok::before { content: '✓ '; }
.sui-saved-flash { animation: sui-flash .8s ease forwards; }

/* motion */
@keyframes sui-fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes sui-rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
@keyframes sui-draw { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes sui-title { 0% { opacity: 0; letter-spacing: -.02em; } 60% { opacity: 1; letter-spacing: .36em; } 100% { opacity: 1; letter-spacing: .32em; } }
@keyframes sui-sweep { 0% { transform: scaleX(0); opacity: 1; } 70% { transform: scaleX(1); opacity: .4; } 100% { transform: scaleX(1); opacity: 0; } }
@keyframes sui-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
@keyframes sui-progress { 0% { left: -45%; width: 35%; } 50% { left: 25%; width: 55%; } 100% { left: 110%; width: 35%; } }
@keyframes sui-flash { 20%, 60% { box-shadow: 0 0 0 2px var(--sui-ok); } 100% { box-shadow: none; } }
.sui-slide-in { animation: sui-slide .38s var(--sui-spring) both; }
@keyframes sui-slide { from { opacity: 0; transform: translateX(16px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
  .sui *, .sui *::before, .sui *::after, .sui::after { animation: none !important; transition: none !important; }
}
```

---

## 15. React components

Small, dependency-free versions of the pieces that need behavior. Style comes from section 14.

### 15.1 Menu

```jsx
import { useEffect, useRef, useState } from "react";

export function Menu({ label, align = "left", primary = false, keepMounted = false, disabled, children }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={ref} className="sui-menu-wrap">
      <button type="button" className={`sui-btn${primary ? " is-primary" : ""}`} aria-haspopup="menu" aria-expanded={open}
        disabled={disabled} onClick={() => setOpen((v) => !v)}>{label} ▾</button>
      {(open || keepMounted) && (
        <div role="menu" aria-label={label} className={`sui-menu${align === "right" ? " right" : ""}`} hidden={!open}
          onClick={(e) => { if (e.target.closest("button") && !e.target.closest("[data-keep-open]")) setOpen(false); }}>
          {children}
        </div>
      )}
    </div>
  );
}
export const MenuItem = ({ children, ...p }) => <button type="button" role="menuitem" className="sui-menu-item" {...p}>{children}</button>;
export const MenuLabel = ({ children }) => <div className="sui-menu-label">{children}</div>;
export const MenuSep = () => <div className="sui-menu-sep" role="separator" />;
```

### 15.2 Page header and footer

```jsx
export function PageHeader({ title, subtitle = [], context = [] }) {
  return (
    <header className="sui-header">
      <div>
        <h1 className="sui-title">{title.toUpperCase()}</h1>
        <div className="sui-sub">:: {subtitle.join(" · ")}</div>
      </div>
      <div className="sui-rule" aria-hidden="true"><span className="sui-diamond" /><span className="sui-line" /><span>||</span></div>
      <div className="sui-ctx">{context.length ? context.map((c) => <div key={c}>{c}</div>) : <div>NOTHING OPEN</div>}</div>
    </header>
  );
}

export function KeyFooter({ app, keys }) {          // keys: [["CTRL+K", "SEARCH"], ...]
  return (
    <footer className="sui-footer">
      <div className="sui-staff thin" aria-hidden="true"><i /><i /></div>
      <div className="sui-keys"><span className="sui-grow">{app}</span>{keys.map(([k, v]) => <span key={v}>{k} :: {v}</span>)}</div>
    </footer>
  );
}
```

### 15.3 Panel with tabs

```jsx
export function Panel({ title, end, children }) {
  return <section className="sui-panel"><div className="sui-strip">{title}{end && <span className="end">{end}</span>}</div>{children}</section>;
}

export function Tabs({ tabs, value, onChange }) {        // tabs: [["content", "CONTENT"], ["keys", "KEYS · 2"]]
  return (
    <div className="sui-tabs inner" role="tablist">
      {tabs.map(([k, label]) => (
        <button key={k} type="button" role="tab" aria-selected={value === k} className="sui-btn" onClick={() => onChange(k)}>{label}</button>
      ))}
    </div>
  );
}
// <div role="tabpanel" hidden={tab !== "keys"}>…</div>  — hidden panels stay mounted
```

### 15.4 Console (outline)

```jsx
// State to keep: open, mode ("dock" | "float"), height, pos {x, y, w, h}; persist all four in localStorage (try/catch).
// - document.body.style.paddingBottom = `${(open && mode === "dock" ? height : 32) + 8}px`
// - window keydown: (e.ctrlKey || e.metaKey) && e.key === "/" -> toggle
// - dock: drag .sui-console-grip -> height = clamp(160, innerHeight - 120, startHeight - dy)
// - float: drag the header where !e.target.closest("button, select, input, textarea") -> move; corner mark -> resize
// Closed:
<button type="button" className="sui-console-bar" aria-label="Open the console" onClick={() => setOpen(true)}>
  <span className="sui-diamond" aria-hidden="true" /><span>NAME</span><span className="dim">:: WHAT IT DOES</span>
  <span className="end">2 OPEN CHANGES · CTRL+/ ▴</span>
</button>
// Open:
<aside className={`sui-console${mode === "float" ? " is-float" : ""}`} aria-label="Console" style={frame}>
  {mode === "dock" && <div className="sui-console-grip" aria-hidden="true" onPointerDown={startResize} />}
  <div className="sui-console-head" onPointerDown={mode === "float" ? startMove : undefined}>
    <span className="sui-diamond" aria-hidden="true" /><b className="sui-console-name">NAME</b>
    <span className="sui-console-ctx">:: CONTEXT</span><span className="sui-grow" />
    <button className="sui-btn sm">NEW</button>
    <button className="sui-btn sm" aria-label={mode === "float" ? "Dock at the bottom" : "Float as a window"}>{mode === "float" ? "⇊ DOCK" : "⧉ FLOAT"}</button>
    <button className="sui-btn sm" aria-label="Hide the console" onClick={() => setOpen(false)}>▾ HIDE</button>
  </div>
  <div className="sui-console-body">
    <div style={{ flex: "1 1 360px", display: "flex", flexDirection: "column", minWidth: 0 }}>
      <div className="sui-console-log" aria-live="polite">{lines.map((l) => <div key={l.id}><span className="who">{l.who} ::</span> {l.text}</div>)}</div>
      <div className="sui-console-input"><textarea rows={2} aria-label="Message" /><button className="sui-btn is-primary">SEND</button></div>
    </div>
    <div className="sui-console-side">{/* .sui-change rows with OPEN / KEEP / UNDO */}</div>
  </div>
</aside>
```

---

## 16. Checklist for a new screen

- [ ] Staff band, tab row, header (title, `:: subtitle`, rule, context), footer with key hints.
- [ ] Only tokens; no hex in components; no border radius; no new hues.
- [ ] Toolbar: at most 5 visible actions, one primary; the rest in `NEW ▾` / `TOOLS ▾` / `EXPORT ▾` / `GENERATE ▾`.
- [ ] Every panel starts with a strip; empty states say the next step.
- [ ] Long editors split into tabs; hidden tabs stay mounted.
- [ ] Selected things are inverted; the list's selected row has the cursor.
- [ ] Accent only for danger, errors, secrets and undone states, always with a word or symbol.
- [ ] Contrast checked against section 11; focus ring visible; icon buttons labeled; menus and tabs have roles.
- [ ] Works at 390 px wide with no sideways scroll; touch targets ≥ 44 px.
- [ ] Dark mode checked: strips and selected items are light blocks with dark text.
- [ ] Motion: spring curve, lines before content, 80 ms stagger, reduced-motion respected.
- [ ] Copy: UPPERCASE labels, `Report:` / `Proposal:` system voice, `⊗` errors, `✓` saves.
