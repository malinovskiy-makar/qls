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

*Автоматически собрано командой `manage.py calc2_map`. Дата: 2026-10-06. HEAD: `0cc7cf39`. Не редактировать руками — вся эта часть файла, от отметки начала автосекции и до отметки её конца, перезаписывается заново при каждом запуске команды.*

### Файлы (маршрут → представление → шаблон → статика)

| Путь | Строк | КБ | Тип |
|---|---:|---:|---|
| `calc2/urls.py` | 19 | 0.6 | python |
| `calc2/views.py` | 224 | 13.4 | python |
| `calc2/templates/calc2/calc2.html` | 2616 | 217.6 | шаблон |
| `calc2/static/calc2/calc2.css` | 3354 | 244.6 | CSS |
| `calc2/static/calc2/00-config.js` | 563 | 48.5 | JS |
| `calc2/static/calc2/10-math-core.js` | 1126 | 73.5 | JS |
| `calc2/static/calc2/20-plane.js` | 991 | 67.2 | JS |
| `calc2/static/calc2/30-curves.js` | 1341 | 97.9 | JS |
| `calc2/static/calc2/40-scenes-market.js` | 3729 | 266.0 | JS |
| `calc2/static/calc2/42-scenes-mono.js` | 1677 | 121.2 | JS |
| `calc2/static/calc2/44-scenes-firm.js` | 1209 | 80.3 | JS |
| `calc2/static/calc2/46-scenes-labor.js` | 744 | 53.7 | JS |
| `calc2/static/calc2/48-scenes-consumer.js` | 263 | 16.0 | JS |
| `calc2/static/calc2/50-scenes-macro.js` | 416 | 28.4 | JS |
| `calc2/static/calc2/52-modes.js` | 933 | 63.6 | JS |
| `calc2/static/calc2/54-scenes-ppf.js` | 3093 | 198.3 | JS |
| `calc2/static/calc2/56-scenes-inequality.js` | 530 | 34.1 | JS |
| `calc2/static/calc2/60-overlays.js` | 4572 | 287.7 | JS |
| `calc2/static/calc2/70-scenes-math.js` | 2570 | 162.6 | JS |
| `calc2/static/calc2/80-ui.js` | 675 | 41.6 | JS |
| `calc2/static/calc2/82-input.js` | 2159 | 126.7 | JS |
| `calc2/static/calc2/84-picker.js` | 571 | 42.9 | JS |
| `calc2/static/calc2/86-workspace.js` | 1960 | 126.5 | JS |
| `calc2/static/calc2/88-params.js` | 1926 | 130.0 | JS |
| `calc2/static/calc2/89-model-state.js` | 319 | 18.7 | JS |
| `calc2/static/calc2/90-explain.js` | 381 | 63.1 | JS |
| `calc2/static/calc2/91-session.js` | 396 | 19.7 | JS |
| `calc2/static/calc2/92-ui-kit.js` | 326 | 18.5 | JS |
| `calc2/static/calc2/93-shell.js` | 193 | 11.1 | JS |
| `calc2/static/calc2/94-answer.js` | 379 | 23.0 | JS |
| `calc2/static/calc2/95-picker-screen.js` | 397 | 21.5 | JS |
| `calc2/static/calc2/96-self.js` | 172 | 9.9 | JS |
| `calc2/static/calc2/99-boot.js` | 108 | 9.0 | JS |

