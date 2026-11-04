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

*Автоматически собрано командой `manage.py calc2_map`. Дата: 2026-11-03. HEAD: `15bd4a4b`. Не редактировать руками — вся эта часть файла, от отметки начала автосекции и до отметки её конца, перезаписывается заново при каждом запуске команды.*

### Файлы (маршрут → представление → шаблон → статика)

| Путь | Строк | КБ | Тип |
|---|---:|---:|---|
| `calc2/urls.py` | 19 | 0.6 | python |
| `calc2/views.py` | 224 | 13.4 | python |
| `calc2/templates/calc2/calc2.html` | 2338 | 188.8 | шаблон |
| `calc2/static/calc2/calc2.css` | 4397 | 332.5 | CSS |
| `calc2/static/calc2/previews.json` | 46 | 33.7 | json |
| `calc2/static/calc2/00-config.js` | 578 | 50.2 | JS |
| `calc2/static/calc2/10-math-core.js` | 1166 | 76.6 | JS |
| `calc2/static/calc2/12-numbers.js` | 239 | 12.1 | JS |
| `calc2/static/calc2/20-plane.js` | 999 | 68.2 | JS |
| `calc2/static/calc2/30-curves.js` | 1517 | 110.5 | JS |
| `calc2/static/calc2/40-scenes-market.js` | 3895 | 281.7 | JS |
| `calc2/static/calc2/41-market-policies.js` | 260 | 17.4 | JS |
| `calc2/static/calc2/42-scenes-mono.js` | 2090 | 154.6 | JS |
| `calc2/static/calc2/43-discrimination.js` | 182 | 9.9 | JS |
| `calc2/static/calc2/44-scenes-firm.js` | 1068 | 69.2 | JS |
| `calc2/static/calc2/45-plants.js` | 300 | 23.2 | JS |
| `calc2/static/calc2/46-firm-supply.js` | 312 | 32.1 | JS |
| `calc2/static/calc2/47-firm-market.js` | 199 | 19.6 | JS |
| `calc2/static/calc2/46-scenes-labor.js` | 900 | 68.8 | JS |
| `calc2/static/calc2/48-scenes-consumer.js` | 279 | 18.2 | JS |
| `calc2/static/calc2/49-trade-policy.js` | 262 | 27.3 | JS |
| `calc2/static/calc2/50-scenes-macro.js` | 514 | 35.1 | JS |
| `calc2/static/calc2/51-islm.js` | 112 | 14.8 | JS |
| `calc2/static/calc2/52-modes.js` | 1007 | 68.8 | JS |
| `calc2/static/calc2/53-adas.js` | 130 | 15.9 | JS |
| `calc2/static/calc2/54-scenes-ppf.js` | 3269 | 211.1 | JS |
| `calc2/static/calc2/55-big-trade.js` | 170 | 14.8 | JS |
| `calc2/static/calc2/56-scenes-inequality.js` | 491 | 34.7 | JS |
| `calc2/static/calc2/57-distributions.js` | 161 | 18.6 | JS |
| `calc2/static/calc2/60-overlays.js` | 5025 | 320.9 | JS |
| `calc2/static/calc2/70-scenes-math.js` | 2179 | 141.2 | JS |
| `calc2/static/calc2/72-export-tex.js` | 1669 | 128.6 | JS |
| `calc2/static/calc2/80-ui.js` | 856 | 54.3 | JS |
| `calc2/static/calc2/82-input.js` | 2366 | 140.9 | JS |
| `calc2/static/calc2/84-picker.js` | 591 | 45.1 | JS |
| `calc2/static/calc2/86-workspace.js` | 2159 | 141.1 | JS |
| `calc2/static/calc2/88-params.js` | 2026 | 139.6 | JS |
| `calc2/static/calc2/89-model-state.js` | 374 | 24.8 | JS |
| `calc2/static/calc2/90-explain.js` | 389 | 69.3 | JS |
| `calc2/static/calc2/91-session.js` | 502 | 26.6 | JS |
| `calc2/static/calc2/92-ui-kit.js` | 1332 | 92.3 | JS |
| `calc2/static/calc2/93-shell.js` | 284 | 17.4 | JS |
| `calc2/static/calc2/94-answer.js` | 1093 | 72.1 | JS |
| `calc2/static/calc2/95-picker-screen.js` | 470 | 26.7 | JS |
| `calc2/static/calc2/96-self.js` | 353 | 23.3 | JS |
| `calc2/static/calc2/99-boot.js` | 112 | 9.5 | JS |

