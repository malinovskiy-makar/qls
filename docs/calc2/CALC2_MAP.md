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
| Экспорт `.tex`/PDF: кривая или площадь на бумаге не совпадает с экраном, PDF не собирается | `calc2/views.py` (`compile_pdf_pdflatex`, `_TEX_FORBIDDEN`, `pdflatex_available`); `70-scenes-math.js` (`buildTex`, `mathToPgf` — сборка идёт из состояния и SVG вперемешку, не только из `STATE`, см. «Фаза L откачена» в CLAUDE.md) |
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

*Автоматически собрано командой `manage.py calc2_map`. Дата: 2026-08-26. HEAD: `1afaa83`. Не редактировать руками — вся эта часть файла, от отметки начала автосекции и до отметки её конца, перезаписывается заново при каждом запуске команды.*

### Файлы (маршрут → представление → шаблон → статика)

| Путь | Строк | КБ | Тип |
|---|---:|---:|---|
| `calc2/urls.py` | 19 | 0.6 | python |
| `calc2/views.py` | 207 | 11.9 | python |
| `calc2/templates/calc2/calc2.html` | 2465 | 199.9 | шаблон |
| `calc2/static/calc2/calc2.css` | 2187 | 152.4 | CSS |
| `calc2/static/calc2/00-config.js` | 546 | 46.1 | JS |
| `calc2/static/calc2/10-math-core.js` | 942 | 61.3 | JS |
| `calc2/static/calc2/20-plane.js` | 708 | 49.4 | JS |
| `calc2/static/calc2/30-curves.js` | 1317 | 96.0 | JS |
| `calc2/static/calc2/40-scenes-market.js` | 3431 | 238.3 | JS |
| `calc2/static/calc2/42-scenes-mono.js` | 1200 | 84.5 | JS |
| `calc2/static/calc2/44-scenes-firm.js` | 1201 | 79.4 | JS |
| `calc2/static/calc2/46-scenes-labor.js` | 736 | 53.1 | JS |
| `calc2/static/calc2/48-scenes-consumer.js` | 261 | 15.7 | JS |
| `calc2/static/calc2/50-scenes-macro.js` | 416 | 28.4 | JS |
| `calc2/static/calc2/52-modes.js` | 827 | 55.7 | JS |
| `calc2/static/calc2/54-scenes-ppf.js` | 2622 | 169.9 | JS |
| `calc2/static/calc2/56-scenes-inequality.js` | 532 | 34.0 | JS |
| `calc2/static/calc2/60-overlays.js` | 4206 | 259.8 | JS |
| `calc2/static/calc2/70-scenes-math.js` | 2428 | 154.1 | JS |
| `calc2/static/calc2/80-ui.js` | 526 | 33.2 | JS |
| `calc2/static/calc2/82-input.js` | 2030 | 116.8 | JS |
| `calc2/static/calc2/84-picker.js` | 570 | 41.3 | JS |
| `calc2/static/calc2/86-workspace.js` | 1659 | 104.6 | JS |
| `calc2/static/calc2/88-params.js` | 1800 | 118.5 | JS |
| `calc2/static/calc2/90-explain.js` | 381 | 63.1 | JS |
| `calc2/static/calc2/99-boot.js` | 92 | 7.5 | JS |

**Итого: 26 файлов, 33309 строк, 2275.6 КБ.**

### Индекс функций (объявления верхнего уровня, по возрастанию строки)

#### `calc2/static/calc2/00-config.js`

- строка 71 — `fsStep`
- строка 442 — `cssVar`
- строка 446 — `refreshColors`
- строка 519 — `canvasMode`
- строка 524 — `canvasArmed`
- строка 530 — `roleColor`
- строка 536 — `setCalcTheme`
- строка 542 — `toggleCalcTheme`

#### `calc2/static/calc2/10-math-core.js`

- строка 17 — `topLevelEqIndex`
- строка 36 — `axisScope`
- строка 42 — `compileFormula`
- строка 58 — `evalCurve`
- строка 76 — `detectLinear`
- строка 128 — `curveParamNames`
- строка 143 — `paramSignature`
- строка 148 — `refreshLinearForParams`
- строка 180 — `fmtLinear`
- строка 204 — `compileFormulaP`
- строка 215 — `evalQofP`
- строка 230 — `detectLinearP`
- строка 264 — `invertQofP`
- строка 287 — `buildCurveFromQP`
- строка 312 — `makeVerticalCurve`
- строка 316 — `isVertical`
- строка 322 — `curveZeroQ`
- строка 374 — `frameFloorQ`
- строка 375 — `frameFloorP`
- строка 378 — `naturalSpanQ`
- строка 384 — `eqSearchSpan`
- строка 397 — `bumpModelSpan`
- строка 398 — `modelSpanQ`
- строка 413 — `findEquilibrium`
- строка 473 — `findOffQuadIntersection`
- строка 498 — `bisect`
- строка 510 — `integrate`
- строка 532 — `signChanges`
- строка 548 — `areaBetween`
- строка 559 — `crossingCount`
- строка 580 — `findRoot`
- строка 598 — `invCurve`
- строка 612 — `curveDeriv`
- строка 619 — `compileExt`
- строка 627 — `evalSocial`
- строка 655 — `compileTwoVar`
- строка 665 — `compileTwoVarUncached`
- строка 675 — `evalTwoVar`
- строка 687 — `solveLevelB`
- строка 725 — `traceLevelCurve`
- строка 750 — `partialA`
- строка 755 — `partialB`
- строка 762 — `mrsAt`
- строка 774 — `optimizeAlongConstraint`
- строка 838 — `qtyHasCyrillic`
- строка 843 — `qtyIsQuantity`
- строка 857 — `qtyParts`
- строка 915 — `qtyLatex`

