# Графики под канон — прогресс

Ветка: `feat/calc2-canon` (создана от `main`, коммит 72546b1)
Последнее обновление: 2026-08-18, фаза 0
Остаток контекста на момент записи: ~78 %

## ⚠️ Расхождение промпта с репозиторием — прочитать первым

Промпт, аудит и карточка Notion говорят: «весь код вкладки живёт в одном файле
`calc2/templates/calc2/calc2.html` (~6 700 строк)». **Это неверно.** Файл разрезан
ещё в сессии calc2 от 2026-07 и сейчас выглядит так:

| Что | Где | Строк |
|---|---|---|
| разметка | `calc2/templates/calc2/calc2.html` | 2 325 |
| стили | `calc2/static/calc2/calc2.css` | 1 770 |
| код | 23 скрипта `calc2/static/calc2/NN-*.js`, подключены по порядку | 20 149 |
| **итого** | | **24 244** |

На работу это не влияет по существу — меняется только адрес правки. Но правило
промпта «один файл на всю работу» читать как «только каталог `calc2/` плюс
`templates/_tokens.html` в фазе 1». Ни один файл платформы не трогается.

## Карта кода — где что искать

Порядок подключения важен: он повторяет прежний порядок объявлений.

| Файл | За что отвечает | Ключевое для нашей работы |
|---|---|---|
| `00-config.js` | `CONFIG`, `STATE`, палитра, тема | `STATE` (84), `refreshColors`, `roleColor`, `setCalcTheme` |
| `10-math-core.js` | разбор формул, корни, интегрирование | `compileFormula`, `evalCurve`, `detectLinear`, `findEquilibrium`, `integrate` |
| `20-plane.js` | шкалы, оси, сетка, **поля холста** | **`fmt` (81) — форматтер чисел**, `fmtInput`, `fitMargins`, `makeScales`, `drawAxes`, `axisTicks` |
| `30-curves.js` | кривые, **подписи кривых** | `labelCurve`, `spreadLabels`, `applyLabelSize`, `curveAnchor`, `attachDrag` |
| `40…56-scenes-*.js` | сцены по разделам | `update*Panel` — сборка строк `<div class="stat">`, `draw*` — отрисовка |
| `52-modes.js` | режимы, зум, панорама, авто-масштаб | `setMode`, `applyScenarioVisibility`, `zoomBy`, `panByPixels`, `applyAutoRanges` |
| `60-overlays.js` | `redrawAll` и слой поверх сцены | `drawOverlays`, `typesetStats`, `drawLegend`, `legendCorner`, `keyTargets`, `drawMarks`, `resetDecor`, `SCENE_DEFAULTS` (2847), `saveSceneSnapshot`, `paramScope`, `syncParams`, `makeColorPicker`, площади |
| `70-scenes-math.js` | раздел «Математика» + **экспорт** | `mathScales`, `drawPlaneAxes`, `buildTex`, `exportPNG`, `exportPDF`, `openExport` |
| `80-ui.js` | список кривых | `addCurve`, `updateCurveExpr`, `setRole`, `renderCurveList`, `showError` |
| `82-input.js` | ввод формул, MathLive, клавиатура | `latexToMath`, `mathToTex`, `buildMathfield`, `buildKeyboard`, `equipFormulaField`, `upgradeSelect` |
| `84-picker.js` | окно выбора моделей | `loadScene`, `pickScene`, `SCENE_ROUTE` (185), `applyCardScope`, `openPicker`, `blockSpec` |
| `86-workspace.js` | шапка, панели, подсказки, печать | `clearResultPanels`, `syncAnalyticsPanel`, `hintTip`, `showHintTip`, `wireHintButtons`, `fillPrintBlocks`, `setWrenchOpen` |
| `88-params.js` | правая панель, ползунки | `updatePult`, `syncPultRegulators`, `refreshRegulators`, `makePchip`, `buildParamChip` |
| `90-explain.js` | тексты «Объяснение модели» | `sceneExplainHtml` |
| `99-boot.js` | запуск | `init`, `lockNumberFields` |

Что уже есть и переиспользуется, а не строится заново:
`fmt()` (единый форматтер уже существует, ~470 вызовов — чинить надо не «завести»,
а «провести через него всё и считать суммы из округлённого»);
`fitMargins()` (поля холста уже считаются, а не константа — проверить, что мерит);
`spreadLabels` / `dodgeLabel` (зачаток слоя подписей);
`legendCorner` (зачаток раскладки плавающего);
`clearResultPanels` (зачаток скрытия чужих блоков).

## Фазы

| № | Фаза | Статус | Коммит | Заметка |
|---|---|---|---|---|
| 0 | Укладка документов | готово | — | канон, аудит, протокол, ссылка в CLAUDE.md |
| 1 | Основание: токены и контраст (п. 75) | не начато | | |
| 2 | Числа и состояние сцены (п. 1–13) | не начато | | |
| 3 | График: подписи, оси, поля, легенда (п. 30–31, 34–48) | не начато | | |
| 4 | Ввод формул (п. 14–23) | не начато | | |
| 5 | Взаимодействие с холстом (п. 24–29, 32–33) | не начато | | |
| 6 | Панели: общий каркас (п. 49–61) | не начато | | |
| 7 | Каталог, экспорт, печать (п. 62–74) | не начато | | |
| 8 | Подсказки, тексты, ширина окна (п. 76–82) | не начато | | |
| 9 | Тест канона | не начато | | пишется последней |

## Что делать следующей сессии

Начинать с фазы 1 (токены и контраст подписей). Прочитать в таком порядке:
этот файл → `reports/calc2-canon/points.md` → `DESIGN.md` части 1 и 5.1 →
`reports/calc2-audit.md` нужные пункты. Канон и аудит лежат в репозитории,
в контексте их держать не нужно — читать точечно.

## Открытые вопросы к владельцу

1. **Код не в одном файле** (см. выше). Правки пойдут по 23 скриптам и CSS
   каталога `calc2/`. Подтверждения не жду — существо работы не меняется,
   но в отчёте это названо.
