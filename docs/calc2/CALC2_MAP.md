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

*Автоматически собрано командой `manage.py calc2_map`. Дата: 2026-09-06. HEAD: `75511ff`. Не редактировать руками — вся эта часть файла, от отметки начала автосекции и до отметки её конца, перезаписывается заново при каждом запуске команды.*

### Файлы (маршрут → представление → шаблон → статика)

| Путь | Строк | КБ | Тип |
|---|---:|---:|---|
| `calc2/urls.py` | 19 | 0.6 | python |
| `calc2/views.py` | 219 | 13.3 | python |
| `calc2/templates/calc2/calc2.html` | 2527 | 208.4 | шаблон |
| `calc2/static/calc2/calc2.css` | 2352 | 171.6 | CSS |
| `calc2/static/calc2/00-config.js` | 563 | 49.1 | JS |
| `calc2/static/calc2/10-math-core.js` | 1126 | 74.6 | JS |
| `calc2/static/calc2/20-plane.js` | 991 | 68.2 | JS |
| `calc2/static/calc2/30-curves.js` | 1323 | 98.0 | JS |
| `calc2/static/calc2/40-scenes-market.js` | 3722 | 269.0 | JS |
| `calc2/static/calc2/42-scenes-mono.js` | 1677 | 123.0 | JS |
| `calc2/static/calc2/44-scenes-firm.js` | 1207 | 81.1 | JS |
| `calc2/static/calc2/46-scenes-labor.js` | 736 | 53.9 | JS |
| `calc2/static/calc2/48-scenes-consumer.js` | 261 | 16.0 | JS |
| `calc2/static/calc2/50-scenes-macro.js` | 416 | 28.8 | JS |
| `calc2/static/calc2/52-modes.js` | 927 | 64.1 | JS |
| `calc2/static/calc2/54-scenes-ppf.js` | 3093 | 201.4 | JS |
| `calc2/static/calc2/56-scenes-inequality.js` | 530 | 34.6 | JS |
| `calc2/static/calc2/60-overlays.js` | 4451 | 282.9 | JS |
| `calc2/static/calc2/70-scenes-math.js` | 2450 | 158.2 | JS |
| `calc2/static/calc2/80-ui.js` | 526 | 33.8 | JS |
| `calc2/static/calc2/82-input.js` | 1966 | 117.5 | JS |
| `calc2/static/calc2/84-picker.js` | 577 | 43.4 | JS |
| `calc2/static/calc2/86-workspace.js` | 1869 | 121.2 | JS |
| `calc2/static/calc2/88-params.js` | 1869 | 127.3 | JS |
| `calc2/static/calc2/90-explain.js` | 381 | 63.5 | JS |
| `calc2/static/calc2/99-boot.js` | 98 | 8.1 | JS |

