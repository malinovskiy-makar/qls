---
name: ЭкЗадачи
description: Olympiad-economics task bank, homework builder, and graphing calculator — a quiet, precise workbench for teacher and student.
colors:
  graphite: "#1a1f2e"
  accent: "#BE185D"
  accent-deep: "#9D1450"
  warm-paper: "#f7f7f5"
  paper-cool: "#f5f5f3"
  pencil-line: "#e8e8e4"
  graphite-text: "#1a1a1a"
  muted-text: "#666666"
  amber: "#b26b00"
  solution-green: "#1d7e45"
  green-tint: "#e9faf0"
  tag-tint: "var(--accent-tint)"
  error-red: "#c0392b"
  error-tint: "#fff0f0"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "44px"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-1px"
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "normal"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "normal"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.5px"
rounded:
  sm: "6px"
  md: "10px"
  lg: "12px"
  pill: "20px"
  logo: "7px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "40px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "7px 12px"
  button-primary-hover:
    backgroundColor: "{colors.accent-deep}"
    textColor: "#ffffff"
  button-dark:
    backgroundColor: "{colors.graphite}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "11px 16px"
  card:
    backgroundColor: "#ffffff"
    textColor: "{colors.graphite-text}"
    rounded: "{rounded.md}"
    padding: "16px 20px"
  chip:
    backgroundColor: "{colors.tag-tint}"
    textColor: "{colors.accent}"
    rounded: "{rounded.pill}"
    padding: "2px 9px"
  input:
    backgroundColor: "#ffffff"
    textColor: "{colors.graphite-text}"
    rounded: "{rounded.sm}"
    padding: "7px 10px"
  nav:
    backgroundColor: "{colors.graphite}"
    textColor: "#ffffff"
    height: "48px"
---

> **Владелец:** Claude Code
> **Обновлён:** 2026-08-18
> **Статус:** актуален

> ⚠️ **Единственный источник истины по цветам — `templates/_tokens.html`.**
> Этот файл описывает намерение и правила применения; конкретные значения
> берите из токенов. Акцент сайта — малиновый `#BE185D` (светлая тема) /
> `#FF4D94` (тёмная). Прежний синий `#4f7cff` не используется с 2026-06-23.
> У `/calc2/` свой изолированный мир токенов — общими его не трогать.

# Design System: ЭкЗадачи

## 1. Overview

**Creative North Star: "The Graphite Notebook"**

ЭкЗадачи looks like a well-kept graphite notebook owned by a serious economics coach: warm off-white pages, a graphite-dark spine, one disciplined accent pen reserved for the things that matter, and a soft amber pencil that marks difficulty. The interface is calm and dense with information but never loud. It earns trust the way a good notebook does — the math is always legible, the structure is always obvious, and nothing decorative competes with the content. Warmth comes from the paper tone (`#f7f7f5`, never stark `#ffffff` for surfaces that recede) and from generous line-height on problem text, not from mascots, gradients, or gamification.

The system is built for two roles on one platform. Teachers see a denser surface (filter rails, homework builders, review tables); students see a lighter one (assignments, progress). Both share the same graphite header, the same accent accent language, and the same flat-paper card vocabulary, so the platform always feels like one tool. This is infrastructure, not a course: every screen should feel like a precise instrument a professional reaches for, not a marketing page that wants something from them.

It explicitly rejects three things. It is **not Corporate SaaS** — no gradient hero metrics, no "01 / 02 / 03" section scaffolding, no upsell surfaces inside the app. It is **not a Soviet textbook or Word document** — no Times New Roman, no black-on-stark-white walls of text, no dot-matrix table forms. And the public product is **not a reskinned Django admin** — the catalog, student cabinet, and teacher panel must carry visibly different weight and affordances than `/admin/`.

