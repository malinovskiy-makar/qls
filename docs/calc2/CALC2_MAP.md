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

*Автоматически собрано командой `manage.py calc2_map`. Дата: 2026-11-02. HEAD: `030fd336`. Не редактировать руками — вся эта часть файла, от отметки начала автосекции и до отметки её конца, перезаписывается заново при каждом запуске команды.*

### Файлы (маршрут → представление → шаблон → статика)

| Путь | Строк | КБ | Тип |
|---|---:|---:|---|
| `calc2/urls.py` | 19 | 0.6 | python |
| `calc2/views.py` | 224 | 13.4 | python |
| `calc2/templates/calc2/calc2.html` | 2284 | 184.0 | шаблон |
| `calc2/static/calc2/calc2.css` | 4311 | 326.4 | CSS |
| `calc2/static/calc2/previews.json` | 44 | 30.9 | json |
| `calc2/static/calc2/00-config.js` | 578 | 50.2 | JS |
| `calc2/static/calc2/10-math-core.js` | 1169 | 76.8 | JS |
| `calc2/static/calc2/20-plane.js` | 1021 | 69.5 | JS |
| `calc2/static/calc2/30-curves.js` | 1517 | 110.4 | JS |
| `calc2/static/calc2/40-scenes-market.js` | 3878 | 280.5 | JS |
| `calc2/static/calc2/42-scenes-mono.js` | 2036 | 150.1 | JS |
| `calc2/static/calc2/44-scenes-firm.js` | 1208 | 80.2 | JS |
| `calc2/static/calc2/46-scenes-labor.js` | 900 | 68.8 | JS |
| `calc2/static/calc2/48-scenes-consumer.js` | 279 | 18.2 | JS |
| `calc2/static/calc2/50-scenes-macro.js` | 445 | 30.3 | JS |
| `calc2/static/calc2/52-modes.js` | 1007 | 68.8 | JS |
| `calc2/static/calc2/54-scenes-ppf.js` | 3283 | 212.3 | JS |
| `calc2/static/calc2/56-scenes-inequality.js` | 555 | 36.3 | JS |
| `calc2/static/calc2/60-overlays.js` | 4968 | 317.5 | JS |
| `calc2/static/calc2/70-scenes-math.js` | 2096 | 136.8 | JS |
| `calc2/static/calc2/72-export-tex.js` | 1661 | 127.7 | JS |
| `calc2/static/calc2/80-ui.js` | 860 | 54.4 | JS |
| `calc2/static/calc2/82-input.js` | 2355 | 140.4 | JS |
| `calc2/static/calc2/84-picker.js` | 582 | 44.4 | JS |
| `calc2/static/calc2/86-workspace.js` | 2157 | 141.0 | JS |
| `calc2/static/calc2/88-params.js` | 2022 | 139.3 | JS |
| `calc2/static/calc2/89-model-state.js` | 362 | 23.8 | JS |
| `calc2/static/calc2/90-explain.js` | 394 | 64.7 | JS |
| `calc2/static/calc2/91-session.js` | 502 | 26.6 | JS |
| `calc2/static/calc2/92-ui-kit.js` | 1330 | 91.7 | JS |
| `calc2/static/calc2/93-shell.js` | 284 | 17.4 | JS |
| `calc2/static/calc2/94-answer.js` | 1074 | 71.3 | JS |
| `calc2/static/calc2/95-picker-screen.js` | 470 | 26.7 | JS |
| `calc2/static/calc2/96-self.js` | 322 | 21.4 | JS |
| `calc2/static/calc2/99-boot.js` | 112 | 9.5 | JS |

**Итого: 35 файлов, 46309 строк, 3262.1 КБ.**

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
- строка 398 — `fmtLinear`
- строка 422 — `compileFormulaP`
- строка 433 — `evalQofP`
- строка 448 — `detectLinearP`
- строка 482 — `invertQofP`
- строка 505 — `buildCurveFromQP`
- строка 530 — `makeVerticalCurve`
- строка 534 — `isVertical`
- строка 540 — `curveZeroQ`
- строка 592 — `frameFloorQ`
- строка 593 — `frameFloorP`
- строка 596 — `naturalSpanQ`
- строка 602 — `eqSearchSpan`
- строка 615 — `bumpModelSpan`
- строка 616 — `modelSpanQ`
- строка 631 — `findEquilibrium`
- строка 691 — `findOffQuadIntersection`
- строка 716 — `bisect`
- строка 728 — `integrate`
- строка 750 — `signChanges`
- строка 766 — `areaBetween`
- строка 777 — `crossingCount`
- строка 798 — `findRoot`
- строка 816 — `invCurve`
- строка 830 — `curveDeriv`
- строка 837 — `compileExt`
- строка 845 — `evalSocial`
- строка 873 — `compileTwoVar`
- строка 883 — `compileTwoVarUncached`
- строка 893 — `evalTwoVar`
- строка 905 — `solveLevelB`
- строка 943 — `traceLevelCurve`
- строка 974 — `partialA`
- строка 979 — `partialB`
- строка 986 — `mrsAt`
- строка 1001 — `optimizeAlongConstraint`
- строка 1065 — `qtyHasCyrillic`
- строка 1070 — `qtyIsQuantity`
- строка 1084 — `qtyParts`
- строка 1142 — `qtyLatex`

