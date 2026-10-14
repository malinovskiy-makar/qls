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

*Автоматически собрано командой `manage.py calc2_map`. Дата: 2026-10-14. HEAD: `bd90b57c`. Не редактировать руками — вся эта часть файла, от отметки начала автосекции и до отметки её конца, перезаписывается заново при каждом запуске команды.*

### Файлы (маршрут → представление → шаблон → статика)

| Путь | Строк | КБ | Тип |
|---|---:|---:|---|
| `calc2/urls.py` | 19 | 0.6 | python |
| `calc2/views.py` | 224 | 13.4 | python |
| `calc2/templates/calc2/calc2.html` | 2293 | 184.4 | шаблон |
| `calc2/static/calc2/calc2.css` | 4036 | 300.6 | CSS |
| `calc2/static/calc2/previews.json` | 44 | 30.7 | json |
| `calc2/static/calc2/00-config.js` | 576 | 49.8 | JS |
| `calc2/static/calc2/10-math-core.js` | 1126 | 73.5 | JS |
| `calc2/static/calc2/20-plane.js` | 993 | 67.4 | JS |
| `calc2/static/calc2/30-curves.js` | 1452 | 105.7 | JS |
| `calc2/static/calc2/40-scenes-market.js` | 3778 | 271.0 | JS |
| `calc2/static/calc2/42-scenes-mono.js` | 1832 | 133.9 | JS |
| `calc2/static/calc2/44-scenes-firm.js` | 1204 | 79.8 | JS |
| `calc2/static/calc2/46-scenes-labor.js` | 755 | 54.4 | JS |
| `calc2/static/calc2/48-scenes-consumer.js` | 265 | 16.3 | JS |
| `calc2/static/calc2/50-scenes-macro.js` | 425 | 28.9 | JS |
| `calc2/static/calc2/52-modes.js` | 956 | 65.5 | JS |
| `calc2/static/calc2/54-scenes-ppf.js` | 3275 | 211.8 | JS |
| `calc2/static/calc2/56-scenes-inequality.js` | 555 | 36.3 | JS |
| `calc2/static/calc2/60-overlays.js` | 4796 | 304.0 | JS |
| `calc2/static/calc2/70-scenes-math.js` | 2084 | 135.9 | JS |
| `calc2/static/calc2/72-export-tex.js` | 1661 | 127.7 | JS |
| `calc2/static/calc2/80-ui.js` | 696 | 43.1 | JS |
| `calc2/static/calc2/82-input.js` | 2235 | 132.0 | JS |
| `calc2/static/calc2/84-picker.js` | 580 | 43.9 | JS |
| `calc2/static/calc2/86-workspace.js` | 2156 | 140.9 | JS |
| `calc2/static/calc2/88-params.js` | 1962 | 133.2 | JS |
| `calc2/static/calc2/89-model-state.js` | 357 | 23.0 | JS |
| `calc2/static/calc2/90-explain.js` | 381 | 63.1 | JS |
| `calc2/static/calc2/91-session.js` | 502 | 26.6 | JS |
| `calc2/static/calc2/92-ui-kit.js` | 788 | 51.0 | JS |
| `calc2/static/calc2/93-shell.js` | 282 | 17.0 | JS |
| `calc2/static/calc2/94-answer.js` | 910 | 58.2 | JS |
| `calc2/static/calc2/95-picker-screen.js` | 470 | 26.7 | JS |
| `calc2/static/calc2/96-self.js` | 322 | 21.4 | JS |
| `calc2/static/calc2/99-boot.js` | 112 | 9.5 | JS |

**Итого: 35 файлов, 44102 строк, 3081.2 КБ.**

### Индекс функций (объявления верхнего уровня, по возрастанию строки)

#### `calc2/static/calc2/00-config.js`

