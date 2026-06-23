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

## Color
- **Curve palette is FIXED** (colorblind-distinct, identical in both themes), in CSS vars:
  `--curve-d #2F6FED` (спрос) · `--curve-s #E0563B` (предложение) · `--curve-mr #8B3FE0` (MR)
  · `--curve-mc #119C8A` (MC) · `--curve-tax #2E9E44` (налог/субсидия/бюджет — один цвет)
  · `--curve-dwl #8C8C84` (DWL) · `--curve-reg #B5791F` (потолок/пол/МРОТ) · `--curve-ghost #9AA0A6`.
  Area fills = same colors at 0.16–0.22 opacity. Cost curves: `--cost-mc/atc/avc/afc/vc`
  (teal/blue/amber/violet/slate — 5 distinct).
- **UI accent = raspberry** `#BE185D` light / `#FF4D94` dark. Chosen because it does NOT
  collide with any curve hue (blue/orange-red/violet/teal/green/amber/gray) and is clearly
  different from the site's ink-blue. White text on light accent = 6:1 (AA); accent-as-text
  on light surfaces ≈ 5:1. Dark accent uses dark `--on-accent #190810`.
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
- **Scoreboard:** "decided metric" readout — `--stat b` 19px/700 tabular-nums (Q*, P*…),
  label 12px muted. Big numbers are the instrument readout.

## Layout (Scene)
Full-bleed `.graph-wrap` (absolute inset:0). Left **dock** 56px (tool/score toggles, grid,
save+export stubs, theme). **Header** top-left: "← Сценарии" + scene name. **Tools** panel
bottom-left (relocated control sections; "Все настройки" reveals secondary mode/scenes/axes).
**Scoreboard** top-right (relocated `#info-*` blocks). Panels collapse via dock / × ; slide
horizontally (translateX). Narrow screens (≤760px): panels shrink, scene name hides.

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
