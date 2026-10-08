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

*Автоматически собрано командой `manage.py calc2_map`. Дата: 2026-10-08. HEAD: `85cf3fd8`. Не редактировать руками — вся эта часть файла, от отметки начала автосекции и до отметки её конца, перезаписывается заново при каждом запуске команды.*

### Файлы (маршрут → представление → шаблон → статика)

| Путь | Строк | КБ | Тип |
|---|---:|---:|---|
| `calc2/urls.py` | 19 | 0.6 | python |
| `calc2/views.py` | 224 | 13.4 | python |
| `calc2/templates/calc2/calc2.html` | 2591 | 216.8 | шаблон |
| `calc2/static/calc2/calc2.css` | 3404 | 248.4 | CSS |
| `calc2/static/calc2/00-config.js` | 563 | 48.5 | JS |
| `calc2/static/calc2/10-math-core.js` | 1126 | 73.5 | JS |
| `calc2/static/calc2/20-plane.js` | 993 | 67.4 | JS |
| `calc2/static/calc2/30-curves.js` | 1428 | 103.9 | JS |
| `calc2/static/calc2/40-scenes-market.js` | 3748 | 268.1 | JS |
| `calc2/static/calc2/42-scenes-mono.js` | 1764 | 129.3 | JS |
| `calc2/static/calc2/44-scenes-firm.js` | 1209 | 80.4 | JS |
| `calc2/static/calc2/46-scenes-labor.js` | 756 | 54.8 | JS |
| `calc2/static/calc2/48-scenes-consumer.js` | 265 | 16.3 | JS |
| `calc2/static/calc2/50-scenes-macro.js` | 435 | 30.1 | JS |
| `calc2/static/calc2/52-modes.js` | 938 | 63.9 | JS |
| `calc2/static/calc2/54-scenes-ppf.js` | 3161 | 203.3 | JS |
| `calc2/static/calc2/56-scenes-inequality.js` | 558 | 36.5 | JS |
| `calc2/static/calc2/60-overlays.js` | 4582 | 289.0 | JS |
| `calc2/static/calc2/70-scenes-math.js` | 1623 | 106.4 | JS |
| `calc2/static/calc2/72-export-tex.js` | 1546 | 115.7 | JS |
| `calc2/static/calc2/80-ui.js` | 675 | 41.6 | JS |
| `calc2/static/calc2/82-input.js` | 2159 | 126.7 | JS |
| `calc2/static/calc2/84-picker.js` | 571 | 42.9 | JS |
| `calc2/static/calc2/86-workspace.js` | 1982 | 128.1 | JS |
| `calc2/static/calc2/88-params.js` | 1926 | 130.0 | JS |
| `calc2/static/calc2/89-model-state.js` | 323 | 19.3 | JS |
| `calc2/static/calc2/90-explain.js` | 381 | 63.1 | JS |
| `calc2/static/calc2/91-session.js` | 441 | 22.3 | JS |
| `calc2/static/calc2/92-ui-kit.js` | 336 | 19.2 | JS |
| `calc2/static/calc2/93-shell.js` | 207 | 12.0 | JS |
| `calc2/static/calc2/94-answer.js` | 391 | 24.4 | JS |
| `calc2/static/calc2/95-picker-screen.js` | 397 | 21.5 | JS |
| `calc2/static/calc2/96-self.js` | 207 | 12.6 | JS |
| `calc2/static/calc2/99-boot.js` | 108 | 9.0 | JS |

**Итого: 34 файлов, 41037 строк, 2839.1 КБ.**

### Индекс функций (объявления верхнего уровня, по возрастанию строки)

#### `calc2/static/calc2/00-config.js`

- строка 71 — `fsStep`
- строка 466 — `cssVar`
- строка 470 — `refreshColors`
- строка 543 — `canvasMode`
- строка 548 — `canvasArmed`
- строка 554 — `roleColor`

#### `calc2/static/calc2/10-math-core.js`

- строка 17 — `topLevelEqIndex`
- строка 36 — `axisScope`
- строка 42 — `compileFormula`
- строка 88 — `simplifyRecord`
- строка 108 — `isNaNNode`
- строка 123 — `liftConditional`
- строка 150 — `simplifyChainStr`
- строка 181 — `simplifyBody`
- строка 218 — `sameNumerically`
- строка 242 — `evalCurve`
- строка 260 — `detectLinear`
- строка 312 — `curveParamNames`
- строка 327 — `paramSignature`
- строка 332 — `refreshLinearForParams`
- строка 364 — `fmtLinear`
- строка 388 — `compileFormulaP`
- строка 399 — `evalQofP`
- строка 414 — `detectLinearP`
- строка 448 — `invertQofP`
- строка 471 — `buildCurveFromQP`
- строка 496 — `makeVerticalCurve`
- строка 500 — `isVertical`
- строка 506 — `curveZeroQ`
- строка 558 — `frameFloorQ`
- строка 559 — `frameFloorP`
- строка 562 — `naturalSpanQ`
- строка 568 — `eqSearchSpan`
- строка 581 — `bumpModelSpan`
- строка 582 — `modelSpanQ`
- строка 597 — `findEquilibrium`
- строка 657 — `findOffQuadIntersection`
- строка 682 — `bisect`
- строка 694 — `integrate`
- строка 716 — `signChanges`
- строка 732 — `areaBetween`
- строка 743 — `crossingCount`
- строка 764 — `findRoot`
- строка 782 — `invCurve`
- строка 796 — `curveDeriv`
- строка 803 — `compileExt`
- строка 811 — `evalSocial`
- строка 839 — `compileTwoVar`
- строка 849 — `compileTwoVarUncached`
- строка 859 — `evalTwoVar`
- строка 871 — `solveLevelB`
- строка 909 — `traceLevelCurve`
- строка 934 — `partialA`
- строка 939 — `partialB`
- строка 946 — `mrsAt`
- строка 958 — `optimizeAlongConstraint`
- строка 1022 — `qtyHasCyrillic`
- строка 1027 — `qtyIsQuantity`
- строка 1041 — `qtyParts`
- строка 1099 — `qtyLatex`

#### `calc2/static/calc2/20-plane.js`