- строка 71 — `fsStep`
- строка 471 — `cssVar`
- строка 475 — `refreshColors`
- строка 555 — `canvasMode`
- строка 561 — `canvasArmed`
- строка 567 — `roleColor`

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
- строка 629 — `spreadLabels`
- строка 802 — `parseColor`
- строка 817 — `relLum`
- строка 825 — `contrastOf`
- строка 830 — `rgbToHsl`
- строка 843 — `hslToRgb`
- строка 870 — `labelInk`
- строка 902 — `applyLabelInk`
- строка 929 — `mixToBg`
- строка 937 — `applyLabelSize`
- строка 971 — `smoothLabel`
- строка 1001 — `requestLabelFrame`
- строка 1006 — `resetLabelPositions`
- строка 1016 — `curveLabelAnchor`
- строка 1025 — `labelCurve`
- строка 1111 — `curveWidth`
- строка 1153 — `curveDash`
- строка 1161 — `curveOpacity`
- строка 1169 — `drawCurves`
- строка 1330 — `sceneDrawsCurveList`
- строка 1339 — `syncCurveListVisibility`
- строка 1354 — `curveDragAllowed`
- строка 1364 — `roundDrag`
- строка 1406 — `setCurveFreeTerm`

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
- строка 2840 — `syncPcHint`
- строка 2848 — `markCurrentIntervHint`
- строка 2857 — `intervHintKey`
- строка 2867 — `intervHintHtml`
- строка 2889 — `syncTaxHint`
- строка 2927 — `setTaxKind`
- строка 2933 — `updateTaxPanel`
- строка 3066 — `setTaxSide`
- строка 3077 — `setTaxSideButtons`
- строка 3090 — `drawElasticityZones`
- строка 3108 — `drawElasticityPoint`
- строка 3137 — `attachElastDrag`
- строка 3145 — `drawElasticityPointS`
- строка 3165 — `attachElastDragS`
- строка 3173 — `updateElasticityPanel`
- строка 3237 — `drawExtAreas`
- строка 3251 — `drawExtCurves`
- строка 3278 — `drawExtPoints`
- строка 3312 — `drawExtScenario`
- строка 3321 — `updateExtPanel`
- строка 3362 — `setExtSign`
- строка 3371 — `syncSocialFields`
- строка 3399 — `syncExtHint`
- строка 3410 — `socialDefaultExpr`
- строка 3416 — `recompileSocial`
- строка 3438 — `setPRegFields`
- строка 3447 — `setPReg`
- строка 3456 — `drawPcAreas`
- строка 3483 — `drawPriceControl`
- строка 3532 — `attachPcDrag`
- строка 3541 — `updatePcPanel`
- строка 3586 — `setQuotaFields`
- строка 3598 — `setQuota`
- строка 3605 — `setQuotaPos`
- строка 3615 — `updateQuotaPriceLabel`
- строка 3627 — `drawQuotaAreas`
- строка 3654 — `drawQuotaLines`
- строка 3699 — `attachQuotaDrag`
- строка 3712 — `updateQuotaPanel`
- строка 3759 — `drawGhost`

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
- строка 152 — `mcDragCurve`
- строка 157 — `mcDragStep`
- строка 161 — `drawMcDragHandle`
- строка 202 — `drawMonopolyPoints`
- строка 239 — `updateMonoPanel`
- строка 270 — `setMarket`
- строка 305 — `monopolyCeiling`
- строка 353 — `drawMonoCeilingAreas`
- строка 372 — `drawMonoKinkedMR`
- строка 389 — `drawMonoCeilingPoints`
- строка 421 — `drawMonoCeilingLine`
- строка 445 — `monopolyTax`
- строка 470 — `monopolyFloor`
- строка 512 — `monopolyQuota`
- строка 540 — `drawMonoQuotaAreas`
- строка 562 — `drawMonoQuotaPoints`
- строка 584 — `drawMonoQuotaLine`
- строка 610 — `naturalATC`
- строка 622 — `naturalATCFormula`
- строка 641 — `findRootLast`
- строка 656 — `recomputeNatural`
- строка 685 — `drawNaturalAreas`
- строка 700 — `drawNaturalCurves`
- строка 723 — `drawNaturalPoints`
- строка 752 — `drawNaturalFull`
- строка 760 — `updateNaturalPanel`
- строка 798 — `drawMonoTaxAreas`
- строка 834 — `drawMonoTaxShiftedMC`
- строка 852 — `drawMonoTaxPoints`
- строка 873 — `drawMonoFloorAreas`
- строка 888 — `drawMonoFloorPoints`
- строка 908 — `drawMonoFloorLine`
- строка 923 — `updateMonoInterventionPanel`
- строка 1056 — `makeCurve`
- строка 1066 — `segExpr`
- строка 1073 — `kinkedDemandExpr`
- строка 1084 — `drawDiscr1`
- строка 1115 — `updateDiscr1Panel`
- строка 1140 — `allocateMR`
- строка 1153 — `recomputeDiscr3`
- строка 1193 — `drawMiniMarket`
- строка 1300 — `redrawDiscr3`
- строка 1343 — `drawMonoExport`
- строка 1467 — `updateDiscr3Panel`
- строка 1530 — `applyD3WorldLabels`
- строка 1552 — `buildKinkedDemand`
- строка 1599 — `recomputeKinked`
- строка 1639 — `drawKinkedFull`
- строка 1728 — `updateKinkPanel`
- строка 1757 — `applyMonoVisibility`
- строка 1778 — `ensureMonopolyCurves`
- строка 1789 — `fillIfEmpty`
- строка 1792 — `ensureD3Fields`
- строка 1797 — `ensureKinkFields`
- строка 1803 — `ensureMonopolyPreset`
- строка 1810 — `setMonoMode`
- строка 1821 — `setKinkInput`

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
- строка 402 — `redrawCosts`
- строка 437 — `recomputeLongRun`
- строка 506 — `drawLongRunArea`
- строка 514 — `fillLongRunArea`
- строка 538 — `drawLongRunMarks`
- строка 543 — `fillLongRunMarks`
- строка 575 — `drawLongRunHandle`
- строка 586 — `setLrPrice`
- строка 594 — `syncLrPriceFields`
- строка 612 — `beginLrDrag`
- строка 614 — `dragLrPrice`
- строка 629 — `endLrDrag`
- строка 636 — `updateLongRunPanel`
- строка 679 — `prodEval`
- строка 687 — `prodMP`
- строка 692 — `prodAP`
- строка 700 — `maxOf`
- строка 720 — `realMax`
- строка 722 — `recomputeProduction`
- строка 741 — `redrawProduction`
- строка 857 — `noMaxNote`
- строка 866 — `updateProdPanel`
- строка 890 — `recomputeIsoquant`
- строка 901 — `redrawIsoquant`
- строка 917 — `updateIsoPanel`
- строка 954 — `plantMC`
- строка 960 — `plantTC`
- строка 966 — `plantQatMC`
- строка 982 — `recomputePlants`
- строка 1016 — `plantsAt`
- строка 1033 — `redrawPlants`
- строка 1114 — `updatePlantsPanel`
- строка 1144 — `setPlantsView`
- строка 1151 — `setPlantsQ`
- строка 1162 — `setCostsInputMode`
- строка 1170 — `syncCostsInputMode`
- строка 1184 — `setCostsSub`

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
- строка 602 — `setLaborStruct`
- строка 625 — `updateLaborPanel`
- строка 716 — `redrawLabor`

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
- строка 413 — `setMacroModel`