**Key Characteristics:**
- Warm-paper surfaces, graphite structure, a single accent accent used sparingly.
- Flat by default; depth appears only on interaction (hover lift, focus ring, modal).
- Math is first-class: KaTeX-rendered formulas, never images, never broken `$`.
- Information-dense but quiet — the accent earns attention because it is rare.
- One platform, two densities: teacher-dense, student-light, shared language.

## 2. Colors

A warm-neutral paper palette anchored by a graphite dark and lit by exactly one saturated accent, with two functional signal colors (amber for difficulty, green for "has solution").

### Primary
- **Accent (Crimson)** (`#BE185D`): The single brand accent. Used for the logo tile, active nav state, primary buttons, focused inputs, links, chips, and the difficulty/solution affordances that need to read as "interactive." This is the one voice — it should never cover large areas.
- **Accent Deep** (`#9D1450`): The pressed/hover state of every accent surface. Slightly desaturated and darkened so hover feels like weight, not color change.

### Secondary
- **Graphite** (`#1a1f2e`): The structural dark. Header bar, nav, dark "Войти" submit button, and any surface that frames rather than holds content. It is a blue-leaning near-black, not pure black — it belongs to the same cool family as the accent.

### Tertiary (functional signals)
- **Difficulty Amber** (`#b26b00` светлая / `#f5a623` тёмная): Reserved exclusively for difficulty stars (★) and their tints (`#fff8ed`, `#fff3d9`). Pairs color with the star shape so difficulty is never color-only.
- **Solution Green** (`#1d7e45` светлая): Reserved for the "решение ✓" badge and confirmation states, on a green tint (`#e9faf0`). Always paired with the ✓ glyph or explicit text.

### Neutral
- **Graphite Text** (`#1a1a1a`): Primary body and heading text on paper. Carries the WCAG-AA contrast load.
- **Muted Text** (`#666666`): Secondary text — meta, captions, slogans, inactive labels.
- **Warm Paper** (`#f7f7f5`): The recessive surface — filter cards, panels, the contextual rail. Surfaces that hold content sit on white; surfaces that frame it sit on warm paper.
- **Paper Cool** (`#f5f5f3`): The full-bleed page background behind the login card.
- **Pencil Line** (`#e8e8e4`): Borders and dividers, almost always at `0.5px`–`1.5px`. The hairline that defines a card without shouting.
- **Accent Tint** (`var(--accent-tint)`): The pale accent wash behind chips/tags.

### Error
- **Error Red** (`#c0392b`) on **Error Tint** (`#fff0f0`) with a `#ffd5d5` border: login failures and validation only. Never used decoratively.

### Named Rules
**The One Voice Rule.** Accent Crimson (`#BE185D`) appears on ≤10% of any screen. Its rarity is what makes "active," "primary," and "interactive" instantly legible. If two accent elements compete on one screen, one of them is wrong.

**The No-Stark-White Rule.** Pure `#ffffff` is for content cards only. Page chrome and recessive panels use warm paper (`#f7f7f5`) or cool paper (`#f5f5f3`). A screen that is all `#ffffff` reads as a Django admin grid, not as ЭкЗадачи.

**The Signal-Color Lockbox.** Amber means difficulty, green means solution-present. Neither is ever borrowed for decoration, hover, or emphasis. A color that means something cannot also mean nothing.

## 3. Typography

**Display / Body / Label Font:** The native system stack — `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`. One family across the whole UI; weight and size carry the hierarchy.
**Math Font:** KaTeX (Computer Modern) for all formulas — rendered, never rasterized.

**Character:** Neutral, legible, fast-loading, and invisible by design — the system font gets out of the way so economics content and math render are the only things the eye resolves. The personality lives in weight contrast (800 display against 400 body) and in tight tracking on the wordmark, not in a bespoke typeface.

