# Карта модулей calc2

## Как читать эту карту

Карта нужна для одного: по описанию бага в `/calc2/` выбрать два-три файла и
приложить их в чат, вместо того чтобы гадать по именам или просить весь набор
исходников вслепую. Сначала смотрите таблицу «Симптом → куда смотреть» —
большинство жалоб укладываются в готовую строку. Если своей строки нет,
смотрите «Модули» — там по каждому файлу написано, за что он отвечает и что
в нём искать, простыми словами. Карта не заменяет чтение кода (см. решение
Notion «calc2 в чате разбирается по исходникам, а не по симптомам») — она
только сокращает путь до нужного файла.

## Модули

Порядок — как в шаблоне: скрипты подключаются по счёту, поэтому файлы
объявлений здесь идут в том же порядке загрузки. ⚠️ Их **22**, не 21 — в
CLAUDE.md с сессии, где появился `90-explain.js`, счётчик не поправили;
здесь и в автосекции ниже число настоящее, посчитанное по шаблону.

**`calc2/urls.py`** — два маршрута: `/calc2/` (сама страница) и
`/calc2/export/pdf/` (POST, сборка PDF из присланного `.tex`). Смотреть, если
жалоба вообще на то, что страница/кнопка PDF не открывается по адресу.

**`calc2/views.py`** — `Calc2View` рендерит шаблон и кладёт в контекст
`has_pdflatex` (есть ли на сервере чем собрать PDF — от этого зависит, видна
ли кнопка «Скачать PDF» в разметке); `export_pdf` — сборка присланного `.tex`
через pdflatex: фильтр запрещённых LaTeX-команд `_TEX_FORBIDDEN`, компиляция
`compile_pdf_pdflatex`. Смотреть при жалобах на PDF-экспорт (не собирается,
кнопки нет, приходит смысла лишённая ошибка).

**`calc2/templates/calc2/calc2.html`** — вся разметка страницы одним файлом
(2421 строка): четыре колонки (полоса иконок · «Ввод функций + Аналитика» ·
холст графика · «Основные параметры»), меню гаечного ключа над графиком, окно
выбора сценария (10 блоков), в конце файла — подключение `calc2.css` и всех
22 скриптов по порядку. Смотреть, если элемента вообще нет на экране (не
найден `id`), если разметка выглядит «сломанной» независимо от данных, или
если непонятно, в каком файле искать логику конкретной кнопки/поля — тут
всегда есть её `id`, по которому грепается обработчик в JS.

**`calc2/static/calc2/calc2.css`** — все стили калькулятора одним файлом.
Свой ИЗОЛИРОВАННЫЙ мир токенов (`--curve-*`, `--cost-*`, свой переключатель
темы) — не путать с токенами остального сайта (`_tokens.html`). Смотреть при
жалобах «выглядит не так»: не тот цвет, размер, отступ, наложение элементов —
если элемент точно есть в разметке (см. calc2.html), но неправильно нарисован.

**`00-config.js`** — `CONFIG` (границы плоскости `Qmin/Qmax/Pmin/Pmax`, шаг
сетки, отступы полей `margin`), `STATE` (главный объект состояния —
активная сцена, кривые, оформление, масштаб), палитра `COL`, размеры
подписей `FS`/`FS_PT`/`LABEL_SIZE_DEFAULT`. Смотреть при жалобах на масштаб
«по умолчанию» после сброса, неверную палитру, размер шрифта подписей (три
буквы «А» в меню).

**`10-math-core.js`** — разбор и вычисление ОДНОЙ явной формулы `y = f(x)`:
`compileFormula`, `evalCurve`, `detectLinear`/`refreshLinearForParams`
(быстрый путь для прямых линий — именно он перетаскивает кривую мышью),
`curveParamNames`/`paramSignature`. ⚠️ Подготовка строки (`prepExpr`,
перевод LaTeX, раскрытие неявного умножения) здесь НЕ живёт — она в
`60-overlays.js`, несмотря на то что логично было бы ждать её тут. Смотреть
при «неверное число при вычислении y(x)» и при поведении, которое зависит
именно от того, распознана ли формула как ПРЯМАЯ (перетаскивание, быстрый
пересчёт).

**`20-plane.js`** — шкалы (`mainScales`/`mathScales`), оси и числа на них
(`axisValueX`/`axisValueY`, `coordAlreadyAt`), сетка, зум и панорама
(`panByPixels`), подгонка полей холста под самую широкую подпись
(`fitMargins`). Смотреть при «подпись деления/координаты оторвалась от оси»,
«пунктир к оси без числа», «зум/панорама не работает или прыгает».

**`30-curves.js`** — отрисовка кривых на холсте, полоса захвата
(`data-hit`/`data-hit-name`), договор о параметрах — рычаг, который ничего
не двигает, не показывается (`sceneDrawsCurveList`), список кривых,
которые НЕ тянутся мышью (`NO_CURVE_DRAG`), ползунки сдвига кривой
(`setCurveFreeTerm`), подпись кривой у края графика (`requestLabelFrame`,
`curveShortName`). Смотреть при «кривую нельзя щёлкнуть/потянуть», «подпись
кривой дёргается, пропадает или показывает не то имя», «ползунок буквы не
появляется в списке кривых».

**`40-scenes-market.js`** — сцена «Спрос и предложение»: равновесие,
потоварный/адвалорный налог и субсидия, эластичность, внешние эффекты (налог
Пигу / корректирующая субсидия). Самый крупный «обычный» сюжет (1685 строк).

**`42-scenes-mono.js`** — монополия и её пять под-режимов: обычная, ценовая
дискриминация 1-й и 3-й степени, «составной спрос» (не путать с моделью
Суизи — так и написано в интерфейсе), естественная монополия.

**`44-scenes-firm.js`** — фирма: издержки (TC/ATC/AVC/AFC/MC) и
долгосрочное равновесие, производство (TP/MP/AP на двух панелях с общей
осью L), два завода (горизонтальное сложение MC).

**`46-scenes-labor.js`** — рынок труда: монопсония, профсоюз-монополист,
МРОТ — четыре под-сюжета.

**`48-scenes-consumer.js`** — выбор потребителя: бюджетная линия с
перетаскиваемыми концами, веер кривых безразличия (5 видов предпочтений),
разложение Слуцкого (три бюджетные линии A→B→C). Самый маленький сценовый
файл (261 строка) — движок касания уровня, которым он пользуется, живёт в
`10-math-core.js`.

**`50-scenes-macro.js`** — семь макромоделей через общий реестр `MACRO`:
AD–AS, кривая Филлипса, денежный рынок, рынок заёмных средств, валютный
рынок, кривая Лаффера, IS–LM.

**`52-modes.js`** — переключение сцен верхнего уровня, возврат масштаба по
нарисованному (`padMax`, `boundsOfDrawn`), правило «окно идёт за формулой,
а не за значением буквы» (`redrawKeepingWindow`, `STATE.zoomLock`),
авто-подгонка осей (`applyAutoRanges`/`applyTradeRanges`). Смотреть при
«рычаг/ползунок двигает окно графика вместо самой кривой» и при «возврат
масштаба» показывает не всё построенное.

**`54-scenes-ppf.js`** — КПВ (кривая производственных возможностей), сумма
КПВ, КТВ и торговля (четыре модели). Единый разбор формулы КПВ в трёх формах
— `parsePpfEquation`, компиляция — `compilePpf` (строка 111), пробный расчёт
— `ppfEvalWith`, панель отказа под полем — `showPaneError`. Самый частый
источник дефектов «буква не двигает кривую» (см. таблицу симптомов).

**`56-scenes-inequality.js`** — неравенство доходов: кривая Лоренца,
децильный коэффициент/коэффициент фондов, прогрессивный налог.

**`60-overlays.js`** — САМЫЙ большой файл (3916 строк) и самый частый адрес
разбора: общий слой, который работает НАД любой сценой. Здесь единая дверь
разбора формулы (`prepExpr`, `expandImplicitMul`, `freeSymbols`, `scopeFor`,
`paramScope`), обёртка перерисовки (`redrawAll` = `redrawScene` +
`drawOverlays`), ключевые точки и пересечения (`keyTargets`, `kinksOf`,
`drawCrossPoints`), прокатывание точки по кривой (`rollerTargetAt`),
заливки/легенда/табло (`applyAreaColors`, `drawLegend`, `typesetStats`),
память сцены (`resetDecor`, `saveSceneSnapshot`/`restoreSceneSnapshot`,
`resetSceneMemory`). **Если баг про разбор формулы, LaTeX, ключевые точки,
площади или легенду — начинать отсюда, а не с файла конкретной сцены.**

**`70-scenes-math.js`** — раздел «Математика» (6 сюжетов): производная и
касательная, оптимизация, деформации графика, перевёрнутые оси, min/max,
оптимум при ограничении. Своя цель двойного щелчка по подписи
(`RENAME_HIT_PX = 24`).

**`80-ui.js`** — мелкая общая разметка интерфейса, не относящаяся напрямую
к панелям формул или параметров (самый маленький «содержательный» файл).

**`82-input.js`** — весь ввод формул: подключение MathLive
(`buildMathfield`, `grabKeys` — перехват клавиш в фазе погружения из-за
кириллицы), очередь полей, которые нельзя собрать под `inert`-окном выбора
(`_mfWaiting`, `flushMathfields`), своя клавиатура, конструктор кусочных
функций, единая дверь к KaTeX (`katexSafe`, `katexInto`), компонент
«редактируемое значение» — имена точек, границы ползунков
(`makeEditableValue`). Смотреть при «формула набирается не в то место»,
«клавиатура/десятичная точка ведёт себя не так», «KaTeX рисует мусор или
красным», «правка имени/границы не сохраняется или сбрасывает значение».

**`84-picker.js`** — окно выбора сценария: реестр карточек → сцена
(`SCENE_ROUTE`), открытие сцены (`pickScene`, `baseScene`), скрытие чужих
переключателей на карточке (`applyCardScope`). Смотреть при «открылась не
та сцена» или «виден переключатель модели, которого не должно быть в этой
карточке».

**`86-workspace.js`** — каркас страницы: шапка, боковые панели и их
сворачивание, авто-раскрытие связанного блока (`openSection`), меню
координатной плоскости.

**`88-params.js`** — правая панель «Основные параметры»: регуляторы сцены,
редактор границ ползунка, два способа правки полосы значения
(`centerBandOn`/`pullIntoBand`).

**`90-explain.js`** — реестр текстов блока «Объяснение модели» по ключу
карточки; используется, когда сама сцена не пишет свой разбор. Самый
маленький сценовый файл по смыслу (одна функция-реестр).

**`99-boot.js`** — точка входа: порядок инициализации при загрузке страницы.
Самый маленький файл вообще (97 строк).

## Тесты и приборы (calc2/tests/)

Два «настоящих» теста прогоняются через `manage.py test calc2`:
`test_calc2_math.py` (поднимает живой сервер и гоняет `calc2_math.mjs` —
контрольные числа математики) и `test_export_pdf.py` (проверка эндпоинта
`/calc2/export/pdf/`). Остальные `.mjs`-файлы — самостоятельные приборы,
которые запускаются руками против `runserver 8099 --noreload`: у каждого
понятное по имени назначение (`calc2_blocks.mjs` — скелет блоков,
`audit_matrix.mjs` — матрица «фича × сцена», `canon_checks.mjs` — часть 4
канона дизайна, `check_tex_escapes.mjs` — съеденные слэши LaTeX,
`*_probe.mjs`/`*_audit.mjs` — точечные проверки конкретных сессий). Список
файлов и назначение каждого — `calc2/tests/README.md` (частично устарел:
написан на раннем этапе, до `check_tex_escapes.mjs` и большинства проб).
Быстрый круг — CLAUDE.md, раздел «Как проверять» под calc2.