**Итого: 46 файлов, 48904 строк, 3496.2 КБ.**

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
- строка 293 — `panelPanBy`
- строка 308 — `gesturePanelId`
- строка 336 — `isEconScene`
- строка 342 — `econLo`
- строка 346 — `quadLo`
- строка 369 — `quadPrice`
- строка 379 — `toPx`
- строка 380 — `toData`
- строка 393 — `fmtSum`
- строка 398 — `shownDiff`
- строка 399 — `fmtDiff`
- строка 406 — `fmt`
- строка 414 — `fmtInput`
- строка 423 — `niceTickStep`
- строка 435 — `axisTicks`
- строка 448 — `xTicks`
- строка 449 — `yTicks`
- строка 452 — `addDefs`
- строка 519 — `drawGrid`
- строка 570 — `extraTickX`
- строка 581 — `extraTickY`
- строка 621 — `dropTickAt`
- строка 648 — `coordValue`
- строка 672 — `coordSplit`
- строка 676 — `coordAlreadyAt`
- строка 722 — `resetDrawnKeyPoints`
- строка 725 — `panelOfGlobalScales`
- строка 729 — `kpNode`
- строка 745 — `collectDashes`
- строка 762 — `dashEndsNear`
- строка 774 — `flushDrawnKeyPoints`
- строка 822 — `noteAxisX`
- строка 827 — `noteAxisY`
- строка 834 — `kpName`
- строка 839 — `axisValueX`
- строка 866 — `axisValueY`
- строка 891 — `axisValueText`
- строка 908 — `drawAxes`

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
- строка 549 — `qtyAtPrice`
- строка 559 — `openQuotaName`
- строка 563 — `recomputeOpenEconomy`
- строка 656 — `drawOpenAreas`
- строка 705 — `drawOpenLines`
- строка 753 — `attachOpenPwDrag`
- строка 761 — `setOpenPw`
- строка 774 — `setOpenTool`
- строка 790 — `syncOpenQuotaLabel`
- строка 796 — `updateOpenPanel`
- строка 856 — `drawEquilibrium`
- строка 893 — `drawOffQuadIntersection`
- строка 932 — `offQuadExplainHtml`
- строка 958 — `pctFormExplainHtml`
- строка 996 — `mathTspans`
- строка 1036 — `hasMathMarkup`
- строка 1060 — `markNotationTspan`
- строка 1077 — `mixedNotationRe`
- строка 1085 — `mixedMathTspans`
- строка 1129 — `qtyTspans`
- строка 1166 — `qtyGreekChar`
- строка 1204 — `texToCanvasText`
- строка 1213 — `renderLabelText`
- строка 1234 — `haloText`
- строка 1267 — `pointName`
- строка 1293 — `yWageLabel`
- строка 1298 — `yWageValue`
- строка 1321 — `isMonopolyScene`
- строка 1329 — `eqSectionTitle`
- строка 1346 — `updateEqSectionTitle`
- строка 1363 — `interventionKeyValues`
- строка 1429 — `countCrossings`
- строка 1438 — `updateInfoPanel`
- строка 1547 — `sumSceneOn`
- строка 1550 — `sumGroupsOf`
- строка 1557 — `sumGroupQty`
- строка 1570 — `sumChokePrice`
- строка 1596 — `sumPriceTop`
- строка 1617 — `sumLinearRecord`
- строка 1719 — `integrateBroken`
- строка 1730 — `curveBreaks`
- строка 1741 — `quadBreaks`
- строка 1757 — `sumSegExpr`
- строка 1774 — `sumPolyline`
- строка 1802 — `sumRebuildSide`
- строка 1853 — `sumSignature`
- строка 1873 — `sumRebuild`
- строка 1893 — `sumAnalyticsKey`
- строка 1911 — `sumGroupName`
- строка 1934 — `sumTagOf`
- строка 1941 — `sumShortTag`
- строка 1970 — `sumGroupColor`
- строка 1975 — `sumStartExpr`
- строка 1983 — `sumReorder`
- строка 1988 — `sumAddGroup`
- строка 2001 — `sumBuildScene`
- строка 2029 — `sumSetCount`
- строка 2048 — `syncSumUi`
- строка 2062 — `sumGroupStats`
- строка 2108 — `sumFinalRecords`
- строка 2126 — `updateSumPanel`
- строка 2187 — `drawAreas`
- строка 2217 — `beforeInterventionNote`
- строка 2226 — `updateAreasPanel`
- строка 2267 — `intervOnBuyer`
- строка 2276 — `drawShiftedSupply`
- строка 2332 — `taxPivotQ`
- строка 2363 — `taxPivotPoint`
- строка 2373 — `drawTaxPivot`
- строка 2408 — `drawTaxAreas`
- строка 2448 — `drawTaxPoints`
- строка 2502 — `attachTaxDrag`
- строка 2523 — `setTax`
- строка 2641 — `taxFormKey`
- строка 2649 — `pctForm`
- строка 2657 — `syncTaxKind`
- строка 2662 — `applyIntervCascade`
- строка 2736 — `setTaxForm`
- строка 2754 — `setType`
- строка 2805 — `rateLetter`
- строка 2809 — `rateUnit`
- строка 2831 — `modelPriceTop`
- строка 2842 — `unitRateMax`
- строка 2852 — `applyPriceRegBounds`
- строка 2861 — `applyTaxRateBounds`
- строка 2896 — `syncQuotaHint`
- строка 2912 — `syncPcHint`
- строка 2920 — `markCurrentIntervHint`
- строка 2929 — `intervHintKey`
- строка 2939 — `intervHintHtml`
- строка 2961 — `syncTaxHint`
- строка 2999 — `setTaxKind`
- строка 3009 — `qpAfter`
- строка 3020 — `updateTaxPanel`
- строка 3156 — `setTaxSide`
- строка 3167 — `setTaxSideButtons`
- строка 3180 — `drawElasticityZones`
- строка 3198 — `drawElasticityPoint`
- строка 3228 — `attachElastDrag`
- строка 3236 — `drawElasticityPointS`
- строка 3256 — `attachElastDragS`
- строка 3264 — `updateElasticityPanel`
- строка 3328 — `drawExtAreas`
- строка 3342 — `drawExtCurves`
- строка 3369 — `drawExtPoints`
- строка 3403 — `drawExtScenario`
- строка 3412 — `updateExtPanel`
- строка 3466 — `setExtSign`
- строка 3475 — `syncSocialFields`
- строка 3503 — `syncExtHint`
- строка 3514 — `socialDefaultExpr`
- строка 3520 — `recompileSocial`
- строка 3542 — `setPRegFields`
- строка 3551 — `setPReg`
- строка 3560 — `drawPcAreas`
- строка 3587 — `drawPriceControl`
- строка 3636 — `attachPcDrag`
- строка 3645 — `updatePcPanel`
- строка 3689 — `setQuotaFields`
- строка 3701 — `setQuota`
- строка 3708 — `setQuotaPos`
- строка 3716 — `setQuotaPrice`
- строка 3723 — `updateQuotaPriceLabel`
- строка 3744 — `drawQuotaAreas`
- строка 3771 — `drawQuotaLines`
- строка 3816 — `attachQuotaDrag`
- строка 3829 — `updateQuotaPanel`
- строка 3876 — `drawGhost`

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
- строка 178 — `competitiveOutput`
- строка 189 — `monoDwlAt`
- строка 197 — `drawMonopolyAreas`
- строка 236 — `drawMonopoly`
- строка 271 — `mcDragCurve`
- строка 276 — `mcDragStep`
- строка 280 — `drawMcDragHandle`
- строка 321 — `drawMonopolyPoints`
- строка 358 — `updateMonoPanel`
- строка 408 — `setMarket`
- строка 443 — `monopolyCeiling`
- строка 494 — `drawMonoCeilingAreas`
- строка 513 — `drawMonoKinkedMR`
- строка 530 — `drawMonoCeilingPoints`
- строка 562 — `drawMonoCeilingLine`
- строка 586 — `monopolyTax`
- строка 609 — `monoBudgetFloor`
- строка 618 — `monopolyFloor`
- строка 660 — `monopolyQuota`
- строка 688 — `drawMonoQuotaAreas`
- строка 710 — `drawMonoQuotaPoints`
- строка 732 — `drawMonoQuotaLine`
- строка 758 — `naturalATC`
- строка 770 — `naturalATCFormula`
- строка 789 — `findRootLast`
- строка 804 — `recomputeNatural`
- строка 833 — `drawNaturalAreas`
- строка 848 — `drawNaturalCurves`
- строка 871 — `drawNaturalPoints`
- строка 911 — `drawNaturalFull`
- строка 919 — `updateNaturalPanel`
- строка 957 — `drawMonoTaxAreas`
- строка 993 — `drawMonoTaxShiftedMC`
- строка 1011 — `drawMonoTaxPoints`
- строка 1032 — `drawMonoFloorAreas`
- строка 1047 — `drawMonoFloorPoints`
- строка 1067 — `drawMonoFloorLine`
- строка 1082 — `updateMonoInterventionPanel`
- строка 1219 — `makeCurve`
- строка 1235 — `segExpr`
- строка 1242 — `kinkedDemandExpr`
- строка 1253 — `drawDiscr1`
- строка 1286 — `updateDiscr1Panel`
- строка 1312 — `allocateMR`
- строка 1338 — `recomputeDiscr3`
- строка 1397 — `drawMiniMarket`
- строка 1504 — `redrawDiscr3`
- строка 1547 — `drawMonoExport`
- строка 1672 — `updateDiscr3Panel`
- строка 1758 — `applyD3WorldLabels`
- строка 1781 — `buildKinkedDemand`
- строка 1801 — `sumDemandCurves`
- строка 1838 — `recomputeKinked`
- строка 1885 — `drawKinkedFull`
- строка 1974 — `updateKinkPanel`
- строка 2015 — `applyMonoVisibility`
- строка 2036 — `ensureMonopolyCurves`
- строка 2047 — `fillIfEmpty`
- строка 2050 — `ensureD3Fields`
- строка 2055 — `ensureKinkFields`
- строка 2061 — `ensureMonopolyPreset`
- строка 2068 — `setMonoMode`
- строка 2079 — `setKinkInput`