### Hierarchy
- **Display** (800, 44px, line-height 1.05, letter-spacing −1px): The "ЭкЗадачи" wordmark and home hero only. The one place the type is allowed to be loud.
- **Headline** (700, 18–20px, 1.3): Page-level and card-group headings ("Войти", section titles).
- **Title** (600–700, 14–15px, 1.4): Problem-card titles, modal titles, list item headings.
- **Body** (400, 13–15px, 1.55–1.65): Problem statements and prose. Generous line-height because problem text is dense and often carries inline math; readability is the feature.
- **Label** (600, 11px, uppercase, letter-spacing 0.5px): Filter-rail section labels, badge captions, table column heads. The quiet structural scaffolding of dense screens.

### Named Rules
**The Readable-Math Rule.** Problem body line-height never drops below 1.55. Inline KaTeX needs vertical air; tight leading turns a fraction into a smudge.

**The Weight-Not-Color Hierarchy.** Heading vs. body is expressed by weight and size, not by tinting text with the accent. Accent text is reserved for links and active state — never for "making a heading pop."

## 4. Elevation

Flat by default. Surfaces rest on the page defined only by a `0.5px`–`1.5px` Pencil Line border. Depth is a *response to state*, not an ambient property — it appears on hover, focus, and overlay, then disappears. There is no global drop-shadow on resting cards; a card you are not touching is a flat sheet of paper.

### Shadow Vocabulary
- **Card hover** (`box-shadow: 0 2px 14px rgba(0,0,0,0.07)`): The gentle lift a problem card takes when hovered, paired with a slightly darker border. The page feels like paper you can pick up.
- **Accent hover** (`box-shadow: 0 4px 16px rgba(190,24,93,0.12)` + `translateY(-2px)`): Home navigation cards — a tinted lift that previews the accent destination.
- **Focus ring** (`box-shadow: 0 0 0 3px rgba(190,24,93,0.15)`): The soft accent halo on a focused search field. Replaces, never adds to, a hard outline.
- **Dropdown** (`box-shadow: 0 4px 20px rgba(0,0,0,0.12)`): The "+ В домашку" menu — enough lift to read as floating above the card.
- **Modal** (`box-shadow: 0 8px 40px rgba(0,0,0,0.18)`): The problem-preview overlay — the deepest shadow in the system, used once at a time over a `rgba(0,0,0,0.45)` scrim.

### Named Rules
**The Flat-By-Default Rule.** Resting surfaces have a border, never a shadow. If a card has a drop-shadow while no one is touching it, the shadow is wrong. Motion and depth are feedback, not decoration.

## 5. Components

### Buttons
- **Shape:** Gently rounded — `6px` (sm) for compact actions, up to `20px`/`26px` full-pill for the home search submit and chips.
- **Primary:** Accent fill, white text, `6px` radius, ~`7px 12px` padding. The home hero submit grows to a `20px` pill inside a `26px` search field.
- **Dark:** Graphite fill (`#1a1f2e`), white text, used for the login "Войти" submit — full-width, `11px` vertical padding. Hover deepens to `#252c40`.
- **Hover / Focus:** Primary deepens to Accent Deep (`#9D1450`); transitions are `~0.12s–0.15s` on `background`, `border-color`, and (cards) `transform`. No bounce, no scale-up beyond a `2px` lift.
- **Ghost / Outline:** White fill, Pencil-Line border, muted text; on hover the border and text shift to accent (e.g. "👁 Условие", "+ В домашку").

### Chips
- **Style:** Pill (`20px` radius), Tag-Tint (`var(--accent-tint)`) background, accent text, `2px 9px` padding, weight 500. The solution variant swaps to green tint + Solution Green text + a ✓.
- **State:** Topic tags are static labels (not interactive); difficulty/type *filter* chips in the rail invert to accent fill when active.

### Cards / Containers
- **Corner Style:** `10px` (problem & filter cards), `12px` (home nav cards, modal, login card).
- **Background:** White for content cards; Warm Paper (`#f7f7f5`) for the recessive filter rail.
- **Shadow Strategy:** None at rest (see Elevation) — `0.5px` Pencil-Line border only. Hover adds Card-hover shadow + border darkening.
- **Internal Padding:** `16px–20px` for list cards, `18px` for the filter card, `24px` for home nav cards, `40px` for the login card.

