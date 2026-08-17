# Interface system — /calc2/ «Сцена» (графический калькулятор 2.0)

Scoped to the calc2 redesign. The rest of the site keeps the "Graphite Notebook"
system in `DESIGN.md` (ink-blue accent). /calc2/ is its own surface: a **graphing
instrument** where the full-bleed plot is the hero and controls/readouts float over it.

## Direction & feel
"Чертёжный инструмент / осциллограф" — calm, exact, a little technical. The graph is
the focal point; UI is quiet graphite chrome so the curve colors are the only saturated
thing on the canvas. Dual theme: **light is default** (classroom / projector / print
parity), **dark** for evening work. Persisted in `localStorage['calc2-theme']`; system
preference is the first-run default; applied pre-paint in a `<head>` bootstrap.
(The key is now plain `localStorage['theme']`, shared with the rest of the site — it was
unified so the theme carries across /calc2/ and the catalog.)

## Color
- **Curve palette is FIXED** (colorblind-distinct, identical in both themes), in CSS vars:
  `--curve-d #2F6FED` (спрос) · `--curve-s #E0563B` (предложение) · `--curve-mr #8B3FE0` (MR)
  · `--curve-mc #119C8A` (MC) · `--curve-tax #2E9E44` (налог/субсидия/бюджет — один цвет)
  · `--curve-dwl #8C8C84` (DWL) · `--curve-reg #B5791F` (потолок/пол/МРОТ) · `--curve-ghost #9AA0A6`.
  Area fills = same colors at 0.16–0.22 opacity. Cost curves: `--cost-mc/atc/avc/afc/vc`
  (teal/blue/amber/violet/slate — 5 distinct).
- **UI accent = raspberry** `#BE185D` light / `#FF4D94` dark. Reserved for **small**
  affordances: checkbox `accent-color`, focus rings (`--accent-ring`), "← Сценарии" border,
  active-state dot on dock. Does NOT collide with any curve hue. White on accent = 6:1 (AA);
  dark accent uses `--on-accent #190810`.
- **Large action buttons (`.btn`)** — graphite, NOT raspberry: `--btn-bg #1e293b` (light) /
  `#334155` (dark); hover `--btn-bg-hover #293548` / `#3e4f69`; text `--on-btn #ffffff` both
  themes. Keeps crimson as a rare signal — not a background fill on every CTA.
- **Structural canvas colors are theme-aware** (`--ink`, `--ink-soft`, `--grid`, `--halo`,
  `--canvas`) and read into a JS `COL` map (`refreshColors()`) on every redraw, so theme
  switching repaints the SVG. SVG gets concrete hex via `COL.*` (never `var()` in SVG attrs).
- Text ramp: `--text` / `--text2` / `--text3` (all AA on their surfaces — `--text3` was
  darkened to pass for 11px labels).

## Depth & surfaces
Borders-first (technical tool). Floating panels sit on `--surface` over the canvas with a
1px `--border` + a soft elevation shadow (`--shadow-panel`). Dock/inputs use `--surface-2`.
One hue, lightness-only shifts across surfaces. Dark mode leans on borders, not shadows.

## Spacing & radius
4px base. Radii scale: `--r-sm 6` (controls) · `--r 8` (inputs/spec frames) · `--r-lg 14`
(cards/panels). Panel padding 12–14px (workbench density).

## Hierarchy
- **Picker (Screen 1):** one hero — `picker-title` 30px/800. Category labels 11px/600 muted.
  Cards carry a mini-graph specimen drawn in the engine's own curve colors (the signature).