- строка 12 — `computeSize`
- строка 45 — `measureText`
- строка 79 — `fitMargins`
- строка 130 — `fitLeftForLabels`
- строка 143 — `makeScales`
- строка 178 — `clearPanels`
- строка 180 — `registerPanel`
- строка 197 — `panelDist`
- строка 206 — `panelAt`
- строка 218 — `activePanel`
- строка 226 — `panelById`
- строка 241 — `panelWin`
- строка 245 — `resetPanelWins`
- строка 253 — `panelZoomBy`
- строка 270 — `panelPanBy`
- строка 284 — `gesturePanelId`
- строка 312 — `isEconScene`
- строка 318 — `econLo`
- строка 322 — `quadLo`
- строка 345 — `quadPrice`
- строка 355 — `toPx`
- строка 356 — `toData`
- строка 372 — `roundShown`
- строка 381 — `fmtSum`
- строка 387 — `shownDiff`
- строка 388 — `fmtDiff`
- строка 400 — `shownDecimals`
- строка 408 — `sumDecimals`
- строка 412 — `fmt`
- строка 433 — `fmtInput`
- строка 443 — `niceTickStep`
- строка 455 — `axisTicks`
- строка 468 — `xTicks`
- строка 469 — `yTicks`
- строка 472 — `addDefs`
- строка 532 — `drawGrid`
- строка 583 — `extraTickX`
- строка 594 — `extraTickY`
- строка 634 — `dropTickAt`
- строка 661 — `coordValue`
- строка 681 — `coordAlreadyAt`
- строка 716 — `resetDrawnKeyPoints`
- строка 719 — `panelOfGlobalScales`
- строка 723 — `kpNode`
- строка 739 — `collectDashes`
- строка 756 — `dashEndsNear`
- строка 768 — `flushDrawnKeyPoints`
- строка 816 — `noteAxisX`
- строка 821 — `noteAxisY`
- строка 828 — `kpName`
- строка 833 — `axisValueX`
- строка 860 — `axisValueY`
- строка 885 — `axisValueText`
- строка 902 — `drawAxes`

#### `calc2/static/calc2/30-curves.js`

- строка 8 — `nextColor`
- строка 73 — `piecewiseNodesQ`
- строка 107 — `pointsFromNodes`
- строка 124 — `curvePoints`
- строка 180 — `drawMarginalCurve`
- строка 260 — `markExpr`
- строка 286 — `markNumeric`
- строка 291 — `markPoly`
- строка 299 — `curveFormula`
- строка 310 — `markCurve`
- строка 324 — `markArea`
- строка 343 — `derivativeExpr`
- строка 390 — `curveAnchor`
- строка 496 — `curveLabelSize`
- строка 497 — `labelScale`
- строка 533 — `unclipLabels`
- строка 602 — `keepAxisNamesInside`
- строка 619 — `spreadLabels`
- строка 792 — `parseColor`
- строка 807 — `relLum`
- строка 815 — `contrastOf`
- строка 820 — `rgbToHsl`
- строка 833 — `hslToRgb`
- строка 860 — `labelInk`
- строка 892 — `applyLabelInk`
- строка 919 — `mixToBg`
- строка 927 — `applyLabelSize`
- строка 961 — `smoothLabel`
- строка 991 — `requestLabelFrame`
- строка 996 — `resetLabelPositions`
- строка 1006 — `curveLabelAnchor`
- строка 1015 — `labelCurve`
- строка 1101 — `curveWidth`
- строка 1143 — `curveDash`
- строка 1151 — `curveOpacity`
- строка 1159 — `drawCurves`
- строка 1320 — `sceneDrawsCurveList`
- строка 1329 — `syncCurveListVisibility`
- строка 1344 — `curveDragAllowed`
- строка 1354 — `roundDrag`
- строка 1392 — `setCurveFreeTerm`

#### `calc2/static/calc2/40-scenes-market.js`

- строка 17 — `curveByRole`
- строка 20 — `curveByRoleAny`
- строка 24 — `recompute`
- строка 510 — `qtyAtPrice`
- строка 520 — `openQuotaName`
- строка 524 — `recomputeOpenEconomy`
- строка 616 — `drawOpenAreas`
- строка 664 — `drawOpenLines`
- строка 711 — `attachOpenPwDrag`
- строка 719 — `setOpenPw`
- строка 732 — `setOpenTool`
- строка 747 — `syncOpenQuotaLabel`
- строка 753 — `updateOpenPanel`
- строка 808 — `drawEquilibrium`
- строка 845 — `drawOffQuadIntersection`
- строка 884 — `offQuadExplainHtml`
- строка 910 — `pctFormExplainHtml`
- строка 947 — `mathTspans`
- строка 987 — `hasMathMarkup`
- строка 1011 — `markNotationTspan`
- строка 1028 — `mixedNotationRe`
- строка 1036 — `mixedMathTspans`
- строка 1080 — `qtyTspans`
- строка 1117 — `qtyGreekChar`
- строка 1155 — `texToCanvasText`
- строка 1164 — `renderLabelText`
- строка 1185 — `haloText`
- строка 1218 — `pointName`
- строка 1244 — `yWageLabel`
- строка 1249 — `yWageValue`
- строка 1272 — `isMonopolyScene`
- строка 1280 — `eqSectionTitle`
- строка 1296 — `updateEqSectionTitle`
- строка 1313 — `interventionKeyValues`
- строка 1378 — `countCrossings`
- строка 1387 — `updateInfoPanel`
- строка 1496 — `sumSceneOn`
- строка 1499 — `sumGroupsOf`
- строка 1506 — `sumGroupQty`
- строка 1519 — `sumChokePrice`
- строка 1545 — `sumPriceTop`
- строка 1566 — `sumLinearRecord`
- строка 1668 — `integrateBroken`
- строка 1679 — `curveBreaks`
- строка 1690 — `quadBreaks`
- строка 1706 — `sumSegExpr`
- строка 1724 — `sumPolyline`
- строка 1752 — `sumRebuildSide`
- строка 1803 — `sumSignature`
- строка 1823 — `sumRebuild`
- строка 1843 — `sumAnalyticsKey`
- строка 1861 — `sumGroupName`
- строка 1884 — `sumTagOf`
- строка 1891 — `sumShortTag`
- строка 1920 — `sumGroupColor`
- строка 1925 — `sumStartExpr`
- строка 1933 — `sumReorder`
- строка 1938 — `sumAddGroup`
- строка 1951 — `sumBuildScene`
- строка 1979 — `sumSetCount`
- строка 1998 — `syncSumUi`
- строка 2012 — `sumGroupStats`
- строка 2058 — `sumFinalRecords`
- строка 2076 — `updateSumPanel`
- строка 2137 — `drawAreas`
- строка 2167 — `beforeInterventionNote`
- строка 2176 — `updateAreasPanel`
- строка 2205 — `intervOnBuyer`
- строка 2214 — `drawShiftedSupply`
- строка 2266 — `taxPivotQ`
- строка 2297 — `taxPivotPoint`
- строка 2306 — `drawTaxPivot`
- строка 2341 — `drawTaxAreas`
- строка 2381 — `drawTaxPoints`
- строка 2434 — `attachTaxDrag`
- строка 2455 — `setTax`
- строка 2573 — `taxFormKey`
- строка 2581 — `pctForm`
- строка 2589 — `syncTaxKind`
- строка 2594 — `applyIntervCascade`
- строка 2667 — `setTaxForm`
- строка 2685 — `setType`
- строка 2735 — `rateLetter`
- строка 2739 — `rateUnit`
- строка 2761 — `modelPriceTop`
- строка 2772 — `unitRateMax`
- строка 2780 — `applyPriceRegBounds`
- строка 2789 — `applyTaxRateBounds`
- строка 2824 — `syncQuotaHint`
- строка 2841 — `syncPcHint`
- строка 2849 — `markCurrentIntervHint`
- строка 2858 — `intervHintKey`
- строка 2868 — `intervHintHtml`
- строка 2882 — `syncTaxHint`
- строка 2912 — `setTaxKind`
- строка 2918 — `updateTaxPanel`
- строка 3041 — `setTaxSide`
- строка 3052 — `setTaxSideButtons`
- строка 3065 — `drawElasticityZones`
- строка 3083 — `drawElasticityPoint`
- строка 3112 — `attachElastDrag`
- строка 3120 — `drawElasticityPointS`
- строка 3140 — `attachElastDragS`
- строка 3148 — `updateElasticityPanel`
- строка 3212 — `drawExtAreas`
- строка 3226 — `drawExtCurves`
- строка 3253 — `drawExtPoints`
- строка 3287 — `drawExtScenario`
- строка 3296 — `updateExtPanel`
- строка 3337 — `setExtSign`
- строка 3346 — `syncSocialFields`
- строка 3378 — `socialDefaultExpr`
- строка 3384 — `recompileSocial`
- строка 3406 — `setPRegFields`
- строка 3415 — `setPReg`
- строка 3424 — `drawPcAreas`
- строка 3451 — `drawPriceControl`
- строка 3500 — `attachPcDrag`
- строка 3509 — `updatePcPanel`
- строка 3554 — `setQuotaFields`
- строка 3566 — `setQuota`
- строка 3573 — `setQuotaPos`
- строка 3583 — `updateQuotaPriceLabel`
- строка 3595 — `drawQuotaAreas`
- строка 3622 — `drawQuotaLines`
- строка 3667 — `attachQuotaDrag`
- строка 3680 — `updateQuotaPanel`
- строка 3729 — `drawGhost`

