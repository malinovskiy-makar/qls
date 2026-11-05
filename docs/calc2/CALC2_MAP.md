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

*Автоматически собрано командой `manage.py calc2_map`. Дата: 2026-11-05. HEAD: `c222080`. Не редактировать руками — вся эта часть файла, от отметки начала автосекции и до отметки её конца, перезаписывается заново при каждом запуске команды.*

### Файлы (маршрут → представление → шаблон → статика)

| Путь | Строк | КБ | Тип |
|---|---:|---:|---|
| `calc2/urls.py` | 19 | 0.6 | python |
| `calc2/views.py` | 227 | 13.7 | python |
| `calc2/templates/calc2/calc2.html` | 2354 | 190.3 | шаблон |
| `calc2/static/calc2/calc2.css` | 4420 | 334.4 | CSS |
| `calc2/static/calc2/previews.json` | 46 | 33.7 | json |
| `calc2/static/calc2/00-config.js` | 578 | 50.2 | JS |
| `calc2/static/calc2/10-math-core.js` | 1179 | 77.4 | JS |
| `calc2/static/calc2/12-numbers.js` | 279 | 14.6 | JS |
| `calc2/static/calc2/13-tax-motion.js` | 236 | 11.8 | JS |
| `calc2/static/calc2/13-number-worker.js` | 13 | 0.8 | JS |
| `calc2/static/calc2/14-input-snap.js` | 95 | 5.2 | JS |
| `calc2/static/calc2/20-plane.js` | 1030 | 70.2 | JS |
| `calc2/static/calc2/30-curves.js` | 1610 | 115.4 | JS |
| `calc2/static/calc2/40-scenes-market.js` | 3908 | 283.1 | JS |
| `calc2/static/calc2/41-market-policies.js` | 271 | 18.0 | JS |
| `calc2/static/calc2/42-scenes-mono.js` | 2100 | 155.3 | JS |
| `calc2/static/calc2/43-discrimination.js` | 182 | 9.9 | JS |
| `calc2/static/calc2/44-scenes-firm.js` | 1075 | 69.5 | JS |
| `calc2/static/calc2/45-plants.js` | 304 | 23.6 | JS |
| `calc2/static/calc2/46-firm-supply.js` | 313 | 32.2 | JS |
| `calc2/static/calc2/47-firm-market.js` | 200 | 19.7 | JS |
| `calc2/static/calc2/46-scenes-labor.js` | 902 | 69.0 | JS |
| `calc2/static/calc2/48-scenes-consumer.js` | 280 | 18.2 | JS |
| `calc2/static/calc2/49-trade-policy.js` | 263 | 27.3 | JS |
| `calc2/static/calc2/50-scenes-macro.js` | 515 | 35.2 | JS |
| `calc2/static/calc2/51-islm.js` | 112 | 14.8 | JS |
| `calc2/static/calc2/52-modes.js` | 996 | 68.4 | JS |
| `calc2/static/calc2/53-adas.js` | 130 | 15.9 | JS |
| `calc2/static/calc2/54-scenes-ppf.js` | 3315 | 213.3 | JS |
| `calc2/static/calc2/55-big-trade.js` | 171 | 14.9 | JS |
| `calc2/static/calc2/56-scenes-inequality.js` | 492 | 34.9 | JS |
| `calc2/static/calc2/57-distributions.js` | 161 | 18.7 | JS |
| `calc2/static/calc2/60-overlays.js` | 5044 | 322.2 | JS |
| `calc2/static/calc2/70-scenes-math.js` | 2187 | 141.9 | JS |
| `calc2/static/calc2/72-export-tex.js` | 1669 | 128.6 | JS |
| `calc2/static/calc2/80-ui.js` | 857 | 54.3 | JS |
| `calc2/static/calc2/82-input.js` | 2368 | 141.2 | JS |
| `calc2/static/calc2/84-picker.js` | 603 | 45.6 | JS |
| `calc2/static/calc2/86-workspace.js` | 2159 | 141.1 | JS |
| `calc2/static/calc2/88-params.js` | 2044 | 140.1 | JS |
| `calc2/static/calc2/89-model-state.js` | 374 | 24.8 | JS |
| `calc2/static/calc2/90-explain.js` | 389 | 69.3 | JS |
| `calc2/static/calc2/91-session.js` | 517 | 27.8 | JS |
| `calc2/static/calc2/92-ui-kit.js` | 1332 | 92.3 | JS |
| `calc2/static/calc2/93-shell.js` | 284 | 17.4 | JS |
| `calc2/static/calc2/94-answer.js` | 1095 | 72.1 | JS |
| `calc2/static/calc2/95-picker-screen.js` | 470 | 26.7 | JS |
| `calc2/static/calc2/96-self.js` | 353 | 23.3 | JS |
| `calc2/static/calc2/99-boot.js` | 112 | 9.5 | JS |

**Итого: 49 файлов, 49633 строк, 3538.4 КБ.**

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
- строка 277 — `evalCurve`
- строка 304 — `detectLinear`
- строка 356 — `curveParamNames`
- строка 371 — `paramSignature`
- строка 376 — `refreshLinearForParams`
- строка 405 — `fmtLinear`
- строка 429 — `compileFormulaP`
- строка 440 — `evalQofP`
- строка 455 — `detectLinearP`
- строка 489 — `invertQofP`
- строка 512 — `buildCurveFromQP`
- строка 537 — `makeVerticalCurve`
- строка 541 — `isVertical`
- строка 547 — `curveZeroQ`
- строка 599 — `frameFloorQ`
- строка 600 — `frameFloorP`
- строка 603 — `naturalSpanQ`
- строка 609 — `eqSearchSpan`
- строка 622 — `bumpModelSpan`
- строка 623 — `modelSpanQ`
- строка 638 — `findEquilibrium`
- строка 698 — `findOffQuadIntersection`
- строка 723 — `bisect`
- строка 735 — `integrate`
- строка 757 — `signChanges`
- строка 773 — `areaBetween`
- строка 784 — `crossingCount`
- строка 805 — `findRoot`
- строка 823 — `invCurve`
- строка 837 — `curveDeriv`
- строка 844 — `compileExt`
- строка 852 — `evalSocial`
- строка 880 — `compileTwoVar`
- строка 890 — `compileTwoVarUncached`
- строка 900 — `evalTwoVar`
- строка 915 — `solveLevelB`
- строка 953 — `traceLevelCurve`
- строка 984 — `partialA`
- строка 989 — `partialB`
- строка 996 — `mrsAt`
- строка 1011 — `optimizeAlongConstraint`
- строка 1075 — `qtyHasCyrillic`
- строка 1080 — `qtyIsQuantity`
- строка 1094 — `qtyParts`
- строка 1152 — `qtyLatex`