**Итого: 33 файлов, 39932 строк, 2737.5 КБ.**

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
- строка 43 — `measureText`
- строка 77 — `fitMargins`
- строка 128 — `fitLeftForLabels`
- строка 141 — `makeScales`
- строка 176 — `clearPanels`
- строка 178 — `registerPanel`
- строка 195 — `panelDist`
- строка 204 — `panelAt`
- строка 216 — `activePanel`
- строка 224 — `panelById`
- строка 239 — `panelWin`
- строка 243 — `resetPanelWins`
- строка 251 — `panelZoomBy`
- строка 268 — `panelPanBy`
- строка 282 — `gesturePanelId`
- строка 310 — `isEconScene`
- строка 316 — `econLo`
- строка 320 — `quadLo`
- строка 343 — `quadPrice`
- строка 353 — `toPx`
- строка 354 — `toData`
- строка 370 — `roundShown`
- строка 379 — `fmtSum`
- строка 385 — `shownDiff`
- строка 386 — `fmtDiff`
- строка 398 — `shownDecimals`
- строка 406 — `sumDecimals`
- строка 410 — `fmt`
- строка 431 — `fmtInput`
- строка 441 — `niceTickStep`
- строка 453 — `axisTicks`
- строка 466 — `xTicks`
- строка 467 — `yTicks`
- строка 470 — `addDefs`
- строка 530 — `drawGrid`
- строка 581 — `extraTickX`
- строка 592 — `extraTickY`
- строка 632 — `dropTickAt`
- строка 659 — `coordValue`
- строка 679 — `coordAlreadyAt`
- строка 714 — `resetDrawnKeyPoints`
- строка 717 — `panelOfGlobalScales`
- строка 721 — `kpNode`
- строка 737 — `collectDashes`
- строка 754 — `dashEndsNear`
- строка 766 — `flushDrawnKeyPoints`
- строка 814 — `noteAxisX`
- строка 819 — `noteAxisY`
- строка 826 — `kpName`
- строка 831 — `axisValueX`
- строка 858 — `axisValueY`
- строка 883 — `axisValueText`
- строка 900 — `drawAxes`

#### `calc2/static/calc2/30-curves.js`

- строка 8 — `nextColor`
- строка 73 — `piecewiseNodesQ`
- строка 107 — `pointsFromNodes`
- строка 124 — `curvePoints`
- строка 180 — `drawMarginalCurve`
- строка 242 — `markExpr`
- строка 265 — `derivativeExpr`
- строка 304 — `curveAnchor`
- строка 410 — `curveLabelSize`
- строка 411 — `labelScale`
- строка 447 — `unclipLabels`
- строка 516 — `keepAxisNamesInside`
- строка 533 — `spreadLabels`
- строка 706 — `parseColor`
- строка 721 — `relLum`
- строка 729 — `contrastOf`
- строка 734 — `rgbToHsl`
- строка 747 — `hslToRgb`
- строка 774 — `labelInk`
- строка 806 — `applyLabelInk`
- строка 833 — `mixToBg`
- строка 841 — `applyLabelSize`
- строка 875 — `smoothLabel`
- строка 905 — `requestLabelFrame`
- строка 910 — `resetLabelPositions`
- строка 919 — `curveLabelAnchor`
- строка 928 — `labelCurve`
- строка 1014 — `curveWidth`
- строка 1056 — `curveDash`
- строка 1064 — `curveOpacity`
- строка 1072 — `drawCurves`
- строка 1233 — `sceneDrawsCurveList`
- строка 1242 — `syncCurveListVisibility`
- строка 1257 — `curveDragAllowed`
- строка 1267 — `roundDrag`
- строка 1305 — `setCurveFreeTerm`

#### `calc2/static/calc2/40-scenes-market.js`