#### `calc2/static/calc2/42-scenes-mono.js`

- строка 11 — `mcSourceCurve`
- строка 15 — `mcSourceCurveAny`
- строка 20 — `mcAt`
- строка 51 — `mcFloor`
- строка 56 — `mcFormula`
- строка 62 — `mrFormula`
- строка 69 — `marginalRevenue`
- строка 78 — `drawMonopolyAreas`
- строка 117 — `drawMonopoly`
- строка 140 — `drawMonopolyPoints`
- строка 177 — `updateMonoPanel`
- строка 208 — `setMarket`
- строка 243 — `monopolyCeiling`
- строка 291 — `drawMonoCeilingAreas`
- строка 310 — `drawMonoKinkedMR`
- строка 327 — `drawMonoCeilingPoints`
- строка 359 — `drawMonoCeilingLine`
- строка 383 — `monopolyTax`
- строка 408 — `monopolyFloor`
- строка 450 — `monopolyQuota`
- строка 478 — `drawMonoQuotaAreas`
- строка 500 — `drawMonoQuotaPoints`
- строка 522 — `drawMonoQuotaLine`
- строка 548 — `naturalATC`
- строка 560 — `naturalATCFormula`
- строка 579 — `findRootLast`
- строка 594 — `recomputeNatural`
- строка 623 — `drawNaturalAreas`
- строка 638 — `drawNaturalCurves`
- строка 661 — `drawNaturalPoints`
- строка 690 — `drawNaturalFull`
- строка 698 — `updateNaturalPanel`
- строка 736 — `drawMonoTaxAreas`
- строка 772 — `drawMonoTaxShiftedMC`
- строка 790 — `drawMonoTaxPoints`
- строка 811 — `drawMonoFloorAreas`
- строка 826 — `drawMonoFloorPoints`
- строка 846 — `drawMonoFloorLine`
- строка 861 — `updateMonoInterventionPanel`
- строка 987 — `makeCurve`
- строка 997 — `segExpr`
- строка 1004 — `kinkedDemandExpr`
- строка 1015 — `drawDiscr1`
- строка 1046 — `updateDiscr1Panel`
- строка 1071 — `allocateMR`
- строка 1084 — `recomputeDiscr3`
- строка 1124 — `drawMiniMarket`
- строка 1231 — `redrawDiscr3`
- строка 1274 — `drawMonoExport`
- строка 1398 — `updateDiscr3Panel`
- строка 1461 — `applyD3WorldLabels`
- строка 1484 — `buildKinkedDemand`
- строка 1531 — `recomputeKinked`
- строка 1571 — `drawKinkedFull`
- строка 1660 — `updateKinkPanel`
- строка 1689 — `applyMonoVisibility`
- строка 1710 — `ensureMonopolyCurves`
- строка 1721 — `fillIfEmpty`
- строка 1724 — `ensureD3Fields`
- строка 1729 — `ensureKinkFields`
- строка 1735 — `ensureMonopolyPreset`
- строка 1742 — `setMonoMode`
- строка 1753 — `setKinkInput`

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
- строка 353 — `noMinNote`
- строка 363 — `updateCostsPanel`
- строка 405 — `redrawCosts`
- строка 440 — `recomputeLongRun`
- строка 509 — `drawLongRunArea`
- строка 517 — `fillLongRunArea`
- строка 541 — `drawLongRunMarks`
- строка 546 — `fillLongRunMarks`
- строка 578 — `drawLongRunHandle`
- строка 589 — `setLrPrice`
- строка 597 — `syncLrPriceFields`
- строка 615 — `beginLrDrag`
- строка 617 — `dragLrPrice`
- строка 632 — `endLrDrag`
- строка 639 — `updateLongRunPanel`
- строка 682 — `prodEval`
- строка 690 — `prodMP`
- строка 695 — `prodAP`
- строка 703 — `maxOf`
- строка 723 — `realMax`
- строка 725 — `recomputeProduction`
- строка 744 — `redrawProduction`
- строка 860 — `noMaxNote`
- строка 869 — `updateProdPanel`
- строка 893 — `recomputeIsoquant`
- строка 904 — `redrawIsoquant`
- строка 920 — `updateIsoPanel`
- строка 958 — `plantMC`
- строка 964 — `plantTC`
- строка 970 — `plantQatMC`
- строка 986 — `recomputePlants`
- строка 1020 — `plantsAt`
- строка 1037 — `redrawPlants`
- строка 1118 — `updatePlantsPanel`
- строка 1149 — `setPlantsView`
- строка 1156 — `setPlantsQ`
- строка 1167 — `setCostsInputMode`
- строка 1175 — `syncCostsInputMode`
- строка 1189 — `setCostsSub`