#### `calc2/static/calc2/12-numbers.js`

- строка 1 — `CalcNumber`
- строка 5 — `gcd`
- строка 6 — `frac`
- строка 11 — `fixed`
- строка 17 — `fixedRoot`
- строка 24 — `radicalClose`
- строка 28 — `quadratic`
- строка 52 — `relation`
- строка 97 — `recognize`
- строка 122 — `collect`
- строка 129 — `seed`
- строка 137 — `close`
- строка 138 — `decimal`
- строка 144 — `rational`
- строка 154 — `fraction`
- строка 158 — `radical`
- строка 165 — `classify`
- строка 192 — `format`
- строка 204 — `factor`
- строка 209 — `expression`
- строка 219 — `texText`
- строка 229 — `parse`
- строка 251 — `readText`

#### `calc2/static/calc2/13-tax-motion.js`

- строка 3 — `TaxMotion`

#### `calc2/static/calc2/13-number-worker.js`

*(объявлений верхнего уровня не найдено)*

#### `calc2/static/calc2/14-input-snap.js`

- строка 3 — `InputSnap`

#### `calc2/static/calc2/20-plane.js`

- строка 14 — `computeSize`
- строка 54 — `measureText`
- строка 90 — `fixedTaxCoordinateBand`
- строка 95 — `fitMargins`
- строка 149 — `fitLeftForLabels`
- строка 162 — `fitCoordinateMargin`
- строка 192 — `makeScales`
- строка 227 — `clearPanels`
- строка 229 — `registerPanel`
- строка 246 — `panelDist`
- строка 255 — `panelAt`
- строка 267 — `activePanel`
- строка 275 — `panelById`
- строка 290 — `panelWin`
- строка 294 — `resetPanelWins`
- строка 302 — `panelZoomBy`
- строка 320 — `panelPanBy`
- строка 335 — `gesturePanelId`
- строка 363 — `isEconScene`
- строка 369 — `econLo`
- строка 373 — `quadLo`
- строка 396 — `quadPrice`
- строка 406 — `toPx`
- строка 407 — `toData`
- строка 420 — `fmtSum`
- строка 425 — `shownDiff`
- строка 426 — `fmtDiff`
- строка 433 — `fmt`
- строка 441 — `fmtInput`
- строка 450 — `niceTickStep`
- строка 462 — `axisTicks`
- строка 475 — `xTicks`
- строка 476 — `yTicks`
- строка 479 — `addDefs`
- строка 546 — `drawGrid`
- строка 597 — `extraTickX`
- строка 608 — `extraTickY`
- строка 648 — `dropTickAt`
- строка 675 — `coordValue`
- строка 699 — `coordSplit`
- строка 703 — `coordAlreadyAt`
- строка 749 — `resetDrawnKeyPoints`
- строка 752 — `panelOfGlobalScales`
- строка 756 — `kpNode`
- строка 772 — `collectDashes`
- строка 789 — `dashEndsNear`
- строка 801 — `flushDrawnKeyPoints`
- строка 849 — `noteAxisX`
- строка 856 — `noteAxisY`
- строка 863 — `kpName`
- строка 868 — `axisValueX`
- строка 896 — `axisValueY`
- строка 922 — `axisValueText`
- строка 939 — `drawAxes`

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
- строка 354 — `derivativeExpr`
- строка 405 — `curveAnchor`
- строка 516 — `curveLabelSize`
- строка 517 — `labelScale`
- строка 553 — `unclipLabels`
- строка 622 — `keepAxisNamesInside`
- строка 650 — `yieldTicksToCoords`
- строка 679 — `spaceAxisLabelsFromHandles`
- строка 698 — `syncRenameHits`
- строка 710 — `spreadLabels`
- строка 922 — `redrawAfterFonts`
- строка 964 — `parseColor`
- строка 979 — `relLum`
- строка 987 — `contrastOf`
- строка 992 — `rgbToHsl`
- строка 1005 — `hslToRgb`
- строка 1032 — `labelInk`
- строка 1064 — `applyLabelInk`
- строка 1091 — `mixToBg`
- строка 1099 — `applyLabelSize`
- строка 1133 — `smoothLabel`
- строка 1173 — `requestLabelFrame`
- строка 1178 — `resetLabelPositions`
- строка 1188 — `curveLabelAnchor`
- строка 1197 — `labelCurve`
- строка 1283 — `curveWidth`
- строка 1325 — `curveDash`
- строка 1333 — `curveOpacity`
- строка 1341 — `drawCurves`
- строка 1502 — `sceneDrawsCurveList`
- строка 1511 — `syncCurveListVisibility`
- строка 1526 — `curveDragAllowed`
- строка 1570 — `setCurveFreeTerm`

#### `calc2/static/calc2/40-scenes-market.js`