#### `calc2/static/calc2/20-plane.js`

- строка 12 — `computeSize`
- строка 52 — `measureText`
- строка 86 — `fitMargins`
- строка 137 — `fitLeftForLabels`
- строка 150 — `makeScales`
- строка 185 — `clearPanels`
- строка 187 — `registerPanel`
- строка 204 — `panelDist`
- строка 213 — `panelAt`
- строка 225 — `activePanel`
- строка 233 — `panelById`
- строка 248 — `panelWin`
- строка 252 — `resetPanelWins`
- строка 260 — `panelZoomBy`
- строка 277 — `panelPanBy`
- строка 291 — `gesturePanelId`
- строка 319 — `isEconScene`
- строка 325 — `econLo`
- строка 329 — `quadLo`
- строка 352 — `quadPrice`
- строка 362 — `toPx`
- строка 363 — `toData`
- строка 379 — `roundShown`
- строка 383 — `fmtSum`
- строка 389 — `shownDiff`
- строка 390 — `fmtDiff`
- строка 402 — `shownDecimals`
- строка 410 — `sumDecimals`
- строка 414 — `fmt`
- строка 435 — `fmtInput`
- строка 445 — `niceTickStep`
- строка 457 — `axisTicks`
- строка 470 — `xTicks`
- строка 471 — `yTicks`
- строка 474 — `addDefs`
- строка 541 — `drawGrid`
- строка 592 — `extraTickX`
- строка 603 — `extraTickY`
- строка 643 — `dropTickAt`
- строка 670 — `coordValue`
- строка 694 — `coordSplit`
- строка 698 — `coordAlreadyAt`
- строка 744 — `resetDrawnKeyPoints`
- строка 747 — `panelOfGlobalScales`
- строка 751 — `kpNode`
- строка 767 — `collectDashes`
- строка 784 — `dashEndsNear`
- строка 796 — `flushDrawnKeyPoints`
- строка 844 — `noteAxisX`
- строка 849 — `noteAxisY`
- строка 856 — `kpName`
- строка 861 — `axisValueX`
- строка 888 — `axisValueY`
- строка 913 — `axisValueText`
- строка 930 — `drawAxes`

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
- строка 542 — `qtyAtPrice`
- строка 552 — `openQuotaName`
- строка 556 — `recomputeOpenEconomy`
- строка 648 — `drawOpenAreas`
- строка 696 — `drawOpenLines`
- строка 743 — `attachOpenPwDrag`
- строка 751 — `setOpenPw`
- строка 764 — `setOpenTool`
- строка 779 — `syncOpenQuotaLabel`
- строка 785 — `updateOpenPanel`
- строка 844 — `drawEquilibrium`
- строка 881 — `drawOffQuadIntersection`
- строка 920 — `offQuadExplainHtml`
- строка 946 — `pctFormExplainHtml`
- строка 983 — `mathTspans`
- строка 1023 — `hasMathMarkup`
- строка 1047 — `markNotationTspan`
- строка 1064 — `mixedNotationRe`
- строка 1072 — `mixedMathTspans`
- строка 1116 — `qtyTspans`
- строка 1153 — `qtyGreekChar`
- строка 1191 — `texToCanvasText`
- строка 1200 — `renderLabelText`
- строка 1221 — `haloText`
- строка 1254 — `pointName`
- строка 1280 — `yWageLabel`
- строка 1285 — `yWageValue`
- строка 1308 — `isMonopolyScene`
- строка 1316 — `eqSectionTitle`
- строка 1332 — `updateEqSectionTitle`
- строка 1349 — `interventionKeyValues`
- строка 1414 — `countCrossings`
- строка 1423 — `updateInfoPanel`
- строка 1532 — `sumSceneOn`
- строка 1535 — `sumGroupsOf`
- строка 1542 — `sumGroupQty`
- строка 1555 — `sumChokePrice`
- строка 1581 — `sumPriceTop`
- строка 1602 — `sumLinearRecord`
- строка 1704 — `integrateBroken`
- строка 1715 — `curveBreaks`
- строка 1726 — `quadBreaks`
- строка 1742 — `sumSegExpr`
- строка 1760 — `sumPolyline`
- строка 1788 — `sumRebuildSide`
- строка 1839 — `sumSignature`
- строка 1859 — `sumRebuild`
- строка 1879 — `sumAnalyticsKey`
- строка 1897 — `sumGroupName`
- строка 1920 — `sumTagOf`
- строка 1927 — `sumShortTag`
- строка 1956 — `sumGroupColor`
- строка 1961 — `sumStartExpr`
- строка 1969 — `sumReorder`
- строка 1974 — `sumAddGroup`
- строка 1987 — `sumBuildScene`
- строка 2015 — `sumSetCount`
- строка 2034 — `syncSumUi`
- строка 2048 — `sumGroupStats`
- строка 2094 — `sumFinalRecords`
- строка 2112 — `updateSumPanel`
- строка 2173 — `drawAreas`
- строка 2203 — `beforeInterventionNote`
- строка 2212 — `updateAreasPanel`
- строка 2253 — `intervOnBuyer`
- строка 2262 — `drawShiftedSupply`
- строка 2317 — `taxPivotQ`
- строка 2348 — `taxPivotPoint`
- строка 2357 — `drawTaxPivot`
- строка 2392 — `drawTaxAreas`
- строка 2432 — `drawTaxPoints`
- строка 2485 — `attachTaxDrag`
- строка 2506 — `setTax`
- строка 2624 — `taxFormKey`
- строка 2632 — `pctForm`
- строка 2640 — `syncTaxKind`
- строка 2645 — `applyIntervCascade`
- строка 2718 — `setTaxForm`
- строка 2736 — `setType`
- строка 2787 — `rateLetter`
- строка 2791 — `rateUnit`
- строка 2813 — `modelPriceTop`
- строка 2824 — `unitRateMax`
- строка 2834 — `applyPriceRegBounds`
- строка 2843 — `applyTaxRateBounds`
- строка 2878 — `syncQuotaHint`
- строка 2894 — `syncPcHint`
- строка 2902 — `markCurrentIntervHint`
- строка 2911 — `intervHintKey`
- строка 2921 — `intervHintHtml`
- строка 2943 — `syncTaxHint`
- строка 2981 — `setTaxKind`
- строка 2991 — `qpAfter`
- строка 3002 — `updateTaxPanel`
- строка 3138 — `setTaxSide`
- строка 3149 — `setTaxSideButtons`
- строка 3162 — `drawElasticityZones`
- строка 3180 — `drawElasticityPoint`
- строка 3210 — `attachElastDrag`
- строка 3218 — `drawElasticityPointS`
- строка 3238 — `attachElastDragS`
- строка 3246 — `updateElasticityPanel`
- строка 3310 — `drawExtAreas`
- строка 3324 — `drawExtCurves`
- строка 3351 — `drawExtPoints`
- строка 3385 — `drawExtScenario`
- строка 3394 — `updateExtPanel`
- строка 3448 — `setExtSign`
- строка 3457 — `syncSocialFields`
- строка 3485 — `syncExtHint`
- строка 3496 — `socialDefaultExpr`
- строка 3502 — `recompileSocial`
- строка 3524 — `setPRegFields`
- строка 3533 — `setPReg`
- строка 3542 — `drawPcAreas`
- строка 3569 — `drawPriceControl`
- строка 3618 — `attachPcDrag`
- строка 3627 — `updatePcPanel`
- строка 3672 — `setQuotaFields`
- строка 3684 — `setQuota`
- строка 3691 — `setQuotaPos`
- строка 3699 — `setQuotaPrice`
- строка 3706 — `updateQuotaPriceLabel`
- строка 3727 — `drawQuotaAreas`
- строка 3754 — `drawQuotaLines`
- строка 3799 — `attachQuotaDrag`
- строка 3812 — `updateQuotaPanel`
- строка 3859 — `drawGhost`

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
- строка 689 — `prodMP`
- строка 694 — `prodAP`
- строка 702 — `maxOf`
- строка 722 — `realMax`
- строка 724 — `recomputeProduction`
- строка 743 — `redrawProduction`
- строка 861 — `noMaxNote`
- строка 870 — `updateProdPanel`
- строка 894 — `recomputeIsoquant`
- строка 905 — `redrawIsoquant`
- строка 921 — `updateIsoPanel`
- строка 958 — `plantMC`
- строка 964 — `plantTC`
- строка 970 — `plantQatMC`
- строка 986 — `recomputePlants`
- строка 1020 — `plantsAt`
- строка 1037 — `redrawPlants`
- строка 1118 — `updatePlantsPanel`
- строка 1148 — `setPlantsView`
- строка 1155 — `setPlantsQ`
- строка 1166 — `setCostsInputMode`
- строка 1174 — `syncCostsInputMode`
- строка 1188 — `setCostsSub`

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
- строка 1012 — `ppfNum`
- строка 1023 — `ppfSnap`
- строка 1033 — `ppfPiecesToExpr`
- строка 1050 — `ppfLinearExpr`
- строка 1057 — `combinedPpfLinearRecord`
- строка 1234 — `ppfPoly2Xmax`
- строка 1253 — `ppfCostOf`
- строка 1262 — `ppfValid`
- строка 1270 — `ppfFam`
- строка 1271 — `ppfClamp`
- строка 1282 — `ppfReduceActive`
- строка 1301 — `ppfPieceTex`
- строка 1351 — `ppfPoly2Terms`
- строка 1361 — `ppfPolyJoin`
- строка 1377 — `ppfPieceBody`
- строка 1415 — `ppfPieceAt`
- строка 1428 — `ppfPiecesRecord`
- строка 1476 — `ppfSumByEqualCost`
- строка 1581 — `ppfSumByEnvelope`
- строка 1670 — `ppfEnvPiece`
- строка 1681 — `ppfMergeSameLine`
- строка 1701 — `ppfCostKinds`
- строка 1710 — `ppfCostValue`
- строка 1720 — `ppfWhyNumeric`
- строка 1773 — `ppfSumMixedPair`
- строка 1938 — `ppfSumAnalytic`
- строка 1956 — `combinedPpfFormula`
- строка 1992 — `verifyFormula`
- строка 2003 — `detectKinks`
- строка 2028 — `showPaneError`
- строка 2039 — `ppfSumCount`
- строка 2040 — `ppfSumGet`
- строка 2045 — `ppfSumSet`
- строка 2050 — `ppfSumName`
- строка 2054 — `ppfSumColor`
- строка 2068 — `ppfSumSignature`
- строка 2078 — `recomputePpfSum`
- строка 2084 — `ensurePpfSum`
- строка 2088 — `recomputePpfSumRaw`
- строка 2199 — `renderPpfSumRows`
- строка 2250 — `detectSumKinks`
- строка 2268 — `drawPpfSumCurves`
- строка 2300 — `drawPpfSumMarks`
- строка 2326 — `updatePpfSumPanel`
- строка 2443 — `fmtRu`
- строка 2447 — `ppfSumSchemaData`
- строка 2481 — `schemaNote`
- строка 2488 — `drawPpfSumSchema`
- строка 2540 — `redrawPpfSum`
- строка 2553 — `setPpfSumView`
- строка 2564 — `cornerByValue`
- строка 2588 — `bestByValue`
- строка 2611 — `ppfOcRange`
- строка 2625 — `recomputePpfTrade`
- строка 2690 — `drawPpfTrade`
- строка 2718 — `drawPpfTradeMarks`
- строка 2746 — `updatePpfTradePanel`
- строка 2898 — `syncPpftPriceUI`
- строка 2909 — `redrawPpfTrade`
- строка 2930 — `recomputeTradeB`
- строка 3019 — `tradeCpfPoints`
- строка 3037 — `tradeCpfMark`
- строка 3056 — `tradeBPanels`
- строка 3077 — `drawTradeB`
- строка 3150 — `drawTradeBMarks`
- строка 3153 — `tbName`
- строка 3159 — `updateTradeBPanel`
- строка 3229 — `syncTbPriceUI`
- строка 3242 — `redrawTradeB`
- строка 3257 — `setTradeScenario`
- строка 3269 — `setPpfSub`

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
- строка 81 — `redrawScene`
- строка 228 — `redrawGraphMode`
- строка 240 — `renderMmRows`
- строка 286 — `graphRowsBox`
- строка 289 — `renderGraphRows`
- строка 308 — `graphError`
- строка 315 — `buildGraphRow`
- строка 397 — `equipGraphRows`
- строка 405 — `graphRowInput`
- строка 450 — `mainScales`
- строка 461 — `drawOverlays`
- строка 569 — `guardedPanelIds`
- строка 573 — `guardPanelBoxes`
- строка 609 — `panelsChangedSinceLastPass`
- строка 614 — `markPanelsChanged`
- строка 617 — `flushPendingPanelClears`
- строка 626 — `refreshAnalyticsPanel`
- строка 654 — `typesetStats`
- строка 706 — `addStatSign`
- строка 719 — `statToTex`
- строка 757 — `katexVisibleText`
- строка 763 — `restatWide`
- строка 809 — `statInkWidth`
- строка 817 — `statTooWide`
- строка 826 — `statPieces`
- строка 861 — `texAbbrev`
- строка 867 — `renderMathIn`
- строка 910 — `areaKey`
- строка 915 — `subDigits`
- строка 920 — `applyAreaColors`
- строка 930 — `currentAreas`
- строка 948 — `areaOfPathEl`
- строка 1010 — `areaShort`
- строка 1019 — `drawLegend`
- строка 1082 — `floatRects`
- строка 1102 — `legendCorner`
- строка 1179 — `viewWindow`
- строка 1191 — `axisWords`
- строка 1197 — `crossPoints`
- строка 1299 — `invalidateKeyTargets`
- строка 1302 — `kinksOf`
- строка 1350 — `keyTargets`
- строка 1525 — `snapVertexAt`
- строка 1557 — `markPanelId`
- строка 1577 — `armedPanelId`
- строка 1583 — `drawCrossPoints`
- строка 1732 — `armCurve`
- строка 1738 — `disarmCurve`
- строка 1746 — `keyPointLit`
- строка 1759 — `drawCurveHits`
- строка 1797 — `pinKeyPoint`
- строка 1817 — `hoverLabel`
- строка 1828 — `drawRoller`
- строка 1849 — `rollerTargetAt`
- строка 1879 — `rollerClampX`
- строка 1898 — `rollerMove`
- строка 1914 — `showRollTip`
- строка 1937 — `hideRollTip`
- строка 1946 — `rollerOff`
- строка 1957 — `curveRightEdge`
- строка 1982 — `axisXLetter`
- строка 1992 — `axisLetter`
- строка 2005 — `armVerts`
- строка 2047 — `markServiceNodes`
- строка 2064 — `syncCanvasMode`
- строка 2086 — `leaveCanvasMode`
- строка 2092 — `finishCanvasMode`
- строка 2097 — `addAreaVert`
- строка 2110 — `vertPanels`
- строка 2113 — `vertsMixed`
- строка 2115 — `clearAreaVerts`
- строка 2120 — `renderVertList`
- строка 2129 — `syncAreaCalcButton`
- строка 2155 — `areaPickedCurve`
- строка 2164 — `areaCurveRange`
- строка 2182 — `syncAreaRangeLabel`
- строка 2221 — `freshenVertNames`
- строка 2239 — `drawAreaVerts`
- строка 2268 — `areaTargets`
- строка 2272 — `calcAreaUnderCurve`
- строка 2285 — `ringArea`
- строка 2295 — `segCross`
- строка 2302 — `ringSelfCrosses`
- строка 2324 — `angleRing`
- строка 2330 — `bestAreaRing`
- строка 2360 — `calcAreaPolygon`
- строка 2377 — `AREA_PALETTE`
- строка 2387 — `areaLive`
- строка 2408 — `areasLive`
- строка 2410 — `runAreaCalc`
- строка 2422 — `pushArea`
- строка 2443 — `addPolyArea`
- строка 2456 — `syncPtsSelBar`
- строка 2478 — `clearAreaCalc`
- строка 2485 — `drawAreaCalc`
- строка 2526 — `renameCommit`
- строка 2532 — `areaById`
- строка 2533 — `areaVertsLabel`
- строка 2540 — `updateAreaCalcPanel`
- строка 2608 — `openAreaMenu`
- строка 2653 — `syncAreaCalcUI`
- строка 2692 — `updateQuickArea`
- строка 2702 — `curveNameInto`
- строка 2706 — `buildAreaCurveButtons`
- строка 2740 — `pickAreaCurve`
- строка 2748 — `syncAreaCurveButtons`
- строка 2767 — `setAreaCalcMode`
- строка 2782 — `closeAreaBuild`
- строка 2788 — `cancelAreaBuild`
- строка 2800 — `finishPolyBuild`
- строка 2809 — `wireFolds`
- строка 2834 — `wireAreaCalc`
- строка 2869 — `paramsAllowed`
- строка 2894 — `isReservedName`
- строка 2934 — `expandImplicitMul`
- строка 2980 — `visibleSvgText`
- строка 3006 — `chartLabelSource`
- строка 3016 — `chartLabelBase`
- строка 3033 — `chartLabelKind`
- строка 3047 — `typesetChartLabels`
- строка 3075 — `prepExpr`
- строка 3093 — `texToPlain`
- строка 3119 — `sceneReservedKey`
- строка 3123 — `freeSymbols`
- строка 3141 — `freeSymbolsUncached`
- строка 3169 — `sceneReserved`
- строка 3192 — `sceneExtraParams`
- строка 3198 — `paramValue`
- строка 3204 — `paramScope`
- строка 3214 — `scopeFor`
- строка 3221 — `evalWithParams`
- строка 3232 — `syncParams`
- строка 3288 — `buildParamChip`
- строка 3413 — `initSceneColorPickers`
- строка 3425 — `syncSceneColorPickers`
- строка 3433 — `syncAxisPlaceholders`
- строка 3448 — `titleAnchorPx`
- строка 3458 — `drawGraphTitle`
- строка 3497 — `editGraphTitleOnCanvas`
- строка 3542 — `normHex`
- строка 3564 — `paletteSix`
- строка 3572 — `closeColorMenu`
- строка 3586 — `onDocClosePick`
- строка 3592 — `onEscClosePick`
- строка 3612 — `paletteTwelve`
- строка 3613 — `makeColorPicker`
- строка 3725 — `autoCurveName`
- строка 3734 — `curveShortName`
- строка 3744 — `markCaption`
- строка 3753 — `drawMarks`
- строка 3857 — `snapTargets`
- строка 3865 — `snapTargetsAll`
- строка 3993 — `macroSnapTargets`
- строка 4012 — `consumerSnapTargets`
- строка 4041 — `ineqSnapTargets`
- строка 4055 — `mathSnapTargets`
- строка 4120 — `tradeSnapTargets`
- строка 4141 — `axisSnapAt`
- строка 4161 — `snapDistPx`
- строка 4182 — `snapPointAt`
- строка 4225 — `showSnapHint`
- строка 4244 — `armMark`
- строка 4257 — `cancelMarkDraft`
- строка 4297 — `resetDecor`
- строка 4389 — `_undoCopyChild`
- строка 4403 — `_undoCopy`
- строка 4423 — `pushUndo`
- строка 4434 — `undoLast`
- строка 4451 — `clearUndo`
- строка 4458 — `forgetSceneSnapshot`
- строка 4460 — `resetSceneMemory`
- строка 4471 — `saveSceneSnapshot`
- строка 4484 — `restoreSceneSnapshot`
- строка 4512 — `keyOnText`
- строка 4519 — `markOnText`
- строка 4529 — `notationTex`
- строка 4536 — `markOnInto`
- строка 4545 — `markNameTex`
- строка 4552 — `addMarkAt`
- строка 4592 — `colorDist`
- строка 4601 — `drawnStrokeColors`
- строка 4617 — `nextMarkColor`
- строка 4640 — `canvasNameLetters`
- строка 4652 — `nextMarkName`
- строка 4664 — `newMark`
- строка 4680 — `pendingMark`
- строка 4683 — `startMarkDraft`
- строка 4692 — `markSnapFn`
- строка 4703 — `renderMarkList`
- строка 4715 — `ensureAddMarkButton`
- строка 4726 — `buildMarkRow`
- строка 4882 — `markById`
- строка 4883 — `openMarkMenu`
- строка 4896 — `fillMarkMenu`
- строка 4938 — `renameMark`
- строка 4953 — `editMarkCoords`
- строка 4962 — `removeMark`