#### `calc2/static/calc2/43-discrimination.js`

- строка 3 — `d3CostMode`
- строка 7 — `discriminationMR`
- строка 17 — `discriminationRoot`
- строка 26 — `discriminationSpan`
- строка 34 — `discriminationCost`
- строка 47 — `discriminationComparison`
- строка 82 — `discriminationPriceComparison`
- строка 156 — `discriminationTable`
- строка 175 — `discriminationGroupMC`

#### `calc2/static/calc2/44-scenes-firm.js`

- строка 16 — `costScanTop`
- строка 21 — `evalTC`
- строка 30 — `evalPart`
- строка 36 — `hasPart`
- строка 41 — `costsFC`
- строка 46 — `costTC`
- строка 56 — `costVC`
- строка 62 — `costATC`
- строка 67 — `costAVC`
- строка 72 — `costAFC`
- строка 81 — `costMC`
- строка 89 — `costHas`
- строка 114 — `minOf`
- строка 136 — `realMin`
- строка 144 — `shutdownPrice`
- строка 153 — `computeFCfromTC`
- строка 173 — `costsSignature`
- строка 178 — `paramsSignature`
- строка 184 — `recomputeCosts`
- строка 230 — `checkCostsConsistency`
- строка 257 — `costPoints`
- строка 293 — `costExprs`
- строка 324 — `drawCostCurves`
- строка 384 — `noMinNote`
- строка 394 — `updateCostsPanel`
- строка 434 — `redrawCosts`
- строка 471 — `recomputeLongRun`
- строка 541 — `drawLongRunArea`
- строка 549 — `fillLongRunArea`
- строка 573 — `drawLongRunMarks`
- строка 578 — `fillLongRunMarks`
- строка 610 — `drawLongRunHandle`
- строка 621 — `setLrPrice`
- строка 629 — `syncLrPriceFields`
- строка 647 — `beginLrDrag`
- строка 649 — `dragLrPrice`
- строка 664 — `endLrDrag`
- строка 671 — `updateLongRunPanel`
- строка 714 — `prodEval`
- строка 724 — `prodDerivative`
- строка 738 — `prodMP`
- строка 745 — `prodAP`
- строка 753 — `maxOf`
- строка 780 — `realMax`
- строка 782 — `recomputeProduction`
- строка 801 — `redrawProduction`
- строка 919 — `noMaxNote`
- строка 928 — `updateProdPanel`
- строка 952 — `recomputeIsoquant`
- строка 963 — `redrawIsoquant`
- строка 979 — `updateIsoPanel`
- строка 1008 — `setPlantsView`
- строка 1015 — `setPlantsQ`
- строка 1026 — `setCostsInputMode`
- строка 1034 — `syncCostsInputMode`
- строка 1048 — `setCostsSub`