- строка 17 — `curveByRole`
- строка 20 — `curveByRoleAny`
- строка 24 — `recompute`
- строка 551 — `qtyAtPrice`
- строка 561 — `openQuotaName`
- строка 565 — `recomputeOpenEconomy`
- строка 658 — `drawOpenAreas`
- строка 707 — `drawOpenLines`
- строка 755 — `attachOpenPwDrag`
- строка 763 — `setOpenPw`
- строка 776 — `setOpenTool`
- строка 792 — `syncOpenQuotaLabel`
- строка 798 — `updateOpenPanel`
- строка 858 — `drawEquilibrium`
- строка 895 — `drawOffQuadIntersection`
- строка 934 — `offQuadExplainHtml`
- строка 960 — `pctFormExplainHtml`
- строка 998 — `mathTspans`
- строка 1038 — `hasMathMarkup`
- строка 1062 — `markNotationTspan`
- строка 1079 — `mixedNotationRe`
- строка 1087 — `mixedMathTspans`
- строка 1131 — `qtyTspans`
- строка 1168 — `qtyGreekChar`
- строка 1206 — `texToCanvasText`
- строка 1215 — `renderLabelText`
- строка 1236 — `haloText`
- строка 1269 — `pointName`
- строка 1296 — `yWageLabel`
- строка 1301 — `yWageValue`
- строка 1324 — `isMonopolyScene`
- строка 1332 — `eqSectionTitle`
- строка 1349 — `updateEqSectionTitle`
- строка 1366 — `interventionKeyValues`
- строка 1432 — `countCrossings`
- строка 1441 — `updateInfoPanel`
- строка 1550 — `sumSceneOn`
- строка 1553 — `sumGroupsOf`
- строка 1560 — `sumGroupQty`
- строка 1573 — `sumChokePrice`
- строка 1599 — `sumPriceTop`
- строка 1620 — `sumLinearRecord`
- строка 1722 — `curvePiecewiseLinear`
- строка 1725 — `integrateBroken`
- строка 1736 — `curveBreaks`
- строка 1747 — `quadBreaks`
- строка 1763 — `sumSegExpr`
- строка 1780 — `sumPolyline`
- строка 1808 — `sumRebuildSide`
- строка 1859 — `sumSignature`
- строка 1879 — `sumRebuild`
- строка 1899 — `sumAnalyticsKey`
- строка 1917 — `sumGroupName`
- строка 1940 — `sumTagOf`
- строка 1947 — `sumShortTag`
- строка 1976 — `sumGroupColor`
- строка 1981 — `sumStartExpr`
- строка 1989 — `sumReorder`
- строка 1994 — `sumAddGroup`
- строка 2007 — `sumBuildScene`
- строка 2035 — `sumSetCount`
- строка 2054 — `syncSumUi`
- строка 2068 — `sumGroupStats`
- строка 2114 — `sumFinalRecords`
- строка 2132 — `updateSumPanel`
- строка 2193 — `drawAreas`
- строка 2223 — `beforeInterventionNote`
- строка 2232 — `updateAreasPanel`
- строка 2273 — `intervOnBuyer`
- строка 2282 — `drawShiftedSupply`
- строка 2338 — `taxPivotQ`
- строка 2369 — `taxPivotPoint`
- строка 2379 — `drawTaxPivot`
- строка 2414 — `drawTaxAreas`
- строка 2454 — `drawTaxPoints`
- строка 2508 — `attachTaxDrag`
- строка 2533 — `setTax`
- строка 2653 — `taxFormKey`
- строка 2661 — `pctForm`
- строка 2669 — `syncTaxKind`
- строка 2674 — `applyIntervCascade`
- строка 2748 — `setTaxForm`
- строка 2766 — `setType`
- строка 2817 — `rateLetter`
- строка 2821 — `rateUnit`
- строка 2843 — `modelPriceTop`
- строка 2854 — `unitRateMax`
- строка 2864 — `applyPriceRegBounds`
- строка 2873 — `applyTaxRateBounds`
- строка 2908 — `syncQuotaHint`
- строка 2924 — `syncPcHint`
- строка 2932 — `markCurrentIntervHint`
- строка 2941 — `intervHintKey`
- строка 2951 — `intervHintHtml`
- строка 2973 — `syncTaxHint`
- строка 3011 — `setTaxKind`
- строка 3021 — `qpAfter`
- строка 3033 — `updateTaxPanel`
- строка 3169 — `setTaxSide`
- строка 3180 — `setTaxSideButtons`
- строка 3193 — `drawElasticityZones`
- строка 3211 — `drawElasticityPoint`
- строка 3241 — `attachElastDrag`
- строка 3249 — `drawElasticityPointS`
- строка 3269 — `attachElastDragS`
- строка 3277 — `updateElasticityPanel`
- строка 3341 — `drawExtAreas`
- строка 3355 — `drawExtCurves`
- строка 3382 — `drawExtPoints`
- строка 3416 — `drawExtScenario`
- строка 3425 — `updateExtPanel`
- строка 3479 — `setExtSign`
- строка 3488 — `syncSocialFields`
- строка 3516 — `syncExtHint`
- строка 3527 — `socialDefaultExpr`
- строка 3533 — `recompileSocial`
- строка 3555 — `setPRegFields`
- строка 3564 — `setPReg`
- строка 3573 — `drawPcAreas`
- строка 3600 — `drawPriceControl`
- строка 3649 — `attachPcDrag`
- строка 3658 — `updatePcPanel`
- строка 3702 — `setQuotaFields`
- строка 3714 — `setQuota`
- строка 3721 — `setQuotaPos`
- строка 3729 — `setQuotaPrice`
- строка 3736 — `updateQuotaPriceLabel`
- строка 3757 — `drawQuotaAreas`
- строка 3784 — `drawQuotaLines`
- строка 3829 — `attachQuotaDrag`
- строка 3842 — `updateQuotaPanel`
- строка 3889 — `drawGhost`

#### `calc2/static/calc2/41-market-policies.js`