## Точки сборки: четыре двери, через которые проходит всё

Карта отвечает по файлам, но чаще нужен другой разрез: «где ОДНО место, через
которое собирается вот эта часть экрана». Их четыре, и знать их полезнее, чем
помнить двадцать два файла.

**Холст графика — `redrawAll()` в `60-overlays.js:10`.** Единственная дверь
перерисовки: `syncParams` (формулы могли завести или потерять буквы) →
`redrawScene()` (сцена рисует себя) → `drawOverlays()` (слой поверх сцены) →
проходы по подписям (размер, обрезка, разведение, чернила) →
`typesetChartLabels()` (шрифты обозначений — намеренно В САМОМ КОНЦЕ, когда
холст собран целиком) → `refreshRegulators()`. Любое изменение состояния зовёт
её и перерисовывает ВСЁ заново; частичной перерисовки в движке нет.
Смотреть сюда, если «изменил значение — на графике не отразилось» или
«отразилось, но с опозданием на один шаг».

**Сцена внутри холста — `redrawScene()` в `60-overlays.js:45`.** Развилка по
`STATE.mode` и `STATE.scenario`: она выбирает, какая из сорока с лишним
рисовалок сцены сработает. Смотреть, если рисуется чужая модель или не
рисуется ничего.

**Левая панель — `cardifySections()` + `collapseCards()` + `syncFirstCard()`
в `86-workspace.js:241-379`.** Разметка всех карточек лежит в шаблоне СРАЗУ
ВСЯ; сцена не строит панель, а показывает и скрывает готовые блоки
(`style.display`). Кто именно скрывает — `applyScenarioVisibility()` в
`52-modes.js`, `applyMonoVisibility()` в `42-scenes-mono.js` и `lock` у
маршрута сцены. ⚠️ Правило, купленное дефектом: **видимость блока ставится в
«приведи экран к состоянию», а не в обработчике щелчка** — иначе смена модели
её не застанет и блок протечёт в чужую сцену (так было с MSB/MSC, 24.08).

**Правая аналитика — `refreshAnalyticsPanel()` в `60-overlays.js:430`.**
`syncAnalyticsPanel()` (разбор уезжает в свой блок) → `typesetChartLabels()` →
`renderMathIn(#sb-body)` (формулы) → `typesetStats(#sb-body)` (числа тоже
формулой). Зовётся не только из общей перерисовки: перетаскивание линии цены
обновляет ТОЛЬКО панель, и без отдельного прохода числа в пути показывались
сырым текстом.

**Подсказки — `#hint-tip` и `wireTips()` в `86-workspace.js`.** Плашка ОДНА на
весь калькулятор, текст берётся из атрибута `data-tip`, математика внутри
размечается долларами (`tipName`, `tipExpr`, `tipPlain`). Нативного `title` в
калькуляторе нет ни одного и быть не должно — за этим следит правило канона
`title_on_interactive`.

## Как добавить новую сцену

Порядок шагов, а не список файлов. Всё, кроме шага 4, — по одной записи.

1. **Карточка в меню** — `calc2/templates/calc2/calc2.html`, окно выбора
   (`#scene-picker`): `<button class="scard" data-scene="ключ">` с названием и
   строкой `.scard-desc`. Ключ карточки — он же ключ маршрута.
2. **Имя сцены** — `SCENE_NAMES` в `84-picker.js` (пишется в заголовок над
   графиком).
3. **Маршрут** — `SCENE_ROUTE` в `84-picker.js`: `{ run: () => …, lock: […] }`.
   `run` — только КОМПОЗИЦИЯ уже имеющихся действий движка (`setMode`,
   `setMonoMode`, `loadScene` и т.п.); своей математики у карточки быть не
   должно. `lock` — id переключателей соседних моделей, которые эта сцена
   прячет. `base` — если сцена это подрежим другой.
4. **Своя рисовалка** (только если сцена рисует что-то новое) — в файле по
   теме: рынок → `40-scenes-market.js`, монополия → `42`, фирма → `44`,
   труд → `46`, потребитель → `48`, макро → `50`, КПВ → `54`,
   неравенство → `56`, математика → `70`. Плюс ветка в `redrawScene()`.
5. **Свои поля ввода** — блок в шаблоне со своим `id` и `style="display:none"`,
   показ через ту функцию видимости, что отвечает за её семейство (см. «Левая
   панель» выше). Проводка полей — в `88-params.js`.
6. **Пояснение модели** — `90-explain.js` (текст под гаечным ключом).
7. **Проверки.** Реестр `CARDS` в `calc2/tests/calc2_blocks.mjs` (карточка
   открывается, состояние то, что обещано, чужие переключатели спрятаны) и —
   если у сцены есть контрольные числа — `calc2/tests/calc2_math.mjs`.
   Число сцен зашито в двух проверках сразу: `calc2_blocks` требует ровно 44,
   аудит шрифтов печатает своё число — обе придётся поправить.

⚠️ **Подписи холста рисуются ТОЛЬКО через `renderLabelText`.** Голый
`.text(строка)` у нового `<text>` — это дефект: подпись не получит ни
математического начертания обозначений, ни `data-raw` для выгрузки в `.tex`.
Четыре таких места нашлись 24.08 и были переведены.

## Симптом → куда смотреть

Таблица построена на реально закрытых багах из Notion (направление
«Калькулятор») и ловушках, записанных в CLAUDE.md. Номера строк — на момент
написания карты (HEAD `f8e3506`); они смещаются при каждой правке, сверяйте
по имени функции, не только по числу.