#### `calc2/static/calc2/45-plants.js`

- строка 4 — `plantsPolynomial`
- строка 24 — `plantsValue`
- строка 25 — `plantsQuadraticRoots`
- строка 30 — `plantsCandidate`
- строка 42 — `plantsEnvelope`
- строка 67 — `plantsConvolve`
- строка 78 — `plantsExactPieces`
- строка 88 — `plantsExactAt`
- строка 107 — `plantInputRows`
- строка 112 — `setPlantInputRows`
- строка 116 — `addPlant`
- строка 117 — `removePlant`
- строка 118 — `plantCost`
- строка 119 — `plantMarginal`
- строка 120 — `plantsCompile`
- строка 134 — `plantsGrid`
- строка 164 — `plantsIntegral`
- строка 167 — `plantsAt`
- строка 176 — `recomputePlants`
- строка 197 — `plantsShownAt`
- строка 198 — `plantsExpr`
- строка 205 — `redrawPlants`
- строка 239 — `plantsFinalRecord`
- строка 253 — `updatePlantsPanel`
- строка 276 — `renderPlantRows`

#### `calc2/static/calc2/46-firm-supply.js`

- строка 3 — `firmPolynomial`
- строка 21 — `firmPolyAt`
- строка 23 — `firmPolyExpr`
- строка 27 — `firmPolyRoots`
- строка 36 — `firmPolynomialPieces`
- строка 56 — `firmTax`
- строка 63 — `firmSupplyBuild`
- строка 112 — `firmZeroRevenue`
- строка 119 — `firmCandidateAt`
- строка 127 — `firmSupplyAt`
- строка 137 — `firmSupplySchedule`
- строка 163 — `firmShutdown`
- строка 179 — `firmSupplyNumeric`
- строка 211 — `firmSupplyConfig`
- строка 213 — `recomputeFirmSupply`
- строка 221 — `recomputeFirmSupplyPrice`
- строка 231 — `firmOutputText`
- строка 237 — `firmFinalRecord`
- строка 256 — `updateFirmSupplyPanel`
- строка 270 — `drawFirmSupply`
- строка 289 — `firmCostExpressions`
- строка 293 — `renderFirmSupplyControls`

#### `calc2/static/calc2/47-firm-market.js`

- строка 2 — `firmMarketBisect`
- строка 5 — `firmMarketDemand`
- строка 20 — `firmMarketContains`
- строка 26 — `firmMarketSolve`
- строка 93 — `renderFirmMarketControls`
- строка 107 — `firmMarketScaledRecord`
- строка 113 — `updateFirmMarketPanel`
- строка 133 — `firmMarketPanel`
- строка 157 — `firmMarketDrawSupply`
- строка 171 — `redrawFirmMarket`

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

#### `calc2/static/calc2/49-trade-policy.js`

- строка 3 — `tradeChannels`
- строка 23 — `tradeBuyer`
- строка 24 — `tradeSeller`
- строка 25 — `tradeCurve`
- строка 41 — `tradeAutark`
- строка 48 — `tradeCountry`
- строка 85 — `tradeMono`
- строка 118 — `tradeMonoResult`
- строка 123 — `tradeGolden`
- строка 127 — `tradeMaxNumeric`
- строка 133 — `tradeMonoNumeric`
- строка 147 — `tradePolicyState`
- строка 152 — `setTradePolicy`
- строка 161 — `tradeControlsHTML`
- строка 170 — `renderTradePolicyControls`
- строка 200 — `recomputeTradeOpen`
- строка 208 — `recomputeTradeMono`
- строка 214 — `tradeAnswerRows`
- строка 220 — `tradeHero`
- строка 221 — `updateTradePanel`
- строка 230 — `drawTradeCountryAreas`
- строка 238 — `drawTradeCountryLines`
- строка 245 — `drawTradeMono`

#### `calc2/static/calc2/50-scenes-macro.js`

- строка 20 — `compileVar`
- строка 31 — `evalVar`
- строка 40 — `macroCurveY`
- строка 49 — `macroCurveInv`
- строка 78 — `macroCurveAny`
- строка 111 — `lafferSolution`
- строка 154 — `macroP`
- строка 160 — `recomputeMacro`
- строка 285 — `drawMacroCurve`
- строка 322 — `redrawMacro`
- строка 408 — `drawEquilibriumAt`
- строка 419 — `updateMacroPanel`
- строка 500 — `setMacroModel`

#### `calc2/static/calc2/51-islm.js`

- строка 2 — `islmDefaults`
- строка 3 — `islmScalar`
- строка 4 — `macroSimplify`
- строка 5 — `islmSubstitute`
- строка 6 — `islmAffine`
- строка 9 — `islmRoots`
- строка 16 — `islmSolve`
- строка 51 — `islmScenario`
- строка 74 — `recomputeIslmParameters`
- строка 81 — `islmPanelHtml`
- строка 91 — `setIslmInput`
- строка 92 — `islmAddShock`
- строка 93 — `renderIslmControls`

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

#### `calc2/static/calc2/53-adas.js`

- строка 2 — `adasValue`
- строка 3 — `adasOneRoot`
- строка 4 — `adasCompile`
- строка 5 — `adasInverse`
- строка 12 — `adasCurve`
- строка 21 — `adasIntersection`
- строка 28 — `adasDemand`
- строка 32 — `adasLabor`
- строка 55 — `adasScenario`
- строка 86 — `recomputeAdasAdvanced`
- строка 93 — `adasPanelHtml`
- строка 100 — `adasAdvanced`
- строка 101 — `setAdasMode`
- строка 102 — `adasAddShock`
- строка 103 — `renderAdasControls`

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
- строка 2923 — `recomputeTradeB`
- строка 3016 — `tradeCpfPoints`
- строка 3034 — `tradeCpfMark`
- строка 3053 — `tradeBPanels`
- строка 3074 — `drawTradeB`
- строка 3147 — `drawTradeBMarks`
- строка 3150 — `tbName`
- строка 3156 — `updateTradeBPanel`
- строка 3215 — `syncTbPriceUI`
- строка 3228 — `redrawTradeB`
- строка 3243 — `setTradeScenario`
- строка 3255 — `setPpfSub`