**Итого: 26 файлов, 35876 строк, 2511.6 КБ.**

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
- строка 872 — `smoothLabel`
- строка 902 — `requestLabelFrame`
- строка 907 — `resetLabelPositions`
- строка 916 — `curveLabelAnchor`
- строка 925 — `labelCurve`
- строка 996 — `curveWidth`
- строка 1038 — `curveDash`
- строка 1046 — `curveOpacity`
- строка 1054 — `drawCurves`
- строка 1215 — `sceneDrawsCurveList`
- строка 1224 — `syncCurveListVisibility`
- строка 1239 — `curveDragAllowed`
- строка 1249 — `roundDrag`
- строка 1287 — `setCurveFreeTerm`

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
- строка 1831 — `sumAnalyticsKey`
- строка 1849 — `sumGroupName`
- строка 1872 — `sumTagOf`
- строка 1879 — `sumShortTag`
- строка 1908 — `sumGroupColor`
- строка 1913 — `sumStartExpr`
- строка 1921 — `sumReorder`
- строка 1926 — `sumAddGroup`
- строка 1939 — `sumBuildScene`
- строка 1967 — `sumSetCount`
- строка 1986 — `syncSumUi`
- строка 2000 — `sumGroupStats`
- строка 2046 — `sumFinalRecords`
- строка 2064 — `updateSumPanel`
- строка 2125 — `drawAreas`
- строка 2153 — `beforeInterventionNote`
- строка 2162 — `updateAreasPanel`
- строка 2191 — `intervOnBuyer`
- строка 2200 — `drawShiftedSupply`
- строка 2252 — `taxPivotQ`
- строка 2283 — `taxPivotPoint`
- строка 2292 — `drawTaxPivot`
- строка 2327 — `drawTaxAreas`
- строка 2363 — `drawTaxPoints`
- строка 2416 — `attachTaxDrag`
- строка 2437 — `setTax`
- строка 2555 — `taxFormKey`
- строка 2563 — `pctForm`
- строка 2571 — `syncTaxKind`
- строка 2576 — `applyIntervCascade`
- строка 2649 — `setTaxForm`
- строка 2667 — `setType`
- строка 2717 — `rateLetter`
- строка 2721 — `rateUnit`
- строка 2743 — `modelPriceTop`
- строка 2754 — `unitRateMax`
- строка 2762 — `applyPriceRegBounds`
- строка 2771 — `applyTaxRateBounds`
- строка 2806 — `syncQuotaHint`
- строка 2823 — `syncPcHint`
- строка 2831 — `markCurrentIntervHint`
- строка 2840 — `intervHintKey`
- строка 2850 — `intervHintHtml`
- строка 2864 — `syncTaxHint`
- строка 2894 — `setTaxKind`
- строка 2900 — `updateTaxPanel`
- строка 3023 — `setTaxSide`
- строка 3034 — `setTaxSideButtons`
- строка 3047 — `drawElasticityZones`
- строка 3065 — `drawElasticityPoint`
- строка 3094 — `attachElastDrag`
- строка 3102 — `drawElasticityPointS`
- строка 3122 — `attachElastDragS`
- строка 3130 — `updateElasticityPanel`
- строка 3194 — `drawExtAreas`
- строка 3206 — `drawExtCurves`
- строка 3230 — `drawExtPoints`
- строка 3264 — `drawExtScenario`
- строка 3273 — `updateExtPanel`
- строка 3314 — `setExtSign`
- строка 3323 — `syncSocialFields`
- строка 3355 — `socialDefaultExpr`
- строка 3361 — `recompileSocial`
- строка 3383 — `setPRegFields`
- строка 3392 — `setPReg`
- строка 3401 — `drawPcAreas`
- строка 3425 — `drawPriceControl`
- строка 3474 — `attachPcDrag`
- строка 3483 — `updatePcPanel`
- строка 3528 — `setQuotaFields`
- строка 3540 — `setQuota`
- строка 3547 — `setQuotaPos`
- строка 3557 — `updateQuotaPriceLabel`
- строка 3569 — `drawQuotaAreas`
- строка 3596 — `drawQuotaLines`
- строка 3641 — `attachQuotaDrag`
- строка 3654 — `updateQuotaPanel`
- строка 3703 — `drawGhost`

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
- строка 918 — `updateIsoPanel`
- строка 956 — `plantMC`
- строка 962 — `plantTC`
- строка 968 — `plantQatMC`
- строка 984 — `recomputePlants`
- строка 1018 — `plantsAt`
- строка 1035 — `redrawPlants`
- строка 1116 — `updatePlantsPanel`
- строка 1147 — `setPlantsView`
- строка 1154 — `setPlantsQ`
- строка 1165 — `setCostsInputMode`
- строка 1173 — `syncCostsInputMode`
- строка 1187 — `setCostsSub`

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
- строка 165 — `scheduleRangeAnim`
- строка 184 — `padMax`
- строка 202 — `curveAxisBounds`
- строка 233 — `boundsOfDrawn`
- строка 273 — `redrawKeepingWindow`
- строка 278 — `applyAutoRanges`
- строка 305 — `zoomRound`
- строка 311 — `zoomBy`
- строка 394 — `panByPixels`
- строка 474 — `wantedRanges`
- строка 507 — `growRanges`
- строка 523 — `growWindowToModel`
- строка 534 — `resetZoom`
- строка 565 — `flushWheel`
- строка 576 — `initZoom`
- строка 771 — `zoomStep`
- строка 780 — `cancelRangeAnim`
- строка 792 — `makeThrottle`
- строка 805 — `ineqRedraw`
- строка 808 — `setMode`
- строка 888 — `applyScenarioVisibility`
- строка 914 — `setScenario`

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
- строка 71 — `redrawScene`
- строка 216 — `redrawGraphMode`
- строка 227 — `renderMmRows`
- строка 268 — `graphRowsBox`
- строка 271 — `renderGraphRows`
- строка 289 — `graphError`
- строка 296 — `buildGraphRow`
- строка 378 — `equipGraphRows`
- строка 386 — `graphRowInput`
- строка 431 — `mainScales`
- строка 442 — `drawOverlays`
- строка 548 — `guardedPanelIds`
- строка 552 — `guardPanelBoxes`
- строка 588 — `panelsChangedSinceLastPass`
- строка 593 — `markPanelsChanged`
- строка 596 — `flushPendingPanelClears`
- строка 605 — `refreshAnalyticsPanel`
- строка 633 — `typesetStats`
- строка 680 — `addStatSign`
- строка 693 — `statToTex`
- строка 725 — `katexVisibleText`
- строка 731 — `restatWide`
- строка 771 — `statInkWidth`
- строка 779 — `statTooWide`
- строка 788 — `statPieces`
- строка 823 — `texAbbrev`
- строка 829 — `renderMathIn`
- строка 872 — `areaKey`
- строка 877 — `subDigits`
- строка 882 — `applyAreaColors`
- строка 892 — `currentAreas`
- строка 910 — `areaOfPathEl`
- строка 972 — `areaShort`
- строка 981 — `drawLegend`
- строка 1044 — `floatRects`
- строка 1061 — `legendCorner`
- строка 1138 — `viewWindow`
- строка 1150 — `axisWords`
- строка 1156 — `crossPoints`
- строка 1258 — `invalidateKeyTargets`
- строка 1261 — `kinksOf`
- строка 1309 — `keyTargets`
- строка 1484 — `snapVertexAt`
- строка 1516 — `markPanelId`
- строка 1536 — `armedPanelId`
- строка 1542 — `drawCrossPoints`
- строка 1652 — `armCurve`
- строка 1658 — `disarmCurve`
- строка 1666 — `keyPointLit`
- строка 1679 — `drawCurveHits`
- строка 1717 — `pinKeyPoint`
- строка 1737 — `hoverLabel`
- строка 1748 — `drawRoller`
- строка 1769 — `rollerTargetAt`
- строка 1799 — `rollerClampX`
- строка 1818 — `rollerMove`
- строка 1834 — `showRollTip`
- строка 1857 — `hideRollTip`
- строка 1866 — `rollerOff`
- строка 1877 — `curveRightEdge`
- строка 1902 — `axisXLetter`
- строка 1912 — `axisLetter`
- строка 1925 — `armVerts`
- строка 1959 — `syncCanvasMode`
- строка 1979 — `leaveCanvasMode`
- строка 1984 — `addAreaVert`
- строка 1997 — `vertPanels`
- строка 2000 — `vertsMixed`
- строка 2002 — `clearAreaVerts`
- строка 2008 — `renderVertList`
- строка 2080 — `syncAreaCalcButton`
- строка 2092 — `areaPickedCurve`
- строка 2101 — `areaCurveRange`
- строка 2119 — `syncAreaRangeLabel`
- строка 2155 — `freshenVertNames`
- строка 2171 — `drawAreaVerts`
- строка 2240 — `areaTargets`
- строка 2244 — `calcAreaUnderCurve`
- строка 2257 — `ringArea`
- строка 2267 — `segCross`
- строка 2274 — `ringSelfCrosses`
- строка 2296 — `angleRing`
- строка 2302 — `bestAreaRing`
- строка 2332 — `calcAreaPolygon`
- строка 2349 — `AREA_PALETTE`
- строка 2351 — `runAreaCalc`
- строка 2371 — `clearAreaCalc`
- строка 2378 — `drawAreaCalc`
- строка 2408 — `updateAreaCalcPanel`
- строка 2506 — `syncAreaCalcUI`
- строка 2541 — `updateQuickArea`
- строка 2543 — `setAreaCalcMode`
- строка 2559 — `wireFolds`
- строка 2584 — `wireAreaCalc`
- строка 2613 — `paramsAllowed`
- строка 2638 — `isReservedName`
- строка 2678 — `expandImplicitMul`
- строка 2724 — `visibleSvgText`
- строка 2750 — `chartLabelSource`
- строка 2760 — `chartLabelBase`
- строка 2777 — `chartLabelKind`
- строка 2791 — `typesetChartLabels`
- строка 2819 — `prepExpr`
- строка 2837 — `texToPlain`
- строка 2863 — `sceneReservedKey`
- строка 2867 — `freeSymbols`
- строка 2885 — `freeSymbolsUncached`
- строка 2913 — `sceneReserved`
- строка 2936 — `sceneExtraParams`
- строка 2942 — `paramValue`
- строка 2948 — `paramScope`
- строка 2958 — `scopeFor`
- строка 2965 — `evalWithParams`
- строка 2976 — `syncParams`
- строка 3032 — `buildParamChip`
- строка 3155 — `initSceneColorPickers`
- строка 3167 — `syncSceneColorPickers`
- строка 3175 — `syncAxisPlaceholders`
- строка 3190 — `titleAnchorPx`
- строка 3200 — `drawGraphTitle`
- строка 3239 — `editGraphTitleOnCanvas`
- строка 3284 — `normHex`
- строка 3306 — `paletteSix`
- строка 3314 — `closeColorMenu`
- строка 3328 — `onDocClosePick`
- строка 3332 — `onEscClosePick`
- строка 3339 — `makeColorPicker`
- строка 3426 — `autoCurveName`
- строка 3435 — `curveShortName`
- строка 3445 — `markCaption`
- строка 3454 — `drawMarks`
- строка 3553 — `snapTargets`
- строка 3561 — `snapTargetsAll`
- строка 3689 — `macroSnapTargets`
- строка 3708 — `consumerSnapTargets`
- строка 3737 — `ineqSnapTargets`
- строка 3751 — `mathSnapTargets`
- строка 3816 — `tradeSnapTargets`
- строка 3837 — `axisSnapAt`
- строка 3857 — `snapDistPx`
- строка 3878 — `snapPointAt`
- строка 3921 — `showSnapHint`
- строка 3940 — `armMark`
- строка 3953 — `cancelMarkDraft`
- строка 3993 — `resetDecor`
- строка 4084 — `_undoCopyChild`
- строка 4098 — `_undoCopy`
- строка 4112 — `pushUndo`
- строка 4122 — `undoLast`
- строка 4138 — `clearUndo`
- строка 4145 — `forgetSceneSnapshot`
- строка 4147 — `resetSceneMemory`
- строка 4149 — `saveSceneSnapshot`
- строка 4158 — `restoreSceneSnapshot`
- строка 4177 — `addMarkAt`
- строка 4214 — `colorDist`
- строка 4223 — `drawnStrokeColors`
- строка 4239 — `nextMarkColor`
- строка 4255 — `newMark`
- строка 4269 — `pendingMark`
- строка 4272 — `startMarkDraft`
- строка 4281 — `markSnapFn`
- строка 4291 — `renderMarkList`
- строка 4304 — `ensureAddMarkButton`
- строка 4314 — `buildMarkRow`

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
- строка 890 — `drawLevelCurveOn`
- строка 901 — `mathOptimumReasoning`
- строка 938 — `updateMathPanel`
- строка 1077 — `redrawMath`
- строка 1116 — `setMathSub`
- строка 1139 — `setMathWindow`
- строка 1153 — `setMathX0`
- строка 1178 — `downloadBlob`
- строка 1187 — `exportBaseName`
- строка 1193 — `exportPNG`
- строка 1220 — `texEscape`
- строка 1227 — `r2`
- строка 1258 — `texPlotSize`
- строка 1282 — `texText`
- строка 1295 — `labelPlainText`
- строка 1327 — `quantityTex`
- строка 1344 — `texHex`
- строка 1359 — `texSamplePath`
- строка 1391 — `texResample`
- строка 1434 — `mathToPgf`
- строка 1482 — `pgfStroke`
- строка 1521 — `texDashPattern`
- строка 1533 — `texCondBounds`
- строка 1544 — `texCondPieces`
- строка 1566 — `buildTexFromState`
- строка 1889 — `buildTexLegacy`
- строка 2237 — `texWantState`
- строка 2241 — `buildTex`
- строка 2248 — `exportTex`
- строка 2256 — `exportPDF`
- строка 2276 — `buildExportFields`
- строка 2293 — `refreshExportPreview`
- строка 2327 — `expValue`
- строка 2329 — `openExport`
- строка 2346 — `closeExport`
- строка 2365 — `updateGraphPanel`
- строка 2422 — `graphExplainNote`

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
- строка 569 — `fieldProblem`
- строка 619 — `unknownTexCommand`
- строка 628 — `texGroup`
- строка 638 — `latexToMath`
- строка 784 — `isUndefinedTailNode`
- строка 789 — `unwrapParens`
- строка 800 — `pwCondTex`
- строка 819 — `condChainToCases`
- строка 841 — `mathToLatexField`
- строка 863 — `upgradeFormulaField`
- строка 910 — `fitFormulaField`
- строка 961 — `fitFormulaFields`
- строка 964 — `fitFormulaFieldsSoon`
- строка 979 — `fieldOnScreen`
- строка 991 — `flushMathfieldsSoon`
- строка 997 — `flushMathfields`
- строка 1031 — `katexSafe`
- строка 1067 — `katexInto`
- строка 1082 — `placeholderTex`
- строка 1091 — `texSafeText`
- строка 1095 — `buildMathfield`
- строка 1269 — `insertIntoField`
- строка 1288 — `keyboardAdapter`
- строка 1290 — `insert`
- строка 1291 — `deleteBack`
- строка 1296 — `clear`
- строка 1300 — `piecewise`
- строка 1308 — `buildKeyboard`
- строка 1313 — `closeAllKeyboardsExcept`
- строка 1340 — `onFormulaInput`
- строка 1361 — `scheduleParamsSync`
- строка 1367 — `registerFormulaField`
- строка 1384 — `fieldActive`
- строка 1393 — `liveFormulaTexts`
- строка 1420 — `equipFormulaField`
- строка 1457 — `equipAllFormulaFields`
- строка 1461 — `attachFormulaHelp`
- строка 1651 — `makeEditableValue`
- строка 1756 — `makeToggle`
- строка 1798 — `segToToggle`
- строка 1830 — `closeAllSelectMenus`
- строка 1834 — `upgradeSelect`
- строка 1935 — `upgradeTextField`
- строка 1958 — `upgradeTextFieldsIn`