- строка 17 — `curveByRole`
- строка 20 — `curveByRoleAny`
- строка 24 — `recompute`
- строка 510 — `qtyAtPrice`
- строка 520 — `openQuotaName`
- строка 524 — `recomputeOpenEconomy`
- строка 616 — `drawOpenAreas`
- строка 661 — `drawOpenLines`
- строка 708 — `attachOpenPwDrag`
- строка 716 — `setOpenPw`
- строка 729 — `setOpenTool`
- строка 744 — `syncOpenQuotaLabel`
- строка 750 — `updateOpenPanel`
- строка 805 — `drawEquilibrium`
- строка 842 — `drawOffQuadIntersection`
- строка 879 — `offQuadExplainHtml`
- строка 905 — `pctFormExplainHtml`
- строка 942 — `mathTspans`
- строка 982 — `hasMathMarkup`
- строка 1006 — `markNotationTspan`
- строка 1023 — `mixedNotationRe`
- строка 1031 — `mixedMathTspans`
- строка 1075 — `qtyTspans`
- строка 1112 — `qtyGreekChar`
- строка 1150 — `texToCanvasText`
- строка 1159 — `renderLabelText`
- строка 1180 — `haloText`
- строка 1213 — `pointName`
- строка 1239 — `yWageLabel`
- строка 1244 — `yWageValue`
- строка 1267 — `isMonopolyScene`
- строка 1275 — `eqSectionTitle`
- строка 1291 — `updateEqSectionTitle`
- строка 1308 — `interventionKeyValues`
- строка 1373 — `countCrossings`
- строка 1382 — `updateInfoPanel`
- строка 1491 — `sumSceneOn`
- строка 1494 — `sumGroupsOf`
- строка 1501 — `sumGroupQty`
- строка 1514 — `sumChokePrice`
- строка 1540 — `sumPriceTop`
- строка 1561 — `sumLinearRecord`
- строка 1663 — `integrateBroken`
- строка 1674 — `curveBreaks`
- строка 1685 — `quadBreaks`
- строка 1701 — `sumSegExpr`
- строка 1719 — `sumPolyline`
- строка 1747 — `sumRebuildSide`
- строка 1798 — `sumSignature`
- строка 1818 — `sumRebuild`
- строка 1838 — `sumAnalyticsKey`
- строка 1856 — `sumGroupName`
- строка 1879 — `sumTagOf`
- строка 1886 — `sumShortTag`
- строка 1915 — `sumGroupColor`
- строка 1920 — `sumStartExpr`
- строка 1928 — `sumReorder`
- строка 1933 — `sumAddGroup`
- строка 1946 — `sumBuildScene`
- строка 1974 — `sumSetCount`
- строка 1993 — `syncSumUi`
- строка 2007 — `sumGroupStats`
- строка 2053 — `sumFinalRecords`
- строка 2071 — `updateSumPanel`
- строка 2132 — `drawAreas`
- строка 2160 — `beforeInterventionNote`
- строка 2169 — `updateAreasPanel`
- строка 2198 — `intervOnBuyer`
- строка 2207 — `drawShiftedSupply`
- строка 2259 — `taxPivotQ`
- строка 2290 — `taxPivotPoint`
- строка 2299 — `drawTaxPivot`
- строка 2334 — `drawTaxAreas`
- строка 2370 — `drawTaxPoints`
- строка 2423 — `attachTaxDrag`
- строка 2444 — `setTax`
- строка 2562 — `taxFormKey`
- строка 2570 — `pctForm`
- строка 2578 — `syncTaxKind`
- строка 2583 — `applyIntervCascade`
- строка 2656 — `setTaxForm`
- строка 2674 — `setType`
- строка 2724 — `rateLetter`
- строка 2728 — `rateUnit`
- строка 2750 — `modelPriceTop`
- строка 2761 — `unitRateMax`
- строка 2769 — `applyPriceRegBounds`
- строка 2778 — `applyTaxRateBounds`
- строка 2813 — `syncQuotaHint`
- строка 2830 — `syncPcHint`
- строка 2838 — `markCurrentIntervHint`
- строка 2847 — `intervHintKey`
- строка 2857 — `intervHintHtml`
- строка 2871 — `syncTaxHint`
- строка 2901 — `setTaxKind`
- строка 2907 — `updateTaxPanel`
- строка 3030 — `setTaxSide`
- строка 3041 — `setTaxSideButtons`
- строка 3054 — `drawElasticityZones`
- строка 3072 — `drawElasticityPoint`
- строка 3101 — `attachElastDrag`
- строка 3109 — `drawElasticityPointS`
- строка 3129 — `attachElastDragS`
- строка 3137 — `updateElasticityPanel`
- строка 3201 — `drawExtAreas`
- строка 3213 — `drawExtCurves`
- строка 3237 — `drawExtPoints`
- строка 3271 — `drawExtScenario`
- строка 3280 — `updateExtPanel`
- строка 3321 — `setExtSign`
- строка 3330 — `syncSocialFields`
- строка 3362 — `socialDefaultExpr`
- строка 3368 — `recompileSocial`
- строка 3390 — `setPRegFields`
- строка 3399 — `setPReg`
- строка 3408 — `drawPcAreas`
- строка 3432 — `drawPriceControl`
- строка 3481 — `attachPcDrag`
- строка 3490 — `updatePcPanel`
- строка 3535 — `setQuotaFields`
- строка 3547 — `setQuota`
- строка 3554 — `setQuotaPos`
- строка 3564 — `updateQuotaPriceLabel`
- строка 3576 — `drawQuotaAreas`
- строка 3603 — `drawQuotaLines`
- строка 3648 — `attachQuotaDrag`
- строка 3661 — `updateQuotaPanel`
- строка 3710 — `drawGhost`