#### `calc2/static/calc2/46-scenes-labor.js`

- строка 14 — `laborMCL`
- строка 26 — `laborMinMonopsony`
- строка 64 — `laborMinCompetition`
- строка 89 — `laborUnionMonopoly`
- строка 103 — `laborUnionWageFloor`
- строка 114 — `recomputeLabor`
- строка 196 — `laborPoint`
- строка 214 — `drawLaborGhost`
- строка 224 — `drawLaborSurpluses`
- строка 242 — `drawLaborMinWelfare`
- строка 274 — `drawLaborMCL`
- строка 308 — `drawLaborDWL`
- строка 322 — `drawLaborMonopsonyPoints`
- строка 378 — `drawLaborCompPoints`
- строка 404 — `drawLaborMinLine`
- строка 418 — `attachLaborMinDrag`
- строка 426 — `setLaborMinFields`
- строка 433 — `setLaborMin`
- строка 445 — `drawLaborUnionMRL`
- строка 457 — `drawLaborGapDWL`
- строка 468 — `drawLaborUnionPoints`
- строка 502 — `drawLaborUnionWageLine`
- строка 516 — `attachUnionWageDrag`
- строка 524 — `setUnionWageFields`
- строка 531 — `setUnionWage`
- строка 541 — `setUnionModel`
- строка 558 — `drawLaborBilateral`
- строка 586 — `updateLaborBilateralPanel`
- строка 604 — `setLaborStruct`
- строка 627 — `updateLaborPanel`
- строка 717 — `redrawLabor`

#### `calc2/static/calc2/48-scenes-consumer.js`

- строка 12 — `consumerUtility`
- строка 27 — `consumerOptimum`
- строка 35 — `setConsSlutsky`
- строка 46 — `recomputeConsumer`
- строка 81 — `drawBudgetLine`
- строка 96 — `drawLevelCurve`
- строка 108 — `drawChoicePoint`
- строка 120 — `attachBudgetHandles`
- строка 145 — `setConsumerNum`
- строка 154 — `redrawConsumer`
- строка 188 — `updateConsumerPanel`
- строка 239 — `applyConsumerTypeUI`
- строка 253 — `setConsumerType`

#### `calc2/static/calc2/50-scenes-macro.js`

- строка 20 — `compileVar`
- строка 31 — `evalVar`
- строка 40 — `macroCurveY`
- строка 49 — `macroCurveInv`
- строка 89 — `macroP`
- строка 95 — `recomputeMacro`
- строка 217 — `drawMacroCurve`
- строка 249 — `redrawMacro`
- строка 328 — `drawEquilibriumAt`
- строка 339 — `updateMacroPanel`
- строка 423 — `setMacroModel`

#### `calc2/static/calc2/52-modes.js`

- строка 14 — `setRanges`
- строка 37 — `syncViewFields`
- строка 76 — `updateResetViewBtn`
- строка 93 — `markViewDirty`
- строка 113 — `prefersReducedMotion`
- строка 118 — `animateRanges`
- строка 149 — `applyTradeRanges`
- строка 175 — `scheduleRangeAnim`
- строка 194 — `padMax`
- строка 212 — `curveAxisBounds`
- строка 243 — `boundsOfDrawn`
- строка 283 — `redrawKeepingWindow`
- строка 288 — `applyAutoRanges`
- строка 315 — `zoomRound`
- строка 321 — `zoomBy`
- строка 404 — `panByPixels`
- строка 484 — `wantedRanges`
- строка 517 — `growRanges`
- строка 533 — `growWindowToModel`
- строка 544 — `resetZoom`
- строка 575 — `flushWheel`
- строка 586 — `initZoom`
- строка 782 — `zoomStep`
- строка 791 — `cancelRangeAnim`
- строка 803 — `makeThrottle`
- строка 816 — `ineqRedraw`
- строка 819 — `setMode`
- строка 899 — `applyScenarioVisibility`
- строка 925 — `setScenario`

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
- строка 701 — `classifyPpf`
- строка 762 — `ppfFitR2`
- строка 784 — `niceMax`
- строка 792 — `singlePpfPoints`
- строка 799 — `findRootIn`
- строка 811 — `interpY`
- строка 825 — `maxAllocY`
- строка 850 — `combinedPpfPoints`
- строка 860 — `allocAt`
- строка 891 — `detectCombinedKinks`
- строка 966 — `ppfCoefTex`
- строка 975 — `ppfNum`
- строка 986 — `ppfSnap`
- строка 996 — `ppfPiecesToExpr`
- строка 1013 — `ppfLinearExpr`
- строка 1020 — `combinedPpfLinearRecord`
- строка 1197 — `ppfPoly2Xmax`
- строка 1216 — `ppfCostOf`
- строка 1225 — `ppfValid`
- строка 1233 — `ppfFam`
- строка 1234 — `ppfClamp`
- строка 1245 — `ppfReduceActive`
- строка 1264 — `ppfPieceTex`
- строка 1314 — `ppfPoly2Terms`
- строка 1324 — `ppfPolyJoin`
- строка 1340 — `ppfPieceBody`
- строка 1378 — `ppfPieceAt`
- строка 1393 — `ppfPiecesRecord`
- строка 1432 — `ppfSumByEqualCost`
- строка 1537 — `ppfSumByEnvelope`
- строка 1626 — `ppfEnvPiece`
- строка 1637 — `ppfMergeSameLine`
- строка 1657 — `ppfCostKinds`
- строка 1666 — `ppfCostValue`
- строка 1676 — `ppfWhyNumeric`
- строка 1729 — `ppfSumMixedPair`
- строка 1894 — `ppfSumAnalytic`
- строка 1912 — `combinedPpfFormula`
- строка 1948 — `verifyFormula`
- строка 1959 — `detectKinks`
- строка 1984 — `showPaneError`
- строка 1995 — `ppfSumCount`
- строка 1996 — `ppfSumGet`
- строка 2001 — `ppfSumSet`
- строка 2006 — `ppfSumName`
- строка 2010 — `ppfSumColor`
- строка 2024 — `ppfSumSignature`
- строка 2034 — `recomputePpfSum`
- строка 2040 — `ensurePpfSum`
- строка 2044 — `recomputePpfSumRaw`
- строка 2155 — `renderPpfSumRows`
- строка 2200 — `detectSumKinks`
- строка 2218 — `drawPpfSumCurves`
- строка 2250 — `drawPpfSumMarks`
- строка 2276 — `updatePpfSumPanel`
- строка 2392 — `fmtRu`
- строка 2396 — `ppfSumSchemaData`
- строка 2430 — `schemaNote`
- строка 2437 — `drawPpfSumSchema`
- строка 2489 — `redrawPpfSum`
- строка 2502 — `setPpfSumView`
- строка 2513 — `cornerByValue`
- строка 2537 — `bestByValue`
- строка 2556 — `recomputePpfTrade`
- строка 2598 — `drawPpfTrade`
- строка 2626 — `drawPpfTradeMarks`
- строка 2654 — `updatePpfTradePanel`
- строка 2776 — `syncPpftPriceUI`
- строка 2787 — `redrawPpfTrade`
- строка 2808 — `recomputeTradeB`
- строка 2897 — `tradeCpfPoints`
- строка 2915 — `tradeCpfMark`
- строка 2934 — `tradeBPanels`
- строка 2955 — `drawTradeB`
- строка 3028 — `drawTradeBMarks`
- строка 3031 — `tbName`
- строка 3037 — `updateTradeBPanel`
- строка 3107 — `syncTbPriceUI`
- строка 3120 — `redrawTradeB`
- строка 3135 — `setTradeScenario`
- строка 3147 — `setPpfSub`

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
- строка 429 — `redrawInequality`
- строка 478 — `defaultGroupShares`
- строка 485 — `setIneqInput`
- строка 502 — `setIneqAlpha`
- строка 518 — `setIneqGroupN`
- строка 529 — `setIneqRedistTool`
- строка 540 — `renderIneqGroupsTable`