#### `calc2/static/calc2/20-plane.js`

- строка 12 — `computeSize`
- строка 43 — `measureText`
- строка 77 — `fitMargins`
- строка 128 — `fitLeftForLabels`
- строка 141 — `makeScales`
- строка 168 — `isEconScene`
- строка 174 — `econLo`
- строка 178 — `quadLo`
- строка 201 — `quadPrice`
- строка 211 — `toPx`
- строка 212 — `toData`
- строка 228 — `roundShown`
- строка 237 — `fmtSum`
- строка 243 — `shownDiff`
- строка 244 — `fmtDiff`
- строка 256 — `shownDecimals`
- строка 264 — `sumDecimals`
- строка 268 — `fmt`
- строка 289 — `fmtInput`
- строка 299 — `niceTickStep`
- строка 311 — `axisTicks`
- строка 324 — `xTicks`
- строка 325 — `yTicks`
- строка 328 — `addDefs`
- строка 388 — `drawGrid`
- строка 439 — `extraTickX`
- строка 450 — `extraTickY`
- строка 490 — `dropTickAt`
- строка 517 — `coordValue`
- строка 537 — `coordAlreadyAt`
- строка 548 — `axisValueX`
- строка 575 — `axisValueY`
- строка 600 — `axisValueText`
- строка 617 — `drawAxes`

#### `calc2/static/calc2/30-curves.js`

- строка 8 — `nextColor`
- строка 73 — `piecewiseNodesQ`
- строка 101 — `pointsFromNodes`
- строка 118 — `curvePoints`
- строка 174 — `drawMarginalCurve`
- строка 236 — `markExpr`
- строка 259 — `derivativeExpr`
- строка 298 — `curveAnchor`
- строка 404 — `curveLabelSize`
- строка 405 — `labelScale`
- строка 441 — `unclipLabels`
- строка 510 — `keepAxisNamesInside`
- строка 527 — `spreadLabels`
- строка 700 — `parseColor`
- строка 715 — `relLum`
- строка 723 — `contrastOf`
- строка 728 — `rgbToHsl`
- строка 741 — `hslToRgb`
- строка 768 — `labelInk`
- строка 800 — `applyLabelInk`
- строка 827 — `mixToBg`
- строка 835 — `applyLabelSize`
- строка 866 — `smoothLabel`
- строка 896 — `requestLabelFrame`
- строка 901 — `resetLabelPositions`
- строка 910 — `curveLabelAnchor`
- строка 919 — `labelCurve`
- строка 990 — `curveWidth`
- строка 1032 — `curveDash`
- строка 1040 — `curveOpacity`
- строка 1048 — `drawCurves`
- строка 1209 — `sceneDrawsCurveList`
- строка 1218 — `syncCurveListVisibility`
- строка 1233 — `curveDragAllowed`
- строка 1243 — `roundDrag`
- строка 1281 — `setCurveFreeTerm`

#### `calc2/static/calc2/40-scenes-market.js`