#### `calc2/static/calc2/42-scenes-mono.js`

- строка 11 — `mcSourceCurve`
- строка 15 — `mcSourceCurveAny`
- строка 20 — `mcAt`
- строка 51 — `mcFloor`
- строка 55 — `marginalRevenue`
- строка 64 — `drawMonopolyAreas`
- строка 99 — `drawMonopoly`
- строка 119 — `drawMonopolyPoints`
- строка 156 — `updateMonoPanel`
- строка 187 — `setMarket`
- строка 222 — `monopolyCeiling`
- строка 270 — `drawMonoCeilingAreas`
- строка 289 — `drawMonoKinkedMR`
- строка 306 — `drawMonoCeilingPoints`
- строка 338 — `drawMonoCeilingLine`
- строка 362 — `monopolyTax`
- строка 387 — `monopolyFloor`
- строка 429 — `monopolyQuota`
- строка 457 — `drawMonoQuotaAreas`
- строка 479 — `drawMonoQuotaPoints`
- строка 501 — `drawMonoQuotaLine`
- строка 527 — `naturalATC`
- строка 538 — `findRootLast`
- строка 553 — `recomputeNatural`
- строка 582 — `drawNaturalAreas`
- строка 597 — `drawNaturalCurves`
- строка 616 — `drawNaturalPoints`
- строка 645 — `drawNaturalFull`
- строка 653 — `updateNaturalPanel`
- строка 691 — `drawMonoTaxAreas`
- строка 725 — `drawMonoTaxShiftedMC`
- строка 740 — `drawMonoTaxPoints`
- строка 761 — `drawMonoFloorAreas`
- строка 776 — `drawMonoFloorPoints`
- строка 796 — `drawMonoFloorLine`
- строка 811 — `updateMonoInterventionPanel`
- строка 937 — `makeCurve`
- строка 946 — `drawDiscr1`
- строка 974 — `updateDiscr1Panel`
- строка 999 — `allocateMR`
- строка 1012 — `recomputeDiscr3`
- строка 1052 — `drawMiniMarket`
- строка 1157 — `redrawDiscr3`
- строка 1200 — `drawMonoExport`
- строка 1323 — `updateDiscr3Panel`
- строка 1386 — `applyD3WorldLabels`
- строка 1409 — `buildKinkedDemand`
- строка 1456 — `recomputeKinked`
- строка 1496 — `drawKinkedFull`
- строка 1573 — `updateKinkPanel`
- строка 1602 — `applyMonoVisibility`
- строка 1623 — `ensureMonopolyCurves`
- строка 1634 — `fillIfEmpty`
- строка 1637 — `ensureD3Fields`
- строка 1642 — `ensureKinkFields`
- строка 1648 — `ensureMonopolyPreset`
- строка 1655 — `setMonoMode`
- строка 1666 — `setKinkInput`

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
- строка 615 — `updateLaborPanel`
- строка 705 — `redrawLabor`

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
- строка 186 — `updateConsumerPanel`
- строка 237 — `applyConsumerTypeUI`
- строка 251 — `setConsumerType`

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
- строка 71 — `updateResetViewBtn`
- строка 88 — `markViewDirty`
- строка 108 — `prefersReducedMotion`
- строка 113 — `animateRanges`
- строка 144 — `applyTradeRanges`
- строка 170 — `scheduleRangeAnim`
- строка 189 — `padMax`
- строка 207 — `curveAxisBounds`
- строка 238 — `boundsOfDrawn`
- строка 278 — `redrawKeepingWindow`
- строка 283 — `applyAutoRanges`
- строка 310 — `zoomRound`
- строка 316 — `zoomBy`
- строка 399 — `panByPixels`
- строка 479 — `wantedRanges`
- строка 512 — `growRanges`
- строка 528 — `growWindowToModel`
- строка 539 — `resetZoom`
- строка 570 — `flushWheel`
- строка 581 — `initZoom`
- строка 777 — `zoomStep`
- строка 786 — `cancelRangeAnim`
- строка 798 — `makeThrottle`
- строка 811 — `ineqRedraw`
- строка 814 — `setMode`
- строка 894 — `applyScenarioVisibility`
- строка 920 — `setScenario`

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
- строка 633 — `ppfTouchXmax`
- строка 670 — `classifyPpf`
- строка 731 — `ppfFitR2`
- строка 753 — `niceMax`
- строка 761 — `singlePpfPoints`
- строка 768 — `findRootIn`
- строка 780 — `interpY`
- строка 794 — `maxAllocY`
- строка 819 — `combinedPpfPoints`
- строка 829 — `allocAt`
- строка 860 — `detectCombinedKinks`
- строка 935 — `ppfCoefTex`
- строка 944 — `ppfNum`
- строка 955 — `ppfSnap`
- строка 965 — `ppfPiecesToExpr`
- строка 982 — `ppfLinearExpr`
- строка 989 — `combinedPpfLinearRecord`
- строка 1166 — `ppfPoly2Xmax`
- строка 1185 — `ppfCostOf`
- строка 1194 — `ppfValid`
- строка 1202 — `ppfFam`
- строка 1203 — `ppfClamp`
- строка 1214 — `ppfReduceActive`
- строка 1233 — `ppfPieceTex`
- строка 1283 — `ppfPoly2Terms`
- строка 1293 — `ppfPolyJoin`
- строка 1309 — `ppfPieceBody`
- строка 1347 — `ppfPieceAt`
- строка 1362 — `ppfPiecesRecord`
- строка 1401 — `ppfSumByEqualCost`
- строка 1506 — `ppfSumByEnvelope`
- строка 1595 — `ppfEnvPiece`
- строка 1606 — `ppfMergeSameLine`
- строка 1626 — `ppfCostKinds`
- строка 1635 — `ppfCostValue`
- строка 1645 — `ppfWhyNumeric`
- строка 1698 — `ppfSumMixedPair`
- строка 1863 — `ppfSumAnalytic`
- строка 1881 — `combinedPpfFormula`
- строка 1917 — `verifyFormula`
- строка 1928 — `detectKinks`
- строка 1953 — `showPaneError`
- строка 1964 — `ppfSumCount`
- строка 1965 — `ppfSumGet`
- строка 1970 — `ppfSumSet`
- строка 1975 — `ppfSumName`
- строка 1979 — `ppfSumColor`
- строка 1993 — `ppfSumSignature`
- строка 2003 — `recomputePpfSum`
- строка 2009 — `ensurePpfSum`
- строка 2013 — `recomputePpfSumRaw`
- строка 2124 — `renderPpfSumRows`
- строка 2169 — `detectSumKinks`
- строка 2187 — `drawPpfSumCurves`
- строка 2208 — `drawPpfSumMarks`
- строка 2234 — `updatePpfSumPanel`
- строка 2350 — `fmtRu`
- строка 2354 — `ppfSumSchemaData`
- строка 2388 — `schemaNote`
- строка 2395 — `drawPpfSumSchema`
- строка 2447 — `redrawPpfSum`
- строка 2460 — `setPpfSumView`
- строка 2471 — `cornerByValue`
- строка 2495 — `bestByValue`
- строка 2514 — `recomputePpfTrade`
- строка 2556 — `drawPpfTrade`
- строка 2581 — `drawPpfTradeMarks`
- строка 2609 — `updatePpfTradePanel`
- строка 2731 — `syncPpftPriceUI`
- строка 2742 — `redrawPpfTrade`
- строка 2763 — `recomputeTradeB`
- строка 2852 — `tradeCpfPoints`
- строка 2869 — `tradeBPanels`
- строка 2890 — `drawTradeB`
- строка 2960 — `drawTradeBMarks`
- строка 2963 — `tbName`
- строка 2969 — `updateTradeBPanel`
- строка 3039 — `syncTbPriceUI`
- строка 3052 — `redrawTradeB`
- строка 3067 — `setTradeScenario`
- строка 3079 — `setPpfSub`

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
- строка 353 — `updateIneqSortNote`
- строка 361 — `updateInequalityPanel`
- строка 401 — `redrawInequality`
- строка 450 — `defaultGroupShares`
- строка 457 — `setIneqInput`
- строка 474 — `setIneqAlpha`
- строка 490 — `setIneqGroupN`
- строка 501 — `setIneqRedistTool`
- строка 512 — `renderIneqGroupsTable`

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
- строка 1072 — `legendCorner`
- строка 1149 — `viewWindow`
- строка 1161 — `axisWords`
- строка 1167 — `crossPoints`
- строка 1269 — `invalidateKeyTargets`
- строка 1272 — `kinksOf`
- строка 1320 — `keyTargets`
- строка 1495 — `snapVertexAt`
- строка 1527 — `markPanelId`
- строка 1547 — `armedPanelId`
- строка 1553 — `drawCrossPoints`
- строка 1690 — `armCurve`
- строка 1696 — `disarmCurve`
- строка 1704 — `keyPointLit`
- строка 1717 — `drawCurveHits`
- строка 1755 — `pinKeyPoint`
- строка 1775 — `hoverLabel`
- строка 1786 — `drawRoller`
- строка 1807 — `rollerTargetAt`
- строка 1837 — `rollerClampX`
- строка 1856 — `rollerMove`
- строка 1872 — `showRollTip`
- строка 1895 — `hideRollTip`
- строка 1904 — `rollerOff`
- строка 1915 — `curveRightEdge`
- строка 1940 — `axisXLetter`
- строка 1950 — `axisLetter`
- строка 1963 — `armVerts`
- строка 2002 — `markServiceNodes`
- строка 2019 — `syncCanvasMode`
- строка 2040 — `leaveCanvasMode`
- строка 2045 — `addAreaVert`
- строка 2058 — `vertPanels`
- строка 2061 — `vertsMixed`
- строка 2063 — `clearAreaVerts`
- строка 2069 — `renderVertList`
- строка 2141 — `syncAreaCalcButton`
- строка 2153 — `areaPickedCurve`
- строка 2162 — `areaCurveRange`
- строка 2180 — `syncAreaRangeLabel`
- строка 2216 — `freshenVertNames`
- строка 2232 — `drawAreaVerts`
- строка 2301 — `areaTargets`
- строка 2305 — `calcAreaUnderCurve`
- строка 2318 — `ringArea`
- строка 2328 — `segCross`
- строка 2335 — `ringSelfCrosses`
- строка 2357 — `angleRing`
- строка 2363 — `bestAreaRing`
- строка 2393 — `calcAreaPolygon`
- строка 2410 — `AREA_PALETTE`
- строка 2412 — `runAreaCalc`
- строка 2432 — `clearAreaCalc`
- строка 2439 — `drawAreaCalc`
- строка 2469 — `updateAreaCalcPanel`
- строка 2567 — `syncAreaCalcUI`
- строка 2602 — `updateQuickArea`
- строка 2604 — `setAreaCalcMode`
- строка 2620 — `wireFolds`
- строка 2645 — `wireAreaCalc`
- строка 2674 — `paramsAllowed`
- строка 2699 — `isReservedName`
- строка 2739 — `expandImplicitMul`
- строка 2785 — `visibleSvgText`
- строка 2811 — `chartLabelSource`
- строка 2821 — `chartLabelBase`
- строка 2838 — `chartLabelKind`
- строка 2852 — `typesetChartLabels`
- строка 2880 — `prepExpr`
- строка 2898 — `texToPlain`
- строка 2924 — `sceneReservedKey`
- строка 2928 — `freeSymbols`
- строка 2946 — `freeSymbolsUncached`
- строка 2974 — `sceneReserved`
- строка 2997 — `sceneExtraParams`
- строка 3003 — `paramValue`
- строка 3009 — `paramScope`
- строка 3019 — `scopeFor`
- строка 3026 — `evalWithParams`
- строка 3037 — `syncParams`
- строка 3093 — `buildParamChip`
- строка 3218 — `initSceneColorPickers`
- строка 3230 — `syncSceneColorPickers`
- строка 3238 — `syncAxisPlaceholders`
- строка 3253 — `titleAnchorPx`
- строка 3263 — `drawGraphTitle`
- строка 3302 — `editGraphTitleOnCanvas`
- строка 3347 — `normHex`
- строка 3369 — `paletteSix`
- строка 3377 — `closeColorMenu`
- строка 3391 — `onDocClosePick`
- строка 3395 — `onEscClosePick`
- строка 3411 — `paletteTwelve`
- строка 3412 — `makeColorPicker`
- строка 3524 — `autoCurveName`
- строка 3533 — `curveShortName`
- строка 3543 — `markCaption`
- строка 3552 — `drawMarks`
- строка 3651 — `snapTargets`
- строка 3659 — `snapTargetsAll`
- строка 3787 — `macroSnapTargets`
- строка 3806 — `consumerSnapTargets`
- строка 3835 — `ineqSnapTargets`
- строка 3849 — `mathSnapTargets`
- строка 3914 — `tradeSnapTargets`
- строка 3935 — `axisSnapAt`
- строка 3955 — `snapDistPx`
- строка 3976 — `snapPointAt`
- строка 4019 — `showSnapHint`
- строка 4038 — `armMark`
- строка 4051 — `cancelMarkDraft`
- строка 4091 — `resetDecor`
- строка 4183 — `_undoCopyChild`
- строка 4197 — `_undoCopy`
- строка 4217 — `pushUndo`
- строка 4228 — `undoLast`
- строка 4245 — `clearUndo`
- строка 4252 — `forgetSceneSnapshot`
- строка 4254 — `resetSceneMemory`
- строка 4265 — `saveSceneSnapshot`
- строка 4278 — `restoreSceneSnapshot`
- строка 4298 — `addMarkAt`
- строка 4335 — `colorDist`
- строка 4344 — `drawnStrokeColors`
- строка 4360 — `nextMarkColor`
- строка 4376 — `newMark`
- строка 4390 — `pendingMark`
- строка 4393 — `startMarkDraft`
- строка 4402 — `markSnapFn`
- строка 4412 — `renderMarkList`
- строка 4425 — `ensureAddMarkButton`
- строка 4435 — `buildMarkRow`

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
- строка 582 — `drawMathOptimum`
- строка 621 — `drawMathTransform`
- строка 641 — `labelCurveMath`
- строка 671 — `mmSlots`
- строка 672 — `mmGet`
- строка 675 — `mmSet`
- строка 680 — `mmLabel`
- строка 682 — `mmColor`
- строка 689 — `drawMathMinMax`
- строка 750 — `compileAB`
- строка 763 — `parseConstraint`
- строка 781 — `constraintPointsIn`
- строка 800 — `constraintPoints`
- строка 805 — `optimizeAlongCurve`
- строка 818 — `constraintFit`
- строка 836 — `drawMathConstraint`
- строка 892 — `drawLevelCurveOn`
- строка 904 — `mathOptimumReasoning`
- строка 941 — `updateMathPanel`
- строка 1080 — `redrawMath`
- строка 1119 — `setMathSub`
- строка 1142 — `setMathWindow`
- строка 1156 — `setMathX0`
- строка 1181 — `downloadBlob`
- строка 1190 — `exportBaseName`
- строка 1203 — `paperChartClone`
- строка 1230 — `exportNumbersLine`
- строка 1237 — `exportExtras`
- строка 1245 — `exportPNG`
- строка 1282 — `texEscape`
- строка 1289 — `r2`
- строка 1320 — `texPlotSize`
- строка 1344 — `texText`
- строка 1357 — `labelPlainText`
- строка 1389 — `quantityTex`
- строка 1406 — `texHex`
- строка 1421 — `texSamplePath`
- строка 1453 — `texResample`
- строка 1496 — `mathToPgf`
- строка 1544 — `pgfStroke`
- строка 1583 — `texDashPattern`
- строка 1595 — `texCondBounds`
- строка 1606 — `texCondPieces`
- строка 1628 — `buildTexFromState`
- строка 1951 — `buildTexLegacy`
- строка 2299 — `texWantState`
- строка 2303 — `buildTex`
- строка 2310 — `exportTex`
- строка 2318 — `exportPDF`
- строка 2338 — `buildExportFields`
- строка 2355 — `refreshExportPreview`
- строка 2389 — `expValue`
- строка 2398 — `syncExportFormat`
- строка 2410 — `refreshExportSheet`
- строка 2418 — `wireExport`
- строка 2447 — `openExport`
- строка 2466 — `closeExport`
- строка 2485 — `updateGraphPanel`
- строка 2542 — `graphExplainNote`

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
- строка 1885 — `fillPrintBlocks`
- строка 1913 — `setPrintViewBox`

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
- строка 58 — `formNodes`
- строка 63 — `captureForm`
- строка 88 — `applyForm`
- строка 132 — `captureStatePlain`
- строка 141 — `applyStatePlain`
- строка 148 — `rerenderModelLists`
- строка 166 — `forceRebuildAfterApply`
- строка 172 — `syncUiFromState`
- строка 179 — `capturePristine`
- строка 190 — `restorePristine`
- строка 210 — `captureMemory`
- строка 215 — `applyMemory`
- строка 238 — `serializeCurves`
- строка 251 — `rebuildCurves`
- строка 271 — `modelKeyOf`
- строка 276 — `collectModelState`
- строка 296 — `applyModelState`

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
- строка 321 — `openModelByUser`
- строка 341 — `restoreOnLoad`
- строка 365 — `resetModelWithUndo`

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
- строка 283 — `syncShowSection`

