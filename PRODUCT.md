> ⚠️ **ФАЙЛ ЗАМОРОЖЕН 2026-07-13.** Актуальная версия — в Notion:
> https://app.notion.com/p/39bb11c92bc1811b90a5e7735cb0605d
> Этот файл больше не обновляется. Оставлен как исторический снимок.
> Не редактировать. Не использовать как источник истины.

# Product

## Register

product

## Users

**Teachers** (primary buyers, 25–45): olympiad economics coaches and tutors in Russia. Non-programmers. They spend their days selecting problems, composing homework sheets, reviewing student solutions, and explaining graphs. They want a tool that gets out of their way — fast to navigate, obvious to use, trustworthy in its math.

**Students** (primary daily users, 14–22): school and university competitors preparing for МОШ, ВсОШ, and IEO. They work through assignments, submit solutions, check answers, and track their own progress. They open the platform on laptops, often alongside textbooks and paper.

Both groups are serious about economics as a discipline. Neither wants to feel like they're using a toy.

## Product Purpose

ЭкЗадачи is an infrastructure tool for olympiad economics education — a task bank, homework builder, graphing calculator, and student-teacher feedback loop in one platform. It exists because no such tool exists in Russian for this niche: the market has video courses, but no place to compose sheets, assign tasks, auto-check tests, track progress, and draw supply-demand graphs, all in one place.

Success looks like: a teacher builds a homework sheet in under 5 minutes, a student submits and sees instant feedback on MCQs, and both trust the math they see (KaTeX-rendered formulas, precise graphs).

## Brand Personality

**Ясный · Дружелюбный · Точный** — Clear, Friendly, Precise.

The platform feels like a smart colleague who happens to be well-organized: it doesn't lecture you, doesn't hide information, doesn't make you hunt for buttons. It respects both teacher expertise and student effort. Warmth comes from clarity and reliability, not from mascots or gamification.

## Anti-references

- **Corporate SaaS** (Salesforce, HubSpot, Notion's marketing pages): no gradient hero metrics, no "01 / 02 / 03" section scaffolding, no aggressive upsell surfaces inside the app.
- **Soviet textbook / Word-style layout**: no Times New Roman, no black-on-white walls of text, no table-heavy forms that look like they were printed on a dot matrix.
- **Stock Django admin**: the public-facing product (catalog, student cabinet, teacher panel) must feel principally different from `/admin/` — different visual weight, different affordances, not just a reskinned data grid.

## Design Principles

1. **Clarity is the feature.** Math must render correctly. Answers must be easy to find. Labels must say what they mean. Never sacrifice readability for decoration.
2. **One tool, many roles.** Teacher and student see different surfaces but feel the same platform. Shared nav, shared color language, different information density.
3. **Precision earns trust.** Graphs, formulas, and calculations must be correct and look correct. A wrong-looking axis or a broken KaTeX expression destroys confidence faster than a missing button.
4. **Speed over flourish.** Interactions should be immediate. Animations exist only where they help orientation (e.g., a panel opening, a result appearing). Never decorate for its own sake.
5. **Grow without breaking.** The platform will add features (calendar, parent cabinet, graph-as-homework). The design system must accommodate new surfaces without each one requiring a visual restart.

## Game Surface — Econ Rush (/game/)

**The brand rule stands: warmth comes from clarity and reliability, not from gamification — and the learning surfaces (student cabinet, teacher panel, catalog) remain free of points, streaks, and badges.** Econ Rush does not soften that rule; it is deliberately fenced off from it.

Econ Rush is a separate, public *acquisition* surface: a serious speed game about economics («серьёзная игра на скорость про экономику»). Its job is to attract prospective students before they have an account — 60 seconds against the clock, real test questions from the bank, a shareable score. It is a demonstration of the platform's content, not a layer on top of the learning workflow. Points, combos, and the timer live only at `/game/` and never leak into assignments, progress pages, or the catalog.

The tone is the same **Ясный · Дружелюбный · Точный**: real olympiad-grade questions, honest feedback (the correct answer is always shown after a miss), a «Разобрать ошибки» list that links every missed question to its full catalog page — the funnel from play to study. No mascots, no confetti-for-everything (only a brief burst on a personal record), keyboard-first, reduced-motion respected.

## Accessibility & Inclusion

- Target: WCAG 2.1 AA (contrast ≥ 4.5:1 for body text, ≥ 3:1 for large/UI text).
- Russian is the primary language; formulas via KaTeX (math rendering, not images).
- Reduced motion: all transitions should degrade gracefully (instant swap or fade) when `prefers-reduced-motion` is active.
- No color-only information encoding — always pair color with shape, label, or position.