#### `calc2/static/calc2/60-overlays.js`

- строка 10 — `redrawAll`
- строка 78 — `redrawScene`
- строка 223 — `redrawGraphMode`
- строка 234 — `renderMmRows`
- строка 279 — `graphRowsBox`
- строка 282 — `renderGraphRows`
- строка 300 — `graphError`
- строка 307 — `buildGraphRow`
- строка 389 — `equipGraphRows`
- строка 397 — `graphRowInput`
- строка 442 — `mainScales`
- строка 453 — `drawOverlays`
- строка 559 — `guardedPanelIds`
- строка 563 — `guardPanelBoxes`
- строка 599 — `panelsChangedSinceLastPass`
- строка 604 — `markPanelsChanged`
- строка 607 — `flushPendingPanelClears`
- строка 616 — `refreshAnalyticsPanel`
- строка 644 — `typesetStats`
- строка 691 — `addStatSign`
- строка 704 — `statToTex`
- строка 736 — `katexVisibleText`
- строка 742 — `restatWide`
- строка 782 — `statInkWidth`
- строка 790 — `statTooWide`
- строка 799 — `statPieces`
- строка 834 — `texAbbrev`
- строка 840 — `renderMathIn`
- строка 883 — `areaKey`
- строка 888 — `subDigits`
- строка 893 — `applyAreaColors`
- строка 903 — `currentAreas`
- строка 921 — `areaOfPathEl`
- строка 983 — `areaShort`
- строка 992 — `drawLegend`
- строка 1055 — `floatRects`
- строка 1075 — `legendCorner`
- строка 1152 — `viewWindow`
- строка 1164 — `axisWords`
- строка 1170 — `crossPoints`
- строка 1272 — `invalidateKeyTargets`
- строка 1275 — `kinksOf`
- строка 1323 — `keyTargets`
- строка 1498 — `snapVertexAt`
- строка 1530 — `markPanelId`
- строка 1550 — `armedPanelId`
- строка 1556 — `drawCrossPoints`
- строка 1693 — `armCurve`
- строка 1699 — `disarmCurve`
- строка 1707 — `keyPointLit`
- строка 1720 — `drawCurveHits`
- строка 1758 — `pinKeyPoint`
- строка 1778 — `hoverLabel`
- строка 1789 — `drawRoller`
- строка 1810 — `rollerTargetAt`
- строка 1840 — `rollerClampX`
- строка 1859 — `rollerMove`
- строка 1875 — `showRollTip`
- строка 1898 — `hideRollTip`
- строка 1907 — `rollerOff`
- строка 1918 — `curveRightEdge`
- строка 1943 — `axisXLetter`
- строка 1953 — `axisLetter`
- строка 1966 — `armVerts`
- строка 2005 — `markServiceNodes`
- строка 2022 — `syncCanvasMode`
- строка 2043 — `leaveCanvasMode`
- строка 2048 — `addAreaVert`
- строка 2061 — `vertPanels`
- строка 2064 — `vertsMixed`
- строка 2066 — `clearAreaVerts`
- строка 2072 — `renderVertList`
- строка 2144 — `syncAreaCalcButton`
- строка 2156 — `areaPickedCurve`
- строка 2165 — `areaCurveRange`
- строка 2183 — `syncAreaRangeLabel`
- строка 2219 — `freshenVertNames`
- строка 2235 — `drawAreaVerts`
- строка 2305 — `areaTargets`
- строка 2309 — `calcAreaUnderCurve`
- строка 2322 — `ringArea`
- строка 2332 — `segCross`
- строка 2339 — `ringSelfCrosses`
- строка 2361 — `angleRing`
- строка 2367 — `bestAreaRing`
- строка 2397 — `calcAreaPolygon`
- строка 2414 — `AREA_PALETTE`
- строка 2416 — `runAreaCalc`
- строка 2436 — `clearAreaCalc`
- строка 2443 — `drawAreaCalc`
- строка 2479 — `updateAreaCalcPanel`
- строка 2577 — `syncAreaCalcUI`
- строка 2612 — `updateQuickArea`
- строка 2614 — `setAreaCalcMode`
- строка 2630 — `wireFolds`
- строка 2655 — `wireAreaCalc`
- строка 2684 — `paramsAllowed`
- строка 2709 — `isReservedName`
- строка 2749 — `expandImplicitMul`
- строка 2795 — `visibleSvgText`
- строка 2821 — `chartLabelSource`
- строка 2831 — `chartLabelBase`
- строка 2848 — `chartLabelKind`
- строка 2862 — `typesetChartLabels`
- строка 2890 — `prepExpr`
- строка 2908 — `texToPlain`
- строка 2934 — `sceneReservedKey`
- строка 2938 — `freeSymbols`
- строка 2956 — `freeSymbolsUncached`
- строка 2984 — `sceneReserved`
- строка 3007 — `sceneExtraParams`
- строка 3013 — `paramValue`
- строка 3019 — `paramScope`
- строка 3029 — `scopeFor`
- строка 3036 — `evalWithParams`
- строка 3047 — `syncParams`
- строка 3103 — `buildParamChip`
- строка 3228 — `initSceneColorPickers`
- строка 3240 — `syncSceneColorPickers`
- строка 3248 — `syncAxisPlaceholders`
- строка 3263 — `titleAnchorPx`
- строка 3273 — `drawGraphTitle`
- строка 3312 — `editGraphTitleOnCanvas`
- строка 3357 — `normHex`
- строка 3379 — `paletteSix`
- строка 3387 — `closeColorMenu`
- строка 3401 — `onDocClosePick`
- строка 3405 — `onEscClosePick`
- строка 3421 — `paletteTwelve`
- строка 3422 — `makeColorPicker`
- строка 3534 — `autoCurveName`
- строка 3543 — `curveShortName`
- строка 3553 — `markCaption`
- строка 3562 — `drawMarks`
- строка 3661 — `snapTargets`
- строка 3669 — `snapTargetsAll`
- строка 3797 — `macroSnapTargets`
- строка 3816 — `consumerSnapTargets`
- строка 3845 — `ineqSnapTargets`
- строка 3859 — `mathSnapTargets`
- строка 3924 — `tradeSnapTargets`
- строка 3945 — `axisSnapAt`
- строка 3965 — `snapDistPx`
- строка 3986 — `snapPointAt`
- строка 4029 — `showSnapHint`
- строка 4048 — `armMark`
- строка 4061 — `cancelMarkDraft`
- строка 4101 — `resetDecor`
- строка 4193 — `_undoCopyChild`
- строка 4207 — `_undoCopy`
- строка 4227 — `pushUndo`
- строка 4238 — `undoLast`
- строка 4255 — `clearUndo`
- строка 4262 — `forgetSceneSnapshot`
- строка 4264 — `resetSceneMemory`
- строка 4275 — `saveSceneSnapshot`
- строка 4288 — `restoreSceneSnapshot`
- строка 4308 — `addMarkAt`
- строка 4345 — `colorDist`
- строка 4354 — `drawnStrokeColors`
- строка 4370 — `nextMarkColor`
- строка 4386 — `newMark`
- строка 4400 — `pendingMark`
- строка 4403 — `startMarkDraft`
- строка 4412 — `markSnapFn`
- строка 4422 — `renderMarkList`
- строка 4435 — `ensureAddMarkButton`
- строка 4445 — `buildMarkRow`