- строка 7 — `curveByRole`
- строка 11 — `recompute`
- строка 456 — `recomputeOpenEconomy`
- строка 521 — `drawOpenAreas`
- строка 558 — `drawOpenLines`
- строка 605 — `attachOpenPwDrag`
- строка 613 — `setOpenPw`
- строка 623 — `setOpenTool`
- строка 635 — `updateOpenPanel`
- строка 671 — `drawEquilibrium`
- строка 708 — `drawOffQuadIntersection`
- строка 745 — `offQuadExplainHtml`
- строка 771 — `pctFormExplainHtml`
- строка 808 — `mathTspans`
- строка 848 — `hasMathMarkup`
- строка 872 — `markNotationTspan`
- строка 889 — `mixedNotationRe`
- строка 897 — `mixedMathTspans`
- строка 941 — `qtyTspans`
- строка 978 — `qtyGreekChar`
- строка 1016 — `texToCanvasText`
- строка 1025 — `renderLabelText`
- строка 1046 — `haloText`
- строка 1079 — `pointName`
- строка 1102 — `yWageLabel`
- строка 1107 — `yWageValue`
- строка 1130 — `isMonopolyScene`
- строка 1138 — `eqSectionTitle`
- строка 1154 — `updateEqSectionTitle`
- строка 1171 — `interventionKeyValues`
- строка 1222 — `countCrossings`
- строка 1231 — `updateInfoPanel`
- строка 1332 — `sumSceneOn`
- строка 1335 — `sumGroupsOf`
- строка 1342 — `sumGroupQty`
- строка 1355 — `sumChokePrice`
- строка 1381 — `sumPriceTop`
- строка 1387 — `sumLinearRecord`
- строка 1485 — `integrateBroken`
- строка 1496 — `curveBreaks`
- строка 1507 — `quadBreaks`
- строка 1523 — `sumSegExpr`
- строка 1541 — `sumPolyline`
- строка 1569 — `sumRebuildSide`
- строка 1620 — `sumSignature`
- строка 1640 — `sumRebuild`
- строка 1653 — `sumAnalyticsKey`
- строка 1671 — `sumGroupName`
- строка 1694 — `sumTagOf`
- строка 1701 — `sumShortTag`
- строка 1730 — `sumGroupColor`
- строка 1735 — `sumStartExpr`
- строка 1743 — `sumReorder`
- строка 1748 — `sumAddGroup`
- строка 1761 — `sumBuildScene`
- строка 1789 — `sumSetCount`
- строка 1808 — `syncSumUi`
- строка 1822 — `sumGroupStats`
- строка 1868 — `sumFinalRecords`
- строка 1886 — `updateSumPanel`
- строка 1947 — `drawAreas`
- строка 1975 — `beforeInterventionNote`
- строка 1984 — `updateAreasPanel`
- строка 2013 — `intervOnBuyer`
- строка 2022 — `drawShiftedSupply`
- строка 2074 — `taxPivotQ`
- строка 2105 — `taxPivotPoint`
- строка 2114 — `drawTaxPivot`
- строка 2149 — `drawTaxAreas`
- строка 2185 — `drawTaxPoints`
- строка 2238 — `attachTaxDrag`
- строка 2259 — `setTax`
- строка 2377 — `taxFormKey`
- строка 2385 — `pctForm`
- строка 2393 — `syncTaxKind`
- строка 2398 — `applyIntervCascade`
- строка 2464 — `setTaxForm`
- строка 2482 — `setType`
- строка 2530 — `rateLetter`
- строка 2534 — `rateUnit`
- строка 2549 — `unitRateMax`
- строка 2560 — `applyTaxRateBounds`
- строка 2579 — `syncTaxHint`
- строка 2605 — `setTaxKind`
- строка 2611 — `updateTaxPanel`
- строка 2734 — `setTaxSide`
- строка 2745 — `setTaxSideButtons`
- строка 2758 — `drawElasticityZones`
- строка 2776 — `drawElasticityPoint`
- строка 2805 — `attachElastDrag`
- строка 2813 — `drawElasticityPointS`
- строка 2833 — `attachElastDragS`
- строка 2841 — `updateElasticityPanel`
- строка 2905 — `drawExtAreas`
- строка 2917 — `drawExtCurves`
- строка 2941 — `drawExtPoints`
- строка 2975 — `drawExtScenario`
- строка 2984 — `updateExtPanel`
- строка 3025 — `setExtSign`
- строка 3034 — `syncSocialFields`
- строка 3066 — `socialDefaultExpr`
- строка 3072 — `recompileSocial`
- строка 3094 — `setPRegFields`
- строка 3102 — `setPReg`
- строка 3111 — `drawPcAreas`
- строка 3135 — `drawPriceControl`
- строка 3184 — `attachPcDrag`
- строка 3193 — `updatePcPanel`
- строка 3238 — `setQuotaFields`
- строка 3249 — `setQuota`
- строка 3256 — `setQuotaPos`
- строка 3266 — `updateQuotaPriceLabel`
- строка 3278 — `drawQuotaAreas`
- строка 3305 — `drawQuotaLines`
- строка 3350 — `attachQuotaDrag`
- строка 3363 — `updateQuotaPanel`
- строка 3412 — `drawGhost`

#### `calc2/static/calc2/42-scenes-mono.js`