#### `calc2/static/calc2/55-big-trade.js`

- строка 3 — `bigTradeDefaults`
- строка 4 — `bigTradePrepare`
- строка 9 — `bigTradeAt`
- строка 10 — `bigTradeEquilibrium`
- строка 43 — `bigTradeSolve`
- строка 55 — `renderBigTradeControls`
- строка 67 — `bigTradeRows`
- строка 79 — `bigTradeHero`
- строка 84 — `updateBigTradePanel`
- строка 92 — `bigTradeSyncPriceWindow`
- строка 97 — `bigTradePanelBand`
- строка 102 — `bigTradeCountryPlot`
- строка 128 — `bigTradeWorldPlot`
- строка 146 — `redrawBigTrade`
- строка 166 — `bigTradeSmallLegend`

#### `calc2/static/calc2/56-scenes-inequality.js`

- строка 11 — `parseNumberList`
- строка 18 — `inequalitySharesFromInput`
- строка 25 — `lorenzFromShares`
- строка 34 — `lorenzFromFormula`
- строка 37 — `lorenzAreaUnder`
- строка 48 — `lorenzAt`
- строка 62 — `inequalityStats`
- строка 83 — `inequalityP90P10`
- строка 98 — `ineqRedistShares`
- строка 111 — `applyRedistribution`
- строка 127 — `recomputeInequality`
- строка 156 — `drawInequalityDiagonal`
- строка 165 — `drawInequalityCaptions`
- строка 183 — `ineqDrawData`
- строка 186 — `ineqPercentExpr`
- строка 189 — `lorenzPlotExpr`
- строка 192 — `lorenzMark`
- строка 199 — `lorenzMarkArea`
- строка 209 — `drawInequalityAreas`
- строка 220 — `drawLorenzCurve`
- строка 234 — `drawRobinHood`
- строка 250 — `drawLorenzNodes`
- строка 268 — `ineqDragNode`
- строка 286 — `ineqDragIncome`
- строка 303 — `attachLorenzNodeDrag`
- строка 322 — `drawRedistArrow`
- строка 337 — `updateIneqSortNote`
- строка 345 — `updateInequalityPanel`
- строка 386 — `redrawInequality`
- строка 437 — `defaultGroupShares`
- строка 444 — `setIneqInput`
- строка 461 — `setIneqAlpha`
- строка 468 — `setIneqGroupN`
- строка 480 — `setIneqRedistTool`
- строка 491 — `renderIneqGroupsTable`

#### `calc2/static/calc2/57-distributions.js`

- строка 2 — `ineqNumber`
- строка 5 — `ineqShares`
- строка 13 — `ineqWeightedPoints`
- строка 16 — `ineqSimplify`
- строка 17 — `ineqPieceExpr`
- строка 21 — `ineqLinePieces`
- строка 24 — `ineqIntegrate`
- строка 27 — `ineqStatsFor`
- строка 36 — `ineqHasAlpha`
- строка 37 — `ineqAlphaActive`
- строка 38 — `ineqFormulaExpr`
- строка 42 — `ineqDistribution`
- строка 71 — `ineqUnion`
- строка 101 — `ineqFirstConfig`
- строка 103 — `ineqCalculate`
- строка 111 — `ineqGroupConfig`
- строка 112 — `ineqWriteGroups`
- строка 113 — `ineqSetGroupMode`
- строка 119 — `ineqAddGroup`
- строка 125 — `ineqRemoveGroup`
- строка 126 — `ineqRenderRows`
- строка 138 — `ineqAddCountry`
- строка 142 — `renderIneqCountryControls`

#### `calc2/static/calc2/60-overlays.js`