#### `calc2/static/calc2/70-scenes-math.js`

- строка 24 — `compileMath`
- строка 25 — `evalMathAt`
- строка 31 — `mathH`
- строка 36 — `dNum`
- строка 41 — `d2Num`
- строка 48 — `mathF`
- строка 56 — `rootsOf`
- строка 82 — `mathAnalyse`
- строка 123 — `ansFmt`
- строка 133 — `ansPt`
- строка 135 — `ansList`
- строка 136 — `ansPts`
- строка 138 — `fnSig`
- строка 141 — `ansCached`
- строка 153 — `ansZeros`
- строка 170 — `ansExtrema`
- строка 194 — `ansAnalyse`
- строка 212 — `ansCrosses`
- строка 218 — `niceOut`
- строка 232 — `autoAnswerSeg`
- строка 253 — `answerSpec`
- строка 282 — `answerKeyPoints`
- строка 307 — `graphFitWindow`
- строка 333 — `setGraphWindow`
- строка 353 — `keyPointsSig`
- строка 357 — `axisShowing`
- строка 376 — `graphShowKeyPoints`
- строка 394 — `answerSeg`
- строка 403 — `autoSegOf`
- строка 413 — `ansExtremaRows`
- строка 420 — `ansAttr`
- строка 423 — `ansCtx`
- строка 425 — `ansNameMd`
- строка 428 — `graphHeadTex`
- строка 438 — `refreshAnswerSeg`
- строка 445 — `ansSegText`
- строка 446 — `ansSegParse`
- строка 456 — `syncAnsSegUI`
- строка 488 — `applyAnsSegInputs`
- строка 501 — `resetAnsSegToAuto`
- строка 517 — `mathTransformed`
- строка 534 — `mathScales`
- строка 548 — `drawPlaneAxes`
- строка 570 — `planeTicksX`
- строка 587 — `planeTicksY`
- строка 601 — `mathMark`
- строка 606 — `mathSubst`
- строка 612 — `mathTransformExpr`
- строка 629 — `mathLine`
- строка 662 — `resetLabelBoxes`
- строка 663 — `dodgeLabel`
- строка 675 — `mathDot`
- строка 719 — `makeRenamable`
- строка 762 — `editPointName`
- строка 786 — `editInlineLabel`
- строка 867 — `tangentLayout`
- строка 876 — `tangentPanelAt`
- строка 884 — `tanWin`
- строка 894 — `tanResetWindows`
- строка 899 — `tanScales`
- строка 907 — `drawMathTangent`
- строка 1038 — `drawMathOptimum`
- строка 1078 — `drawMathTransform`
- строка 1099 — `labelCurveMath`
- строка 1130 — `mmSlots`
- строка 1131 — `mmGet`
- строка 1134 — `mmSet`
- строка 1139 — `mmLabel`
- строка 1141 — `mmColor`
- строка 1150 — `mmParts`
- строка 1173 — `drawMathMinMax`
- строка 1220 — `compileAB`
- строка 1233 — `parseConstraint`
- строка 1251 — `constraintPointsIn`
- строка 1270 — `constraintPoints`
- строка 1275 — `optimizeAlongCurve`
- строка 1288 — `constraintFit`
- строка 1306 — `drawMathConstraint`
- строка 1368 — `drawLevelCurveOn`
- строка 1382 — `mathOptimumReasoning`
- строка 1419 — `updateMathPanel`
- строка 1571 — `redrawMath`
- строка 1611 — `setMathSub`
- строка 1634 — `setMathWindow`
- строка 1649 — `setMathX0`
- строка 1674 — `downloadBlob`
- строка 1683 — `exportBaseName`
- строка 1696 — `paperChartClone`
- строка 1723 — `exportNumbersLine`
- строка 1732 — `exportExtras`
- строка 1740 — `exportPNG`
- строка 1781 — `buildTex`
- строка 1790 — `afterFonts`
- строка 1795 — `exportTex`
- строка 1805 — `exportPDF`
- строка 1812 — `exportPDFSend`
- строка 1836 — `exportTitleDefault`
- строка 1838 — `buildExportFields`
- строка 1868 — `refreshExportPreview`
- строка 1906 — `expValue`
- строка 1917 — `syncExportFormat`
- строка 1929 — `refreshExportSheet`
- строка 1937 — `wireExport`
- строка 1966 — `openExport`
- строка 1987 — `closeExport`
- строка 2007 — `updateGraphPanel`
- строка 2068 — `graphExplainNote`