- строка 11 — `mcSourceCurve`
- строка 16 — `mcAt`
- строка 31 — `marginalRevenue`
- строка 40 — `drawMonopolyAreas`
- строка 75 — `drawMonopoly`
- строка 95 — `drawMonopolyPoints`
- строка 132 — `updateMonoPanel`
- строка 163 — `setMarket`
- строка 198 — `monopolyCeiling`
- строка 241 — `drawMonoCeilingAreas`
- строка 260 — `drawMonoKinkedMR`
- строка 277 — `drawMonoCeilingPoints`
- строка 309 — `drawMonoCeilingLine`
- строка 333 — `monopolyTax`
- строка 350 — `monopolyFloor`
- строка 384 — `naturalATC`
- строка 395 — `findRootLast`
- строка 410 — `recomputeNatural`
- строка 439 — `drawNaturalAreas`
- строка 454 — `drawNaturalCurves`
- строка 473 — `drawNaturalPoints`
- строка 502 — `drawNaturalFull`
- строка 510 — `updateNaturalPanel`
- строка 539 — `drawMonoTaxAreas`
- строка 562 — `drawMonoTaxShiftedMC`
- строка 577 — `drawMonoTaxPoints`
- строка 598 — `drawMonoFloorAreas`
- строка 613 — `drawMonoFloorPoints`
- строка 633 — `drawMonoFloorLine`
- строка 648 — `updateMonoInterventionPanel`
- строка 723 — `makeCurve`
- строка 732 — `drawDiscr1`
- строка 756 — `updateDiscr1Panel`
- строка 781 — `allocateMR`
- строка 794 — `recomputeDiscr3`
- строка 814 — `drawMiniMarket`
- строка 901 — `redrawDiscr3`
- строка 924 — `updateDiscr3Panel`
- строка 971 — `applyD3WorldLabels`
- строка 994 — `buildKinkedDemand`
- строка 1041 — `recomputeKinked`
- строка 1061 — `drawKinkedFull`
- строка 1105 — `updateKinkPanel`
- строка 1129 — `applyMonoVisibility`
- строка 1148 — `ensureMonopolyCurves`
- строка 1157 — `fillIfEmpty`
- строка 1160 — `ensureD3Fields`
- строка 1165 — `ensureKinkFields`
- строка 1171 — `ensureMonopolyPreset`
- строка 1178 — `setMonoMode`
- строка 1189 — `setKinkInput`

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
- строка 854 — `noMaxNote`
- строка 863 — `updateProdPanel`
- строка 887 — `recomputeIsoquant`
- строка 898 — `redrawIsoquant`
- строка 912 — `updateIsoPanel`
- строка 950 — `plantMC`
- строка 956 — `plantTC`
- строка 962 — `plantQatMC`
- строка 978 — `recomputePlants`
- строка 1012 — `plantsAt`
- строка 1029 — `redrawPlants`
- строка 1110 — `updatePlantsPanel`
- строка 1141 — `setPlantsView`
- строка 1148 — `setPlantsQ`
- строка 1159 — `setCostsInputMode`
- строка 1167 — `syncCostsInputMode`
- строка 1181 — `setCostsSub`

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
- строка 240 — `drawLaborMinWelfare`
- строка 269 — `drawLaborMCL`
- строка 299 — `drawLaborDWL`
- строка 312 — `drawLaborMonopsonyPoints`
- строка 368 — `drawLaborCompPoints`
- строка 394 — `drawLaborMinLine`
- строка 408 — `attachLaborMinDrag`
- строка 416 — `setLaborMinFields`
- строка 423 — `setLaborMin`
- строка 435 — `drawLaborUnionMRL`
- строка 446 — `drawLaborGapDWL`
- строка 456 — `drawLaborUnionPoints`
- строка 490 — `drawLaborUnionWageLine`
- строка 504 — `attachUnionWageDrag`
- строка 512 — `setUnionWageFields`
- строка 519 — `setUnionWage`
- строка 529 — `setUnionModel`
- строка 546 — `drawLaborBilateral`
- строка 574 — `updateLaborBilateralPanel`
- строка 592 — `setLaborStruct`
- строка 607 — `updateLaborPanel`
- строка 697 — `redrawLabor`

#### `calc2/static/calc2/48-scenes-consumer.js`

- строка 12 — `consumerUtility`
- строка 27 — `consumerOptimum`
- строка 35 — `setConsSlutsky`
- строка 46 — `recomputeConsumer`
- строка 81 — `drawBudgetLine`
- строка 96 — `drawLevelCurve`
- строка 106 — `drawChoicePoint`
- строка 118 — `attachBudgetHandles`
- строка 143 — `setConsumerNum`
- строка 152 — `redrawConsumer`
- строка 184 — `updateConsumerPanel`
- строка 235 — `applyConsumerTypeUI`
- строка 249 — `setConsumerType`

#### `calc2/static/calc2/50-scenes-macro.js`

- строка 20 — `compileVar`
- строка 31 — `evalVar`
- строка 40 — `macroCurveY`
- строка 49 — `macroCurveInv`
- строка 89 — `macroP`
- строка 95 — `recomputeMacro`
- строка 209 — `drawMacroCurve`
- строка 238 — `redrawMacro`
- строка 309 — `drawEquilibriumAt`
- строка 320 — `updateMacroPanel`
- строка 404 — `setMacroModel`

#### `calc2/static/calc2/52-modes.js`