- строка 10 — `redrawAll`
- строка 95 — `redrawScene`
- строка 243 — `redrawGraphMode`
- строка 255 — `renderMmRows`
- строка 301 — `graphRowsBox`
- строка 304 — `renderGraphRows`
- строка 323 — `graphError`
- строка 330 — `buildGraphRow`
- строка 412 — `equipGraphRows`
- строка 420 — `graphRowInput`
- строка 465 — `mainScales`
- строка 476 — `drawOverlays`
- строка 584 — `guardedPanelIds`
- строка 588 — `guardPanelBoxes`
- строка 624 — `panelsChangedSinceLastPass`
- строка 629 — `markPanelsChanged`
- строка 632 — `flushPendingPanelClears`
- строка 641 — `refreshAnalyticsPanel`
- строка 669 — `typesetStats`
- строка 723 — `addStatSign`
- строка 737 — `statToTex`
- строка 775 — `katexVisibleText`
- строка 779 — `restatWide`
- строка 825 — `statInkWidth`
- строка 833 — `statTooWide`
- строка 842 — `statPieces`
- строка 877 — `texAbbrev`
- строка 883 — `renderMathIn`
- строка 926 — `areaKey`
- строка 931 — `subDigits`
- строка 936 — `applyAreaColors`
- строка 946 — `currentAreas`
- строка 964 — `areaOfPathEl`
- строка 1026 — `areaShort`
- строка 1035 — `drawLegend`
- строка 1099 — `floatRects`
- строка 1119 — `legendCorner`
- строка 1196 — `viewWindow`
- строка 1208 — `axisWords`
- строка 1214 — `crossPoints`
- строка 1316 — `invalidateKeyTargets`
- строка 1319 — `kinksOf`
- строка 1367 — `keyTargets`
- строка 1542 — `snapVertexAt`
- строка 1574 — `markPanelId`
- строка 1594 — `armedPanelId`
- строка 1600 — `drawCrossPoints`
- строка 1749 — `armCurve`
- строка 1755 — `disarmCurve`
- строка 1763 — `keyPointLit`
- строка 1776 — `drawCurveHits`
- строка 1814 — `pinKeyPoint`
- строка 1834 — `hoverLabel`
- строка 1845 — `drawRoller`
- строка 1866 — `rollerTargetAt`
- строка 1896 — `rollerClampX`
- строка 1915 — `rollerMove`
- строка 1931 — `showRollTip`
- строка 1954 — `hideRollTip`
- строка 1963 — `rollerOff`
- строка 1974 — `curveRightEdge`
- строка 1999 — `axisXLetter`
- строка 2009 — `axisLetter`
- строка 2022 — `armVerts`
- строка 2064 — `markServiceNodes`
- строка 2081 — `syncCanvasMode`
- строка 2103 — `leaveCanvasMode`
- строка 2109 — `finishCanvasMode`
- строка 2114 — `addAreaVert`
- строка 2127 — `vertPanels`
- строка 2130 — `vertsMixed`
- строка 2132 — `clearAreaVerts`
- строка 2137 — `renderVertList`
- строка 2146 — `syncAreaCalcButton`
- строка 2172 — `areaPickedCurve`
- строка 2181 — `areaCurveRange`
- строка 2199 — `syncAreaRangeLabel`
- строка 2238 — `freshenVertNames`
- строка 2256 — `drawAreaVerts`
- строка 2285 — `areaTargets`
- строка 2289 — `calcAreaUnderCurve`
- строка 2302 — `ringArea`
- строка 2312 — `segCross`
- строка 2319 — `ringSelfCrosses`
- строка 2341 — `angleRing`
- строка 2347 — `bestAreaRing`
- строка 2377 — `calcAreaPolygon`
- строка 2394 — `AREA_PALETTE`
- строка 2404 — `areaLive`
- строка 2425 — `areasLive`
- строка 2427 — `runAreaCalc`
- строка 2439 — `pushArea`
- строка 2460 — `addPolyArea`
- строка 2473 — `syncPtsSelBar`
- строка 2495 — `clearAreaCalc`
- строка 2502 — `drawAreaCalc`
- строка 2543 — `renameCommit`
- строка 2549 — `areaById`
- строка 2550 — `areaVertsLabel`
- строка 2557 — `updateAreaCalcPanel`
- строка 2625 — `openAreaMenu`
- строка 2670 — `syncAreaCalcUI`
- строка 2709 — `updateQuickArea`
- строка 2719 — `curveNameInto`
- строка 2723 — `buildAreaCurveButtons`
- строка 2757 — `pickAreaCurve`
- строка 2765 — `syncAreaCurveButtons`
- строка 2784 — `setAreaCalcMode`
- строка 2799 — `closeAreaBuild`
- строка 2805 — `cancelAreaBuild`
- строка 2817 — `finishPolyBuild`
- строка 2826 — `wireFolds`
- строка 2851 — `wireAreaCalc`
- строка 2886 — `paramsAllowed`
- строка 2911 — `isReservedName`
- строка 2951 — `expandImplicitMul`
- строка 2997 — `visibleSvgText`
- строка 3023 — `chartLabelSource`
- строка 3033 — `chartLabelBase`
- строка 3050 — `chartLabelKind`
- строка 3064 — `typesetChartLabels`
- строка 3092 — `prepExpr`
- строка 3110 — `texToPlain`
- строка 3136 — `sceneReservedKey`
- строка 3140 — `freeSymbols`
- строка 3158 — `freeSymbolsUncached`
- строка 3186 — `sceneReserved`
- строка 3212 — `sceneExtraParams`
- строка 3218 — `paramValue`
- строка 3224 — `paramScope`
- строка 3234 — `scopeFor`
- строка 3241 — `evalWithParams`
- строка 3252 — `syncParams`
- строка 3308 — `buildParamChip`
- строка 3433 — `initSceneColorPickers`
- строка 3445 — `syncSceneColorPickers`
- строка 3453 — `syncAxisPlaceholders`
- строка 3468 — `titleAnchorPx`
- строка 3478 — `drawGraphTitle`
- строка 3517 — `editGraphTitleOnCanvas`
- строка 3562 — `normHex`
- строка 3584 — `paletteSix`
- строка 3592 — `closeColorMenu`
- строка 3606 — `onDocClosePick`
- строка 3612 — `onEscClosePick`
- строка 3632 — `paletteTwelve`
- строка 3633 — `makeColorPicker`
- строка 3745 — `autoCurveName`
- строка 3754 — `curveShortName`
- строка 3764 — `markCaption`
- строка 3773 — `drawMarks`
- строка 3877 — `snapTargets`
- строка 3885 — `snapTargetsAll`
- строка 4033 — `macroSnapTargets`
- строка 4052 — `consumerSnapTargets`
- строка 4081 — `ineqSnapTargets`
- строка 4095 — `mathSnapTargets`
- строка 4177 — `tradeSnapTargets`
- строка 4198 — `axisSnapAt`
- строка 4218 — `snapDistPx`
- строка 4239 — `snapPointAt`
- строка 4282 — `showSnapHint`
- строка 4301 — `armMark`
- строка 4314 — `cancelMarkDraft`
- строка 4354 — `resetDecor`
- строка 4446 — `_undoCopyChild`
- строка 4460 — `_undoCopy`
- строка 4480 — `pushUndo`
- строка 4491 — `undoLast`
- строка 4508 — `clearUndo`
- строка 4515 — `forgetSceneSnapshot`
- строка 4517 — `resetSceneMemory`
- строка 4528 — `saveSceneSnapshot`
- строка 4541 — `restoreSceneSnapshot`
- строка 4569 — `keyOnText`
- строка 4576 — `markOnText`
- строка 4586 — `notationTex`
- строка 4593 — `markOnInto`
- строка 4602 — `markNameTex`
- строка 4609 — `addMarkAt`
- строка 4649 — `colorDist`
- строка 4658 — `drawnStrokeColors`
- строка 4674 — `nextMarkColor`
- строка 4697 — `canvasNameLetters`
- строка 4709 — `nextMarkName`
- строка 4721 — `newMark`
- строка 4737 — `pendingMark`
- строка 4740 — `startMarkDraft`
- строка 4749 — `markSnapFn`
- строка 4760 — `renderMarkList`
- строка 4772 — `ensureAddMarkButton`
- строка 4783 — `buildMarkRow`
- строка 4939 — `markById`
- строка 4940 — `openMarkMenu`
- строка 4953 — `fillMarkMenu`
- строка 4995 — `renameMark`
- строка 5010 — `editMarkCoords`
- строка 5019 — `removeMark`

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
- строка 1246 — `constraintContoursIn`
- строка 1298 — `constraintPointsIn`
- строка 1301 — `constraintPoints`
- строка 1308 — `optimizeAlongCurve`
- строка 1363 — `constraintFit`
- строка 1387 — `drawMathConstraint`
- строка 1450 — `drawLevelCurveOn`
- строка 1466 — `mathOptimumReasoning`
- строка 1503 — `updateMathPanel`
- строка 1654 — `redrawMath`
- строка 1694 — `setMathSub`
- строка 1717 — `setMathWindow`
- строка 1732 — `setMathX0`
- строка 1757 — `downloadBlob`
- строка 1766 — `exportBaseName`
- строка 1779 — `paperChartClone`
- строка 1806 — `exportNumbersLine`
- строка 1815 — `exportExtras`
- строка 1823 — `exportPNG`
- строка 1864 — `buildTex`
- строка 1873 — `afterFonts`
- строка 1878 — `exportTex`
- строка 1888 — `exportPDF`
- строка 1895 — `exportPDFSend`
- строка 1919 — `exportTitleDefault`
- строка 1921 — `buildExportFields`
- строка 1951 — `refreshExportPreview`
- строка 1989 — `expValue`
- строка 2000 — `syncExportFormat`
- строка 2012 — `refreshExportSheet`
- строка 2020 — `wireExport`
- строка 2049 — `openExport`
- строка 2070 — `closeExport`
- строка 2090 — `updateGraphPanel`
- строка 2151 — `graphExplainNote`