- **Scoreboard:** "decided metric" readout — `.sb-body .stat b` **16px/700** tabular-nums,
  label 12px/500 muted. (Recorded as 19px originally; lowered to 16 once real scenes turned
  out to show up to ~11 rows at once — 19px made the panel a wall and broke the "one focal
  point" it was meant to create. 16 vs 12 still reads as an instrument readout.)
  The same `.stat` inside **Tools** stays 13px: there it is reference text, not a readout.

## Card specimens — icon geometry (fixed tiers)
Every mini-graph in the picker uses exactly three stroke weights, one marker size, one dash:
**axes/helper 1.5 · secondary or dashed curve 2.2 · primary curve 2.6 · marker r 3.6 ·
dash `5 4`**. Fills that hint at an area use `opacity .16` (matching the canvas area-fill
rule); a deliberately faded line uses `.4`. Bands (deficit strip, integral strips) are
`<rect>` fills, never thick strokes. Before this was fixed there were 11 stroke widths,
5 marker radii and 4 dash patterns across 30 cards.

## Layout (Scene) — docked columns, 2026-07-29
Four columns in a flex row, **no panel ever overlaps the plot**:
`dock 56 · tools 316 · graph (flex:1) · params 268`. Collapsed panel shrinks to a
**26px rail** carrying only its arrow — never a fully hidden panel the user must hunt for.
Width transition 220ms; the canvas redraws from a **ResizeObserver** on `.graph-wrap`
(catches both window resize and panel collapse — there is no `window.resize` listener).

- **Dock (56px)** — exactly four scene actions (back / analytics / save / download),
  each with a right-side tooltip; theme sits alone at the bottom behind the spacer.
- **Tools panel (316px)** — two sticky-titled parts in one scroll: «Ввод функций»
  then «Аналитика» (the former scoreboard). Scene name is the panel head.
  316 vs 268 is deliberate: formulas need width, knobs don't.
- **Params panel (268px)** — live regulators. Each is a two-row `.pchip`:
  name + tabular value on top, full-width range below. One shape for every
  regulator kind; a single-line layout is unreadable in a 268px column.
- **Wrench menu** (`.wrench`, 268px, top-right over the plot) owns everything about
  the *plane*: both axis bounds, tick step, axis names, grid tri-state, legend,
  graph title + its color. Nothing about the *model* lives there.
- **Reset-view button** appears only when `STATE.viewDirty` — an affordance that
  shows up exactly when it has something to do.

## Area legend
Lower-right corner **inside** the plot, vertical stack, short codes only
(CS · PS · Tx · GS · DWL · VC) at 11px/600 with an 11px swatch; full name lives in
`<title>`. It was a horizontal strip across the top margin and fought the graph title.
Note for tests: a legend `<text>` node's `textContent` includes the `<title>` child.

## Math input
`math-field` inherits the input token set (`--input-bg`, `--border`, `--r-sm`) plus
`--caret-color: var(--accent)`; built-in MathLive toggles hidden via `::part()`.
Keyboard `.mkbd` opens **below** the field: 3 tab sections, one open at a time,
keys `min 30×32px` (touch-safe), footer links to examples and the piecewise builder.

## Motion
ease-out `cubic-bezier(.23,1,.32,1)` (`--ease`), all <300ms. Picker content fade+rise once
(no fill-mode → never blank). Panels slide on collapse. Dock press `scale(.92)`. Full
`prefers-reduced-motion` off-switch.

## A11y invariants
Picker = `role="dialog"`/`aria-modal`; app `inert` while open, picker `inert`+`visibility:hidden`
while closed; Escape closes; Tab trapped to cards; focus returns to "← Сценарии". Decorative
icon SVGs `aria-hidden`; specimen SVGs inside `aria-hidden` spans. Dock toggles use `aria-pressed`.

## Hard constraint
Engine math/draw/dispatch function names are frozen (`redrawAll`, `loadScene`, `setMode`,
`setMarket`, `setType`, `setTax`, `setPReg`, `findEquilibrium`, `integrate`, `drawAxes`, …).
Section/control **IDs** and their wiring are preserved — the redesign only moves DOM nodes and
restyles; visibility is still `display` toggled on section IDs by `setMode`/`setScenario`.