- строка 3 — `taxPairOn`
- строка 7 — `taxPolicy`
- строка 12 — `taxPairPolicies`
- строка 17 — `taxPairRateMax`
- строка 23 — `addSecondTax`
- строка 28 — `removeSecondTax`
- строка 32 — `setSecondTax`
- строка 52 — `taxPairCurve`
- строка 60 — `recomputeTaxPair`
- строка 118 — `syncTaxPairUI`
- строка 179 — `drawTaxPairCurves`
- строка 198 — `drawTaxPairPoints`
- строка 239 — `taxPairExplainHtml`
- строка 248 — `updateTaxPairPanel`

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
- строка 276 — `drawMcDragHandle`
- строка 321 — `drawMonopolyPoints`
- строка 358 — `updateMonoPanel`
- строка 409 — `setMarket`
- строка 444 — `monopolyCeiling`
- строка 495 — `drawMonoCeilingAreas`
- строка 514 — `drawMonoKinkedMR`
- строка 531 — `drawMonoCeilingPoints`
- строка 563 — `drawMonoCeilingLine`
- строка 587 — `monopolyTax`
- строка 610 — `monoBudgetFloor`
- строка 619 — `monopolyFloor`
- строка 661 — `monopolyQuota`
- строка 689 — `drawMonoQuotaAreas`
- строка 711 — `drawMonoQuotaPoints`
- строка 733 — `drawMonoQuotaLine`
- строка 759 — `naturalATC`
- строка 775 — `naturalATCFormula`
- строка 794 — `findRootLast`
- строка 809 — `recomputeNatural`
- строка 838 — `drawNaturalAreas`
- строка 853 — `drawNaturalCurves`
- строка 876 — `drawNaturalPoints`
- строка 916 — `drawNaturalFull`
- строка 924 — `updateNaturalPanel`
- строка 963 — `drawMonoTaxAreas`
- строка 999 — `drawMonoTaxShiftedMC`
- строка 1017 — `drawMonoTaxPoints`
- строка 1038 — `drawMonoFloorAreas`
- строка 1053 — `drawMonoFloorPoints`
- строка 1073 — `drawMonoFloorLine`
- строка 1088 — `updateMonoInterventionPanel`
- строка 1226 — `makeCurve`
- строка 1242 — `segExpr`
- строка 1249 — `kinkedDemandExpr`
- строка 1260 — `drawDiscr1`
- строка 1293 — `updateDiscr1Panel`
- строка 1320 — `allocateMR`
- строка 1346 — `recomputeDiscr3`
- строка 1405 — `drawMiniMarket`
- строка 1512 — `redrawDiscr3`
- строка 1555 — `drawMonoExport`
- строка 1680 — `updateDiscr3Panel`
- строка 1767 — `applyD3WorldLabels`
- строка 1790 — `buildKinkedDemand`
- строка 1810 — `sumDemandCurves`
- строка 1847 — `recomputeKinked`
- строка 1894 — `drawKinkedFull`
- строка 1983 — `updateKinkPanel`
- строка 2025 — `applyMonoVisibility`
- строка 2046 — `ensureMonopolyCurves`
- строка 2057 — `fillIfEmpty`
- строка 2060 — `ensureD3Fields`
- строка 2065 — `ensureKinkFields`
- строка 2071 — `ensureMonopolyPreset`
- строка 2078 — `setMonoMode`
- строка 2089 — `setKinkInput`

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
- строка 435 — `redrawCosts`
- строка 472 — `recomputeLongRun`
- строка 542 — `drawLongRunArea`
- строка 550 — `fillLongRunArea`
- строка 574 — `drawLongRunMarks`
- строка 579 — `fillLongRunMarks`
- строка 611 — `drawLongRunHandle`
- строка 625 — `setLrPrice`
- строка 633 — `syncLrPriceFields`
- строка 651 — `beginLrDrag`
- строка 653 — `dragLrPrice`
- строка 668 — `endLrDrag`
- строка 675 — `updateLongRunPanel`
- строка 719 — `prodEval`
- строка 729 — `prodDerivative`
- строка 743 — `prodMP`
- строка 750 — `prodAP`
- строка 758 — `maxOf`
- строка 785 — `realMax`
- строка 787 — `recomputeProduction`
- строка 806 — `redrawProduction`
- строка 924 — `noMaxNote`
- строка 933 — `updateProdPanel`
- строка 958 — `recomputeIsoquant`
- строка 969 — `redrawIsoquant`
- строка 985 — `updateIsoPanel`
- строка 1015 — `setPlantsView`
- строка 1022 — `setPlantsQ`
- строка 1033 — `setCostsInputMode`
- строка 1041 — `syncCostsInputMode`
- строка 1055 — `setCostsSub`

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
- строка 200 — `plantsShownAt`
- строка 201 — `plantsExpr`
- строка 208 — `redrawPlants`
- строка 242 — `plantsFinalRecord`
- строка 256 — `updatePlantsPanel`
- строка 280 — `renderPlantRows`

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
- строка 271 — `drawFirmSupply`
- строка 290 — `firmCostExpressions`
- строка 294 — `renderFirmSupplyControls`

#### `calc2/static/calc2/47-firm-market.js`

- строка 2 — `firmMarketBisect`
- строка 5 — `firmMarketDemand`
- строка 20 — `firmMarketContains`
- строка 26 — `firmMarketSolve`
- строка 93 — `renderFirmMarketControls`
- строка 107 — `firmMarketScaledRecord`
- строка 113 — `updateFirmMarketPanel`
- строка 134 — `firmMarketPanel`
- строка 158 — `firmMarketDrawSupply`
- строка 172 — `redrawFirmMarket`

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
- строка 742 — `setLaborStruct`
- строка 759 — `updateLaborPanel`
- строка 863 — `redrawLabor`

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
- строка 254 — `applyConsumerTypeUI`
- строка 268 — `setConsumerType`

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
- строка 231 — `drawTradeCountryAreas`
- строка 239 — `drawTradeCountryLines`
- строка 246 — `drawTradeMono`

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
- строка 501 — `setMacroModel`

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
- строка 39 — `syncViewFields`
- строка 75 — `updateResetViewBtn`
- строка 92 — `markViewDirty`
- строка 113 — `prefersReducedMotion`
- строка 118 — `animateRanges`
- строка 150 — `applyTradeRanges`
- строка 178 — `scheduleRangeAnim`
- строка 197 — `padMax`
- строка 215 — `curveAxisBounds`
- строка 246 — `boundsOfDrawn`
- строка 286 — `redrawKeepingWindow`
- строка 292 — `applyAutoRanges`
- строка 321 — `zoomRound`
- строка 327 — `zoomBy`
- строка 412 — `panByPixels`
- строка 492 — `wantedRanges`
- строка 517 — `modelAnswerPoints`
- строка 536 — `requestFormulaFit`
- строка 565 — `growRanges`
- строка 582 — `growWindowToModel`
- строка 604 — `resetZoom`
- строка 648 — `flushWheel`
- строка 659 — `initZoom`
- строка 855 — `zoomStep`
- строка 864 — `cancelRangeAnim`
- строка 871 — `ineqRedraw`
- строка 874 — `setMode`
- строка 957 — `applyScenarioVisibility`
- строка 983 — `setScenario`

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