#### `calc2/static/calc2/72-export-tex.js`

- строка 30 — `texPaperActive`
- строка 35 — `texPaperComputeSize`
- строка 1666 — `texEnterPaper`
- строка 1667 — `texCapture`
- строка 1668 — `texEmit`
- строка 1669 — `texInventory`

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
- строка 306 — `rememberStartCurves`
- строка 311 — `startExprOf`
- строка 316 — `curveIsPiecewise`
- строка 329 — `renderCurveList`
- строка 681 — `refreshCurveRow`
- строка 698 — `curveToSingleFormula`

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
- строка 1662 — `markFormulaField`
- строка 1670 — `syncFormulaEditBases`
- строка 1686 — `onFormulaInput`
- строка 1750 — `scheduleParamsSync`
- строка 1756 — `registerFormulaField`
- строка 1773 — `fieldActive`
- строка 1782 — `liveFormulaTexts`
- строка 1818 — `equipFormulaField`
- строка 1855 — `equipAllFormulaFields`
- строка 1859 — `attachFormulaHelp`
- строка 2049 — `makeEditableValue`
- строка 2155 — `makeToggle`
- строка 2197 — `segToToggle`
- строка 2229 — `closeAllSelectMenus`
- строка 2233 — `upgradeSelect`
- строка 2334 — `upgradeTextField`
- строка 2357 — `upgradeTextFieldsIn`

#### `calc2/static/calc2/84-picker.js`

- строка 8 — `loadScene`
- строка 148 — `closePicker`
- строка 170 — `openPicker`
- строка 343 — `baseScene`
- строка 352 — `applyCardScope`
- строка 430 — `blockSpec`
- строка 442 — `foldPickerGroups`
- строка 529 — `plural`
- строка 537 — `pickScene`

#### `calc2/static/calc2/86-workspace.js`