#### `calc2/static/calc2/72-export-tex.js`

- строка 30 — `texPaperActive`
- строка 35 — `texPaperComputeSize`
- строка 1658 — `texEnterPaper`
- строка 1659 — `texCapture`
- строка 1660 — `texEmit`
- строка 1661 — `texInventory`

#### `calc2/static/calc2/80-ui.js`

- строка 7 — `showError`
- строка 11 — `hideError`
- строка 30 — `curveSrcForm`
- строка 53 — `exprHasLetter`
- строка 60 — `priceLetters`
- строка 68 — `niceNumTex`
- строка 76 — `linearTexNice`
- строка 107 — `lhsKey`
- строка 110 — `splitCurveLhs`
- строка 134 — `buildAnyCurve`
- строка 157 — `addCurve`
- строка 201 — `addEmptyCurve`
- строка 222 — `curveRecord`
- строка 227 — `restoreCurveRecord`
- строка 232 — `updateCurveExpr`
- строка 265 — `setRole`
- строка 295 — `curveHumanName`
- строка 302 — `curvePrefix`
- строка 310 — `rememberStartCurves`
- строка 315 — `startExprOf`
- строка 320 — `curveIsPiecewise`
- строка 333 — `renderCurveList`
- строка 685 — `refreshCurveRow`
- строка 702 — `curveToSingleFormula`