- строка 22 — `ppfAffine`
- строка 45 — `parsePpfEquation`
- строка 78 — `parseYofX`
- строка 94 — `makeInverseF`
- строка 114 — `makeImplicitF`
- строка 136 — `compilePpf`
- строка 157 — `evalPpf`
- строка 164 — `ppfSlope`
- строка 171 — `clampPpfX`
- строка 183 — `ppfTypeLabel`
- строка 195 — `recomputePpf`
- строка 224 — `evalPpf2`
- строка 234 — `bundleRay`
- строка 255 — `bundleSlopeAt`
- строка 262 — `bundleDragTo`
- строка 283 — `tradeBundleGain`
- строка 304 — `ppfMark`
- строка 315 — `ppfMarkArea`
- строка 325 — `ppfExplicitExpr`
- строка 331 — `drawPpfCurve`
- строка 393 — `drawBundleRay`
- строка 471 — `ppfOppAt`
- строка 477 — `updatePpfPanel`
- строка 568 — `redrawPpf`
- строка 622 — `ppfEvalWith`
- строка 654 — `ppfSlopeOf`
- строка 667 — `ppfXmaxOf`
- строка 681 — `fitLinear`
- строка 705 — `ppfTouchXmax`
- строка 750 — `ppfFitsOnGrid`
- строка 765 — `classifyPpf`
- строка 840 — `ppfFitR2`
- строка 862 — `niceMax`
- строка 870 — `singlePpfPoints`
- строка 877 — `findRootIn`
- строка 889 — `interpY`
- строка 903 — `maxAllocY`
- строка 929 — `combinedPpfPoints`
- строка 939 — `allocAt`
- строка 970 — `detectCombinedKinks`
- строка 1045 — `ppfCoefTex`
- строка 1052 — `ppfNum`
- строка 1062 — `ppfSnap`
- строка 1074 — `ppfPiecesToExpr`
- строка 1091 — `ppfLinearExpr`
- строка 1098 — `combinedPpfLinearRecord`
- строка 1275 — `ppfPoly2Xmax`
- строка 1294 — `ppfCostOf`
- строка 1303 — `ppfValid`
- строка 1311 — `ppfFam`
- строка 1312 — `ppfClamp`
- строка 1323 — `ppfReduceActive`
- строка 1342 — `ppfPieceTex`
- строка 1392 — `ppfPoly2Terms`
- строка 1402 — `ppfPolyJoin`
- строка 1418 — `ppfPieceBody`
- строка 1456 — `ppfPieceAt`
- строка 1469 — `ppfPiecesRecord`
- строка 1517 — `ppfSumByEqualCost`
- строка 1622 — `ppfSumByEnvelope`
- строка 1711 — `ppfEnvPiece`
- строка 1722 — `ppfMergeSameLine`
- строка 1742 — `ppfCostKinds`
- строка 1751 — `ppfCostValue`
- строка 1761 — `ppfWhyNumeric`
- строка 1814 — `ppfSumMixedPair`
- строка 1979 — `ppfSumAnalytic`
- строка 1997 — `combinedPpfFormula`
- строка 2033 — `verifyFormula`
- строка 2044 — `detectKinks`
- строка 2069 — `showPaneError`
- строка 2080 — `ppfSumCount`
- строка 2081 — `ppfSumGet`
- строка 2086 — `ppfSumSet`
- строка 2091 — `ppfSumName`
- строка 2095 — `ppfSumColor`
- строка 2109 — `ppfSumSignature`
- строка 2119 — `recomputePpfSum`
- строка 2125 — `ensurePpfSum`
- строка 2129 — `recomputePpfSumRaw`
- строка 2241 — `renderPpfSumRows`
- строка 2292 — `detectSumKinks`
- строка 2310 — `drawPpfSumCurves`
- строка 2342 — `drawPpfSumMarks`
- строка 2368 — `updatePpfSumPanel`
- строка 2486 — `fmtRu`
- строка 2490 — `ppfSumSchemaData`
- строка 2524 — `schemaNote`
- строка 2531 — `drawPpfSumSchema`
- строка 2583 — `redrawPpfSum`
- строка 2596 — `setPpfSumView`
- строка 2607 — `cornerByValue`
- строка 2631 — `bestByValue`
- строка 2654 — `ppfOcRange`
- строка 2668 — `recomputePpfTrade`
- строка 2733 — `drawPpfTrade`
- строка 2761 — `drawPpfTradeMarks`
- строка 2789 — `updatePpfTradePanel`
- строка 2942 — `syncPpftPriceUI`
- строка 2953 — `redrawPpfTrade`
- строка 2968 — `recomputeTradeB`
- строка 3061 — `tradeCpfPoints`
- строка 3079 — `tradeCpfMark`
- строка 3098 — `tradeBPanels`
- строка 3119 — `drawTradeB`
- строка 3192 — `drawTradeBMarks`
- строка 3195 — `tbName`
- строка 3201 — `updateTradeBPanel`
- строка 3261 — `syncTbPriceUI`
- строка 3274 — `redrawTradeB`
- строка 3289 — `setTradeScenario`
- строка 3301 — `setPpfSub`

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
- строка 93 — `bigTradeSyncPriceWindow`
- строка 98 — `bigTradePanelBand`
- строка 103 — `bigTradeCountryPlot`
- строка 129 — `bigTradeWorldPlot`
- строка 147 — `redrawBigTrade`
- строка 167 — `bigTradeSmallLegend`

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
- строка 387 — `redrawInequality`
- строка 438 — `defaultGroupShares`
- строка 445 — `setIneqInput`
- строка 462 — `setIneqAlpha`
- строка 469 — `setIneqGroupN`
- строка 481 — `setIneqRedistTool`
- строка 492 — `renderIneqGroupsTable`

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