- строка 14 — `setRanges`
- строка 37 — `syncViewFields`
- строка 70 — `updateResetViewBtn`
- строка 83 — `markViewDirty`
- строка 103 — `prefersReducedMotion`
- строка 108 — `animateRanges`
- строка 139 — `applyTradeRanges`
- строка 162 — `scheduleRangeAnim`
- строка 181 — `padMax`
- строка 199 — `curveAxisBounds`
- строка 225 — `boundsOfDrawn`
- строка 265 — `redrawKeepingWindow`
- строка 270 — `applyAutoRanges`
- строка 295 — `zoomRound`
- строка 301 — `zoomBy`
- строка 374 — `panByPixels`
- строка 443 — `resetZoom`
- строка 483 — `flushWheel`
- строка 492 — `initZoom`
- строка 672 — `zoomStep`
- строка 681 — `cancelRangeAnim`
- строка 693 — `makeThrottle`
- строка 706 — `ineqRedraw`
- строка 709 — `setMode`
- строка 788 — `applyScenarioVisibility`
- строка 814 — `setScenario`

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
- строка 277 — `drawPpfCurve`
- строка 337 — `drawBundleRay`
- строка 413 — `ppfOppAt`
- строка 419 — `updatePpfPanel`
- строка 509 — `redrawPpf`
- строка 562 — `ppfEvalWith`
- строка 582 — `ppfSlopeOf`
- строка 595 — `ppfXmaxOf`
- строка 609 — `fitLinear`
- строка 623 — `classifyPpf`
- строка 649 — `niceMax`
- строка 657 — `singlePpfPoints`
- строка 664 — `findRootIn`
- строка 676 — `interpY`
- строка 690 — `maxAllocY`
- строка 715 — `combinedPpfPoints`
- строка 725 — `allocAt`
- строка 756 — `detectCombinedKinks`
- строка 831 — `ppfCoefTex`
- строка 840 — `ppfNum`
- строка 851 — `ppfSnap`
- строка 861 — `ppfPiecesToExpr`
- строка 878 — `ppfLinearExpr`
- строка 885 — `combinedPpfLinearRecord`
- строка 1009 — `ppfFam`
- строка 1010 — `ppfClamp`
- строка 1021 — `ppfReduceActive`
- строка 1040 — `ppfPieceTex`
- строка 1064 — `ppfPieceBody`
- строка 1089 — `ppfPieceAt`
- строка 1101 — `ppfPiecesRecord`
- строка 1136 — `ppfSumByEqualCost`
- строка 1241 — `ppfSumByEnvelope`
- строка 1329 — `ppfEnvPiece`
- строка 1340 — `ppfMergeSameLine`
- строка 1360 — `ppfCostKinds`
- строка 1369 — `ppfCostValue`
- строка 1379 — `ppfWhyNumeric`
- строка 1405 — `ppfSumAnalytic`
- строка 1421 — `combinedPpfFormula`
- строка 1457 — `verifyFormula`
- строка 1468 — `detectKinks`
- строка 1493 — `showPaneError`
- строка 1504 — `ppfSumCount`
- строка 1505 — `ppfSumGet`
- строка 1510 — `ppfSumSet`
- строка 1515 — `ppfSumName`
- строка 1519 — `ppfSumColor`
- строка 1533 — `ppfSumSignature`
- строка 1543 — `recomputePpfSum`
- строка 1549 — `ensurePpfSum`
- строка 1553 — `recomputePpfSumRaw`
- строка 1660 — `renderPpfSumRows`
- строка 1706 — `detectSumKinks`
- строка 1724 — `drawPpfSumCurves`
- строка 1745 — `drawPpfSumMarks`
- строка 1771 — `updatePpfSumPanel`
- строка 1884 — `fmtRu`
- строка 1888 — `ppfSumSchemaData`
- строка 1922 — `schemaNote`
- строка 1929 — `drawPpfSumSchema`
- строка 1981 — `redrawPpfSum`
- строка 1994 — `setPpfSumView`
- строка 2005 — `cornerByValue`
- строка 2029 — `bestByValue`
- строка 2048 — `recomputePpfTrade`
- строка 2090 — `drawPpfTrade`
- строка 2115 — `drawPpfTradeMarks`
- строка 2143 — `updatePpfTradePanel`
- строка 2265 — `syncPpftPriceUI`
- строка 2276 — `redrawPpfTrade`
- строка 2297 — `recomputeTradeB`
- строка 2386 — `tradeCpfPoints`
- строка 2403 — `tradeBPanels`
- строка 2424 — `drawTradeB`
- строка 2489 — `drawTradeBMarks`
- строка 2492 — `tbName`
- строка 2498 — `updateTradeBPanel`
- строка 2568 — `syncTbPriceUI`
- строка 2581 — `redrawTradeB`
- строка 2596 — `setTradeScenario`
- строка 2608 — `setPpfSub`

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
- строка 233 — `drawInequalityAreas`
- строка 244 — `drawLorenzCurve`
- строка 252 — `drawRobinHood`
- строка 268 — `drawLorenzNodes`
- строка 286 — `ineqDragNode`
- строка 302 — `ineqDragIncome`
- строка 319 — `attachLorenzNodeDrag`
- строка 338 — `drawRedistArrow`
- строка 352 — `ineqSnapshot`
- строка 359 — `updateIneqSortNote`
- строка 367 — `updateInequalityPanel`
- строка 414 — `redrawInequality`
- строка 453 — `defaultGroupShares`
- строка 460 — `setIneqInput`
- строка 477 — `setIneqAlpha`
- строка 492 — `setIneqGroupN`
- строка 503 — `setIneqRedistTool`
- строка 514 — `renderIneqGroupsTable`

#### `calc2/static/calc2/60-overlays.js`