#### `calc2/static/calc2/93-shell.js`

- строка 11 — `modelBlockOf`
- строка 16 — `syncModelHead`
- строка 28 — `syncZoomLevel`
- строка 44 — `setFocusMode`
- строка 54 — `afterColumnShown`
- строка 63 — `syncToolSeg`
- строка 70 — `setTool`
- строка 83 — `wireShell`
- строка 155 — `phMoreLayout`
- строка 178 — `wirePhoneMore`

#### `calc2/static/calc2/94-answer.js`

- строка 85 — `heroLabel`
- строка 100 — `notationTex`
- строка 112 — `plainText`
- строка 118 — `statRows`
- строка 122 — `txRow`
- строка 141 — `answerSignature`
- строка 147 — `scheduleAnswer`
- строка 153 — `buildAnswer`
- строка 262 — `buildBurden`
- строка 301 — `buildStatus`
- строка 321 — `buildExplainAccordion`

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
- строка 100 — `selfAfterAnswer`
- строка 116 — `applySelf`
- строка 134 — `selfCanvas`
- строка 161 — `wireSelf`

#### `calc2/static/calc2/99-boot.js`

- строка 13 — `lockNumberFields`
- строка 42 — `init`

**Итого функций в индексе: 1189.**

<!-- AUTO:END -->