#### `calc2/static/calc2/82-input.js`

- строка 11 — `texFallback`
- строка 23 — `texVarsItalic`
- строка 27 — `mathToTex`
- строка 44 — `renderTex`
- строка 53 — `renderTexRaw`
- строка 67 — `onKatexReady`
- строка 97 — `pwCond`
- строка 106 — `pwRows`
- строка 127 — `pwPrefixOf`
- строка 132 — `pwFormula`
- строка 151 — `pwLatex`
- строка 173 — `pwVar`
- строка 198 — `casesToNarrow`
- строка 211 — `isNarrowCases`
- строка 215 — `casesUnwrapNarrow`
- строка 230 — `casesToMath`
- строка 261 — `condToMath`
- строка 272 — `renderPw`
- строка 343 — `pwSyncHead`
- строка 358 — `pwSetCount`
- строка 369 — `pwAddRow`
- строка 386 — `pwRemoveRow`
- строка 397 — `pwCheck`
- строка 421 — `pwAttachKeyboard`
- строка 443 — `pwPreview`
- строка 483 — `pwVarForField`
- строка 511 — `pwDefaultRows`
- строка 517 — `pwBalanced`
- строка 530 — `pwSplitTernary`
- строка 554 — `pwCondBounds`
- строка 575 — `pwParse`
- строка 611 — `pwSplitRows`
- строка 635 — `openPiecewise`
- строка 653 — `closePiecewise`
- строка 662 — `insertIntoFormula`
- строка 692 — `mathfieldClass`
- строка 696 — `onMathliveReady`
- строка 732 — `fieldProblem`
- строка 782 — `unknownTexCommand`
- строка 791 — `texGroup`
- строка 801 — `latexToMath`
- строка 947 — `isUndefinedTailNode`
- строка 952 — `unwrapParens`
- строка 963 — `pwCondTex`
- строка 982 — `condChainToCases`
- строка 1004 — `mathToLatexField`
- строка 1026 — `upgradeFormulaField`
- строка 1076 — `fitFormulaField`
- строка 1150 — `fitFormulaFields`
- строка 1153 — `fitFormulaFieldsSoon`
- строка 1173 — `fieldOnScreen`
- строка 1185 — `flushMathfieldsSoon`
- строка 1191 — `flushMathfields`
- строка 1229 — `katexSafe`
- строка 1265 — `katexInto`
- строка 1280 — `placeholderTex`
- строка 1289 — `texSafeText`
- строка 1293 — `buildMathfield`
- строка 1478 — `setFormulaFieldQuiet`
- строка 1500 — `insertIntoField`
- строка 1519 — `keyboardAdapter`
- строка 1521 — `insert`
- строка 1522 — `deleteBack`
- строка 1527 — `clear`
- строка 1531 — `piecewise`
- строка 1540 — `buildKeyboard`
- строка 1550 — `addHowToTab`
- строка 1587 — `closeAllKeyboardsExcept`
- строка 1626 — `formulaInputError`
- строка 1660 — `markFormulaField`
- строка 1668 — `syncFormulaEditBases`
- строка 1684 — `onFormulaInput`
- строка 1748 — `scheduleParamsSync`
- строка 1754 — `registerFormulaField`
- строка 1771 — `fieldActive`
- строка 1780 — `liveFormulaTexts`
- строка 1808 — `equipFormulaField`
- строка 1845 — `equipAllFormulaFields`
- строка 1849 — `attachFormulaHelp`
- строка 2039 — `makeEditableValue`
- строка 2144 — `makeToggle`
- строка 2186 — `segToToggle`
- строка 2218 — `closeAllSelectMenus`
- строка 2222 — `upgradeSelect`
- строка 2323 — `upgradeTextField`
- строка 2346 — `upgradeTextFieldsIn`

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
- строка 282 — `editEqValue`
- строка 349 — `centerBandOn`
- строка 353 — `pullIntoBand`
- строка 357 — `attachBoundsEditor`
- строка 439 — `refreshRegulators`
- строка 450 — `makePchip`
- строка 478 — `curveShiftBase`
- строка 488 — `pultShiftHalf`
- строка 492 — `resetPultShiftHalf`
- строка 495 — `buildPultCurveChips`
- строка 586 — `syncPultCurveValues`
- строка 609 — `capturePultHome`
- строка 616 — `capturePultHomes`
- строка 621 — `returnPultHome`
- строка 633 — `syncPultRegulators`
- строка 664 — `upgradeRegulator`
- строка 847 — `boundText`
- строка 848 — `shortRegulatorName`
- строка 874 — `ppfLinearFormula`
- строка 880 — `ppfInterceptsOf`
- строка 888 — `ppfSetSingle`
- строка 896 — `ppfSetSum`
- строка 916 — `addPultXChip`
- строка 943 — `buildPultExtra`
- строка 976 — `ineqParseIncomes`
- строка 979 — `ineqMasterRebase`
- строка 984 — `ineqMasterScale`
- строка 1002 — `ineqMasterApply`
- строка 1014 — `ineqMasterDetach`
- строка 1019 — `buildIneqMasterChip`
- строка 1032 — `showPult`
- строка 1059 — `updatePult`
- строка 1094 — `liveFormula`
- строка 1114 — `wireControls`

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