#### `calc2/static/calc2/70-scenes-math.js`

- строка 24 — `compileMath`
- строка 25 — `evalMathAt`
- строка 29 — `mathH`
- строка 30 — `dNum`
- строка 35 — `d2Num`
- строка 42 — `mathF`
- строка 50 — `rootsOf`
- строка 76 — `mathAnalyse`
- строка 106 — `mathTransformed`
- строка 123 — `mathScales`
- строка 137 — `drawPlaneAxes`
- строка 159 — `planeTicksX`
- строка 176 — `planeTicksY`
- строка 190 — `mathMark`
- строка 195 — `mathSubst`
- строка 201 — `mathTransformExpr`
- строка 218 — `mathLine`
- строка 242 — `resetLabelBoxes`
- строка 243 — `dodgeLabel`
- строка 255 — `mathDot`
- строка 299 — `makeRenamable`
- строка 342 — `editPointName`
- строка 366 — `editInlineLabel`
- строка 447 — `tangentLayout`
- строка 456 — `tangentPanelAt`
- строка 464 — `tanWin`
- строка 474 — `tanResetWindows`
- строка 479 — `tanScales`
- строка 487 — `drawMathTangent`
- строка 616 — `drawMathOptimum`
- строка 655 — `drawMathTransform`
- строка 676 — `labelCurveMath`
- строка 706 — `mmSlots`
- строка 707 — `mmGet`
- строка 710 — `mmSet`
- строка 715 — `mmLabel`
- строка 717 — `mmColor`
- строка 724 — `drawMathMinMax`
- строка 787 — `compileAB`
- строка 800 — `parseConstraint`
- строка 818 — `constraintPointsIn`
- строка 837 — `constraintPoints`
- строка 842 — `optimizeAlongCurve`
- строка 855 — `constraintFit`
- строка 873 — `drawMathConstraint`
- строка 936 — `drawLevelCurveOn`
- строка 950 — `mathOptimumReasoning`
- строка 987 — `updateMathPanel`
- строка 1126 — `redrawMath`
- строка 1165 — `setMathSub`
- строка 1188 — `setMathWindow`
- строка 1202 — `setMathX0`
- строка 1227 — `downloadBlob`
- строка 1236 — `exportBaseName`
- строка 1249 — `paperChartClone`
- строка 1276 — `exportNumbersLine`
- строка 1284 — `exportExtras`
- строка 1292 — `exportPNG`
- строка 1333 — `buildTex`
- строка 1342 — `afterFonts`
- строка 1347 — `exportTex`
- строка 1357 — `exportPDF`
- строка 1364 — `exportPDFSend`
- строка 1380 — `buildExportFields`
- строка 1401 — `refreshExportPreview`
- строка 1439 — `expValue`
- строка 1448 — `syncExportFormat`
- строка 1460 — `refreshExportSheet`
- строка 1468 — `wireExport`
- строка 1497 — `openExport`
- строка 1518 — `closeExport`
- строка 1538 — `updateGraphPanel`
- строка 1595 — `graphExplainNote`