| Симптом (как видит человек) | Куда смотреть |
|---|---|
| Формула с буквой-параметром не строится / считает NaN | `10-math-core.js` (`compileFormula:22`, `detectLinear`, `refreshLinearForParams`) для явных `y=f(x)`; `60-overlays.js` (`prepExpr:2367` — ⚠️ НЕ в `10-math-core.js`, вопреки первому впечатлению; `freeSymbols:2415`, `scopeFor:2506`, `paramScope:2496`) для подготовки строки и области видимости; для КПВ отдельно — `54-scenes-ppf.js` (`compilePpf:111`, `parsePpfEquation`, `ppfEvalWith:562` — сверить, что и разбор, и расчёт идут через один и тот же `scopeFor`, см. «третий отказ» сессии 22.08) |
| LaTeX из поля ввода рвётся на отдельные буквы (`100-a\cdot x` → мусор) | `60-overlays.js` (`expandImplicitMul:2341`, `prepExpr:2367` — порядок важен: сначала перевод LaTeX в обычную запись, потом раскрытие неявного умножения, не наоборот) |
| Отказ по формуле показан в свёрнутой правой панели («Ключевые значения»), а не под самим полем | `54-scenes-ppf.js` (`showPaneError:867`, места вызова у `#ppf-error`/`#ppfsum-error`/`#ppft-error`/`#tb-error` — проверить, что все четыре реально заполняются, а не только одно) |
| Подпись деления или координаты оторвалась от оси / пунктир к оси идёт без числа | `20-plane.js` (`axisValueX:477`, `axisValueY:504`, `coordAlreadyAt:466`, класс `axis-num` против `coord-num`); у сцен со своими мини-панелями (дискриминация в `42-scenes-mono.js`, панели производства в `44-scenes-firm.js`) проверить, что они тоже проставляют класс `coord-num` — своя копия отрисовки легко его теряет |
| Ползунок буквы появляется позже, чем принята формула, или сбрасывает набранное число | `60-overlays.js` (`syncParams:2524` читает `input`, а не сырой LaTeX — см. находку Н7); `82-input.js` (`grabKeys`, очередь `_mfWaiting` — поле MathLive не собирается, пока сцена под `inert`) |
| Подпись кривой дёргается, пропадает у края графика или показывает не то имя | `30-curves.js` (`requestLabelFrame:725`, `curveShortName:2985` в `60-overlays.js` — переехало отдельной функцией; правило «подпись переносится, а не скрывается») |
| Кривую нельзя щёлкнуть, потянуть мышью или взвести её ключевые точки | `30-curves.js` (`sceneDrawsCurveList:890`, `NO_CURVE_DRAG`) — ⚠️ перетаскивание кривой мышью УДАЛЕНО целиком решением владельца от 20.08 (`CURVE_MOUSE_DRAG`, `attachDrag` и т.п. больше не существуют) — если жалоба именно «кривая не тянется», сначала проверить, не про это ли речь, а не искать несуществующий код |
| Ключевые точки / пересечения кривых не находятся, залипают или дублируют друг друга | `60-overlays.js` (`keyTargets:1114`, `kinksOf:1066`, `drawCrossPoints:1246`, `rollerTargetAt:1497`, `coordAlreadyAt` в `20-plane.js` — «одно место — одно число» для совпавших координат) |
| Ползунок/протяжка ручки двигает окно графика целиком, а не саму кривую | `52-modes.js` (`redrawKeepingWindow:251`, `padMax:167`, `boundsOfDrawn:211`, `STATE.zoomLock`) |
| Легенда или заливка площади не того цвета, дублирует подпись или путается с исходной формулой | `60-overlays.js` (`applyAreaColors:694`, `drawLegend:791`, `typesetStats:445` — при чтении текста легенды в тестах обязателен клон без `.katex-mathml`/`annotation`, иначе число из KaTeX читается трижды) |
| Открылась не та сцена / на карточке виден переключатель чужой модели | `84-picker.js` (`SCENE_ROUTE:185`, `pickScene:461`, `baseScene:265`, `applyCardScope`) |
| KaTeX рисует мусор, красным текстом, или кириллица в формуле выглядит курсивным произведением букв | `82-input.js` (`katexSafe:648`, `katexInto:684` — единственная дверь к KaTeX; узкий неразрывный пробел U+202F, обёртка `\text{...}` для кириллицы) |
| Правка имени точки или границы ползунка не применяется / стирает уже введённое значение | `82-input.js` (`makeEditableValue:1384` — пустое «прежнее» значение обязано означать «прежнего не было», а не `set('')`) |
| Экспорт `.tex`/PDF: кривая или площадь на бумаге не совпадает с экраном, PDF не собирается | `calc2/views.py` (`compile_pdf_pdflatex`, `_TEX_FORBIDDEN`, `pdflatex_available`); `70-scenes-math.js` (`buildTex` — единственная дверь); `72-export-tex.js` (бумажный прогон, опись со сверкой записей, сборка; ADR 0139); записи сцен — словарь `30-curves.js` (`markExpr`, `markArea`, `markNumeric`, `markPoly`, `markCurve`); приборы — `calc2/tests/tex/` |
| Элемент вообще не виден на экране, хотя код его явно создаёт / кнопка не реагирует ни на что | Сначала `calc2/templates/calc2/calc2.html` — проверить, что `id` есть в разметке (класс дефектов «оборванный обработчик»: контрол переделали, обработчик остался висеть на несуществующем элементе — 6 таких случаев нашла проверка связей сессии 10.08); потом сам JS-файл по имени обработчика |
| Блок или поле чужой модели видно после захода в другую сцену | Видимость поставлена в обработчике щелчка вместо «приведи экран к состоянию»: `52-modes.js` (`applyScenarioVisibility`, `setScenario`), `42-scenes-mono.js` (`applyMonoVisibility`), `lock` у маршрута в `84-picker.js`. Класс дефекта закрывался дважды — параметры между сценами и блок MSB/MSC (24.08) |
| Обозначение на графике или в подсказке набрано обычным шрифтом, а не формулой | Холст: `60-overlays.js` (`typesetChartLabels`, `chartLabelSource`, `chartLabelBase`, `chartLabelKind` — решение принимается по `data-raw`, а НЕ по склейке tspan'ов) и `40-scenes-market.js` (`renderLabelText`, `mixedMathTspans`, `markNotationTspan`). Подсказки: `86-workspace.js` (`tipName`, `tipExpr`). Прибор — `calc2/tests/night2_font_audit.mjs`, должен давать 0 |
| Проверка канона зелёная, а нарушение на экране видно | Прибор считает только ВИДИМОЕ: `calc2/tests/canon_checks.mjs` (`expandAll` — раскрывает все складные блоки и обе панели перед подсчётом). Если проверка что-то «не видит», сначала спросите, не свёрнуто ли оно. Тот же класс — `clip-path` и `opacity` в измерителе |
| После сброса/входа в сцену границы окна или сетка не такие, как ожидалось | `20-plane.js` (`fitMargins:77`, `mainScales`); `86-workspace.js` (`openSection:310`) для авто-раскрытия связанной панели |

## Чего в карте нет

Честно, а не правдоподобно: чего карта не покрывает или не гарантирует.

- **22 `.mjs`-файла в `calc2/tests/`** не расписаны построчно и не входят в
  индекс функций — их назначение видно по имени и коротко описано выше, но
  карта не проверяет, что каждый из них ещё актуален. Часть могла устареть
  вместе с кодом, который проверяла (см. пометку про `README.md`).
- **Индекс функций ловит только объявления верхнего уровня** через регулярки
  (`function foo(`, `const foo = (...) => `, `class Foo`, `foo: function(`
  на неглубоком отступе) — это НЕ полный разбор AST. Функции, объявленные
  внутри замыканий (например, обработчики внутри `d3 .on(...)`, вложенные
  вспомогательные функции), в индекс не попадают. Если в файле «должна быть»
  функция, а в индексе её нет, — скорее всего она локальная, ищите текстовым
  поиском внутри файла.
- **`calc2.css` не имеет функционального индекса вообще** — только строки и
  КБ в таблице автосекции. Структура селекторов (какие классы за что
  отвечают) в карте не описана.
- **Номера строк в индексе функций смещаются с каждой правкой файла.**
  Тест-страж их НЕ проверяет намеренно (иначе он был бы шумным и его начали
  бы игнорировать, см. CLAUDE.md про номера строк в отчётах calc2). При
  разборе бага по карте сверяйтесь с именем функции, а не только с числом.
- **`calc2/views.py` и `calc2/urls.py` не получают индекс функций** —
  собирается только по `.js`-файлам, чтобы не раздувать карту питоном,
  которого в этих двух файлах всего около 200 строк на двоих.
- **Карта показывает, что функция ОБЪЯВЛЕНА, а не то, что она вызывается.**
  Мёртвый код (объявлена, но нигде не используется) картой не отличается от
  живого — для этого нужен отдельный анализ вызовов, которого здесь нет.
- **Таблица «Симптом → куда смотреть» не исчерпывающая.** Она построена на
  уже закрытых багах и известных ловушках CLAUDE.md на момент написания
  (2026-08-21, HEAD `f8e3506`); новый класс дефекта в неё сам не попадёт —
  дописывайте строку, когда разберёте баг, которого здесь нет.
- **Удалённого в карте нет, и это правильно.** Сюжет «Сдвиги»
  (`scenario 'shift'`) и переключатель структуры рынка
  (`#market-struct-row` / `#seg-comp` / `#seg-mono`) удалены 24.08 после
  замера: значение `'shift'` было недостижимо, переключатель не был виден ни
  в одной из 44 сцен. Если в старом отчёте или чужой ветке встретите
  `drawShiftScenario`, `updateShiftPanel`, `setShift`, `L_MARKET` — этого
  кода больше нет. Список удалённых `id` держится проверкой
  `calc2_blocks.mjs` («в разметке отсутствует»).
- **`models.py`, `admin.py`, `apps.py`** в приложении calc2 — стандартные
  пустые заготовки Django (моделей у calc2 нет, см. CLAUDE.md), они не
  участвуют в маршруте `/calc2/` и в карту не включены вовсе.

## Автосекция (генерируется командой)

<!-- AUTO:START -->

*Автоматически собрано командой `manage.py calc2_map`. Дата: 2026-11-02. HEAD: `060d4321`. Не редактировать руками — вся эта часть файла, от отметки начала автосекции и до отметки её конца, перезаписывается заново при каждом запуске команды.*

### Файлы (маршрут → представление → шаблон → статика)

| Путь | Строк | КБ | Тип |
|---|---:|---:|---|
| `calc2/urls.py` | 19 | 0.6 | python |
| `calc2/views.py` | 224 | 13.4 | python |
| `calc2/templates/calc2/calc2.html` | 2287 | 184.1 | шаблон |
| `calc2/static/calc2/calc2.css` | 4326 | 327.5 | CSS |
| `calc2/static/calc2/previews.json` | 44 | 30.9 | json |
| `calc2/static/calc2/00-config.js` | 578 | 50.2 | JS |
| `calc2/static/calc2/10-math-core.js` | 1166 | 76.6 | JS |
| `calc2/static/calc2/12-numbers.js` | 239 | 12.1 | JS |
| `calc2/static/calc2/20-plane.js` | 997 | 68.0 | JS |
| `calc2/static/calc2/30-curves.js` | 1517 | 110.4 | JS |
| `calc2/static/calc2/40-scenes-market.js` | 3886 | 280.9 | JS |
| `calc2/static/calc2/41-market-policies.js` | 260 | 17.4 | JS |
| `calc2/static/calc2/42-scenes-mono.js` | 2036 | 150.1 | JS |
| `calc2/static/calc2/44-scenes-firm.js` | 1233 | 81.3 | JS |
| `calc2/static/calc2/46-scenes-labor.js` | 900 | 68.8 | JS |
| `calc2/static/calc2/48-scenes-consumer.js` | 279 | 18.2 | JS |
| `calc2/static/calc2/50-scenes-macro.js` | 445 | 30.3 | JS |
| `calc2/static/calc2/52-modes.js` | 1007 | 68.8 | JS |
| `calc2/static/calc2/54-scenes-ppf.js` | 3282 | 212.3 | JS |
| `calc2/static/calc2/56-scenes-inequality.js` | 555 | 36.3 | JS |
| `calc2/static/calc2/60-overlays.js` | 4974 | 317.7 | JS |
| `calc2/static/calc2/70-scenes-math.js` | 2091 | 136.0 | JS |
| `calc2/static/calc2/72-export-tex.js` | 1665 | 128.2 | JS |
| `calc2/static/calc2/80-ui.js` | 855 | 54.2 | JS |
| `calc2/static/calc2/82-input.js` | 2357 | 140.4 | JS |
| `calc2/static/calc2/84-picker.js` | 582 | 44.4 | JS |
| `calc2/static/calc2/86-workspace.js` | 2157 | 141.0 | JS |
| `calc2/static/calc2/88-params.js` | 2023 | 139.3 | JS |
| `calc2/static/calc2/89-model-state.js` | 362 | 23.8 | JS |
| `calc2/static/calc2/90-explain.js` | 394 | 64.8 | JS |
| `calc2/static/calc2/91-session.js` | 502 | 26.6 | JS |
| `calc2/static/calc2/92-ui-kit.js` | 1330 | 91.7 | JS |
| `calc2/static/calc2/93-shell.js` | 284 | 17.4 | JS |
| `calc2/static/calc2/94-answer.js` | 1088 | 71.7 | JS |
| `calc2/static/calc2/95-picker-screen.js` | 470 | 26.7 | JS |
| `calc2/static/calc2/96-self.js` | 346 | 22.8 | JS |
| `calc2/static/calc2/99-boot.js` | 112 | 9.5 | JS |

**Итого: 37 файлов, 46872 строк, 3294.4 КБ.**

### Индекс функций (объявления верхнего уровня, по возрастанию строки)

#### `calc2/static/calc2/00-config.js`

- строка 71 — `fsStep`
- строка 471 — `cssVar`
- строка 475 — `refreshColors`
- строка 557 — `canvasMode`
- строка 563 — `canvasArmed`
- строка 569 — `roleColor`

#### `calc2/static/calc2/10-math-core.js`

- строка 17 — `topLevelEqIndex`
- строка 36 — `axisScope`
- строка 47 — `mathErrorRu`
- строка 58 — `compileFormula`
- строка 104 — `simplifyRecord`
- строка 128 — `qpRecordAfter`
- строка 142 — `isNaNNode`
- строка 157 — `liftConditional`
- строка 184 — `simplifyChainStr`
- строка 215 — `simplifyBody`
- строка 252 — `sameNumerically`
- строка 276 — `evalCurve`
- строка 294 — `detectLinear`
- строка 346 — `curveParamNames`
- строка 361 — `paramSignature`
- строка 366 — `refreshLinearForParams`
- строка 395 — `fmtLinear`
- строка 419 — `compileFormulaP`
- строка 430 — `evalQofP`
- строка 445 — `detectLinearP`
- строка 479 — `invertQofP`
- строка 502 — `buildCurveFromQP`
- строка 527 — `makeVerticalCurve`
- строка 531 — `isVertical`
- строка 537 — `curveZeroQ`
- строка 589 — `frameFloorQ`
- строка 590 — `frameFloorP`
- строка 593 — `naturalSpanQ`
- строка 599 — `eqSearchSpan`
- строка 612 — `bumpModelSpan`
- строка 613 — `modelSpanQ`
- строка 628 — `findEquilibrium`
- строка 688 — `findOffQuadIntersection`
- строка 713 — `bisect`
- строка 725 — `integrate`
- строка 747 — `signChanges`
- строка 763 — `areaBetween`
- строка 774 — `crossingCount`
- строка 795 — `findRoot`
- строка 813 — `invCurve`
- строка 827 — `curveDeriv`
- строка 834 — `compileExt`
- строка 842 — `evalSocial`
- строка 870 — `compileTwoVar`
- строка 880 — `compileTwoVarUncached`
- строка 890 — `evalTwoVar`
- строка 902 — `solveLevelB`
- строка 940 — `traceLevelCurve`
- строка 971 — `partialA`
- строка 976 — `partialB`
- строка 983 — `mrsAt`
- строка 998 — `optimizeAlongConstraint`
- строка 1062 — `qtyHasCyrillic`
- строка 1067 — `qtyIsQuantity`
- строка 1081 — `qtyParts`
- строка 1139 — `qtyLatex`

#### `calc2/static/calc2/12-numbers.js`

- строка 1 — `CalcNumber`
- строка 5 — `gcd`
- строка 6 — `frac`
- строка 11 — `fixed`
- строка 17 — `fixedRoot`
- строка 24 — `radicalClose`
- строка 28 — `quadratic`
- строка 52 — `relation`
- строка 80 — `recognize`
- строка 105 — `close`
- строка 106 — `decimal`
- строка 112 — `rational`
- строка 122 — `fraction`
- строка 126 — `radical`
- строка 133 — `classify`
- строка 156 — `format`
- строка 167 — `factor`
- строка 172 — `expression`
- строка 179 — `texText`
- строка 189 — `parse`
- строка 211 — `readText`

#### `calc2/static/calc2/20-plane.js`

- строка 13 — `computeSize`
- строка 53 — `measureText`
- строка 87 — `fitMargins`
- строка 138 — `fitLeftForLabels`
- строка 151 — `fitCoordinateMargin`
- строка 165 — `makeScales`
- строка 200 — `clearPanels`
- строка 202 — `registerPanel`
- строка 219 — `panelDist`
- строка 228 — `panelAt`
- строка 240 — `activePanel`
- строка 248 — `panelById`
- строка 263 — `panelWin`
- строка 267 — `resetPanelWins`
- строка 275 — `panelZoomBy`
- строка 292 — `panelPanBy`
- строка 306 — `gesturePanelId`
- строка 334 — `isEconScene`
- строка 340 — `econLo`
- строка 344 — `quadLo`
- строка 367 — `quadPrice`
- строка 377 — `toPx`
- строка 378 — `toData`
- строка 391 — `fmtSum`
- строка 396 — `shownDiff`
- строка 397 — `fmtDiff`
- строка 404 — `fmt`
- строка 412 — `fmtInput`
- строка 421 — `niceTickStep`
- строка 433 — `axisTicks`
- строка 446 — `xTicks`
- строка 447 — `yTicks`
- строка 450 — `addDefs`
- строка 517 — `drawGrid`
- строка 568 — `extraTickX`
- строка 579 — `extraTickY`
- строка 619 — `dropTickAt`
- строка 646 — `coordValue`
- строка 670 — `coordSplit`
- строка 674 — `coordAlreadyAt`
- строка 720 — `resetDrawnKeyPoints`
- строка 723 — `panelOfGlobalScales`
- строка 727 — `kpNode`
- строка 743 — `collectDashes`
- строка 760 — `dashEndsNear`
- строка 772 — `flushDrawnKeyPoints`
- строка 820 — `noteAxisX`
- строка 825 — `noteAxisY`
- строка 832 — `kpName`
- строка 837 — `axisValueX`
- строка 864 — `axisValueY`
- строка 889 — `axisValueText`
- строка 906 — `drawAxes`

#### `calc2/static/calc2/30-curves.js`

- строка 8 — `nextColor`
- строка 73 — `piecewiseNodesQ`
- строка 107 — `pointsFromNodes`
- строка 124 — `curvePoints`
- строка 180 — `drawMarginalCurve`
- строка 260 — `markExpr`
- строка 286 — `markNumeric`
- строка 291 — `markPoly`
- строка 301 — `texTag`
- строка 309 — `curveFormula`
- строка 320 — `markCurve`
- строка 334 — `markArea`
- строка 353 — `derivativeExpr`
- строка 400 — `curveAnchor`
- строка 506 — `curveLabelSize`
- строка 507 — `labelScale`
- строка 543 — `unclipLabels`
- строка 612 — `keepAxisNamesInside`
- строка 640 — `yieldTicksToCoords`
- строка 668 — `spreadLabels`
- строка 828 — `redrawAfterFonts`
- строка 867 — `parseColor`
- строка 882 — `relLum`
- строка 890 — `contrastOf`
- строка 895 — `rgbToHsl`
- строка 908 — `hslToRgb`
- строка 935 — `labelInk`
- строка 967 — `applyLabelInk`
- строка 994 — `mixToBg`
- строка 1002 — `applyLabelSize`
- строка 1036 — `smoothLabel`
- строка 1066 — `requestLabelFrame`
- строка 1071 — `resetLabelPositions`
- строка 1081 — `curveLabelAnchor`
- строка 1090 — `labelCurve`
- строка 1176 — `curveWidth`
- строка 1218 — `curveDash`
- строка 1226 — `curveOpacity`
- строка 1234 — `drawCurves`
- строка 1395 — `sceneDrawsCurveList`
- строка 1404 — `syncCurveListVisibility`
- строка 1419 — `curveDragAllowed`
- строка 1429 — `roundDrag`
- строка 1471 — `setCurveFreeTerm`

#### `calc2/static/calc2/40-scenes-market.js`

- строка 17 — `curveByRole`
- строка 20 — `curveByRoleAny`
- строка 24 — `recompute`
- строка 545 — `qtyAtPrice`
- строка 555 — `openQuotaName`
- строка 559 — `recomputeOpenEconomy`
- строка 651 — `drawOpenAreas`
- строка 699 — `drawOpenLines`
- строка 746 — `attachOpenPwDrag`
- строка 754 — `setOpenPw`
- строка 767 — `setOpenTool`
- строка 782 — `syncOpenQuotaLabel`
- строка 788 — `updateOpenPanel`
- строка 847 — `drawEquilibrium`
- строка 884 — `drawOffQuadIntersection`
- строка 923 — `offQuadExplainHtml`
- строка 949 — `pctFormExplainHtml`
- строка 987 — `mathTspans`
- строка 1027 — `hasMathMarkup`
- строка 1051 — `markNotationTspan`
- строка 1068 — `mixedNotationRe`
- строка 1076 — `mixedMathTspans`
- строка 1120 — `qtyTspans`
- строка 1157 — `qtyGreekChar`
- строка 1195 — `texToCanvasText`
- строка 1204 — `renderLabelText`
- строка 1225 — `haloText`
- строка 1258 — `pointName`
- строка 1284 — `yWageLabel`
- строка 1289 — `yWageValue`
- строка 1312 — `isMonopolyScene`
- строка 1320 — `eqSectionTitle`
- строка 1337 — `updateEqSectionTitle`
- строка 1354 — `interventionKeyValues`
- строка 1420 — `countCrossings`
- строка 1429 — `updateInfoPanel`
- строка 1538 — `sumSceneOn`
- строка 1541 — `sumGroupsOf`
- строка 1548 — `sumGroupQty`
- строка 1561 — `sumChokePrice`
- строка 1587 — `sumPriceTop`
- строка 1608 — `sumLinearRecord`
- строка 1710 — `integrateBroken`
- строка 1721 — `curveBreaks`
- строка 1732 — `quadBreaks`
- строка 1748 — `sumSegExpr`
- строка 1765 — `sumPolyline`
- строка 1793 — `sumRebuildSide`
- строка 1844 — `sumSignature`
- строка 1864 — `sumRebuild`
- строка 1884 — `sumAnalyticsKey`
- строка 1902 — `sumGroupName`
- строка 1925 — `sumTagOf`
- строка 1932 — `sumShortTag`
- строка 1961 — `sumGroupColor`
- строка 1966 — `sumStartExpr`
- строка 1974 — `sumReorder`
- строка 1979 — `sumAddGroup`
- строка 1992 — `sumBuildScene`
- строка 2020 — `sumSetCount`
- строка 2039 — `syncSumUi`
- строка 2053 — `sumGroupStats`
- строка 2099 — `sumFinalRecords`
- строка 2117 — `updateSumPanel`
- строка 2178 — `drawAreas`
- строка 2208 — `beforeInterventionNote`
- строка 2217 — `updateAreasPanel`
- строка 2258 — `intervOnBuyer`
- строка 2267 — `drawShiftedSupply`
- строка 2323 — `taxPivotQ`
- строка 2354 — `taxPivotPoint`
- строка 2364 — `drawTaxPivot`
- строка 2399 — `drawTaxAreas`
- строка 2439 — `drawTaxPoints`
- строка 2493 — `attachTaxDrag`
- строка 2514 — `setTax`
- строка 2632 — `taxFormKey`
- строка 2640 — `pctForm`
- строка 2648 — `syncTaxKind`
- строка 2653 — `applyIntervCascade`
- строка 2727 — `setTaxForm`
- строка 2745 — `setType`
- строка 2796 — `rateLetter`
- строка 2800 — `rateUnit`
- строка 2822 — `modelPriceTop`
- строка 2833 — `unitRateMax`
- строка 2843 — `applyPriceRegBounds`
- строка 2852 — `applyTaxRateBounds`
- строка 2887 — `syncQuotaHint`
- строка 2903 — `syncPcHint`
- строка 2911 — `markCurrentIntervHint`
- строка 2920 — `intervHintKey`
- строка 2930 — `intervHintHtml`
- строка 2952 — `syncTaxHint`
- строка 2990 — `setTaxKind`
- строка 3000 — `qpAfter`
- строка 3011 — `updateTaxPanel`
- строка 3147 — `setTaxSide`
- строка 3158 — `setTaxSideButtons`
- строка 3171 — `drawElasticityZones`
- строка 3189 — `drawElasticityPoint`
- строка 3219 — `attachElastDrag`
- строка 3227 — `drawElasticityPointS`
- строка 3247 — `attachElastDragS`
- строка 3255 — `updateElasticityPanel`
- строка 3319 — `drawExtAreas`
- строка 3333 — `drawExtCurves`
- строка 3360 — `drawExtPoints`
- строка 3394 — `drawExtScenario`
- строка 3403 — `updateExtPanel`
- строка 3457 — `setExtSign`
- строка 3466 — `syncSocialFields`
- строка 3494 — `syncExtHint`
- строка 3505 — `socialDefaultExpr`
- строка 3511 — `recompileSocial`
- строка 3533 — `setPRegFields`
- строка 3542 — `setPReg`
- строка 3551 — `drawPcAreas`
- строка 3578 — `drawPriceControl`
- строка 3627 — `attachPcDrag`
- строка 3636 — `updatePcPanel`
- строка 3680 — `setQuotaFields`
- строка 3692 — `setQuota`
- строка 3699 — `setQuotaPos`
- строка 3707 — `setQuotaPrice`
- строка 3714 — `updateQuotaPriceLabel`
- строка 3735 — `drawQuotaAreas`
- строка 3762 — `drawQuotaLines`
- строка 3807 — `attachQuotaDrag`
- строка 3820 — `updateQuotaPanel`
- строка 3867 — `drawGhost`

#### `calc2/static/calc2/41-market-policies.js`

- строка 3 — `taxPairOn`
- строка 7 — `taxPolicy`
- строка 12 — `taxPairPolicies`
- строка 17 — `taxPairRateMax`
- строка 23 — `addSecondTax`
- строка 28 — `removeSecondTax`
- строка 32 — `setSecondTax`
- строка 47 — `taxPairCurve`
- строка 54 — `recomputeTaxPair`
- строка 112 — `syncTaxPairUI`
- строка 172 — `drawTaxPairCurves`
- строка 191 — `drawTaxPairPoints`
- строка 228 — `taxPairExplainHtml`
- строка 237 — `updateTaxPairPanel`

#### `calc2/static/calc2/42-scenes-mono.js`

- строка 11 — `mcSourceCurve`
- строка 15 — `mcSourceCurveAny`
- строка 20 — `mcAt`
- строка 51 — `mcFloor`
- строка 56 — `mcFormula`
- строка 62 — `mrFormula`
- строка 69 — `marginalRevenue`
- строка 80 — `monoRootsIn`
- строка 103 — `monoOutputCap`
- строка 137 — `monoBestOutput`
- строка 177 — `competitiveOutput`
- строка 188 — `monoDwlAt`
- строка 196 — `drawMonopolyAreas`
- строка 235 — `drawMonopoly`
- строка 270 — `mcDragCurve`
- строка 275 — `mcDragStep`
- строка 279 — `drawMcDragHandle`
- строка 320 — `drawMonopolyPoints`
- строка 357 — `updateMonoPanel`
- строка 407 — `setMarket`
- строка 442 — `monopolyCeiling`
- строка 493 — `drawMonoCeilingAreas`
- строка 512 — `drawMonoKinkedMR`
- строка 529 — `drawMonoCeilingPoints`
- строка 561 — `drawMonoCeilingLine`
- строка 585 — `monopolyTax`
- строка 608 — `monoBudgetFloor`
- строка 617 — `monopolyFloor`
- строка 659 — `monopolyQuota`
- строка 687 — `drawMonoQuotaAreas`
- строка 709 — `drawMonoQuotaPoints`
- строка 731 — `drawMonoQuotaLine`
- строка 757 — `naturalATC`
- строка 769 — `naturalATCFormula`
- строка 788 — `findRootLast`
- строка 803 — `recomputeNatural`
- строка 832 — `drawNaturalAreas`
- строка 847 — `drawNaturalCurves`
- строка 870 — `drawNaturalPoints`
- строка 899 — `drawNaturalFull`
- строка 907 — `updateNaturalPanel`
- строка 945 — `drawMonoTaxAreas`
- строка 981 — `drawMonoTaxShiftedMC`
- строка 999 — `drawMonoTaxPoints`
- строка 1020 — `drawMonoFloorAreas`
- строка 1035 — `drawMonoFloorPoints`
- строка 1055 — `drawMonoFloorLine`
- строка 1070 — `updateMonoInterventionPanel`
- строка 1207 — `makeCurve`
- строка 1223 — `segExpr`
- строка 1230 — `kinkedDemandExpr`
- строка 1241 — `drawDiscr1`
- строка 1273 — `updateDiscr1Panel`
- строка 1298 — `allocateMR`
- строка 1311 — `recomputeDiscr3`
- строка 1367 — `drawMiniMarket`
- строка 1474 — `redrawDiscr3`
- строка 1517 — `drawMonoExport`
- строка 1641 — `updateDiscr3Panel`
- строка 1715 — `applyD3WorldLabels`
- строка 1737 — `buildKinkedDemand`
- строка 1784 — `recomputeKinked`
- строка 1831 — `drawKinkedFull`
- строка 1920 — `updateKinkPanel`
- строка 1961 — `applyMonoVisibility`
- строка 1982 — `ensureMonopolyCurves`
- строка 1993 — `fillIfEmpty`
- строка 1996 — `ensureD3Fields`
- строка 2001 — `ensureKinkFields`
- строка 2007 — `ensureMonopolyPreset`
- строка 2014 — `setMonoMode`
- строка 2025 — `setKinkInput`

#### `calc2/static/calc2/44-scenes-firm.js`

- строка 16 — `costScanTop`
- строка 21 — `evalTC`
- строка 30 — `evalPart`
- строка 36 — `hasPart`
- строка 41 — `costsFC`
- строка 46 — `costTC`
- строка 55 — `costVC`
- строка 60 — `costATC`
- строка 64 — `costAVC`
- строка 68 — `costAFC`
- строка 76 — `costMC`
- строка 83 — `costHas`
- строка 107 — `minOf`
- строка 129 — `realMin`
- строка 137 — `shutdownPrice`
- строка 146 — `computeFCfromTC`
- строка 166 — `costsSignature`
- строка 171 — `paramsSignature`
- строка 177 — `recomputeCosts`
- строка 221 — `checkCostsConsistency`
- строка 248 — `costPoints`
- строка 266 — `costExprs`
- строка 296 — `drawCostCurves`
- строка 355 — `noMinNote`
- строка 365 — `updateCostsPanel`
- строка 404 — `redrawCosts`
- строка 439 — `recomputeLongRun`
- строка 508 — `drawLongRunArea`
- строка 516 — `fillLongRunArea`
- строка 540 — `drawLongRunMarks`
- строка 545 — `fillLongRunMarks`
- строка 577 — `drawLongRunHandle`
- строка 588 — `setLrPrice`
- строка 596 — `syncLrPriceFields`
- строка 614 — `beginLrDrag`
- строка 616 — `dragLrPrice`
- строка 631 — `endLrDrag`
- строка 638 — `updateLongRunPanel`
- строка 681 — `prodEval`
- строка 691 — `prodDerivative`
- строка 705 — `prodMP`
- строка 712 — `prodAP`
- строка 720 — `maxOf`
- строка 747 — `realMax`
- строка 749 — `recomputeProduction`
- строка 768 — `redrawProduction`
- строка 886 — `noMaxNote`
- строка 895 — `updateProdPanel`
- строка 919 — `recomputeIsoquant`
- строка 930 — `redrawIsoquant`
- строка 946 — `updateIsoPanel`
- строка 983 — `plantMC`
- строка 989 — `plantTC`
- строка 995 — `plantQatMC`
- строка 1011 — `recomputePlants`
- строка 1045 — `plantsAt`
- строка 1062 — `redrawPlants`
- строка 1143 — `updatePlantsPanel`
- строка 1173 — `setPlantsView`
- строка 1180 — `setPlantsQ`
- строка 1191 — `setCostsInputMode`
- строка 1199 — `syncCostsInputMode`
- строка 1213 — `setCostsSub`

#### `calc2/static/calc2/46-scenes-labor.js`

- строка 14 — `laborMCL`
- строка 26 — `laborMinMonopsony`
- строка 64 — `laborMinCompetition`
- строка 93 — `laborUnionMonopoly`
- строка 125 — `laborUnionWageFloor`
- строка 141 — `laborBilateralMin`
- строка 164 — `recomputeLabor`
- строка 250 — `laborPoint`
- строка 268 — `drawLaborGhost`
- строка 278 — `drawLaborSurpluses`
- строка 296 — `drawLaborMinWelfare`
- строка 328 — `drawLaborMCL`
- строка 364 — `drawLaborDWL`
- строка 378 — `drawLaborMonopsonyPoints`
- строка 434 — `drawLaborCompPoints`
- строка 460 — `drawLaborMinLine`
- строка 474 — `attachLaborMinDrag`
- строка 482 — `setLaborMinFields`
- строка 490 — `setLaborMinOn`
- строка 497 — `setLaborMin`
- строка 509 — `drawLaborUnionMRL`
- строка 521 — `drawLaborGapDWL`
- строка 532 — `drawLaborUnionPoints`
- строка 572 — `drawLaborUnionWageLine`
- строка 586 — `attachUnionWageDrag`
- строка 594 — `setUnionWageFields`
- строка 601 — `setUnionWage`
- строка 611 — `setUnionModel`
- строка 633 — `drawLaborBilateral`
- строка 700 — `updateLaborBilateralPanel`
- строка 741 — `setLaborStruct`
- строка 758 — `updateLaborPanel`
- строка 861 — `redrawLabor`

#### `calc2/static/calc2/48-scenes-consumer.js`

- строка 12 — `consumerUtility`
- строка 27 — `consumerOptimum`
- строка 35 — `setConsSlutsky`
- строка 46 — `recomputeConsumer`
- строка 81 — `drawBudgetLine`
- строка 96 — `drawLevelCurve`
- строка 117 — `drawChoicePoint`
- строка 129 — `attachBudgetHandles`
- строка 154 — `setConsumerNum`
- строка 163 — `redrawConsumer`
- строка 197 — `updateConsumerPanel`
- строка 253 — `applyConsumerTypeUI`
- строка 267 — `setConsumerType`

#### `calc2/static/calc2/50-scenes-macro.js`

- строка 20 — `compileVar`
- строка 31 — `evalVar`
- строка 40 — `macroCurveY`
- строка 49 — `macroCurveInv`
- строка 78 — `macroCurveAny`
- строка 107 — `macroP`
- строка 113 — `recomputeMacro`
- строка 235 — `drawMacroCurve`
- строка 267 — `redrawMacro`
- строка 346 — `drawEquilibriumAt`
- строка 357 — `updateMacroPanel`
- строка 433 — `setMacroModel`

#### `calc2/static/calc2/52-modes.js`

- строка 14 — `setRanges`
- строка 38 — `syncViewFields`
- строка 74 — `updateResetViewBtn`
- строка 91 — `markViewDirty`
- строка 112 — `prefersReducedMotion`
- строка 117 — `animateRanges`
- строка 148 — `applyTradeRanges`
- строка 174 — `scheduleRangeAnim`
- строка 193 — `padMax`
- строка 211 — `curveAxisBounds`
- строка 242 — `boundsOfDrawn`
- строка 282 — `redrawKeepingWindow`
- строка 288 — `applyAutoRanges`
- строка 315 — `zoomRound`
- строка 321 — `zoomBy`
- строка 406 — `panByPixels`
- строка 486 — `wantedRanges`
- строка 511 — `modelAnswerPoints`
- строка 530 — `requestFormulaFit`
- строка 559 — `growRanges`
- строка 575 — `growWindowToModel`
- строка 597 — `resetZoom`
- строка 641 — `flushWheel`
- строка 652 — `initZoom`
- строка 848 — `zoomStep`
- строка 857 — `cancelRangeAnim`
- строка 869 — `makeThrottle`
- строка 882 — `ineqRedraw`
- строка 885 — `setMode`
- строка 968 — `applyScenarioVisibility`
- строка 994 — `setScenario`

#### `calc2/static/calc2/54-scenes-ppf.js`

- строка 20 — `parsePpfEquation`
- строка 53 — `parseYofX`
- строка 69 — `makeInverseF`
- строка 89 — `makeImplicitF`
- строка 111 — `compilePpf`
- строка 132 — `evalPpf`
- строка 139 — `ppfSlope`
- строка 146 — `clampPpfX`
- строка 158 — `ppfTypeLabel`
- строка 170 — `recomputePpf`
- строка 199 — `evalPpf2`
- строка 209 — `bundleRay`
- строка 230 — `bundleSlopeAt`
- строка 237 — `bundleDragTo`
- строка 258 — `tradeBundleGain`
- строка 279 — `ppfMark`
- строка 290 — `ppfMarkArea`
- строка 300 — `ppfExplicitExpr`
- строка 306 — `drawPpfCurve`
- строка 368 — `drawBundleRay`
- строка 444 — `ppfOppAt`
- строка 450 — `updatePpfPanel`
- строка 540 — `redrawPpf`
- строка 593 — `ppfEvalWith`
- строка 613 — `ppfSlopeOf`
- строка 626 — `ppfXmaxOf`
- строка 640 — `fitLinear`
- строка 664 — `ppfTouchXmax`
- строка 709 — `ppfFitsOnGrid`
- строка 724 — `classifyPpf`
- строка 799 — `ppfFitR2`
- строка 821 — `niceMax`
- строка 829 — `singlePpfPoints`
- строка 836 — `findRootIn`
- строка 848 — `interpY`
- строка 862 — `maxAllocY`
- строка 887 — `combinedPpfPoints`
- строка 897 — `allocAt`
- строка 928 — `detectCombinedKinks`
- строка 1003 — `ppfCoefTex`
- строка 1010 — `ppfNum`
- строка 1020 — `ppfSnap`
- строка 1032 — `ppfPiecesToExpr`
- строка 1049 — `ppfLinearExpr`
- строка 1056 — `combinedPpfLinearRecord`
- строка 1233 — `ppfPoly2Xmax`
- строка 1252 — `ppfCostOf`
- строка 1261 — `ppfValid`
- строка 1269 — `ppfFam`
- строка 1270 — `ppfClamp`
- строка 1281 — `ppfReduceActive`
- строка 1300 — `ppfPieceTex`
- строка 1350 — `ppfPoly2Terms`
- строка 1360 — `ppfPolyJoin`
- строка 1376 — `ppfPieceBody`
- строка 1414 — `ppfPieceAt`
- строка 1427 — `ppfPiecesRecord`
- строка 1475 — `ppfSumByEqualCost`
- строка 1580 — `ppfSumByEnvelope`
- строка 1669 — `ppfEnvPiece`
- строка 1680 — `ppfMergeSameLine`
- строка 1700 — `ppfCostKinds`
- строка 1709 — `ppfCostValue`
- строка 1719 — `ppfWhyNumeric`
- строка 1772 — `ppfSumMixedPair`
- строка 1937 — `ppfSumAnalytic`
- строка 1955 — `combinedPpfFormula`
- строка 1991 — `verifyFormula`
- строка 2002 — `detectKinks`
- строка 2027 — `showPaneError`
- строка 2038 — `ppfSumCount`
- строка 2039 — `ppfSumGet`
- строка 2044 — `ppfSumSet`
- строка 2049 — `ppfSumName`
- строка 2053 — `ppfSumColor`
- строка 2067 — `ppfSumSignature`
- строка 2077 — `recomputePpfSum`
- строка 2083 — `ensurePpfSum`
- строка 2087 — `recomputePpfSumRaw`
- строка 2198 — `renderPpfSumRows`
- строка 2249 — `detectSumKinks`
- строка 2267 — `drawPpfSumCurves`
- строка 2299 — `drawPpfSumMarks`
- строка 2325 — `updatePpfSumPanel`
- строка 2442 — `fmtRu`
- строка 2446 — `ppfSumSchemaData`
- строка 2480 — `schemaNote`
- строка 2487 — `drawPpfSumSchema`
- строка 2539 — `redrawPpfSum`
- строка 2552 — `setPpfSumView`
- строка 2563 — `cornerByValue`
- строка 2587 — `bestByValue`
- строка 2610 — `ppfOcRange`
- строка 2624 — `recomputePpfTrade`
- строка 2689 — `drawPpfTrade`
- строка 2717 — `drawPpfTradeMarks`
- строка 2745 — `updatePpfTradePanel`
- строка 2897 — `syncPpftPriceUI`
- строка 2908 — `redrawPpfTrade`
- строка 2929 — `recomputeTradeB`
- строка 3018 — `tradeCpfPoints`
- строка 3036 — `tradeCpfMark`
- строка 3055 — `tradeBPanels`
- строка 3076 — `drawTradeB`
- строка 3149 — `drawTradeBMarks`
- строка 3152 — `tbName`
- строка 3158 — `updateTradeBPanel`
- строка 3228 — `syncTbPriceUI`
- строка 3241 — `redrawTradeB`
- строка 3256 — `setTradeScenario`
- строка 3268 — `setPpfSub`

#### `calc2/static/calc2/56-scenes-inequality.js`

- строка 11 — `parseNumberList`
- строка 18 — `inequalitySharesFromInput`
- строка 47 — `lorenzFromShares`
- строка 56 — `lorenzFromFormula`
- строка 78 — `lorenzAreaUnder`
- строка 89 — `lorenzAt`
- строка 103 — `inequalityStats`
- строка 124 — `inequalityP90P10`
- строка 139 — `ineqRedistShares`
- строка 152 — `applyRedistribution`
- строка 168 — `recomputeInequality`
- строка 209 — `drawInequalityDiagonal`
- строка 218 — `drawInequalityCaptions`
- строка 236 — `lorenzPlotExpr`
- строка 243 — `lorenzMark`
- строка 250 — `lorenzMarkArea`
- строка 260 — `drawInequalityAreas`
- строка 271 — `drawLorenzCurve`
- строка 280 — `drawRobinHood`
- строка 296 — `drawLorenzNodes`
- строка 314 — `ineqDragNode`
- строка 330 — `ineqDragIncome`
- строка 347 — `attachLorenzNodeDrag`
- строка 366 — `drawRedistArrow`
- строка 381 — `updateIneqSortNote`
- строка 389 — `updateInequalityPanel`
- строка 426 — `redrawInequality`
- строка 475 — `defaultGroupShares`
- строка 482 — `setIneqInput`
- строка 499 — `setIneqAlpha`
- строка 515 — `setIneqGroupN`
- строка 526 — `setIneqRedistTool`
- строка 537 — `renderIneqGroupsTable`

#### `calc2/static/calc2/60-overlays.js`

- строка 10 — `redrawAll`
- строка 86 — `redrawScene`
- строка 233 — `redrawGraphMode`
- строка 245 — `renderMmRows`
- строка 291 — `graphRowsBox`
- строка 294 — `renderGraphRows`
- строка 313 — `graphError`
- строка 320 — `buildGraphRow`
- строка 402 — `equipGraphRows`
- строка 410 — `graphRowInput`
- строка 455 — `mainScales`
- строка 466 — `drawOverlays`
- строка 574 — `guardedPanelIds`
- строка 578 — `guardPanelBoxes`
- строка 614 — `panelsChangedSinceLastPass`
- строка 619 — `markPanelsChanged`
- строка 622 — `flushPendingPanelClears`
- строка 631 — `refreshAnalyticsPanel`
- строка 659 — `typesetStats`
- строка 713 — `addStatSign`
- строка 727 — `statToTex`
- строка 765 — `katexVisibleText`
- строка 769 — `restatWide`
- строка 815 — `statInkWidth`
- строка 823 — `statTooWide`
- строка 832 — `statPieces`
- строка 867 — `texAbbrev`
- строка 873 — `renderMathIn`
- строка 916 — `areaKey`
- строка 921 — `subDigits`
- строка 926 — `applyAreaColors`
- строка 936 — `currentAreas`
- строка 954 — `areaOfPathEl`
- строка 1016 — `areaShort`
- строка 1025 — `drawLegend`
- строка 1088 — `floatRects`
- строка 1108 — `legendCorner`
- строка 1185 — `viewWindow`
- строка 1197 — `axisWords`
- строка 1203 — `crossPoints`
- строка 1305 — `invalidateKeyTargets`
- строка 1308 — `kinksOf`
- строка 1356 — `keyTargets`
- строка 1531 — `snapVertexAt`
- строка 1563 — `markPanelId`
- строка 1583 — `armedPanelId`
- строка 1589 — `drawCrossPoints`
- строка 1738 — `armCurve`
- строка 1744 — `disarmCurve`
- строка 1752 — `keyPointLit`
- строка 1765 — `drawCurveHits`
- строка 1803 — `pinKeyPoint`
- строка 1823 — `hoverLabel`
- строка 1834 — `drawRoller`
- строка 1855 — `rollerTargetAt`
- строка 1885 — `rollerClampX`
- строка 1904 — `rollerMove`
- строка 1920 — `showRollTip`
- строка 1943 — `hideRollTip`
- строка 1952 — `rollerOff`
- строка 1963 — `curveRightEdge`
- строка 1988 — `axisXLetter`
- строка 1998 — `axisLetter`
- строка 2011 — `armVerts`
- строка 2053 — `markServiceNodes`
- строка 2070 — `syncCanvasMode`
- строка 2092 — `leaveCanvasMode`
- строка 2098 — `finishCanvasMode`
- строка 2103 — `addAreaVert`
- строка 2116 — `vertPanels`
- строка 2119 — `vertsMixed`
- строка 2121 — `clearAreaVerts`
- строка 2126 — `renderVertList`
- строка 2135 — `syncAreaCalcButton`
- строка 2161 — `areaPickedCurve`
- строка 2170 — `areaCurveRange`
- строка 2188 — `syncAreaRangeLabel`
- строка 2227 — `freshenVertNames`
- строка 2245 — `drawAreaVerts`
- строка 2274 — `areaTargets`
- строка 2278 — `calcAreaUnderCurve`
- строка 2291 — `ringArea`
- строка 2301 — `segCross`
- строка 2308 — `ringSelfCrosses`
- строка 2330 — `angleRing`
- строка 2336 — `bestAreaRing`
- строка 2366 — `calcAreaPolygon`
- строка 2383 — `AREA_PALETTE`
- строка 2393 — `areaLive`
- строка 2414 — `areasLive`
- строка 2416 — `runAreaCalc`
- строка 2428 — `pushArea`
- строка 2449 — `addPolyArea`
- строка 2462 — `syncPtsSelBar`
- строка 2484 — `clearAreaCalc`
- строка 2491 — `drawAreaCalc`
- строка 2532 — `renameCommit`
- строка 2538 — `areaById`
- строка 2539 — `areaVertsLabel`
- строка 2546 — `updateAreaCalcPanel`
- строка 2614 — `openAreaMenu`
- строка 2659 — `syncAreaCalcUI`
- строка 2698 — `updateQuickArea`
- строка 2708 — `curveNameInto`
- строка 2712 — `buildAreaCurveButtons`
- строка 2746 — `pickAreaCurve`
- строка 2754 — `syncAreaCurveButtons`
- строка 2773 — `setAreaCalcMode`
- строка 2788 — `closeAreaBuild`
- строка 2794 — `cancelAreaBuild`
- строка 2806 — `finishPolyBuild`
- строка 2815 — `wireFolds`
- строка 2840 — `wireAreaCalc`
- строка 2875 — `paramsAllowed`
- строка 2900 — `isReservedName`
- строка 2940 — `expandImplicitMul`
- строка 2986 — `visibleSvgText`
- строка 3012 — `chartLabelSource`
- строка 3022 — `chartLabelBase`
- строка 3039 — `chartLabelKind`
- строка 3053 — `typesetChartLabels`
- строка 3081 — `prepExpr`
- строка 3099 — `texToPlain`
- строка 3125 — `sceneReservedKey`
- строка 3129 — `freeSymbols`
- строка 3147 — `freeSymbolsUncached`
- строка 3175 — `sceneReserved`
- строка 3198 — `sceneExtraParams`
- строка 3204 — `paramValue`
- строка 3210 — `paramScope`
- строка 3220 — `scopeFor`
- строка 3227 — `evalWithParams`
- строка 3238 — `syncParams`
- строка 3294 — `buildParamChip`
- строка 3419 — `initSceneColorPickers`
- строка 3431 — `syncSceneColorPickers`
- строка 3439 — `syncAxisPlaceholders`
- строка 3454 — `titleAnchorPx`
- строка 3464 — `drawGraphTitle`
- строка 3503 — `editGraphTitleOnCanvas`
- строка 3548 — `normHex`
- строка 3570 — `paletteSix`
- строка 3578 — `closeColorMenu`
- строка 3592 — `onDocClosePick`
- строка 3598 — `onEscClosePick`
- строка 3618 — `paletteTwelve`
- строка 3619 — `makeColorPicker`
- строка 3731 — `autoCurveName`
- строка 3740 — `curveShortName`
- строка 3750 — `markCaption`
- строка 3759 — `drawMarks`
- строка 3863 — `snapTargets`
- строка 3871 — `snapTargetsAll`
- строка 3999 — `macroSnapTargets`
- строка 4018 — `consumerSnapTargets`
- строка 4047 — `ineqSnapTargets`
- строка 4061 — `mathSnapTargets`
- строка 4126 — `tradeSnapTargets`
- строка 4147 — `axisSnapAt`
- строка 4167 — `snapDistPx`
- строка 4188 — `snapPointAt`
- строка 4231 — `showSnapHint`
- строка 4250 — `armMark`
- строка 4263 — `cancelMarkDraft`
- строка 4303 — `resetDecor`
- строка 4395 — `_undoCopyChild`
- строка 4409 — `_undoCopy`
- строка 4429 — `pushUndo`
- строка 4440 — `undoLast`
- строка 4457 — `clearUndo`
- строка 4464 — `forgetSceneSnapshot`
- строка 4466 — `resetSceneMemory`
- строка 4477 — `saveSceneSnapshot`
- строка 4490 — `restoreSceneSnapshot`
- строка 4518 — `keyOnText`
- строка 4525 — `markOnText`
- строка 4535 — `notationTex`
- строка 4542 — `markOnInto`
- строка 4551 — `markNameTex`
- строка 4558 — `addMarkAt`
- строка 4598 — `colorDist`
- строка 4607 — `drawnStrokeColors`
- строка 4623 — `nextMarkColor`
- строка 4646 — `canvasNameLetters`
- строка 4658 — `nextMarkName`
- строка 4670 — `newMark`
- строка 4686 — `pendingMark`
- строка 4689 — `startMarkDraft`
- строка 4698 — `markSnapFn`
- строка 4709 — `renderMarkList`
- строка 4721 — `ensureAddMarkButton`
- строка 4732 — `buildMarkRow`
- строка 4888 — `markById`
- строка 4889 — `openMarkMenu`
- строка 4902 — `fillMarkMenu`
- строка 4944 — `renameMark`
- строка 4959 — `editMarkCoords`
- строка 4968 — `removeMark`

#### `calc2/static/calc2/70-scenes-math.js`

- строка 24 — `compileMath`
- строка 25 — `evalMathAt`
- строка 31 — `mathH`
- строка 36 — `dNum`
- строка 41 — `d2Num`
- строка 48 — `mathF`
- строка 56 — `rootsOf`
- строка 82 — `mathAnalyse`
- строка 120 — `ansFmt`
- строка 123 — `ansPt`
- строка 125 — `ansList`
- строка 126 — `ansPts`
- строка 128 — `fnSig`
- строка 131 — `ansCached`
- строка 143 — `ansZeros`
- строка 160 — `ansExtrema`
- строка 184 — `ansAnalyse`
- строка 202 — `ansCrosses`
- строка 208 — `niceOut`
- строка 222 — `autoAnswerSeg`
- строка 243 — `answerSpec`
- строка 272 — `answerKeyPoints`
- строка 297 — `graphFitWindow`
- строка 323 — `setGraphWindow`
- строка 343 — `keyPointsSig`
- строка 347 — `axisShowing`
- строка 366 — `graphShowKeyPoints`
- строка 384 — `answerSeg`
- строка 393 — `autoSegOf`
- строка 403 — `ansExtremaRows`
- строка 410 — `ansAttr`
- строка 413 — `ansCtx`
- строка 415 — `ansNameMd`
- строка 418 — `graphHeadTex`
- строка 428 — `refreshAnswerSeg`
- строка 435 — `ansSegText`
- строка 436 — `ansSegParse`
- строка 445 — `syncAnsSegUI`
- строка 480 — `applyAnsSegInputs`
- строка 496 — `resetAnsSegToAuto`
- строка 512 — `mathTransformed`
- строка 529 — `mathScales`
- строка 543 — `drawPlaneAxes`
- строка 565 — `planeTicksX`
- строка 582 — `planeTicksY`
- строка 596 — `mathMark`
- строка 601 — `mathSubst`
- строка 607 — `mathTransformExpr`
- строка 624 — `mathLine`
- строка 657 — `resetLabelBoxes`
- строка 658 — `dodgeLabel`
- строка 670 — `mathDot`
- строка 714 — `makeRenamable`
- строка 757 — `editPointName`
- строка 781 — `editInlineLabel`
- строка 862 — `tangentLayout`
- строка 871 — `tangentPanelAt`
- строка 879 — `tanWin`
- строка 889 — `tanResetWindows`
- строка 894 — `tanScales`
- строка 902 — `drawMathTangent`
- строка 1033 — `drawMathOptimum`
- строка 1073 — `drawMathTransform`
- строка 1094 — `labelCurveMath`
- строка 1125 — `mmSlots`
- строка 1126 — `mmGet`
- строка 1129 — `mmSet`
- строка 1134 — `mmLabel`
- строка 1136 — `mmColor`
- строка 1145 — `mmParts`
- строка 1168 — `drawMathMinMax`
- строка 1215 — `compileAB`
- строка 1228 — `parseConstraint`
- строка 1246 — `constraintPointsIn`
- строка 1265 — `constraintPoints`
- строка 1270 — `optimizeAlongCurve`
- строка 1283 — `constraintFit`
- строка 1301 — `drawMathConstraint`
- строка 1363 — `drawLevelCurveOn`
- строка 1377 — `mathOptimumReasoning`
- строка 1414 — `updateMathPanel`
- строка 1566 — `redrawMath`
- строка 1606 — `setMathSub`
- строка 1629 — `setMathWindow`
- строка 1644 — `setMathX0`
- строка 1669 — `downloadBlob`
- строка 1678 — `exportBaseName`
- строка 1691 — `paperChartClone`
- строка 1718 — `exportNumbersLine`
- строка 1727 — `exportExtras`
- строка 1735 — `exportPNG`
- строка 1776 — `buildTex`
- строка 1785 — `afterFonts`
- строка 1790 — `exportTex`
- строка 1800 — `exportPDF`
- строка 1807 — `exportPDFSend`
- строка 1831 — `exportTitleDefault`
- строка 1833 — `buildExportFields`
- строка 1863 — `refreshExportPreview`
- строка 1901 — `expValue`
- строка 1912 — `syncExportFormat`
- строка 1924 — `refreshExportSheet`
- строка 1932 — `wireExport`
- строка 1961 — `openExport`
- строка 1982 — `closeExport`
- строка 2002 — `updateGraphPanel`
- строка 2063 — `graphExplainNote`

#### `calc2/static/calc2/72-export-tex.js`

- строка 30 — `texPaperActive`
- строка 35 — `texPaperComputeSize`
- строка 1662 — `texEnterPaper`
- строка 1663 — `texCapture`
- строка 1664 — `texEmit`
- строка 1665 — `texInventory`

#### `calc2/static/calc2/80-ui.js`

- строка 7 — `showError`
- строка 11 — `hideError`
- строка 30 — `curveSrcForm`
- строка 53 — `exprHasLetter`
- строка 60 — `priceLetters`
- строка 68 — `niceNumTex`
- строка 71 — `linearTexNice`
- строка 102 — `lhsKey`
- строка 105 — `splitCurveLhs`
- строка 129 — `buildAnyCurve`
- строка 152 — `addCurve`
- строка 196 — `addEmptyCurve`
- строка 217 — `curveRecord`
- строка 222 — `restoreCurveRecord`
- строка 227 — `updateCurveExpr`
- строка 260 — `setRole`
- строка 290 — `curveHumanName`
- строка 297 — `curvePrefix`
- строка 305 — `rememberStartCurves`
- строка 310 — `startExprOf`
- строка 315 — `curveIsPiecewise`
- строка 328 — `renderCurveList`
- строка 680 — `refreshCurveRow`
- строка 697 — `curveToSingleFormula`

#### `calc2/static/calc2/82-input.js`

- строка 11 — `texFallback`
- строка 23 — `texVarsItalic`
- строка 27 — `mathToTex`
- строка 45 — `renderTex`
- строка 54 — `renderTexRaw`
- строка 68 — `onKatexReady`
- строка 98 — `pwCond`
- строка 107 — `pwRows`
- строка 128 — `pwPrefixOf`
- строка 133 — `pwFormula`
- строка 152 — `pwLatex`
- строка 174 — `pwVar`
- строка 199 — `casesToNarrow`
- строка 212 — `isNarrowCases`
- строка 216 — `casesUnwrapNarrow`
- строка 231 — `casesToMath`
- строка 262 — `condToMath`
- строка 273 — `renderPw`
- строка 344 — `pwSyncHead`
- строка 359 — `pwSetCount`
- строка 370 — `pwAddRow`
- строка 387 — `pwRemoveRow`
- строка 398 — `pwCheck`
- строка 422 — `pwAttachKeyboard`
- строка 444 — `pwPreview`
- строка 484 — `pwVarForField`
- строка 512 — `pwDefaultRows`
- строка 518 — `pwBalanced`
- строка 531 — `pwSplitTernary`
- строка 555 — `pwCondBounds`
- строка 576 — `pwParse`
- строка 612 — `pwSplitRows`
- строка 636 — `openPiecewise`
- строка 654 — `closePiecewise`
- строка 663 — `insertIntoFormula`
- строка 693 — `mathfieldClass`
- строка 697 — `onMathliveReady`
- строка 733 — `fieldProblem`
- строка 783 — `unknownTexCommand`
- строка 792 — `texGroup`
- строка 802 — `latexToMath`
- строка 948 — `isUndefinedTailNode`
- строка 953 — `unwrapParens`
- строка 964 — `pwCondTex`
- строка 983 — `condChainToCases`
- строка 1005 — `mathToLatexField`
- строка 1027 — `upgradeFormulaField`
- строка 1077 — `fitFormulaField`
- строка 1151 — `fitFormulaFields`
- строка 1154 — `fitFormulaFieldsSoon`
- строка 1174 — `fieldOnScreen`
- строка 1186 — `flushMathfieldsSoon`
- строка 1192 — `flushMathfields`
- строка 1230 — `katexSafe`
- строка 1266 — `katexInto`
- строка 1281 — `placeholderTex`
- строка 1290 — `texSafeText`
- строка 1294 — `buildMathfield`
- строка 1479 — `setFormulaFieldQuiet`
- строка 1501 — `insertIntoField`
- строка 1520 — `keyboardAdapter`
- строка 1522 — `insert`
- строка 1523 — `deleteBack`
- строка 1528 — `clear`
- строка 1532 — `piecewise`
- строка 1541 — `buildKeyboard`
- строка 1551 — `addHowToTab`
- строка 1588 — `closeAllKeyboardsExcept`
- строка 1627 — `formulaInputError`
- строка 1661 — `markFormulaField`
- строка 1669 — `syncFormulaEditBases`
- строка 1685 — `onFormulaInput`
- строка 1749 — `scheduleParamsSync`
- строка 1755 — `registerFormulaField`
- строка 1772 — `fieldActive`
- строка 1781 — `liveFormulaTexts`
- строка 1809 — `equipFormulaField`
- строка 1846 — `equipAllFormulaFields`
- строка 1850 — `attachFormulaHelp`
- строка 2040 — `makeEditableValue`
- строка 2146 — `makeToggle`
- строка 2188 — `segToToggle`
- строка 2220 — `closeAllSelectMenus`
- строка 2224 — `upgradeSelect`
- строка 2325 — `upgradeTextField`
- строка 2348 — `upgradeTextFieldsIn`

#### `calc2/static/calc2/84-picker.js`

- строка 8 — `loadScene`
- строка 148 — `closePicker`
- строка 170 — `openPicker`
- строка 334 — `baseScene`
- строка 343 — `applyCardScope`
- строка 421 — `blockSpec`
- строка 433 — `foldPickerGroups`
- строка 520 — `plural`
- строка 528 — `pickScene`

#### `calc2/static/calc2/86-workspace.js`

- строка 55 — `setFieldValue`
- строка 61 — `relocateForScene`
- строка 76 — `clearResultPanels`
- строка 94 — `toast`
- строка 109 — `dockActive`
- строка 116 — `setSideOpen`
- строка 143 — `setToolsOpen`
- строка 144 — `setParamsOpen`
- строка 154 — `hasAnalytics`
- строка 161 — `moveExplanations`
- строка 259 — `conditionNotesSig`
- строка 271 — `conditionNotesToExplain`
- строка 321 — `answerNotesToExplain`
- строка 370 — `syncAnalyticsPanel`
- строка 454 — `sectionIcon`
- строка 465 — `cardifySections`
- строка 557 — `collapseCards`
- строка 575 — `syncLabelSizeSeg`
- строка 586 — `openSection`
- строка 623 — `cardWithFormula`
- строка 636 — `syncFirstCard`
- строка 655 — `wireScene`
- строка 824 — `resetCurrentScene`
- строка 834 — `setWrenchOpen`
- строка 844 — `applyViewBounds`
- строка 871 — `quadWindow`
- строка 876 — `quadSameWindow`
- строка 895 — `offQuadShownPoints`
- строка 925 — `fitWindowToOffQuad`
- строка 947 — `setFirstQuad`
- строка 997 — `setGridMode`
- строка 1015 — `hintTip`
- строка 1042 — `fitTipMath`
- строка 1065 — `showHintTip`
- строка 1123 — `hideHintTip`
- строка 1148 — `tipText`
- строка 1177 — `tipTex`
- строка 1187 — `tipName`
- строка 1204 — `tipExpr`
- строка 1214 — `tipPlain`
- строка 1243 — `ffEsc`
- строка 1253 — `ffLatexOf`
- строка 1275 — `finalFunctionHtml`
- строка 1300 — `ffParseCases`
- строка 1322 — `ffCondCompact`
- строка 1346 — `ffMathHtml`
- строка 1370 — `ffKatexW`
- строка 1386 — `ffFitCases`
- строка 1473 — `fitFinalMath`
- строка 1502 — `ffCopyText`
- строка 1510 — `ffCopyFallback`
- строка 1522 — `wireFinalCopy`
- строка 1555 — `ffOpenExpand`
- строка 1576 — `ffCloseExpand`
- строка 1588 — `setFinalFunctions`
- строка 1606 — `refitFinalMathSoon`
- строка 1634 — `markNotationsIn`
- строка 1666 — `paintNotation`
- строка 1676 — `showTipFor`
- строка 1682 — `wireTips`
- строка 1734 — `syncTipLabels`
- строка 1747 — `hintAnchor`
- строка 1828 — `fitPanelMath`
- строка 1858 — `syncHintDots`
- строка 1873 — `hintsToDots`
- строка 1912 — `wireHintButtons`
- строка 1954 — `wireWrench`
- строка 2080 — `fillPrintBlocks`
- строка 2110 — `setPrintViewBox`

#### `calc2/static/calc2/88-params.js`

- строка 69 — `pultRegulatorIds`
- строка 167 — `pultCurveList`
- строка 178 — `pultExtraSig`
- строка 184 — `pultExtraSigBase`
- строка 196 — `pultShouldShow`
- строка 206 — `shiftChipLabel`
- строка 220 — `curveChipLabel`
- строка 229 — `pultCurveSig`
- строка 239 — `paintEqLabel`
- строка 254 — `texifyName`
- строка 284 — `editEqValue`
- строка 351 — `centerBandOn`
- строка 355 — `pullIntoBand`
- строка 359 — `attachBoundsEditor`
- строка 441 — `refreshRegulators`
- строка 452 — `makePchip`
- строка 480 — `curveShiftBase`
- строка 490 — `pultShiftHalf`
- строка 494 — `resetPultShiftHalf`
- строка 497 — `buildPultCurveChips`
- строка 588 — `syncPultCurveValues`
- строка 611 — `capturePultHome`
- строка 618 — `capturePultHomes`
- строка 623 — `returnPultHome`
- строка 635 — `syncPultRegulators`
- строка 666 — `upgradeRegulator`
- строка 849 — `boundText`
- строка 850 — `shortRegulatorName`
- строка 876 — `ppfLinearFormula`
- строка 881 — `ppfInterceptsOf`
- строка 889 — `ppfSetSingle`
- строка 897 — `ppfSetSum`
- строка 917 — `addPultXChip`
- строка 944 — `buildPultExtra`
- строка 977 — `ineqParseIncomes`
- строка 980 — `ineqMasterRebase`
- строка 985 — `ineqMasterScale`
- строка 1003 — `ineqMasterApply`
- строка 1015 — `ineqMasterDetach`
- строка 1020 — `buildIneqMasterChip`
- строка 1033 — `showPult`
- строка 1060 — `updatePult`
- строка 1095 — `liveFormula`
- строка 1115 — `wireControls`

#### `calc2/static/calc2/89-model-state.js`

- строка 42 — `plainCopy`
- строка 81 — `togglesInOrder`
- строка 90 — `isDisclosureBtn`
- строка 93 — `formNodes`
- строка 98 — `captureForm`
- строка 123 — `applyForm`
- строка 172 — `captureStatePlain`
- строка 181 — `applyStatePlain`
- строка 188 — `rerenderModelLists`
- строка 206 — `forceRebuildAfterApply`
- строка 212 — `syncUiFromState`
- строка 219 — `capturePristine`
- строка 230 — `restorePristine`
- строка 250 — `captureMemory`
- строка 255 — `applyMemory`
- строка 278 — `serializeCurves`
- строка 291 — `rebuildCurves`
- строка 311 — `modelKeyOf`
- строка 316 — `collectModelState`
- строка 336 — `applyModelState`

#### `calc2/static/calc2/90-explain.js`

- строка 388 — `sceneExplainHtml`

#### `calc2/static/calc2/91-session.js`

- строка 44 — `histOf`
- строка 56 — `histSig`
- строка 66 — `captureOpenUi`
- строка 72 — `restoreOpenUi`
- строка 89 — `applyKeepView`
- строка 101 — `historyBaseline`
- строка 110 — `historyCheck`
- строка 138 — `historyAfterRedraw`
- строка 146 — `historyMark`
- строка 151 — `historyUndo`
- строка 164 — `historyRedo`
- строка 176 — `historyCan`
- строка 180 — `historyClearAll`
- строка 182 — `notifyHistory`
- строка 188 — `histLabelOf`
- строка 204 — `storeGet`
- строка 205 — `storeSet`
- строка 210 — `compactModelState`
- строка 224 — `expandModelState`
- строка 233 — `autosaveModel`
- строка 247 — `forgetAutosaves`
- строка 257 — `savedModel`
- строка 263 — `recentModels`
- строка 269 — `writeModelToUrl`
- строка 279 — `dropShareHash`
- строка 295 — `fromProblemOf`
- строка 299 — `dropFromParam`
- строка 308 — `showBackToProblem`
- строка 315 — `hideBackToProblem`
- строка 320 — `openFromProblem`
- строка 331 — `b64urlEncode`
- строка 335 — `b64urlDecode`
- строка 372 — `openModelByUser`
- строка 393 — `restoreOnLoad`
- строка 432 — `viewDefaults`
- строка 469 — `resetModelWithUndo`

#### `calc2/static/calc2/92-ui-kit.js`

- строка 14 — `placePop`
- строка 34 — `closePop`
- строка 46 — `onPopOutside`
- строка 54 — `onPopKey`
- строка 61 — `openPop`
- строка 79 — `openFcMenu`
- строка 80 — `closeFcMenu`
- строка 92 — `tagPultChip`
- строка 96 — `clearPultBox`
- строка 101 — `pultChip`
- строка 111 — `parkCurveSliders`
- строка 125 — `placeCurveSliders`
- строка 180 — `howToBuild`
- строка 231 — `wireUiKit`
- строка 293 — `syncShowSection`
- строка 373 — `vgList`
- строка 375 — `vgNodeOf`
- строка 383 — `vgSetup`
- строка 418 — `vgHomeShown`
- строка 425 — `AREA_ID`
- строка 426 — `syncOnChart`
- строка 522 — `hideEmptyGroupTitles`
- строка 550 — `wrapFieldInCard`
- строка 622 — `formPrefix`
- строка 633 — `paintCard`
- строка 720 — `scAxisLetter`
- строка 730 — `SC_NO_FUNCS`
- строка 731 — `scFirstCardName`
- строка 736 — `scWords`
- строка 761 — `scOn`
- строка 762 — `scProw`
- строка 763 — `scParamAnchor`
- строка 772 — `scSetup`
- строка 834 — `scStepper`
- строка 858 — `scSync`
- строка 897 — `scConsumerCard`
- строка 947 — `scConsumerSync`
- строка 968 — `scIneqSetup`
- строка 1005 — `scIneqSync`
- строка 1032 — `scGraphRows`
- строка 1072 — `scGraphSync`
- строка 1101 — `scMathSetup`
- строка 1125 — `scMathSync`
- строка 1146 — `scParamsCont`
- строка 1161 — `scMinmaxSetup`
- строка 1173 — `scMmRows`
- строка 1205 — `scValueOnly`
- строка 1208 — `scPchips`
- строка 1252 — `scIntervSync`
- строка 1277 — `scExtCards`
- строка 1313 — `applyAreaHidden`
- строка 1327 — `vgFormIds`

#### `calc2/static/calc2/93-shell.js`

- строка 11 — `modelBlockOf`
- строка 16 — `syncModelHead`
- строка 28 — `syncZoomLevel`
- строка 44 — `setFocusMode`
- строка 54 — `afterColumnShown`
- строка 71 — `syncToolSeg`
- строка 78 — `setPtsMode`
- строка 105 — `setTool`
- строка 124 — `answerHidden`
- строка 125 — `setAnswerHidden`
- строка 137 — `showAnswerForSelf`
- строка 140 — `wireAnswerHide`
- строка 151 — `wireShell`
- строка 235 — `phMoreLayout`
- строка 269 — `wirePhoneMore`

#### `calc2/static/calc2/94-answer.js`

- строка 199 — `areasHead`
- строка 205 — `ansNum`
- строка 210 — `answerCellWas`
- строка 243 — `heroLabel`
- строка 259 — `notationTex`
- строка 273 — `plainText`
- строка 276 — `statRows`
- строка 280 — `txRow`
- строка 303 — `answerSignature`
- строка 320 — `scheduleAnswer`
- строка 331 — `answerIsMath`
- строка 335 — `labelCopy`
- строка 346 — `answerNumberItem`
- строка 352 — `answerValueInto`
- строка 398 — `answerGroupHead`
- строка 421 — `segNoteOn`
- строка 425 — `buildSegNote`
- строка 439 — `hideDrainedBlocks`
- строка 484 — `retypesetSeenRows`
- строка 508 — `remeasureStatsAfterFonts`
- строка 523 — `answerReflow`
- строка 534 — `answerCells`
- строка 590 — `buildAnswer`
- строка 729 — `hideEchoes`
- строка 763 — `markFirstSection`
- строка 796 — `decorateTables`
- строка 830 — `liftTableHead`
- строка 858 — `answerRow`
- строка 910 — `burdenOn`
- строка 917 — `burdenNoteText`
- строка 924 — `buildBurden`
- строка 957 — `buildStatus`
- строка 984 — `buildExplainAccordion`
- строка 1049 — `questionsWord`
- строка 1055 — `syncExplainBar`

#### `calc2/static/calc2/95-picker-screen.js`

- строка 26 — `pkNorm`
- строка 29 — `pickerModels`
- строка 41 — `pickerScore`
- строка 57 — `whenText`
- строка 67 — `buildPickerScreen`
- строка 191 — `selectPickerTab`
- строка 203 — `pickerSelectedTab`
- строка 210 — `pickerDefaultTab`
- строка 220 — `pickerOpenTab`
- строка 234 — `loadPickerPreviews`
- строка 242 — `pickerPreviewSvg`
- строка 270 — `fillPickerWells`
- строка 282 — `pickerFilter`
- строка 348 — `renderPickerContinue`
- строка 399 — `buildSwitcher`
- строка 421 — `renderSwitcher`
- строка 459 — `openSwitcher`

#### `calc2/static/calc2/96-self.js`

- строка 19 — `selfNum`
- строка 29 — `selfParse`
- строка 55 — `selfClose`
- строка 56 — `selfAccept`
- строка 70 — `checkGuess`
- строка 85 — `selfIsAnswer`
- строка 88 — `selfText`
- строка 94 — `selfNot`
- строка 96 — `selfKey`
- строка 98 — `setSelfMode`
- строка 113 — `selfCell`
- строка 189 — `selfAfterAnswer`
- строка 205 — `applySelf`
- строка 233 — `selfCanvas`
- строка 285 — `selfMaskText`
- строка 301 — `selfOpenValues`
- строка 318 — `selfPointOpen`
- строка 330 — `selfMasked`
- строка 332 — `wireSelf`

#### `calc2/static/calc2/99-boot.js`

- строка 13 — `lockNumberFields`
- строка 42 — `init`

**Итого функций в индексе: 1433.**

<!-- AUTO:END -->