#### `calc2/static/calc2/52-modes.js`

- строка 14 — `setRanges`
- строка 37 — `syncViewFields`
- строка 73 — `updateResetViewBtn`
- строка 90 — `markViewDirty`
- строка 110 — `prefersReducedMotion`
- строка 115 — `animateRanges`
- строка 146 — `applyTradeRanges`
- строка 172 — `scheduleRangeAnim`
- строка 191 — `padMax`
- строка 209 — `curveAxisBounds`
- строка 240 — `boundsOfDrawn`
- строка 280 — `redrawKeepingWindow`
- строка 285 — `applyAutoRanges`
- строка 312 — `zoomRound`
- строка 318 — `zoomBy`
- строка 403 — `panByPixels`
- строка 483 — `wantedRanges`
- строка 516 — `growRanges`
- строка 532 — `growWindowToModel`
- строка 548 — `resetZoom`
- строка 593 — `flushWheel`
- строка 604 — `initZoom`
- строка 800 — `zoomStep`
- строка 809 — `cancelRangeAnim`
- строка 821 — `makeThrottle`
- строка 834 — `ineqRedraw`
- строка 837 — `setMode`
- строка 917 — `applyScenarioVisibility`
- строка 943 — `setScenario`

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
- строка 1430 — `ppfPiecesRecord`
- строка 1469 — `ppfSumByEqualCost`
- строка 1574 — `ppfSumByEnvelope`
- строка 1663 — `ppfEnvPiece`
- строка 1674 — `ppfMergeSameLine`
- строка 1694 — `ppfCostKinds`
- строка 1703 — `ppfCostValue`
- строка 1713 — `ppfWhyNumeric`
- строка 1766 — `ppfSumMixedPair`
- строка 1931 — `ppfSumAnalytic`
- строка 1949 — `combinedPpfFormula`
- строка 1985 — `verifyFormula`
- строка 1996 — `detectKinks`
- строка 2021 — `showPaneError`
- строка 2032 — `ppfSumCount`
- строка 2033 — `ppfSumGet`
- строка 2038 — `ppfSumSet`
- строка 2043 — `ppfSumName`
- строка 2047 — `ppfSumColor`
- строка 2061 — `ppfSumSignature`
- строка 2071 — `recomputePpfSum`
- строка 2077 — `ensurePpfSum`
- строка 2081 — `recomputePpfSumRaw`
- строка 2192 — `renderPpfSumRows`
- строка 2243 — `detectSumKinks`
- строка 2261 — `drawPpfSumCurves`
- строка 2293 — `drawPpfSumMarks`
- строка 2319 — `updatePpfSumPanel`
- строка 2435 — `fmtRu`
- строка 2439 — `ppfSumSchemaData`
- строка 2473 — `schemaNote`
- строка 2480 — `drawPpfSumSchema`
- строка 2532 — `redrawPpfSum`
- строка 2545 — `setPpfSumView`
- строка 2556 — `cornerByValue`
- строка 2580 — `bestByValue`
- строка 2603 — `ppfOcRange`
- строка 2617 — `recomputePpfTrade`
- строка 2682 — `drawPpfTrade`
- строка 2710 — `drawPpfTradeMarks`
- строка 2738 — `updatePpfTradePanel`
- строка 2890 — `syncPpftPriceUI`
- строка 2901 — `redrawPpfTrade`
- строка 2922 — `recomputeTradeB`
- строка 3011 — `tradeCpfPoints`
- строка 3029 — `tradeCpfMark`
- строка 3048 — `tradeBPanels`
- строка 3069 — `drawTradeB`
- строка 3142 — `drawTradeBMarks`
- строка 3145 — `tbName`
- строка 3151 — `updateTradeBPanel`
- строка 3221 — `syncTbPriceUI`
- строка 3234 — `redrawTradeB`
- строка 3249 — `setTradeScenario`
- строка 3261 — `setPpfSub`

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
- строка 80 — `redrawScene`
- строка 227 — `redrawGraphMode`
- строка 239 — `renderMmRows`
- строка 284 — `graphRowsBox`
- строка 287 — `renderGraphRows`
- строка 305 — `graphError`
- строка 312 — `buildGraphRow`
- строка 394 — `equipGraphRows`
- строка 402 — `graphRowInput`
- строка 447 — `mainScales`
- строка 458 — `drawOverlays`
- строка 566 — `guardedPanelIds`
- строка 570 — `guardPanelBoxes`
- строка 606 — `panelsChangedSinceLastPass`
- строка 611 — `markPanelsChanged`
- строка 614 — `flushPendingPanelClears`
- строка 623 — `refreshAnalyticsPanel`
- строка 651 — `typesetStats`
- строка 703 — `addStatSign`
- строка 716 — `statToTex`
- строка 754 — `katexVisibleText`
- строка 760 — `restatWide`
- строка 806 — `statInkWidth`
- строка 814 — `statTooWide`
- строка 823 — `statPieces`
- строка 858 — `texAbbrev`
- строка 864 — `renderMathIn`
- строка 907 — `areaKey`
- строка 912 — `subDigits`
- строка 917 — `applyAreaColors`
- строка 927 — `currentAreas`
- строка 945 — `areaOfPathEl`
- строка 1007 — `areaShort`
- строка 1016 — `drawLegend`
- строка 1079 — `floatRects`
- строка 1099 — `legendCorner`
- строка 1176 — `viewWindow`
- строка 1188 — `axisWords`
- строка 1194 — `crossPoints`
- строка 1296 — `invalidateKeyTargets`
- строка 1299 — `kinksOf`
- строка 1347 — `keyTargets`
- строка 1522 — `snapVertexAt`
- строка 1554 — `markPanelId`
- строка 1574 — `armedPanelId`
- строка 1580 — `drawCrossPoints`
- строка 1729 — `armCurve`
- строка 1735 — `disarmCurve`
- строка 1743 — `keyPointLit`
- строка 1756 — `drawCurveHits`
- строка 1794 — `pinKeyPoint`
- строка 1814 — `hoverLabel`
- строка 1825 — `drawRoller`
- строка 1846 — `rollerTargetAt`
- строка 1876 — `rollerClampX`
- строка 1895 — `rollerMove`
- строка 1911 — `showRollTip`
- строка 1934 — `hideRollTip`
- строка 1943 — `rollerOff`
- строка 1954 — `curveRightEdge`
- строка 1979 — `axisXLetter`
- строка 1989 — `axisLetter`
- строка 2002 — `armVerts`
- строка 2043 — `markServiceNodes`
- строка 2060 — `syncCanvasMode`
- строка 2082 — `leaveCanvasMode`
- строка 2088 — `finishCanvasMode`
- строка 2093 — `addAreaVert`
- строка 2106 — `vertPanels`
- строка 2109 — `vertsMixed`
- строка 2111 — `clearAreaVerts`
- строка 2117 — `renderVertList`
- строка 2189 — `syncAreaCalcButton`
- строка 2215 — `areaPickedCurve`
- строка 2224 — `areaCurveRange`
- строка 2242 — `syncAreaRangeLabel`
- строка 2281 — `freshenVertNames`
- строка 2297 — `drawAreaVerts`
- строка 2370 — `areaTargets`
- строка 2374 — `calcAreaUnderCurve`
- строка 2387 — `ringArea`
- строка 2397 — `segCross`
- строка 2404 — `ringSelfCrosses`
- строка 2426 — `angleRing`
- строка 2432 — `bestAreaRing`
- строка 2462 — `calcAreaPolygon`
- строка 2479 — `AREA_PALETTE`
- строка 2481 — `runAreaCalc`
- строка 2502 — `clearAreaCalc`
- строка 2509 — `drawAreaCalc`
- строка 2545 — `updateAreaCalcPanel`
- строка 2646 — `syncAreaCalcUI`
- строка 2685 — `updateQuickArea`
- строка 2695 — `curveNameInto`
- строка 2699 — `buildAreaCurveButtons`
- строка 2733 — `pickAreaCurve`
- строка 2741 — `syncAreaCurveButtons`
- строка 2760 — `setAreaCalcMode`
- строка 2775 — `closeAreaBuild`
- строка 2781 — `cancelAreaBuild`
- строка 2792 — `finishPolyBuild`
- строка 2803 — `wireFolds`
- строка 2828 — `wireAreaCalc`
- строка 2867 — `paramsAllowed`
- строка 2892 — `isReservedName`
- строка 2932 — `expandImplicitMul`
- строка 2978 — `visibleSvgText`
- строка 3004 — `chartLabelSource`
- строка 3014 — `chartLabelBase`
- строка 3031 — `chartLabelKind`
- строка 3045 — `typesetChartLabels`
- строка 3073 — `prepExpr`
- строка 3091 — `texToPlain`
- строка 3117 — `sceneReservedKey`
- строка 3121 — `freeSymbols`
- строка 3139 — `freeSymbolsUncached`
- строка 3167 — `sceneReserved`
- строка 3190 — `sceneExtraParams`
- строка 3196 — `paramValue`
- строка 3202 — `paramScope`
- строка 3212 — `scopeFor`
- строка 3219 — `evalWithParams`
- строка 3230 — `syncParams`
- строка 3286 — `buildParamChip`
- строка 3411 — `initSceneColorPickers`
- строка 3423 — `syncSceneColorPickers`
- строка 3431 — `syncAxisPlaceholders`
- строка 3446 — `titleAnchorPx`
- строка 3456 — `drawGraphTitle`
- строка 3495 — `editGraphTitleOnCanvas`
- строка 3540 — `normHex`
- строка 3562 — `paletteSix`
- строка 3570 — `closeColorMenu`
- строка 3584 — `onDocClosePick`
- строка 3588 — `onEscClosePick`
- строка 3604 — `paletteTwelve`
- строка 3605 — `makeColorPicker`
- строка 3717 — `autoCurveName`
- строка 3726 — `curveShortName`
- строка 3736 — `markCaption`
- строка 3745 — `drawMarks`
- строка 3845 — `snapTargets`
- строка 3853 — `snapTargetsAll`
- строка 3981 — `macroSnapTargets`
- строка 4000 — `consumerSnapTargets`
- строка 4029 — `ineqSnapTargets`
- строка 4043 — `mathSnapTargets`
- строка 4108 — `tradeSnapTargets`
- строка 4129 — `axisSnapAt`
- строка 4149 — `snapDistPx`
- строка 4170 — `snapPointAt`
- строка 4213 — `showSnapHint`
- строка 4232 — `armMark`
- строка 4245 — `cancelMarkDraft`
- строка 4285 — `resetDecor`
- строка 4377 — `_undoCopyChild`
- строка 4391 — `_undoCopy`
- строка 4411 — `pushUndo`
- строка 4422 — `undoLast`
- строка 4439 — `clearUndo`
- строка 4446 — `forgetSceneSnapshot`
- строка 4448 — `resetSceneMemory`
- строка 4459 — `saveSceneSnapshot`
- строка 4472 — `restoreSceneSnapshot`
- строка 4497 — `keyOnText`
- строка 4504 — `markOnText`
- строка 4515 — `addMarkAt`
- строка 4554 — `colorDist`
- строка 4563 — `drawnStrokeColors`
- строка 4579 — `nextMarkColor`
- строка 4595 — `newMark`
- строка 4609 — `pendingMark`
- строка 4612 — `startMarkDraft`
- строка 4621 — `markSnapFn`
- строка 4631 — `renderMarkList`
- строка 4644 — `ensureAddMarkButton`
- строка 4655 — `buildMarkRow`

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
- строка 653 — `resetLabelBoxes`
- строка 654 — `dodgeLabel`
- строка 666 — `mathDot`
- строка 710 — `makeRenamable`
- строка 753 — `editPointName`
- строка 777 — `editInlineLabel`
- строка 858 — `tangentLayout`
- строка 867 — `tangentPanelAt`
- строка 875 — `tanWin`
- строка 885 — `tanResetWindows`
- строка 890 — `tanScales`
- строка 898 — `drawMathTangent`
- строка 1027 — `drawMathOptimum`
- строка 1067 — `drawMathTransform`
- строка 1088 — `labelCurveMath`
- строка 1118 — `mmSlots`
- строка 1119 — `mmGet`
- строка 1122 — `mmSet`
- строка 1127 — `mmLabel`
- строка 1129 — `mmColor`
- строка 1138 — `mmParts`
- строка 1161 — `drawMathMinMax`
- строка 1208 — `compileAB`
- строка 1221 — `parseConstraint`
- строка 1239 — `constraintPointsIn`
- строка 1258 — `constraintPoints`
- строка 1263 — `optimizeAlongCurve`
- строка 1276 — `constraintFit`
- строка 1294 — `drawMathConstraint`
- строка 1356 — `drawLevelCurveOn`
- строка 1370 — `mathOptimumReasoning`
- строка 1407 — `updateMathPanel`
- строка 1559 — `redrawMath`
- строка 1599 — `setMathSub`
- строка 1622 — `setMathWindow`
- строка 1637 — `setMathX0`
- строка 1662 — `downloadBlob`
- строка 1671 — `exportBaseName`
- строка 1684 — `paperChartClone`
- строка 1711 — `exportNumbersLine`
- строка 1720 — `exportExtras`
- строка 1728 — `exportPNG`
- строка 1769 — `buildTex`
- строка 1778 — `afterFonts`
- строка 1783 — `exportTex`
- строка 1793 — `exportPDF`
- строка 1800 — `exportPDFSend`
- строка 1824 — `exportTitleDefault`
- строка 1826 — `buildExportFields`
- строка 1856 — `refreshExportPreview`
- строка 1894 — `expValue`
- строка 1905 — `syncExportFormat`
- строка 1917 — `refreshExportSheet`
- строка 1925 — `wireExport`
- строка 1954 — `openExport`
- строка 1975 — `closeExport`
- строка 1995 — `updateGraphPanel`
- строка 2056 — `graphExplainNote`

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
- строка 522 — `refreshCurveRow`
- строка 538 — `curveToSingleFormula`