#### `calc2/static/calc2/72-export-tex.js`

- строка 30 — `texPaperActive`
- строка 35 — `texPaperComputeSize`
- строка 1543 — `texEnterPaper`
- строка 1544 — `texCapture`
- строка 1545 — `texEmit`
- строка 1546 — `texInventory`

#### `calc2/static/calc2/80-ui.js`

- строка 7 — `showError`
- строка 11 — `hideError`
- строка 30 — `curveSrcForm`
- строка 51 — `addCurve`
- строка 91 — `addEmptyCurve`
- строка 110 — `updateCurveExpr`
- строка 142 — `setRole`
- строка 172 — `curveHumanName`
- строка 179 — `curvePrefix`
- строка 187 — `rememberStartCurves`
- строка 192 — `startExprOf`
- строка 197 — `curveIsPiecewise`
- строка 210 — `renderCurveList`
- строка 517 — `curveToSingleFormula`

#### `calc2/static/calc2/82-input.js`

- строка 11 — `texFallback`
- строка 18 — `mathToTex`
- строка 35 — `renderTex`
- строка 44 — `renderTexRaw`
- строка 53 — `onKatexReady`
- строка 83 — `pwCond`
- строка 92 — `pwRows`
- строка 113 — `pwPrefixOf`
- строка 118 — `pwFormula`
- строка 137 — `pwLatex`
- строка 159 — `pwVar`
- строка 184 — `casesToNarrow`
- строка 197 — `isNarrowCases`
- строка 201 — `casesUnwrapNarrow`
- строка 216 — `casesToMath`
- строка 247 — `condToMath`
- строка 258 — `renderPw`
- строка 329 — `pwSyncHead`
- строка 344 — `pwSetCount`
- строка 355 — `pwAddRow`
- строка 372 — `pwRemoveRow`
- строка 383 — `pwCheck`
- строка 407 — `pwAttachKeyboard`
- строка 429 — `pwPreview`
- строка 469 — `pwVarForField`
- строка 497 — `pwDefaultRows`
- строка 503 — `pwBalanced`
- строка 516 — `pwSplitTernary`
- строка 540 — `pwCondBounds`
- строка 561 — `pwParse`
- строка 597 — `pwSplitRows`
- строка 621 — `openPiecewise`
- строка 639 — `closePiecewise`
- строка 648 — `insertIntoFormula`
- строка 678 — `mathfieldClass`
- строка 682 — `onMathliveReady`
- строка 718 — `fieldProblem`
- строка 768 — `unknownTexCommand`
- строка 777 — `texGroup`
- строка 787 — `latexToMath`
- строка 933 — `isUndefinedTailNode`
- строка 938 — `unwrapParens`
- строка 949 — `pwCondTex`
- строка 968 — `condChainToCases`
- строка 990 — `mathToLatexField`
- строка 1012 — `upgradeFormulaField`
- строка 1059 — `fitFormulaField`
- строка 1110 — `fitFormulaFields`
- строка 1113 — `fitFormulaFieldsSoon`
- строка 1128 — `fieldOnScreen`
- строка 1140 — `flushMathfieldsSoon`
- строка 1146 — `flushMathfields`
- строка 1180 — `katexSafe`
- строка 1216 — `katexInto`
- строка 1231 — `placeholderTex`
- строка 1240 — `texSafeText`
- строка 1244 — `buildMathfield`
- строка 1418 — `insertIntoField`
- строка 1437 — `keyboardAdapter`
- строка 1439 — `insert`
- строка 1440 — `deleteBack`
- строка 1445 — `clear`
- строка 1449 — `piecewise`
- строка 1458 — `buildKeyboard`
- строка 1463 — `closeAllKeyboardsExcept`
- строка 1502 — `formulaInputError`
- строка 1525 — `markFormulaField`
- строка 1532 — `onFormulaInput`
- строка 1554 — `scheduleParamsSync`
- строка 1560 — `registerFormulaField`
- строка 1577 — `fieldActive`
- строка 1586 — `liveFormulaTexts`
- строка 1613 — `equipFormulaField`
- строка 1650 — `equipAllFormulaFields`
- строка 1654 — `attachFormulaHelp`
- строка 1844 — `makeEditableValue`
- строка 1949 — `makeToggle`
- строка 1991 — `segToToggle`
- строка 2023 — `closeAllSelectMenus`
- строка 2027 — `upgradeSelect`
- строка 2128 — `upgradeTextField`
- строка 2151 — `upgradeTextFieldsIn`

#### `calc2/static/calc2/84-picker.js`