### Inputs / Fields
- **Style:** White fill, `0.5px–1.5px` Pencil-Line border, `6px` radius, `7px–12px` padding, system font at 13–15px.
- **Focus:** Border shifts to accent; the home search additionally gains the `3px` accent focus halo. No hard browser outline.
- **Error:** Wrapped in the Error-Tint panel with Error-Red text; field itself keeps its border.

### Navigation
- **Style:** A sticky graphite bar (`#1a1f2e`), `48–52px` tall, with the `28px` rounded accent "Эк" logo tile at the left.
- **Typography:** 13px links at weight 500. Inactive links are `rgba(255,255,255,0.6)`; hover goes to full white; the **active** link is full white with a `2px` accent bottom border.
- **Role-aware:** Teacher, student, and guest see different link sets but identical styling — the nav is the clearest expression of "one platform, many roles."

### Filter Rail (signature component)
The left rail in the catalog is the platform's signature dense surface: a Warm-Paper card holding uppercase 11px section labels, a search row, native `select`s for theme/source, amber star-buttons for difficulty, stacked type buttons, and a reset link. It is the teacher's instrument panel — quiet, compact, every control one click deep.

## 6. Do's and Don'ts

### Do:
- **Do** keep Accent Crimson (`#BE185D`) under ~10% of any screen — logo, one primary action, active state, links. Let its rarity do the work (The One Voice Rule).
- **Do** sit recessive chrome on Warm Paper (`#f7f7f5`) and content on white. Mixing them is how the platform reads as "designed," not "admin."
- **Do** define resting surfaces with a `0.5px` Pencil-Line border and reserve shadow for hover/focus/overlay (The Flat-By-Default Rule).
- **Do** keep problem-body line-height ≥ 1.55 so inline KaTeX stays legible (The Readable-Math Rule).
- **Do** pair every signal color with a shape or word — amber with ★, green with ✓ — so nothing is color-only (WCAG 2.1 AA, no color-only encoding).
- **Do** express hierarchy with weight and size; keep transitions ≤ 0.15s and degrade them to instant under `prefers-reduced-motion`.

### Don't:
- **Don't** build Corporate SaaS surfaces: no gradient hero metrics, no "01 / 02 / 03" section scaffolding, no upsell banners inside the app.
- **Don't** fall back to a Soviet-textbook / Word look: no Times New Roman, no black-on-stark-white walls of text, no dot-matrix table forms.
- **Don't** let the public product look like a reskinned Django admin grid — it must carry different visual weight and affordances than `/admin/`.
- **Don't** tint heading text with the accent to "make it pop" — accent text means link or active state, nothing else (The Weight-Not-Color Hierarchy).
- **Don't** borrow amber or green for decoration — they mean difficulty and solution-present, respectively (The Signal-Color Lockbox).
- **Don't** put a drop-shadow on a resting card, and don't use a `border-left` color stripe thicker than the hairline as a substitute for real hierarchy.

## 7. Scoped surface — Graphing instrument (/calc2/)

The new graphing calculator (`/calc2/`) is the one place that **departs from the accent
system on purpose**. It is a tool where the full-bleed plot is the hero and controls/results
float over it like instrument readouts, so it has its own scoped tokens (full detail in
`.interface-design/system.md`). The rest of the site is unchanged.

- **Curve palette (fixed, colorblind-distinct, both themes):** `--curve-d #2F6FED` (спрос),
  `--curve-s #E0563B` (предложение), `--curve-mr #8B3FE0` (MR), `--curve-mc #119C8A` (MC),
  `--curve-tax #2E9E44` (налог/субсидия/бюджет — единый зелёный), `--curve-dwl #8C8C84` (DWL),
  `--curve-reg #B5791F` (потолок/пол/МРОТ), `--curve-ghost #9AA0A6` (исходное состояние).
  Area fills reuse these at 12–22 % opacity. Cost curves: `--cost-mc/atc/avc/afc/vc`.