#### `calc2/static/calc2/82-input.js`

- строка 11 — `texFallback`
- строка 18 — `mathToTex`
- строка 35 — `renderTex`
- строка 44 — `renderTexRaw`
- строка 58 — `onKatexReady`
- строка 88 — `pwCond`
- строка 97 — `pwRows`
- строка 118 — `pwPrefixOf`
- строка 123 — `pwFormula`
- строка 142 — `pwLatex`
- строка 164 — `pwVar`
- строка 189 — `casesToNarrow`
- строка 202 — `isNarrowCases`
- строка 206 — `casesUnwrapNarrow`
- строка 221 — `casesToMath`
- строка 252 — `condToMath`
- строка 263 — `renderPw`
- строка 334 — `pwSyncHead`
- строка 349 — `pwSetCount`
- строка 360 — `pwAddRow`
- строка 377 — `pwRemoveRow`
- строка 388 — `pwCheck`
- строка 412 — `pwAttachKeyboard`
- строка 434 — `pwPreview`
- строка 474 — `pwVarForField`
- строка 502 — `pwDefaultRows`
- строка 508 — `pwBalanced`
- строка 521 — `pwSplitTernary`
- строка 545 — `pwCondBounds`
- строка 566 — `pwParse`
- строка 602 — `pwSplitRows`
- строка 626 — `openPiecewise`
- строка 644 — `closePiecewise`
- строка 653 — `insertIntoFormula`
- строка 683 — `mathfieldClass`
- строка 687 — `onMathliveReady`
- строка 723 — `fieldProblem`
- строка 773 — `unknownTexCommand`
- строка 782 — `texGroup`
- строка 792 — `latexToMath`
- строка 938 — `isUndefinedTailNode`
- строка 943 — `unwrapParens`
- строка 954 — `pwCondTex`
- строка 973 — `condChainToCases`
- строка 995 — `mathToLatexField`
- строка 1017 — `upgradeFormulaField`
- строка 1066 — `fitFormulaField`
- строка 1117 — `fitFormulaFields`
- строка 1120 — `fitFormulaFieldsSoon`
- строка 1135 — `fieldOnScreen`
- строка 1147 — `flushMathfieldsSoon`
- строка 1153 — `flushMathfields`
- строка 1187 — `katexSafe`
- строка 1223 — `katexInto`
- строка 1238 — `placeholderTex`
- строка 1247 — `texSafeText`
- строка 1251 — `buildMathfield`
- строка 1429 — `setFormulaFieldQuiet`
- строка 1451 — `insertIntoField`
- строка 1470 — `keyboardAdapter`
- строка 1472 — `insert`
- строка 1473 — `deleteBack`
- строка 1478 — `clear`
- строка 1482 — `piecewise`
- строка 1491 — `buildKeyboard`
- строка 1501 — `addHowToTab`
- строка 1538 — `closeAllKeyboardsExcept`
- строка 1577 — `formulaInputError`
- строка 1600 — `markFormulaField`
- строка 1607 — `onFormulaInput`
- строка 1629 — `scheduleParamsSync`
- строка 1635 — `registerFormulaField`
- строка 1652 — `fieldActive`
- строка 1661 — `liveFormulaTexts`
- строка 1688 — `equipFormulaField`
- строка 1725 — `equipAllFormulaFields`
- строка 1729 — `attachFormulaHelp`
- строка 1919 — `makeEditableValue`
- строка 2024 — `makeToggle`
- строка 2066 — `segToToggle`
- строка 2098 — `closeAllSelectMenus`
- строка 2102 — `upgradeSelect`
- строка 2203 — `upgradeTextField`
- строка 2226 — `upgradeTextFieldsIn`