- строка 11 — `redrawAll`
- строка 110 — `redrawScene`
- строка 259 — `redrawGraphMode`
- строка 271 — `renderMmRows`
- строка 317 — `graphRowsBox`
- строка 320 — `renderGraphRows`
- строка 339 — `graphError`
- строка 346 — `buildGraphRow`
- строка 428 — `equipGraphRows`
- строка 436 — `graphRowInput`
- строка 481 — `mainScales`
- строка 492 — `drawOverlays`
- строка 601 — `guardedPanelIds`
- строка 605 — `guardPanelBoxes`
- строка 641 — `panelsChangedSinceLastPass`
- строка 646 — `markPanelsChanged`
- строка 649 — `flushPendingPanelClears`
- строка 658 — `refreshAnalyticsPanel`
- строка 686 — `typesetStats`
- строка 740 — `addStatSign`
- строка 754 — `statToTex`
- строка 792 — `katexVisibleText`
- строка 796 — `restatWide`
- строка 842 — `statInkWidth`
- строка 850 — `statTooWide`
- строка 859 — `statPieces`
- строка 894 — `texAbbrev`
- строка 900 — `renderMathIn`
- строка 943 — `areaKey`
- строка 948 — `subDigits`
- строка 953 — `applyAreaColors`
- строка 963 — `currentAreas`
- строка 981 — `areaOfPathEl`
- строка 1043 — `areaShort`
- строка 1052 — `drawLegend`
- строка 1116 — `floatRects`
- строка 1136 — `legendCorner`
- строка 1213 — `viewWindow`
- строка 1225 — `axisWords`
- строка 1231 — `crossPoints`
- строка 1333 — `invalidateKeyTargets`
- строка 1336 — `kinksOf`
- строка 1384 — `keyTargets`
- строка 1559 — `snapVertexAt`
- строка 1591 — `markPanelId`
- строка 1611 — `armedPanelId`
- строка 1617 — `drawCrossPoints`
- строка 1766 — `armCurve`
- строка 1772 — `disarmCurve`
- строка 1780 — `keyPointLit`
- строка 1793 — `drawCurveHits`
- строка 1833 — `pinKeyPoint`
- строка 1853 — `hoverLabel`
- строка 1864 — `drawRoller`
- строка 1885 — `rollerTargetAt`
- строка 1915 — `rollerClampX`
- строка 1934 — `rollerMove`
- строка 1950 — `showRollTip`
- строка 1973 — `hideRollTip`
- строка 1982 — `rollerOff`
- строка 1993 — `curveRightEdge`
- строка 2018 — `axisXLetter`
- строка 2028 — `axisLetter`
- строка 2041 — `armVerts`
- строка 2083 — `markServiceNodes`
- строка 2100 — `syncCanvasMode`
- строка 2122 — `leaveCanvasMode`
- строка 2128 — `finishCanvasMode`
- строка 2133 — `addAreaVert`
- строка 2146 — `vertPanels`
- строка 2149 — `vertsMixed`
- строка 2151 — `clearAreaVerts`
- строка 2156 — `renderVertList`
- строка 2165 — `syncAreaCalcButton`
- строка 2191 — `areaPickedCurve`
- строка 2200 — `areaCurveRange`
- строка 2218 — `syncAreaRangeLabel`
- строка 2257 — `freshenVertNames`
- строка 2275 — `drawAreaVerts`
- строка 2304 — `areaTargets`
- строка 2308 — `calcAreaUnderCurve`
- строка 2321 — `ringArea`
- строка 2331 — `segCross`
- строка 2338 — `ringSelfCrosses`
- строка 2360 — `angleRing`
- строка 2366 — `bestAreaRing`
- строка 2396 — `calcAreaPolygon`
- строка 2413 — `AREA_PALETTE`
- строка 2423 — `areaLive`
- строка 2444 — `areasLive`
- строка 2446 — `runAreaCalc`
- строка 2458 — `pushArea`
- строка 2479 — `addPolyArea`
- строка 2492 — `syncPtsSelBar`
- строка 2514 — `clearAreaCalc`
- строка 2521 — `drawAreaCalc`
- строка 2562 — `renameCommit`
- строка 2568 — `areaById`
- строка 2569 — `areaVertsLabel`
- строка 2576 — `updateAreaCalcPanel`
- строка 2644 — `openAreaMenu`
- строка 2689 — `syncAreaCalcUI`
- строка 2728 — `updateQuickArea`
- строка 2738 — `curveNameInto`
- строка 2742 — `buildAreaCurveButtons`
- строка 2776 — `pickAreaCurve`
- строка 2784 — `syncAreaCurveButtons`
- строка 2803 — `setAreaCalcMode`
- строка 2818 — `closeAreaBuild`
- строка 2824 — `cancelAreaBuild`
- строка 2836 — `finishPolyBuild`
- строка 2845 — `wireFolds`
- строка 2870 — `wireAreaCalc`
- строка 2905 — `paramsAllowed`
- строка 2930 — `isReservedName`
- строка 2970 — `expandImplicitMul`
- строка 3016 — `visibleSvgText`
- строка 3042 — `chartLabelSource`
- строка 3052 — `chartLabelBase`
- строка 3069 — `chartLabelKind`
- строка 3083 — `typesetChartLabels`
- строка 3111 — `prepExpr`
- строка 3129 — `texToPlain`
- строка 3155 — `sceneReservedKey`
- строка 3159 — `freeSymbols`
- строка 3177 — `freeSymbolsUncached`
- строка 3205 — `sceneReserved`
- строка 3231 — `sceneExtraParams`
- строка 3237 — `paramValue`
- строка 3243 — `paramScope`
- строка 3253 — `scopeFor`
- строка 3260 — `evalWithParams`
- строка 3271 — `syncParams`
- строка 3327 — `buildParamChip`
- строка 3452 — `initSceneColorPickers`
- строка 3464 — `syncSceneColorPickers`
- строка 3472 — `syncAxisPlaceholders`
- строка 3487 — `titleAnchorPx`
- строка 3497 — `drawGraphTitle`
- строка 3536 — `editGraphTitleOnCanvas`
- строка 3581 — `normHex`
- строка 3603 — `paletteSix`
- строка 3611 — `closeColorMenu`
- строка 3625 — `onDocClosePick`
- строка 3631 — `onEscClosePick`
- строка 3651 — `paletteTwelve`
- строка 3652 — `makeColorPicker`
- строка 3764 — `autoCurveName`
- строка 3773 — `curveShortName`
- строка 3783 — `markCaption`
- строка 3792 — `drawMarks`
- строка 3896 — `snapTargets`
- строка 3904 — `snapTargetsAll`
- строка 4052 — `macroSnapTargets`
- строка 4071 — `consumerSnapTargets`
- строка 4100 — `ineqSnapTargets`
- строка 4114 — `mathSnapTargets`
- строка 4196 — `tradeSnapTargets`
- строка 4217 — `axisSnapAt`
- строка 4237 — `snapDistPx`
- строка 4258 — `snapPointAt`
- строка 4301 — `showSnapHint`
- строка 4320 — `armMark`
- строка 4333 — `cancelMarkDraft`
- строка 4373 — `resetDecor`
- строка 4465 — `_undoCopyChild`
- строка 4479 — `_undoCopy`
- строка 4499 — `pushUndo`
- строка 4510 — `undoLast`
- строка 4527 — `clearUndo`
- строка 4534 — `forgetSceneSnapshot`
- строка 4536 — `resetSceneMemory`
- строка 4547 — `saveSceneSnapshot`
- строка 4560 — `restoreSceneSnapshot`
- строка 4588 — `keyOnText`
- строка 4595 — `markOnText`
- строка 4605 — `notationTex`
- строка 4612 — `markOnInto`
- строка 4621 — `markNameTex`
- строка 4628 — `addMarkAt`
- строка 4668 — `colorDist`
- строка 4677 — `drawnStrokeColors`
- строка 4693 — `nextMarkColor`
- строка 4716 — `canvasNameLetters`
- строка 4728 — `nextMarkName`
- строка 4740 — `newMark`
- строка 4756 — `pendingMark`
- строка 4759 — `startMarkDraft`
- строка 4768 — `markSnapFn`
- строка 4779 — `renderMarkList`
- строка 4791 — `ensureAddMarkButton`
- строка 4802 — `buildMarkRow`
- строка 4958 — `markById`
- строка 4959 — `openMarkMenu`
- строка 4972 — `fillMarkMenu`
- строка 5014 — `renameMark`
- строка 5029 — `editMarkCoords`
- строка 5038 — `removeMark`

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
- строка 715 — `makeRenamable`
- строка 761 — `editPointName`
- строка 785 — `editInlineLabel`
- строка 866 — `tangentLayout`
- строка 875 — `tangentPanelAt`
- строка 883 — `tanWin`
- строка 893 — `tanResetWindows`
- строка 898 — `tanScales`
- строка 906 — `drawMathTangent`
- строка 1037 — `drawMathOptimum`
- строка 1077 — `drawMathTransform`
- строка 1098 — `labelCurveMath`
- строка 1129 — `mmSlots`
- строка 1130 — `mmGet`
- строка 1133 — `mmSet`
- строка 1138 — `mmLabel`
- строка 1140 — `mmColor`
- строка 1149 — `mmParts`
- строка 1172 — `drawMathMinMax`
- строка 1219 — `compileAB`
- строка 1232 — `parseConstraint`
- строка 1250 — `constraintContoursIn`
- строка 1302 — `constraintPointsIn`
- строка 1305 — `constraintPoints`
- строка 1312 — `optimizeAlongCurve`
- строка 1367 — `constraintFit`
- строка 1391 — `drawMathConstraint`
- строка 1454 — `drawLevelCurveOn`
- строка 1470 — `mathOptimumReasoning`
- строка 1507 — `updateMathPanel`
- строка 1659 — `redrawMath`
- строка 1699 — `setMathSub`
- строка 1722 — `setMathWindow`
- строка 1737 — `setMathX0`
- строка 1762 — `downloadBlob`
- строка 1771 — `exportBaseName`
- строка 1784 — `paperChartClone`
- строка 1813 — `exportNumbersLine`
- строка 1822 — `exportExtras`
- строка 1830 — `exportPNG`
- строка 1871 — `buildTex`
- строка 1880 — `afterFonts`
- строка 1885 — `exportTex`
- строка 1895 — `exportPDF`
- строка 1902 — `exportPDFSend`
- строка 1926 — `exportTitleDefault`
- строка 1928 — `buildExportFields`
- строка 1958 — `refreshExportPreview`
- строка 1996 — `expValue`
- строка 2007 — `syncExportFormat`
- строка 2019 — `refreshExportSheet`
- строка 2027 — `wireExport`
- строка 2056 — `openExport`
- строка 2077 — `closeExport`
- строка 2097 — `updateGraphPanel`
- строка 2159 — `graphExplainNote`

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
- строка 682 — `refreshCurveRow`
- строка 699 — `curveToSingleFormula`

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
- строка 950 — `isUndefinedTailNode`
- строка 955 — `unwrapParens`
- строка 966 — `pwCondTex`
- строка 985 — `condChainToCases`
- строка 1007 — `mathToLatexField`
- строка 1029 — `upgradeFormulaField`
- строка 1079 — `fitFormulaField`
- строка 1153 — `fitFormulaFields`
- строка 1156 — `fitFormulaFieldsSoon`
- строка 1176 — `fieldOnScreen`
- строка 1188 — `flushMathfieldsSoon`
- строка 1194 — `flushMathfields`
- строка 1232 — `katexSafe`
- строка 1268 — `katexInto`
- строка 1283 — `placeholderTex`
- строка 1292 — `texSafeText`
- строка 1296 — `buildMathfield`
- строка 1481 — `setFormulaFieldQuiet`
- строка 1503 — `insertIntoField`
- строка 1522 — `keyboardAdapter`
- строка 1524 — `insert`
- строка 1525 — `deleteBack`
- строка 1530 — `clear`
- строка 1534 — `piecewise`
- строка 1543 — `buildKeyboard`
- строка 1553 — `addHowToTab`
- строка 1590 — `closeAllKeyboardsExcept`
- строка 1629 — `formulaInputError`
- строка 1664 — `markFormulaField`
- строка 1672 — `syncFormulaEditBases`
- строка 1688 — `onFormulaInput`
- строка 1752 — `scheduleParamsSync`
- строка 1758 — `registerFormulaField`
- строка 1775 — `fieldActive`
- строка 1784 — `liveFormulaTexts`
- строка 1820 — `equipFormulaField`
- строка 1857 — `equipAllFormulaFields`
- строка 1861 — `attachFormulaHelp`
- строка 2051 — `makeEditableValue`
- строка 2157 — `makeToggle`
- строка 2199 — `segToToggle`
- строка 2231 — `closeAllSelectMenus`
- строка 2235 — `upgradeSelect`
- строка 2336 — `upgradeTextField`
- строка 2359 — `upgradeTextFieldsIn`