- строка 57 — `setFieldValue`
- строка 63 — `relocateForScene`
- строка 78 — `clearResultPanels`
- строка 96 — `toast`
- строка 111 — `dockActive`
- строка 118 — `setSideOpen`
- строка 145 — `setToolsOpen`
- строка 146 — `setParamsOpen`
- строка 156 — `hasAnalytics`
- строка 163 — `moveExplanations`
- строка 261 — `conditionNotesSig`
- строка 273 — `conditionNotesToExplain`
- строка 323 — `answerNotesToExplain`
- строка 372 — `syncAnalyticsPanel`
- строка 456 — `sectionIcon`
- строка 467 — `cardifySections`
- строка 559 — `collapseCards`
- строка 577 — `syncLabelSizeSeg`
- строка 588 — `openSection`
- строка 625 — `cardWithFormula`
- строка 638 — `syncFirstCard`
- строка 657 — `wireScene`
- строка 826 — `resetCurrentScene`
- строка 836 — `setWrenchOpen`
- строка 846 — `applyViewBounds`
- строка 873 — `quadWindow`
- строка 878 — `quadSameWindow`
- строка 897 — `offQuadShownPoints`
- строка 927 — `fitWindowToOffQuad`
- строка 949 — `setFirstQuad`
- строка 999 — `setGridMode`
- строка 1017 — `hintTip`
- строка 1044 — `fitTipMath`
- строка 1067 — `showHintTip`
- строка 1125 — `hideHintTip`
- строка 1150 — `tipText`
- строка 1179 — `tipTex`
- строка 1189 — `tipName`
- строка 1206 — `tipExpr`
- строка 1216 — `tipPlain`
- строка 1245 — `ffEsc`
- строка 1255 — `ffLatexOf`
- строка 1277 — `finalFunctionHtml`
- строка 1302 — `ffParseCases`
- строка 1324 — `ffCondCompact`
- строка 1348 — `ffMathHtml`
- строка 1372 — `ffKatexW`
- строка 1388 — `ffFitCases`
- строка 1475 — `fitFinalMath`
- строка 1504 — `ffCopyText`
- строка 1512 — `ffCopyFallback`
- строка 1524 — `wireFinalCopy`
- строка 1557 — `ffOpenExpand`
- строка 1578 — `ffCloseExpand`
- строка 1590 — `setFinalFunctions`
- строка 1608 — `refitFinalMathSoon`
- строка 1636 — `markNotationsIn`
- строка 1668 — `paintNotation`
- строка 1678 — `showTipFor`
- строка 1684 — `wireTips`
- строка 1736 — `syncTipLabels`
- строка 1749 — `hintAnchor`
- строка 1830 — `fitPanelMath`
- строка 1860 — `syncHintDots`
- строка 1875 — `hintsToDots`
- строка 1914 — `wireHintButtons`
- строка 1956 — `wireWrench`
- строка 2082 — `fillPrintBlocks`
- строка 2112 — `setPrintViewBox`

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
- строка 1006 — `ineqMasterApply`
- строка 1018 — `ineqMasterDetach`
- строка 1023 — `buildIneqMasterChip`
- строка 1036 — `showPult`
- строка 1063 — `updatePult`
- строка 1098 — `liveFormula`
- строка 1118 — `wireControls`

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
- строка 210 — `forceRebuildAfterApply`
- строка 219 — `syncUiFromState`
- строка 226 — `capturePristine`
- строка 237 — `restorePristine`
- строка 262 — `captureMemory`
- строка 267 — `applyMemory`
- строка 290 — `serializeCurves`
- строка 303 — `rebuildCurves`
- строка 323 — `modelKeyOf`
- строка 328 — `collectModelState`
- строка 348 — `applyModelState`

#### `calc2/static/calc2/90-explain.js`

- строка 383 — `sceneExplainHtml`

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
- строка 722 — `scAxisLetter`
- строка 732 — `SC_NO_FUNCS`
- строка 733 — `scFirstCardName`
- строка 738 — `scWords`
- строка 763 — `scOn`
- строка 764 — `scProw`
- строка 765 — `scParamAnchor`
- строка 774 — `scSetup`
- строка 836 — `scStepper`
- строка 860 — `scSync`
- строка 899 — `scConsumerCard`
- строка 949 — `scConsumerSync`
- строка 970 — `scIneqSetup`
- строка 1007 — `scIneqSync`
- строка 1034 — `scGraphRows`
- строка 1074 — `scGraphSync`
- строка 1103 — `scMathSetup`
- строка 1127 — `scMathSync`
- строка 1148 — `scParamsCont`
- строка 1163 — `scMinmaxSetup`
- строка 1175 — `scMmRows`
- строка 1207 — `scValueOnly`
- строка 1210 — `scPchips`
- строка 1254 — `scIntervSync`
- строка 1279 — `scExtCards`
- строка 1315 — `applyAreaHidden`
- строка 1329 — `vgFormIds`

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

- строка 204 — `areasHead`
- строка 210 — `ansNum`
- строка 215 — `answerCellWas`
- строка 248 — `heroLabel`
- строка 264 — `notationTex`
- строка 278 — `plainText`
- строка 281 — `statRows`
- строка 285 — `txRow`
- строка 308 — `answerSignature`
- строка 325 — `scheduleAnswer`
- строка 336 — `answerIsMath`
- строка 340 — `labelCopy`
- строка 351 — `answerNumberItem`
- строка 357 — `answerValueInto`
- строка 403 — `answerGroupHead`
- строка 426 — `segNoteOn`
- строка 430 — `buildSegNote`
- строка 444 — `hideDrainedBlocks`
- строка 489 — `retypesetSeenRows`
- строка 513 — `remeasureStatsAfterFonts`
- строка 528 — `answerReflow`
- строка 539 — `answerCells`
- строка 595 — `buildAnswer`
- строка 734 — `hideEchoes`
- строка 768 — `markFirstSection`
- строка 801 — `decorateTables`
- строка 835 — `liftTableHead`
- строка 863 — `answerRow`
- строка 915 — `burdenOn`
- строка 922 — `burdenNoteText`
- строка 929 — `buildBurden`
- строка 962 — `buildStatus`
- строка 989 — `buildExplainAccordion`
- строка 1054 — `questionsWord`
- строка 1060 — `syncExplainBar`

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
- строка 60 — `selfClose`
- строка 61 — `selfAccept`
- строка 75 — `checkGuess`
- строка 92 — `selfIsAnswer`
- строка 95 — `selfText`
- строка 101 — `selfNot`
- строка 103 — `selfKey`
- строка 105 — `setSelfMode`
- строка 120 — `selfCell`
- строка 196 — `selfAfterAnswer`
- строка 212 — `applySelf`
- строка 240 — `selfCanvas`
- строка 292 — `selfMaskText`
- строка 308 — `selfOpenValues`
- строка 325 — `selfPointOpen`
- строка 337 — `selfMasked`
- строка 339 — `wireSelf`

#### `calc2/static/calc2/99-boot.js`

- строка 13 — `lockNumberFields`
- строка 42 — `init`

**Итого функций в индексе: 1586.**

<!-- AUTO:END -->