- **UI accent — raspberry**, deliberately NOT accent: `#BE185D` (light) / `#FF4D94` (dark).
  Reserved for **small** affordances only: checkbox `accent-color`, focus rings, "← Сценарии"
  border. Chosen because it collides with no curve hue. White-on-accent = 6:1 (AA).
- **Large action buttons (`.btn`)** — graphite, NOT raspberry: `--btn-bg #1e293b` (light) /
  `#334155` (dark), hover `--btn-bg-hover #293548` / `#3e4f69`, text `--on-btn #ffffff`.
  Linear/Stripe-style calm fill so crimson remains a rare accent, not a background wash.
- **Dual theme** (light default, dark for evening/projector), `data-theme` on `<html>`,
  persisted; structural canvas colors (`--ink/--ink-soft/--grid/--halo/--canvas`) flip with theme.
- **Surfaces:** floating panels on `--surface` with 1px `--border` + soft `--shadow-panel`;
  dock/inputs on `--surface-2`. Radii `--r-sm 6 / --r 8 / --r-lg 14`. Motion `--ease`
  `cubic-bezier(.23,1,.32,1)`, all < 300 ms, full `prefers-reduced-motion` off-switch.
- **Signature:** the scenario-picker cards carry a mini-graph drawn in the engine's own
  curve colors; the scoreboard shows big tabular "instrument" numbers (Q*, P*, …).

## 8. Scoped surface — Game (/game/)

Econ Rush is a public acquisition surface (no login) that stays inside the site's
raspberry «Scene» system but adds a scoped `--rush-*` token layer, every value of
which **maps onto the global tokens** from `templates/_tokens.html` — no raw hex:
`--rush-accent → var(--accent)`, `--rush-surface → var(--surface)`,
`--rush-ok/-tint → var(--green)/(--green-tint)`, `--rush-bad/-tint → var(--error)/
(--error-tint)`, motion ease `cubic-bezier(.23,1,.32,1)`. Both themes come for free
via the shared `localStorage['theme']` key and the shared anti-flash bootstrap.

- **Documented exception to the Signal-Color Lockbox — the time bar.** The 8px
  time track re-colors by remaining time: raspberry (normal) → amber `var(--amber)`
  (<15 s) → red `var(--error)` with a slow pulse (<7 s). This borrows the amber
  signal hue for something other than difficulty stars — allowed HERE ONLY because
  the bar encodes timer semantics (urgency), is unique on screen, never appears on
  learning surfaces, and is always paired with the numeric timer (no color-only
  encoding). Do not copy this pattern elsewhere.
- **Key badges (kbd style):** each answer button carries a 26px square badge
  `1`–`5` — `--surface-2` fill, `--border` outline with a 2px bottom edge
  (keycap look), `--text3` label. Hidden on touch (`hover: none`) and under 720px.
  Hover of the whole option = raspberry border + `--accent-tint` wash; correct =
  green tint + green border; wrong = red tint + shake, correct option outlined
  green. Green/red here are true semantic verdicts — not decoration.
- **Layout:** game scene max 760px, question card on `--surface`, radius 16,
  card-hover shadow from the vocabulary; options grid 2×2 (odd last option spans
  full width), one column on mobile. Final screen: two columns ~880px
  (score + 2×2 stats | «Разобрать ошибки» list), stacked on mobile.
- **Motion:** all under ~500 ms with the calc2 ease; «+6 с» chip flies to the
  time bar (~450 ms), wrong answer shakes 300 ms + brief red vignette, next
  question slides up ~500 ms, combo badge pulses on ×2/×3/×4 thresholds; canvas
  confetti ~1.5 s only on a new personal record. Everything collapses to instant
  swaps under `prefers-reduced-motion`.