#### `calc2/static/calc2/84-picker.js`

- строка 8 — `loadScene`
- строка 17 — `loadScenePreset`
- строка 157 — `closePicker`
- строка 179 — `openPicker`
- строка 352 — `baseScene`
- строка 361 — `applyCardScope`
- строка 439 — `blockSpec`
- строка 451 — `foldPickerGroups`
- строка 538 — `plural`
- строка 546 — `pickScene`

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
- строка 255 — `texifyName`
- строка 285 — `editEqValue`
- строка 367 — `centerBandOn`
- строка 371 — `pullIntoBand`
- строка 375 — `attachBoundsEditor`
- строка 456 — `refreshRegulators`
- строка 467 — `makePchip`
- строка 495 — `curveShiftBase`
- строка 505 — `pultShiftHalf`
- строка 509 — `resetPultShiftHalf`
- строка 512 — `buildPultCurveChips`
- строка 603 — `syncPultCurveValues`
- строка 626 — `capturePultHome`
- строка 633 — `capturePultHomes`
- строка 638 — `returnPultHome`
- строка 650 — `syncPultRegulators`
- строка 681 — `upgradeRegulator`
- строка 867 — `boundText`
- строка 868 — `shortRegulatorName`
- строка 894 — `ppfLinearFormula`
- строка 899 — `ppfInterceptsOf`
- строка 907 — `ppfSetSingle`
- строка 915 — `ppfSetSum`
- строка 935 — `addPultXChip`
- строка 962 — `buildPultExtra`
- строка 995 — `ineqParseIncomes`
- строка 998 — `ineqMasterRebase`
- строка 1003 — `ineqMasterScale`
- строка 1024 — `ineqMasterApply`
- строка 1035 — `ineqMasterDetach`
- строка 1040 — `buildIneqMasterChip`
- строка 1053 — `showPult`
- строка 1080 — `updatePult`
- строка 1115 — `liveFormula`
- строка 1135 — `wireControls`

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