- строка 10 — `redrawAll`
- строка 66 — `redrawScene`
- строка 197 — `redrawGraphMode`
- строка 208 — `renderMmRows`
- строка 249 — `graphRowsBox`
- строка 252 — `renderGraphRows`
- строка 270 — `graphError`
- строка 277 — `buildGraphRow`
- строка 359 — `equipGraphRows`
- строка 367 — `graphRowInput`
- строка 404 — `mainScales`
- строка 416 — `drawOverlays`
- строка 512 — `guardedPanelIds`
- строка 516 — `guardPanelBoxes`
- строка 552 — `panelsChangedSinceLastPass`
- строка 557 — `markPanelsChanged`
- строка 560 — `flushPendingPanelClears`
- строка 569 — `refreshAnalyticsPanel`
- строка 597 — `typesetStats`
- строка 644 — `addStatSign`
- строка 657 — `statToTex`
- строка 689 — `katexVisibleText`
- строка 695 — `restatWide`
- строка 735 — `statInkWidth`
- строка 743 — `statTooWide`
- строка 752 — `statPieces`
- строка 787 — `texAbbrev`
- строка 793 — `renderMathIn`
- строка 836 — `areaKey`
- строка 841 — `subDigits`
- строка 846 — `applyAreaColors`
- строка 856 — `currentAreas`
- строка 874 — `areaOfPathEl`
- строка 936 — `areaShort`
- строка 945 — `drawLegend`
- строка 1008 — `floatRects`
- строка 1025 — `legendCorner`
- строка 1102 — `viewWindow`
- строка 1114 — `axisWords`
- строка 1120 — `crossPoints`
- строка 1218 — `invalidateKeyTargets`
- строка 1221 — `kinksOf`
- строка 1269 — `keyTargets`
- строка 1386 — `snapVertexAt`
- строка 1420 — `drawCrossPoints`
- строка 1529 — `armCurve`
- строка 1535 — `disarmCurve`
- строка 1543 — `keyPointLit`
- строка 1556 — `drawCurveHits`
- строка 1590 — `pinKeyPoint`
- строка 1610 — `hoverLabel`
- строка 1621 — `drawRoller`
- строка 1642 — `rollerTargetAt`
- строка 1668 — `rollerClampX`
- строка 1687 — `rollerMove`
- строка 1703 — `showRollTip`
- строка 1726 — `hideRollTip`
- строка 1735 — `rollerOff`
- строка 1746 — `curveRightEdge`
- строка 1771 — `axisXLetter`
- строка 1781 — `axisLetter`
- строка 1794 — `armVerts`
- строка 1828 — `syncCanvasMode`
- строка 1848 — `leaveCanvasMode`
- строка 1853 — `addAreaVert`
- строка 1860 — `clearAreaVerts`
- строка 1866 — `renderVertList`
- строка 1932 — `syncAreaCalcButton`
- строка 1944 — `areaPickedCurve`
- строка 1953 — `areaCurveRange`
- строка 1971 — `syncAreaRangeLabel`
- строка 2007 — `freshenVertNames`
- строка 2023 — `drawAreaVerts`
- строка 2083 — `areaTargets`
- строка 2087 — `calcAreaUnderCurve`
- строка 2100 — `ringArea`
- строка 2110 — `segCross`
- строка 2117 — `ringSelfCrosses`
- строка 2139 — `angleRing`
- строка 2145 — `bestAreaRing`
- строка 2175 — `calcAreaPolygon`
- строка 2190 — `AREA_PALETTE`
- строка 2192 — `runAreaCalc`
- строка 2212 — `clearAreaCalc`
- строка 2219 — `drawAreaCalc`
- строка 2248 — `updateAreaCalcPanel`
- строка 2346 — `syncAreaCalcUI`
- строка 2381 — `updateQuickArea`
- строка 2383 — `setAreaCalcMode`
- строка 2399 — `wireFolds`
- строка 2424 — `wireAreaCalc`
- строка 2453 — `paramsAllowed`
- строка 2478 — `isReservedName`
- строка 2518 — `expandImplicitMul`
- строка 2564 — `visibleSvgText`
- строка 2590 — `chartLabelSource`
- строка 2600 — `chartLabelBase`
- строка 2617 — `chartLabelKind`
- строка 2631 — `typesetChartLabels`
- строка 2659 — `prepExpr`
- строка 2677 — `texToPlain`
- строка 2703 — `sceneReservedKey`
- строка 2707 — `freeSymbols`
- строка 2725 — `freeSymbolsUncached`
- строка 2753 — `sceneReserved`
- строка 2776 — `sceneExtraParams`
- строка 2782 — `paramValue`
- строка 2788 — `paramScope`
- строка 2798 — `scopeFor`
- строка 2805 — `evalWithParams`
- строка 2816 — `syncParams`
- строка 2872 — `buildParamChip`
- строка 2995 — `initSceneColorPickers`
- строка 3007 — `syncSceneColorPickers`
- строка 3015 — `syncAxisPlaceholders`
- строка 3030 — `titleAnchorPx`
- строка 3040 — `drawGraphTitle`
- строка 3079 — `editGraphTitleOnCanvas`
- строка 3124 — `normHex`
- строка 3146 — `paletteSix`
- строка 3154 — `closeColorMenu`
- строка 3168 — `onDocClosePick`
- строка 3172 — `onEscClosePick`
- строка 3179 — `makeColorPicker`
- строка 3266 — `autoCurveName`
- строка 3275 — `curveShortName`
- строка 3285 — `markCaption`
- строка 3294 — `drawMarks`
- строка 3381 — `snapTargets`
- строка 3467 — `macroSnapTargets`
- строка 3486 — `consumerSnapTargets`
- строка 3515 — `ineqSnapTargets`
- строка 3529 — `mathSnapTargets`
- строка 3581 — `tradeSnapTargets`
- строка 3601 — `axisSnapAt`
- строка 3620 — `snapDistPx`
- строка 3639 — `snapPointAt`
- строка 3680 — `showSnapHint`
- строка 3699 — `armMark`
- строка 3712 — `cancelMarkDraft`
- строка 3752 — `resetDecor`
- строка 3843 — `_undoCopyChild`
- строка 3857 — `_undoCopy`
- строка 3871 — `pushUndo`
- строка 3881 — `undoLast`
- строка 3897 — `clearUndo`
- строка 3904 — `forgetSceneSnapshot`
- строка 3906 — `resetSceneMemory`
- строка 3908 — `saveSceneSnapshot`
- строка 3917 — `restoreSceneSnapshot`
- строка 3936 — `addMarkAt`
- строка 3971 — `colorDist`
- строка 3980 — `drawnStrokeColors`
- строка 3996 — `nextMarkColor`
- строка 4012 — `newMark`
- строка 4024 — `pendingMark`
- строка 4027 — `startMarkDraft`
- строка 4036 — `markSnapFn`
- строка 4046 — `renderMarkList`
- строка 4059 — `ensureAddMarkButton`
- строка 4069 — `buildMarkRow`

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
- строка 189 — `mathLine`
- строка 212 — `resetLabelBoxes`
- строка 213 — `dodgeLabel`
- строка 225 — `mathDot`
- строка 269 — `makeRenamable`
- строка 312 — `editPointName`
- строка 336 — `editInlineLabel`
- строка 417 — `tangentLayout`
- строка 426 — `tangentPanelAt`
- строка 434 — `tanWin`
- строка 444 — `tanResetWindows`
- строка 449 — `tanScales`
- строка 457 — `drawMathTangent`
- строка 572 — `drawMathOptimum`
- строка 611 — `drawMathTransform`
- строка 631 — `labelCurveMath`
- строка 661 — `mmSlots`
- строка 662 — `mmGet`
- строка 665 — `mmSet`
- строка 670 — `mmLabel`
- строка 672 — `mmColor`
- строка 679 — `drawMathMinMax`
- строка 740 — `compileAB`
- строка 753 — `parseConstraint`
- строка 771 — `constraintPointsIn`
- строка 790 — `constraintPoints`
- строка 795 — `optimizeAlongCurve`
- строка 808 — `constraintFit`
- строка 826 — `drawMathConstraint`
- строка 880 — `drawLevelCurveOn`
- строка 891 — `mathOptimumReasoning`
- строка 928 — `updateMathPanel`
- строка 1064 — `redrawMath`
- строка 1094 — `setMathSub`
- строка 1117 — `setMathWindow`
- строка 1131 — `setMathX0`
- строка 1156 — `downloadBlob`
- строка 1165 — `exportBaseName`
- строка 1171 — `exportPNG`
- строка 1198 — `texEscape`
- строка 1205 — `r2`
- строка 1236 — `texPlotSize`
- строка 1260 — `texText`
- строка 1273 — `labelPlainText`
- строка 1305 — `quantityTex`
- строка 1322 — `texHex`
- строка 1337 — `texSamplePath`
- строка 1369 — `texResample`
- строка 1412 — `mathToPgf`
- строка 1460 — `pgfStroke`
- строка 1499 — `texDashPattern`
- строка 1511 — `texCondBounds`
- строка 1522 — `texCondPieces`
- строка 1544 — `buildTexFromState`
- строка 1867 — `buildTexLegacy`
- строка 2215 — `texWantState`
- строка 2219 — `buildTex`
- строка 2226 — `exportTex`
- строка 2234 — `exportPDF`
- строка 2254 — `buildExportFields`
- строка 2271 — `refreshExportPreview`
- строка 2305 — `expValue`
- строка 2307 — `openExport`
- строка 2324 — `closeExport`
- строка 2343 — `updateGraphPanel`
- строка 2400 — `graphExplainNote`