- строка 190 — `areasHead`
- строка 196 — `ansNum`
- строка 202 — `answerCellWas`
- строка 233 — `heroLabel`
- строка 249 — `notationTex`
- строка 263 — `plainText`
- строка 269 — `statRows`
- строка 273 — `txRow`
- строка 296 — `answerSignature`
- строка 313 — `scheduleAnswer`
- строка 324 — `answerIsMath`
- строка 328 — `labelCopy`
- строка 340 — `answerValueInto`
- строка 386 — `answerGroupHead`
- строка 409 — `segNoteOn`
- строка 413 — `buildSegNote`
- строка 427 — `hideDrainedBlocks`
- строка 472 — `retypesetSeenRows`
- строка 496 — `remeasureStatsAfterFonts`
- строка 511 — `answerReflow`
- строка 522 — `answerCells`
- строка 578 — `buildAnswer`
- строка 717 — `hideEchoes`
- строка 751 — `markFirstSection`
- строка 784 — `decorateTables`
- строка 818 — `liftTableHead`
- строка 846 — `answerRow`
- строка 897 — `burdenOn`
- строка 903 — `burdenNoteText`
- строка 910 — `buildBurden`
- строка 943 — `buildStatus`
- строка 970 — `buildExplainAccordion`
- строка 1035 — `questionsWord`
- строка 1041 — `syncExplainBar`

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

- строка 22 — `selfNum`
- строка 37 — `selfParse`
- строка 56 — `selfClose`
- строка 60 — `checkGuess`
- строка 75 — `selfIsAnswer`
- строка 78 — `selfText`
- строка 87 — `selfNot`
- строка 89 — `selfKey`
- строка 91 — `setSelfMode`
- строка 106 — `selfCell`
- строка 166 — `selfAfterAnswer`
- строка 182 — `applySelf`
- строка 210 — `selfCanvas`
- строка 262 — `selfMaskText`
- строка 278 — `selfOpenValues`
- строка 295 — `selfPointOpen`
- строка 306 — `selfMasked`
- строка 308 — `wireSelf`

#### `calc2/static/calc2/99-boot.js`

- строка 13 — `lockNumberFields`
- строка 42 — `init`

**Итого функций в индексе: 1397.**

<!-- AUTO:END -->