- строка 8 — `loadScene`
- строка 147 — `closePicker`
- строка 169 — `openPicker`
- строка 328 — `baseScene`
- строка 337 — `applyCardScope`
- строка 415 — `blockSpec`
- строка 427 — `foldPickerGroups`
- строка 514 — `plural`
- строка 522 — `pickScene`

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
- строка 246 — `syncAnalyticsPanel`
- строка 330 — `sectionIcon`
- строка 341 — `cardifySections`
- строка 433 — `collapseCards`
- строка 451 — `syncLabelSizeSeg`
- строка 462 — `openSection`
- строка 499 — `cardWithFormula`
- строка 512 — `syncFirstCard`
- строка 531 — `wireScene`
- строка 700 — `resetCurrentScene`
- строка 710 — `setWrenchOpen`
- строка 720 — `applyViewBounds`
- строка 747 — `quadWindow`
- строка 752 — `quadSameWindow`
- строка 771 — `offQuadShownPoints`
- строка 801 — `fitWindowToOffQuad`
- строка 823 — `setFirstQuad`
- строка 873 — `setGridMode`
- строка 891 — `hintTip`
- строка 918 — `fitTipMath`
- строка 936 — `showHintTip`
- строка 993 — `hideHintTip`
- строка 1018 — `tipText`
- строка 1047 — `tipTex`
- строка 1057 — `tipName`
- строка 1074 — `tipExpr`
- строка 1084 — `tipPlain`
- строка 1113 — `ffEsc`
- строка 1123 — `ffLatexOf`
- строка 1145 — `finalFunctionHtml`
- строка 1170 — `ffParseCases`
- строка 1192 — `ffCondCompact`
- строка 1216 — `ffMathHtml`
- строка 1240 — `ffKatexW`
- строка 1256 — `ffFitCases`
- строка 1343 — `fitFinalMath`
- строка 1372 — `ffCopyText`
- строка 1380 — `ffCopyFallback`
- строка 1392 — `wireFinalCopy`
- строка 1425 — `ffOpenExpand`
- строка 1446 — `ffCloseExpand`
- строка 1458 — `setFinalFunctions`
- строка 1476 — `refitFinalMathSoon`
- строка 1504 — `markNotationsIn`
- строка 1536 — `paintNotation`
- строка 1546 — `showTipFor`
- строка 1552 — `wireTips`
- строка 1591 — `syncTipLabels`
- строка 1604 — `hintAnchor`
- строка 1685 — `fitPanelMath`
- строка 1715 — `syncHintDots`
- строка 1726 — `hintsToDots`
- строка 1764 — `wireHintButtons`
- строка 1806 — `wireWrench`
- строка 1905 — `fillPrintBlocks`
- строка 1935 — `setPrintViewBox`

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
- строка 276 — `editEqValue`
- строка 343 — `centerBandOn`
- строка 347 — `pullIntoBand`
- строка 351 — `attachBoundsEditor`
- строка 433 — `refreshRegulators`
- строка 444 — `makePchip`
- строка 472 — `curveShiftBase`
- строка 479 — `buildPultCurveChips`
- строка 565 — `syncPultCurveValues`
- строка 588 — `capturePultHome`
- строка 595 — `capturePultHomes`
- строка 600 — `returnPultHome`
- строка 612 — `syncPultRegulators`
- строка 641 — `upgradeRegulator`
- строка 805 — `shortRegulatorName`
- строка 829 — `ppfLinearFormula`
- строка 835 — `ppfInterceptsOf`
- строка 843 — `ppfSetSingle`
- строка 851 — `ppfSetSum`
- строка 871 — `addPultXChip`
- строка 898 — `buildPultExtra`
- строка 930 — `ineqParseIncomes`
- строка 933 — `ineqMasterRebase`
- строка 938 — `ineqMasterScale`
- строка 956 — `ineqMasterApply`
- строка 968 — `ineqMasterDetach`
- строка 973 — `buildIneqMasterChip`
- строка 985 — `showPult`
- строка 1012 — `updatePult`
- строка 1044 — `liveFormula`
- строка 1054 — `wireControls`

#### `calc2/static/calc2/89-model-state.js`

- строка 37 — `plainCopy`
- строка 62 — `formNodes`
- строка 67 — `captureForm`
- строка 92 — `applyForm`
- строка 136 — `captureStatePlain`
- строка 145 — `applyStatePlain`
- строка 152 — `rerenderModelLists`
- строка 170 — `forceRebuildAfterApply`
- строка 176 — `syncUiFromState`
- строка 183 — `capturePristine`
- строка 194 — `restorePristine`
- строка 214 — `captureMemory`
- строка 219 — `applyMemory`
- строка 242 — `serializeCurves`
- строка 255 — `rebuildCurves`
- строка 275 — `modelKeyOf`
- строка 280 — `collectModelState`
- строка 300 — `applyModelState`

#### `calc2/static/calc2/90-explain.js`

- строка 375 — `sceneExplainHtml`

#### `calc2/static/calc2/91-session.js`

- строка 43 — `histOf`
- строка 52 — `histSig`
- строка 62 — `captureOpenUi`
- строка 68 — `restoreOpenUi`
- строка 85 — `applyKeepView`
- строка 97 — `historyBaseline`
- строка 106 — `historyCheck`
- строка 133 — `historyAfterRedraw`
- строка 141 — `historyMark`
- строка 146 — `historyUndo`
- строка 159 — `historyRedo`
- строка 171 — `historyCan`
- строка 175 — `historyClearAll`
- строка 177 — `notifyHistory`
- строка 183 — `histLabelOf`
- строка 199 — `storeGet`
- строка 200 — `storeSet`
- строка 205 — `compactModelState`
- строка 219 — `expandModelState`
- строка 228 — `autosaveModel`
- строка 242 — `forgetAutosaves`
- строка 252 — `savedModel`
- строка 258 — `recentModels`
- строка 264 — `writeModelToUrl`
- строка 272 — `dropShareHash`
- строка 281 — `b64urlEncode`
- строка 285 — `b64urlDecode`
- строка 322 — `openModelByUser`
- строка 342 — `restoreOnLoad`
- строка 372 — `viewDefaults`
- строка 408 — `resetModelWithUndo`

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

#### `calc2/static/calc2/93-shell.js`

- строка 11 — `modelBlockOf`
- строка 16 — `syncModelHead`
- строка 28 — `syncZoomLevel`
- строка 44 — `setFocusMode`
- строка 54 — `afterColumnShown`
- строка 63 — `syncToolSeg`
- строка 70 — `setTool`
- строка 83 — `wireShell`
- строка 158 — `phMoreLayout`
- строка 192 — `wirePhoneMore`

#### `calc2/static/calc2/94-answer.js`

- строка 88 — `heroLabel`
- строка 104 — `notationTex`
- строка 116 — `plainText`
- строка 122 — `statRows`
- строка 126 — `txRow`
- строка 148 — `answerSignature`
- строка 154 — `scheduleAnswer`
- строка 160 — `buildAnswer`
- строка 269 — `buildBurden`
- строка 308 — `buildStatus`
- строка 333 — `buildExplainAccordion`

#### `calc2/static/calc2/95-picker-screen.js`

- строка 24 — `pkNorm`
- строка 27 — `pickerModels`
- строка 39 — `pickerScore`
- строка 55 — `whenText`
- строка 65 — `buildPickerScreen`
- строка 215 — `pickerFilter`
- строка 278 — `renderPickerContinue`
- строка 326 — `buildSwitcher`
- строка 348 — `renderSwitcher`
- строка 386 — `openSwitcher`

#### `calc2/static/calc2/96-self.js`

- строка 20 — `selfNum`
- строка 25 — `checkGuess`
- строка 32 — `selfText`
- строка 39 — `selfKey`
- строка 41 — `setSelfMode`
- строка 54 — `selfCell`
- строка 102 — `selfAfterAnswer`
- строка 118 — `applySelf`
- строка 139 — `selfCanvas`
- строка 187 — `selfMaskText`
- строка 194 — `selfMasked`
- строка 196 — `wireSelf`

#### `calc2/static/calc2/99-boot.js`

- строка 13 — `lockNumberFields`
- строка 42 — `init`

**Итого функций в индексе: 1203.**

<!-- AUTO:END -->