- строка 45 — `histOf`
- строка 57 — `histSig`
- строка 67 — `captureOpenUi`
- строка 73 — `restoreOpenUi`
- строка 90 — `applyKeepView`
- строка 102 — `historyBaseline`
- строка 112 — `historyCheck`
- строка 145 — `historyAfterRedraw`
- строка 153 — `historyTouch`
- строка 161 — `historyMark`
- строка 166 — `historyUndo`
- строка 179 — `historyRedo`
- строка 191 — `historyCan`
- строка 195 — `historyClearAll`
- строка 197 — `notifyHistory`
- строка 203 — `histLabelOf`
- строка 219 — `storeGet`
- строка 220 — `storeSet`
- строка 225 — `compactModelState`
- строка 239 — `expandModelState`
- строка 248 — `autosaveModel`
- строка 262 — `forgetAutosaves`
- строка 272 — `savedModel`
- строка 278 — `recentModels`
- строка 284 — `writeModelToUrl`
- строка 294 — `dropShareHash`
- строка 310 — `fromProblemOf`
- строка 314 — `dropFromParam`
- строка 323 — `showBackToProblem`
- строка 330 — `hideBackToProblem`
- строка 335 — `openFromProblem`
- строка 346 — `b64urlEncode`
- строка 350 — `b64urlDecode`
- строка 387 — `openModelByUser`
- строка 408 — `restoreOnLoad`
- строка 447 — `viewDefaults`
- строка 484 — `resetModelWithUndo`

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
- строка 337 — `answerIsMath`
- строка 341 — `labelCopy`
- строка 352 — `answerNumberItem`
- строка 358 — `answerValueInto`
- строка 404 — `answerGroupHead`
- строка 427 — `segNoteOn`
- строка 431 — `buildSegNote`
- строка 445 — `hideDrainedBlocks`
- строка 490 — `retypesetSeenRows`
- строка 514 — `remeasureStatsAfterFonts`
- строка 529 — `answerReflow`
- строка 540 — `answerCells`
- строка 596 — `buildAnswer`
- строка 736 — `hideEchoes`
- строка 770 — `markFirstSection`
- строка 803 — `decorateTables`
- строка 837 — `liftTableHead`
- строка 865 — `answerRow`
- строка 917 — `burdenOn`
- строка 924 — `burdenNoteText`
- строка 931 — `buildBurden`
- строка 964 — `buildStatus`
- строка 991 — `buildExplainAccordion`
- строка 1056 — `questionsWord`
- строка 1062 — `syncExplainBar`

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

**Итого функций в индексе: 1594.**

<!-- AUTO:END -->