#### `calc2/static/calc2/80-ui.js`

- строка 7 — `showError`
- строка 11 — `hideError`
- строка 30 — `curveSrcForm`
- строка 51 — `addCurve`
- строка 91 — `addEmptyCurve`
- строка 110 — `updateCurveExpr`
- строка 142 — `setRole`
- строка 158 — `renderCurveList`

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
- строка 305 — `pwAttachKeyboard`
- строка 329 — `pwPreview`
- строка 352 — `pwVarForField`
- строка 380 — `pwDefaultRows`
- строка 386 — `pwBalanced`
- строка 399 — `pwSplitTernary`
- строка 423 — `pwCondBounds`
- строка 444 — `pwParse`
- строка 475 — `openPiecewise`
- строка 490 — `closePiecewise`
- строка 499 — `insertIntoFormula`
- строка 529 — `mathfieldClass`
- строка 533 — `onMathliveReady`
- строка 568 — `fieldProblem`
- строка 618 — `unknownTexCommand`
- строка 627 — `texGroup`
- строка 637 — `latexToMath`
- строка 783 — `isUndefinedTailNode`
- строка 788 — `unwrapParens`
- строка 799 — `pwCondTex`
- строка 818 — `condChainToCases`
- строка 840 — `mathToLatexField`
- строка 862 — `upgradeFormulaField`
- строка 909 — `fitFormulaField`
- строка 960 — `fitFormulaFields`
- строка 963 — `fitFormulaFieldsSoon`
- строка 978 — `fieldOnScreen`
- строка 990 — `flushMathfieldsSoon`
- строка 996 — `flushMathfields`
- строка 1030 — `katexSafe`
- строка 1066 — `katexInto`
- строка 1081 — `placeholderTex`
- строка 1090 — `texSafeText`
- строка 1094 — `buildMathfield`
- строка 1246 — `insertIntoField`
- строка 1317 — `mkbdKey`
- строка 1344 — `buildKeyboard`
- строка 1404 — `closeAllKeyboardsExcept`
- строка 1425 — `scheduleParamsSync`
- строка 1431 — `registerFormulaField`
- строка 1448 — `fieldActive`
- строка 1457 — `liveFormulaTexts`
- строка 1484 — `equipFormulaField`
- строка 1521 — `equipAllFormulaFields`
- строка 1525 — `attachFormulaHelp`
- строка 1715 — `makeEditableValue`
- строка 1820 — `makeToggle`
- строка 1862 — `segToToggle`
- строка 1894 — `closeAllSelectMenus`
- строка 1898 — `upgradeSelect`
- строка 1999 — `upgradeTextField`
- строка 2022 — `upgradeTextFieldsIn`