#### `calc2/static/calc2/84-picker.js`

- строка 8 — `loadScene`
- строка 147 — `closePicker`
- строка 169 — `openPicker`
- строка 332 — `baseScene`
- строка 341 — `applyCardScope`
- строка 419 — `blockSpec`
- строка 431 — `foldPickerGroups`
- строка 518 — `plural`
- строка 526 — `pickScene`

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
- строка 320 — `answerNotesToExplain`
- строка 369 — `syncAnalyticsPanel`
- строка 453 — `sectionIcon`
- строка 464 — `cardifySections`
- строка 556 — `collapseCards`
- строка 574 — `syncLabelSizeSeg`
- строка 585 — `openSection`
- строка 622 — `cardWithFormula`
- строка 635 — `syncFirstCard`
- строка 654 — `wireScene`
- строка 823 — `resetCurrentScene`
- строка 833 — `setWrenchOpen`
- строка 843 — `applyViewBounds`
- строка 870 — `quadWindow`
- строка 875 — `quadSameWindow`
- строка 894 — `offQuadShownPoints`
- строка 924 — `fitWindowToOffQuad`
- строка 946 — `setFirstQuad`
- строка 996 — `setGridMode`
- строка 1014 — `hintTip`
- строка 1041 — `fitTipMath`
- строка 1064 — `showHintTip`
- строка 1122 — `hideHintTip`
- строка 1147 — `tipText`
- строка 1176 — `tipTex`
- строка 1186 — `tipName`
- строка 1203 — `tipExpr`
- строка 1213 — `tipPlain`
- строка 1242 — `ffEsc`
- строка 1252 — `ffLatexOf`
- строка 1274 — `finalFunctionHtml`
- строка 1299 — `ffParseCases`
- строка 1321 — `ffCondCompact`
- строка 1345 — `ffMathHtml`
- строка 1369 — `ffKatexW`
- строка 1385 — `ffFitCases`
- строка 1472 — `fitFinalMath`
- строка 1501 — `ffCopyText`
- строка 1509 — `ffCopyFallback`
- строка 1521 — `wireFinalCopy`
- строка 1554 — `ffOpenExpand`
- строка 1575 — `ffCloseExpand`
- строка 1587 — `setFinalFunctions`
- строка 1605 — `refitFinalMathSoon`
- строка 1633 — `markNotationsIn`
- строка 1665 — `paintNotation`
- строка 1675 — `showTipFor`
- строка 1681 — `wireTips`
- строка 1733 — `syncTipLabels`
- строка 1746 — `hintAnchor`
- строка 1827 — `fitPanelMath`
- строка 1857 — `syncHintDots`
- строка 1872 — `hintsToDots`
- строка 1911 — `wireHintButtons`
- строка 1953 — `wireWrench`
- строка 2079 — `fillPrintBlocks`
- строка 2109 — `setPrintViewBox`

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
- строка 280 — `editEqValue`
- строка 347 — `centerBandOn`
- строка 351 — `pullIntoBand`
- строка 355 — `attachBoundsEditor`
- строка 437 — `refreshRegulators`
- строка 448 — `makePchip`
- строка 476 — `curveShiftBase`
- строка 486 — `pultShiftHalf`
- строка 490 — `resetPultShiftHalf`
- строка 493 — `buildPultCurveChips`
- строка 583 — `syncPultCurveValues`
- строка 606 — `capturePultHome`
- строка 613 — `capturePultHomes`
- строка 618 — `returnPultHome`
- строка 630 — `syncPultRegulators`
- строка 659 — `upgradeRegulator`
- строка 823 — `shortRegulatorName`
- строка 849 — `ppfLinearFormula`
- строка 855 — `ppfInterceptsOf`
- строка 863 — `ppfSetSingle`
- строка 871 — `ppfSetSum`
- строка 891 — `addPultXChip`
- строка 918 — `buildPultExtra`
- строка 950 — `ineqParseIncomes`
- строка 953 — `ineqMasterRebase`
- строка 958 — `ineqMasterScale`
- строка 976 — `ineqMasterApply`
- строка 988 — `ineqMasterDetach`
- строка 993 — `buildIneqMasterChip`
- строка 1005 — `showPult`
- строка 1032 — `updatePult`
- строка 1064 — `liveFormula`
- строка 1074 — `wireControls`