#### `calc2/static/calc2/84-picker.js`

- строка 8 — `loadScene`
- строка 147 — `closePicker`
- строка 169 — `openPicker`
- строка 344 — `baseScene`
- строка 353 — `applyCardScope`
- строка 431 — `blockSpec`
- строка 443 — `foldPickerGroups`
- строка 530 — `plural`
- строка 538 — `pickScene`

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
- строка 225 — `syncAnalyticsPanel`
- строка 306 — `sectionIcon`
- строка 313 — `cardifySections`
- строка 367 — `collapseCards`
- строка 384 — `syncLabelSizeSeg`
- строка 395 — `openSection`
- строка 429 — `cardWithFormula`
- строка 442 — `syncFirstCard`
- строка 461 — `wireScene`
- строка 621 — `resetCurrentScene`
- строка 629 — `setWrenchOpen`
- строка 639 — `applyViewBounds`
- строка 666 — `quadWindow`
- строка 671 — `quadSameWindow`
- строка 690 — `offQuadShownPoints`
- строка 720 — `fitWindowToOffQuad`
- строка 742 — `setFirstQuad`
- строка 792 — `setGridMode`
- строка 810 — `hintTip`
- строка 837 — `fitTipMath`
- строка 855 — `showHintTip`
- строка 907 — `hideHintTip`
- строка 932 — `tipText`
- строка 961 — `tipTex`
- строка 971 — `tipName`
- строка 988 — `tipExpr`
- строка 998 — `tipPlain`
- строка 1027 — `ffEsc`
- строка 1037 — `ffLatexOf`
- строка 1059 — `finalFunctionHtml`
- строка 1084 — `ffParseCases`
- строка 1106 — `ffCondCompact`
- строка 1130 — `ffMathHtml`
- строка 1154 — `ffKatexW`
- строка 1170 — `ffFitCases`
- строка 1257 — `fitFinalMath`
- строка 1286 — `ffCopyText`
- строка 1294 — `ffCopyFallback`
- строка 1306 — `wireFinalCopy`
- строка 1339 — `ffOpenExpand`
- строка 1360 — `ffCloseExpand`
- строка 1372 — `setFinalFunctions`
- строка 1390 — `refitFinalMathSoon`
- строка 1418 — `markNotationsIn`
- строка 1448 — `paintNotation`
- строка 1458 — `showTipFor`
- строка 1464 — `wireTips`
- строка 1503 — `syncTipLabels`
- строка 1516 — `hintAnchor`
- строка 1594 — `fitPanelMath`
- строка 1624 — `syncHintDots`
- строка 1635 — `hintsToDots`
- строка 1673 — `wireHintButtons`
- строка 1715 — `wireWrench`
- строка 1794 — `fillPrintBlocks`
- строка 1822 — `setPrintViewBox`

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
- строка 341 — `centerBandOn`
- строка 345 — `pullIntoBand`
- строка 349 — `attachBoundsEditor`
- строка 431 — `refreshRegulators`
- строка 442 — `makePchip`
- строка 470 — `curveShiftBase`
- строка 477 — `buildPultCurveChips`
- строка 560 — `syncPultCurveValues`
- строка 585 — `capturePultHome`
- строка 592 — `capturePultHomes`
- строка 597 — `returnPultHome`
- строка 609 — `syncPultRegulators`
- строка 634 — `upgradeRegulator`
- строка 798 — `shortRegulatorName`
- строка 822 — `ppfLinearFormula`
- строка 828 — `ppfInterceptsOf`
- строка 836 — `ppfSetSingle`
- строка 844 — `ppfSetSum`
- строка 864 — `addPultXChip`
- строка 891 — `buildPultExtra`
- строка 923 — `ineqParseIncomes`
- строка 926 — `ineqMasterRebase`
- строка 931 — `ineqMasterScale`
- строка 949 — `ineqMasterApply`
- строка 961 — `ineqMasterDetach`
- строка 966 — `buildIneqMasterChip`
- строка 978 — `showPult`
- строка 1005 — `updatePult`
- строка 1025 — `wireControls`

#### `calc2/static/calc2/90-explain.js`

- строка 375 — `sceneExplainHtml`

#### `calc2/static/calc2/99-boot.js`

- строка 13 — `lockNumberFields`
- строка 42 — `init`

**Итого функций в индексе: 1062.**

<!-- AUTO:END -->