#### `calc2/static/calc2/84-picker.js`

- строка 8 — `loadScene`
- строка 139 — `closePicker`
- строка 158 — `setPickerBlockOpen`
- строка 163 — `openPicker`
- строка 336 — `baseScene`
- строка 345 — `applyCardScope`
- строка 423 — `blockSpec`
- строка 435 — `foldPickerGroups`
- строка 524 — `plural`
- строка 532 — `pickScene`

#### `calc2/static/calc2/86-workspace.js`

- строка 55 — `setFieldValue`
- строка 61 — `relocateForScene`
- строка 76 — `clearResultPanels`
- строка 93 — `toast`
- строка 100 — `dockActive`
- строка 107 — `setSideOpen`
- строка 128 — `setToolsOpen`
- строка 129 — `setParamsOpen`
- строка 139 — `hasAnalytics`
- строка 146 — `moveExplanations`
- строка 213 — `syncAnalyticsPanel`
- строка 294 — `sectionIcon`
- строка 301 — `cardifySections`
- строка 346 — `collapseCards`
- строка 362 — `syncLabelSizeSeg`
- строка 373 — `openSection`
- строка 407 — `cardWithFormula`
- строка 420 — `syncFirstCard`
- строка 439 — `wireScene`
- строка 601 — `resetCurrentScene`
- строка 609 — `setWrenchOpen`
- строка 619 — `applyViewBounds`
- строка 646 — `quadWindow`
- строка 651 — `quadSameWindow`
- строка 670 — `offQuadShownPoints`
- строка 700 — `fitWindowToOffQuad`
- строка 722 — `setFirstQuad`
- строка 772 — `setGridMode`
- строка 790 — `hintTip`
- строка 812 — `fitTipMath`
- строка 828 — `showHintTip`
- строка 880 — `hideHintTip`
- строка 905 — `tipText`
- строка 934 — `tipTex`
- строка 944 — `tipName`
- строка 961 — `tipExpr`
- строка 971 — `tipPlain`
- строка 994 — `ffEsc`
- строка 1004 — `ffLatexOf`
- строка 1026 — `finalFunctionHtml`
- строка 1049 — `ffCasesStacked`
- строка 1071 — `ffTypeset`
- строка 1092 — `fitFinalMath`
- строка 1128 — `ffCopyText`
- строка 1136 — `ffCopyFallback`
- строка 1148 — `wireFinalCopy`
- строка 1164 — `setFinalFunctions`
- строка 1182 — `refitFinalMathSoon`
- строка 1210 — `markNotationsIn`
- строка 1240 — `paintNotation`
- строка 1250 — `showTipFor`
- строка 1256 — `wireTips`
- строка 1295 — `syncTipLabels`
- строка 1308 — `hintAnchor`
- строка 1386 — `fitPanelMath`
- строка 1416 — `syncHintDots`
- строка 1427 — `hintsToDots`
- строка 1465 — `wireHintButtons`
- строка 1505 — `wireWrench`
- строка 1584 — `fillPrintBlocks`
- строка 1612 — `setPrintViewBox`

#### `calc2/static/calc2/88-params.js`

- строка 63 — `pultRegulatorIds`
- строка 141 — `pultCurveList`
- строка 152 — `pultExtraSig`
- строка 158 — `pultExtraSigBase`
- строка 170 — `pultShouldShow`
- строка 180 — `shiftChipLabel`
- строка 194 — `curveChipLabel`
- строка 203 — `pultCurveSig`
- строка 213 — `paintEqLabel`
- строка 228 — `texifyName`
- строка 250 — `editEqValue`
- строка 309 — `centerBandOn`
- строка 313 — `pullIntoBand`
- строка 317 — `attachBoundsEditor`
- строка 399 — `refreshRegulators`
- строка 410 — `makePchip`
- строка 438 — `curveShiftBase`
- строка 445 — `buildPultCurveChips`
- строка 528 — `syncPultCurveValues`
- строка 553 — `capturePultHome`
- строка 560 — `capturePultHomes`
- строка 565 — `returnPultHome`
- строка 577 — `syncPultRegulators`
- строка 602 — `upgradeRegulator`
- строка 759 — `shortRegulatorName`
- строка 779 — `ppfLinearFormula`
- строка 785 — `ppfInterceptsOf`
- строка 793 — `ppfSetSingle`
- строка 801 — `ppfSetSum`
- строка 818 — `addPultXChip`
- строка 829 — `buildPultExtra`
- строка 861 — `ineqParseIncomes`
- строка 864 — `ineqMasterRebase`
- строка 869 — `ineqMasterScale`
- строка 887 — `ineqMasterApply`
- строка 899 — `ineqMasterDetach`
- строка 904 — `buildIneqMasterChip`
- строка 912 — `showPult`
- строка 939 — `updatePult`
- строка 959 — `wireControls`

#### `calc2/static/calc2/90-explain.js`

- строка 375 — `sceneExplainHtml`

#### `calc2/static/calc2/99-boot.js`

- строка 13 — `lockNumberFields`
- строка 42 — `init`

**Итого функций в индексе: 996.**

<!-- AUTO:END -->