#### `calc2/static/calc2/89-model-state.js`

- строка 40 — `plainCopy`
- строка 77 — `togglesInOrder`
- строка 86 — `isDisclosureBtn`
- строка 89 — `formNodes`
- строка 94 — `captureForm`
- строка 119 — `applyForm`
- строка 168 — `captureStatePlain`
- строка 177 — `applyStatePlain`
- строка 184 — `rerenderModelLists`
- строка 202 — `forceRebuildAfterApply`
- строка 208 — `syncUiFromState`
- строка 215 — `capturePristine`
- строка 226 — `restorePristine`
- строка 246 — `captureMemory`
- строка 251 — `applyMemory`
- строка 274 — `serializeCurves`
- строка 287 — `rebuildCurves`
- строка 307 — `modelKeyOf`
- строка 312 — `collectModelState`
- строка 332 — `applyModelState`

#### `calc2/static/calc2/90-explain.js`

- строка 375 — `sceneExplainHtml`

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
- строка 617 — `paintCard`
- строка 679 — `scOn`
- строка 680 — `scProw`
- строка 681 — `scParamAnchor`
- строка 690 — `scSetup`
- строка 762 — `scSync`
- строка 771 — `applyAreaHidden`
- строка 785 — `vgFormIds`

#### `calc2/static/calc2/93-shell.js`

- строка 11 — `modelBlockOf`
- строка 16 — `syncModelHead`
- строка 28 — `syncZoomLevel`
- строка 44 — `setFocusMode`
- строка 54 — `afterColumnShown`
- строка 71 — `syncToolSeg`
- строка 78 — `setPtsMode`
- строка 103 — `setTool`
- строка 122 — `answerHidden`
- строка 123 — `setAnswerHidden`
- строка 135 — `showAnswerForSelf`
- строка 138 — `wireAnswerHide`
- строка 149 — `wireShell`
- строка 233 — `phMoreLayout`
- строка 267 — `wirePhoneMore`

#### `calc2/static/calc2/94-answer.js`

- строка 111 — `heroLabel`
- строка 127 — `notationTex`
- строка 139 — `plainText`
- строка 145 — `statRows`
- строка 149 — `txRow`
- строка 171 — `answerSignature`
- строка 188 — `scheduleAnswer`
- строка 199 — `answerIsMath`
- строка 203 — `labelCopy`
- строка 215 — `answerValueInto`
- строка 261 — `answerGroupHead`
- строка 284 — `segNoteOn`
- строка 288 — `buildSegNote`
- строка 302 — `hideDrainedBlocks`
- строка 347 — `retypesetSeenRows`
- строка 371 — `remeasureStatsAfterFonts`
- строка 386 — `answerReflow`
- строка 396 — `buildAnswer`
- строка 563 — `hideEchoes`
- строка 597 — `markFirstSection`
- строка 630 — `decorateTables`
- строка 659 — `liftTableHead`
- строка 687 — `answerRow`
- строка 733 — `burdenOn`
- строка 739 — `burdenNoteText`
- строка 746 — `buildBurden`
- строка 779 — `buildStatus`
- строка 806 — `buildExplainAccordion`
- строка 871 — `questionsWord`
- строка 877 — `syncExplainBar`

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

**Итого функций в индексе: 1322.**

<!-- AUTO:END -->
