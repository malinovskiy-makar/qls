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
| Кривую нельзя щёлкнуть, потянуть мышью или взвести её ключевые точки | `30-curves.js` (`sceneDrawsCurveList:890`, `NO_CURVE_DRAG:913`) — ⚠️ перетаскивание кривой мышью УДАЛЕНО целиком решением владельца от 20.08 (`CURVE_MOUSE_DRAG`, `attachDrag` и т.п. больше не существуют) — если жалоба именно «кривая не тянется», сначала проверить, не про это ли речь, а не искать несуществующий код |
| Ключевые точки / пересечения кривых не находятся, залипают или дублируют друг друга | `60-overlays.js` (`keyTargets:1114`, `kinksOf:1066`, `drawCrossPoints:1246`, `rollerTargetAt:1497`, `coordAlreadyAt` в `20-plane.js` — «одно место — одно число» для совпавших координат) |
| Ползунок/протяжка ручки двигает окно графика целиком, а не саму кривую | `52-modes.js` (`redrawKeepingWindow:251`, `padMax:167`, `boundsOfDrawn:211`, `STATE.zoomLock`) |
| Легенда или заливка площади не того цвета, дублирует подпись или путается с исходной формулой | `60-overlays.js` (`applyAreaColors:694`, `drawLegend:791`, `typesetStats:445` — при чтении текста легенды в тестах обязателен клон без `.katex-mathml`/`annotation`, иначе число из KaTeX читается трижды) |
| Открылась не та сцена / на карточке виден переключатель чужой модели | `84-picker.js` (`SCENE_ROUTE:185`, `pickScene:461`, `baseScene:265`, `applyCardScope`) |
| KaTeX рисует мусор, красным текстом, или кириллица в формуле выглядит курсивным произведением букв | `82-input.js` (`katexSafe:648`, `katexInto:684` — единственная дверь к KaTeX; узкий неразрывный пробел U+202F, обёртка `\text{...}` для кириллицы) |
| Правка имени точки или границы ползунка не применяется / стирает уже введённое значение | `82-input.js` (`makeEditableValue:1384` — пустое «прежнее» значение обязано означать «прежнего не было», а не `set('')`) |
| Экспорт `.tex`/PDF: кривая или площадь на бумаге не совпадает с экраном, PDF не собирается | `calc2/views.py` (`compile_pdf_pdflatex`, `_TEX_FORBIDDEN`, `pdflatex_available`); `70-scenes-math.js` (`buildTex`, `mathToPgf` — сборка идёт из состояния и SVG вперемешку, не только из `STATE`, см. «Фаза L откачена» в CLAUDE.md) |
| Элемент вообще не виден на экране, хотя код его явно создаёт / кнопка не реагирует ни на что | Сначала `calc2/templates/calc2/calc2.html` — проверить, что `id` есть в разметке (класс дефектов «оборванный обработчик»: контрол переделали, обработчик остался висеть на несуществующем элементе — 6 таких случаев нашла проверка связей сессии 10.08); потом сам JS-файл по имени обработчика |
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
- **`models.py`, `admin.py`, `apps.py`** в приложении calc2 — стандартные
  пустые заготовки Django (моделей у calc2 нет, см. CLAUDE.md), они не
  участвуют в маршруте `/calc2/` и в карту не включены вовсе.

## Автосекция (генерируется командой)

<!-- AUTO:START -->

*Автоматически собрано командой `manage.py calc2_map`. Дата: 2026-08-24. HEAD: `89fbd89`. Не редактировать руками — вся эта часть файла, от отметки начала автосекции и до отметки её конца, перезаписывается заново при каждом запуске команды.*

### Файлы (маршрут → представление → шаблон → статика)

| Путь | Строк | КБ | Тип |
|---|---:|---:|---|
| `calc2/urls.py` | 19 | 0.6 | python |
| `calc2/views.py` | 207 | 11.9 | python |
| `calc2/templates/calc2/calc2.html` | 2452 | 198.6 | шаблон |
| `calc2/static/calc2/calc2.css` | 1994 | 136.0 | CSS |
| `calc2/static/calc2/00-config.js` | 518 | 43.9 | JS |
| `calc2/static/calc2/10-math-core.js` | 734 | 45.4 | JS |
| `calc2/static/calc2/20-plane.js` | 637 | 43.3 | JS |
| `calc2/static/calc2/30-curves.js` | 1000 | 71.2 | JS |
| `calc2/static/calc2/40-scenes-market.js` | 2459 | 163.6 | JS |
| `calc2/static/calc2/42-scenes-mono.js` | 1198 | 84.3 | JS |
| `calc2/static/calc2/44-scenes-firm.js` | 1195 | 79.1 | JS |
| `calc2/static/calc2/46-scenes-labor.js` | 737 | 53.3 | JS |
| `calc2/static/calc2/48-scenes-consumer.js` | 261 | 15.7 | JS |
| `calc2/static/calc2/50-scenes-macro.js` | 414 | 28.3 | JS |
| `calc2/static/calc2/52-modes.js` | 824 | 55.4 | JS |
| `calc2/static/calc2/54-scenes-ppf.js` | 1901 | 126.2 | JS |
| `calc2/static/calc2/56-scenes-inequality.js` | 532 | 34.0 | JS |
| `calc2/static/calc2/60-overlays.js` | 4053 | 246.8 | JS |
| `calc2/static/calc2/70-scenes-math.js` | 2019 | 131.5 | JS |
| `calc2/static/calc2/80-ui.js` | 485 | 30.5 | JS |
| `calc2/static/calc2/82-input.js` | 1794 | 102.2 | JS |
| `calc2/static/calc2/84-picker.js` | 560 | 40.6 | JS |
| `calc2/static/calc2/86-workspace.js` | 1128 | 69.0 | JS |
| `calc2/static/calc2/88-params.js` | 1705 | 109.6 | JS |
| `calc2/static/calc2/90-explain.js` | 381 | 63.1 | JS |
| `calc2/static/calc2/99-boot.js` | 92 | 7.5 | JS |

**Итого: 26 файлов, 29299 строк, 1991.8 КБ.**

### Индекс функций (объявления верхнего уровня, по возрастанию строки)

#### `calc2/static/calc2/00-config.js`

- строка 53 — `fsStep`
- строка 421 — `cssVar`
- строка 425 — `refreshColors`
- строка 491 — `canvasMode`
- строка 496 — `canvasArmed`
- строка 502 — `roleColor`
- строка 508 — `setCalcTheme`
- строка 514 — `toggleCalcTheme`

#### `calc2/static/calc2/10-math-core.js`

- строка 17 — `topLevelEqIndex`
- строка 36 — `axisScope`
- строка 42 — `compileFormula`
- строка 58 — `evalCurve`
- строка 76 — `detectLinear`
- строка 120 — `curveParamNames`
- строка 135 — `paramSignature`
- строка 140 — `refreshLinearForParams`
- строка 172 — `fmtLinear`
- строка 196 — `compileFormulaP`
- строка 207 — `evalQofP`
- строка 214 — `detectLinearP`
- строка 228 — `invertQofP`
- строка 247 — `buildCurveFromQP`
- строка 272 — `makeVerticalCurve`
- строка 276 — `isVertical`
- строка 285 — `findEquilibrium`
- строка 316 — `bisect`
- строка 328 — `integrate`
- строка 350 — `signChanges`
- строка 366 — `areaBetween`
- строка 377 — `crossingCount`
- строка 382 — `findRoot`
- строка 398 — `invCurve`
- строка 404 — `curveDeriv`
- строка 411 — `compileExt`
- строка 419 — `evalSocial`
- строка 447 — `compileTwoVar`
- строка 457 — `compileTwoVarUncached`
- строка 467 — `evalTwoVar`
- строка 479 — `solveLevelB`
- строка 517 — `traceLevelCurve`
- строка 542 — `partialA`
- строка 547 — `partialB`
- строка 554 — `mrsAt`
- строка 566 — `optimizeAlongConstraint`
- строка 630 — `qtyHasCyrillic`
- строка 635 — `qtyIsQuantity`
- строка 649 — `qtyParts`
- строка 707 — `qtyLatex`

#### `calc2/static/calc2/20-plane.js`

- строка 12 — `computeSize`
- строка 43 — `measureText`
- строка 77 — `fitMargins`
- строка 128 — `fitLeftForLabels`
- строка 141 — `makeScales`
- строка 151 — `quadLo`
- строка 158 — `toPx`
- строка 159 — `toData`
- строка 175 — `roundShown`
- строка 184 — `fmtSum`
- строка 190 — `shownDiff`
- строка 191 — `fmtDiff`
- строка 203 — `shownDecimals`
- строка 211 — `sumDecimals`
- строка 215 — `fmt`
- строка 236 — `fmtInput`
- строка 246 — `niceTickStep`
- строка 258 — `axisTicks`
- строка 271 — `xTicks`
- строка 272 — `yTicks`
- строка 275 — `addDefs`
- строка 317 — `drawGrid`
- строка 368 — `extraTickX`
- строка 379 — `extraTickY`
- строка 419 — `dropTickAt`
- строка 446 — `coordValue`
- строка 466 — `coordAlreadyAt`
- строка 477 — `axisValueX`
- строка 504 — `axisValueY`
- строка 529 — `axisValueText`
- строка 546 — `drawAxes`

#### `calc2/static/calc2/30-curves.js`

- строка 8 — `nextColor`
- строка 29 — `curvePoints`
- строка 75 — `markExpr`
- строка 98 — `derivativeExpr`
- строка 137 — `curveAnchor`
- строка 233 — `curveLabelSize`
- строка 234 — `labelScale`
- строка 270 — `unclipLabels`
- строка 339 — `keepAxisNamesInside`
- строка 356 — `spreadLabels`
- строка 529 — `parseColor`
- строка 544 — `relLum`
- строка 552 — `contrastOf`
- строка 557 — `rgbToHsl`
- строка 570 — `hslToRgb`
- строка 597 — `labelInk`
- строка 629 — `applyLabelInk`
- строка 656 — `mixToBg`
- строка 664 — `applyLabelSize`
- строка 695 — `smoothLabel`
- строка 725 — `requestLabelFrame`
- строка 730 — `resetLabelPositions`
- строка 732 — `labelCurve`
- строка 793 — `drawCurves`
- строка 892 — `sceneDrawsCurveList`
- строка 901 — `syncCurveListVisibility`
- строка 916 — `curveDragAllowed`
- строка 926 — `roundDrag`
- строка 964 — `setCurveFreeTerm`

#### `calc2/static/calc2/40-scenes-market.js`

- строка 7 — `curveByRole`
- строка 11 — `recompute`
- строка 320 — `recomputeOpenEconomy`
- строка 385 — `drawOpenAreas`
- строка 422 — `drawOpenLines`
- строка 469 — `attachOpenPwDrag`
- строка 477 — `setOpenPw`
- строка 487 — `setOpenTool`
- строка 499 — `updateOpenPanel`
- строка 535 — `drawEquilibrium`
- строка 577 — `mathTspans`
- строка 617 — `hasMathMarkup`
- строка 631 — `qtyTspans`
- строка 661 — `qtyGreekChar`
- строка 699 — `texToCanvasText`
- строка 708 — `renderLabelText`
- строка 727 — `haloText`
- строка 760 — `pointName`
- строка 783 — `yWageLabel`
- строка 788 — `yWageValue`
- строка 811 — `isMonopolyScene`
- строка 819 — `eqSectionTitle`
- строка 835 — `updateEqSectionTitle`
- строка 852 — `interventionKeyValues`
- строка 894 — `updateInfoPanel`
- строка 967 — `sumSceneOn`
- строка 970 — `sumGroupsOf`
- строка 977 — `sumGroupQty`
- строка 990 — `sumChokePrice`
- строка 1002 — `sumLinearRecord`
- строка 1058 — `integrateBroken`
- строка 1069 — `curveBreaks`
- строка 1080 — `sumSegExpr`
- строка 1098 — `sumPolyline`
- строка 1115 — `sumRebuildSide`
- строка 1146 — `sumRebuild`
- строка 1164 — `sumGroupName`
- строка 1168 — `sumStartExpr`
- строка 1176 — `sumReorder`
- строка 1181 — `sumAddGroup`
- строка 1190 — `sumBuildScene`
- строка 1214 — `sumSetCount`
- строка 1233 — `syncSumUi`
- строка 1247 — `sumGroupStats`
- строка 1279 — `sumRecordHtml`
- строка 1291 — `updateSumPanel`
- строка 1336 — `drawAreas`
- строка 1364 — `beforeInterventionNote`
- строка 1373 — `updateAreasPanel`
- строка 1396 — `drawShiftedSupply`
- строка 1425 — `drawTaxAreas`
- строка 1457 — `drawTaxPoints`
- строка 1506 — `attachTaxDrag`
- строка 1527 — `setTax`
- строка 1557 — `syncTaxKind`
- строка 1564 — `applyIntervCascade`
- строка 1606 — `setTaxForm`
- строка 1622 — `setType`
- строка 1664 — `applyTaxRateBounds`
- строка 1694 — `setTaxKind`
- строка 1706 — `updateTaxPanel`
- строка 1766 — `setTaxSide`
- строка 1774 — `setTaxSideButtons`
- строка 1787 — `drawElasticityZones`
- строка 1805 — `drawElasticityPoint`
- строка 1833 — `attachElastDrag`
- строка 1841 — `drawElasticityPointS`
- строка 1861 — `attachElastDragS`
- строка 1869 — `updateElasticityPanel`
- строка 1933 — `drawExtAreas`
- строка 1945 — `drawExtCurves`
- строка 1969 — `drawExtPoints`
- строка 2003 — `drawExtScenario`
- строка 2012 — `updateExtPanel`
- строка 2053 — `setExtSign`
- строка 2062 — `syncSocialFields`
- строка 2094 — `socialDefaultExpr`
- строка 2100 — `recompileSocial`
- строка 2122 — `setPRegFields`
- строка 2130 — `setPReg`
- строка 2139 — `drawPcAreas`
- строка 2163 — `drawPriceControl`
- строка 2212 — `attachPcDrag`
- строка 2221 — `updatePcPanel`
- строка 2266 — `setQuotaFields`
- строка 2277 — `setQuota`
- строка 2284 — `setQuotaPos`
- строка 2294 — `updateQuotaPriceLabel`
- строка 2306 — `drawQuotaAreas`
- строка 2333 — `drawQuotaLines`
- строка 2378 — `attachQuotaDrag`
- строка 2391 — `updateQuotaPanel`
- строка 2440 — `drawGhost`

#### `calc2/static/calc2/42-scenes-mono.js`

- строка 11 — `mcSourceCurve`
- строка 16 — `mcAt`
- строка 31 — `marginalRevenue`
- строка 40 — `drawMonopolyAreas`
- строка 75 — `drawMonopoly`
- строка 96 — `drawMonopolyPoints`
- строка 133 — `updateMonoPanel`
- строка 164 — `setMarket`
- строка 199 — `monopolyCeiling`
- строка 242 — `drawMonoCeilingAreas`
- строка 261 — `drawMonoKinkedMR`
- строка 278 — `drawMonoCeilingPoints`
- строка 310 — `drawMonoCeilingLine`
- строка 334 — `monopolyTax`
- строка 351 — `monopolyFloor`
- строка 385 — `naturalATC`
- строка 396 — `findRootLast`
- строка 411 — `recomputeNatural`
- строка 440 — `drawNaturalAreas`
- строка 455 — `drawNaturalCurves`
- строка 475 — `drawNaturalPoints`
- строка 504 — `drawNaturalFull`
- строка 512 — `updateNaturalPanel`
- строка 541 — `drawMonoTaxAreas`
- строка 564 — `drawMonoTaxShiftedMC`
- строка 579 — `drawMonoTaxPoints`
- строка 600 — `drawMonoFloorAreas`
- строка 615 — `drawMonoFloorPoints`
- строка 635 — `drawMonoFloorLine`
- строка 650 — `updateMonoInterventionPanel`
- строка 725 — `makeCurve`
- строка 734 — `drawDiscr1`
- строка 758 — `updateDiscr1Panel`
- строка 783 — `allocateMR`
- строка 796 — `recomputeDiscr3`
- строка 816 — `drawMiniMarket`
- строка 903 — `redrawDiscr3`
- строка 926 — `updateDiscr3Panel`
- строка 973 — `applyD3WorldLabels`
- строка 996 — `buildKinkedDemand`
- строка 1043 — `recomputeKinked`
- строка 1063 — `drawKinkedFull`
- строка 1103 — `updateKinkPanel`
- строка 1127 — `applyMonoVisibility`
- строка 1146 — `ensureMonopolyCurves`
- строка 1155 — `fillIfEmpty`
- строка 1158 — `ensureD3Fields`
- строка 1163 — `ensureKinkFields`
- строка 1169 — `ensureMonopolyPreset`
- строка 1176 — `setMonoMode`
- строка 1187 — `setKinkInput`

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
- строка 848 — `noMaxNote`
- строка 857 — `updateProdPanel`
- строка 881 — `recomputeIsoquant`
- строка 892 — `redrawIsoquant`
- строка 906 — `updateIsoPanel`
- строка 944 — `plantMC`
- строка 950 — `plantTC`
- строка 956 — `plantQatMC`
- строка 972 — `recomputePlants`
- строка 1006 — `plantsAt`
- строка 1023 — `redrawPlants`
- строка 1104 — `updatePlantsPanel`
- строка 1135 — `setPlantsView`
- строка 1142 — `setPlantsQ`
- строка 1153 — `setCostsInputMode`
- строка 1161 — `syncCostsInputMode`
- строка 1175 — `setCostsSub`

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
- строка 447 — `drawLaborGapDWL`
- строка 457 — `drawLaborUnionPoints`
- строка 491 — `drawLaborUnionWageLine`
- строка 505 — `attachUnionWageDrag`
- строка 513 — `setUnionWageFields`
- строка 520 — `setUnionWage`
- строка 530 — `setUnionModel`
- строка 547 — `drawLaborBilateral`
- строка 575 — `updateLaborBilateralPanel`
- строка 593 — `setLaborStruct`
- строка 608 — `updateLaborPanel`
- строка 698 — `redrawLabor`

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
- строка 236 — `redrawMacro`
- строка 307 — `drawEquilibriumAt`
- строка 318 — `updateMacroPanel`
- строка 402 — `setMacroModel`

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
- строка 785 — `applyScenarioVisibility`
- строка 811 — `setScenario`

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
- строка 809 — `combinedPpfFormula`
- строка 845 — `verifyFormula`
- строка 856 — `detectKinks`
- строка 881 — `showPaneError`
- строка 892 — `ppfSumCount`
- строка 893 — `ppfSumGet`
- строка 898 — `ppfSumSet`
- строка 903 — `ppfSumName`
- строка 907 — `ppfSumColor`
- строка 921 — `ppfSumSignature`
- строка 931 — `recomputePpfSum`
- строка 937 — `ensurePpfSum`
- строка 941 — `recomputePpfSumRaw`
- строка 1013 — `renderPpfSumRows`
- строка 1059 — `detectSumKinks`
- строка 1077 — `drawPpfSumCurves`
- строка 1098 — `drawPpfSumMarks`
- строка 1124 — `updatePpfSumPanel`
- строка 1189 — `fmtRu`
- строка 1193 — `ppfSumSchemaData`
- строка 1227 — `schemaNote`
- строка 1234 — `drawPpfSumSchema`
- строка 1286 — `redrawPpfSum`
- строка 1299 — `setPpfSumView`
- строка 1310 — `cornerByValue`
- строка 1334 — `bestByValue`
- строка 1353 — `recomputePpfTrade`
- строка 1395 — `drawPpfTrade`
- строка 1420 — `drawPpfTradeMarks`
- строка 1448 — `updatePpfTradePanel`
- строка 1544 — `syncPpftPriceUI`
- строка 1555 — `redrawPpfTrade`
- строка 1576 — `recomputeTradeB`
- строка 1665 — `tradeCpfPoints`
- строка 1682 — `tradeBPanels`
- строка 1703 — `drawTradeB`
- строка 1768 — `drawTradeBMarks`
- строка 1771 — `tbName`
- строка 1777 — `updateTradeBPanel`
- строка 1847 — `syncTbPriceUI`
- строка 1860 — `redrawTradeB`
- строка 1875 — `setTradeScenario`
- строка 1887 — `setPpfSub`

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
- строка 45 — `redrawScene`
- строка 171 — `redrawGraphMode`
- строка 182 — `renderMmRows`
- строка 223 — `graphRowsBox`
- строка 226 — `renderGraphRows`
- строка 244 — `graphError`
- строка 251 — `buildGraphRow`
- строка 333 — `equipGraphRows`
- строка 341 — `graphRowInput`
- строка 378 — `mainScales`
- строка 390 — `drawOverlays`
- строка 430 — `refreshAnalyticsPanel`
- строка 452 — `typesetStats`
- строка 499 — `addStatSign`
- строка 512 — `statToTex`
- строка 544 — `katexVisibleText`
- строка 550 — `restatWide`
- строка 590 — `statInkWidth`
- строка 598 — `statTooWide`
- строка 607 — `statPieces`
- строка 642 — `texAbbrev`
- строка 648 — `renderMathIn`
- строка 691 — `areaKey`
- строка 696 — `subDigits`
- строка 701 — `applyAreaColors`
- строка 711 — `currentAreas`
- строка 729 — `areaOfPathEl`
- строка 791 — `areaShort`
- строка 800 — `drawLegend`
- строка 863 — `floatRects`
- строка 880 — `legendCorner`
- строка 956 — `viewWindow`
- строка 968 — `axisWords`
- строка 974 — `crossPoints`
- строка 1072 — `invalidateKeyTargets`
- строка 1075 — `kinksOf`
- строка 1123 — `keyTargets`
- строка 1240 — `snapVertexAt`
- строка 1274 — `drawCrossPoints`
- строка 1383 — `armCurve`
- строка 1389 — `disarmCurve`
- строка 1397 — `keyPointLit`
- строка 1410 — `drawCurveHits`
- строка 1444 — `pinKeyPoint`
- строка 1464 — `hoverLabel`
- строка 1475 — `drawRoller`
- строка 1496 — `rollerTargetAt`
- строка 1521 — `rollerClampX`
- строка 1540 — `rollerMove`
- строка 1556 — `showRollTip`
- строка 1579 — `hideRollTip`
- строка 1588 — `rollerOff`
- строка 1599 — `curveRightEdge`
- строка 1624 — `axisXLetter`
- строка 1634 — `axisLetter`
- строка 1647 — `armVerts`
- строка 1681 — `syncCanvasMode`
- строка 1701 — `leaveCanvasMode`
- строка 1706 — `addAreaVert`
- строка 1713 — `clearAreaVerts`
- строка 1719 — `renderVertList`
- строка 1785 — `syncAreaCalcButton`
- строка 1797 — `areaPickedCurve`
- строка 1806 — `areaCurveRange`
- строка 1824 — `syncAreaRangeLabel`
- строка 1860 — `freshenVertNames`
- строка 1876 — `drawAreaVerts`
- строка 1936 — `areaTargets`
- строка 1940 — `calcAreaUnderCurve`
- строка 1953 — `ringArea`
- строка 1963 — `segCross`
- строка 1970 — `ringSelfCrosses`
- строка 1992 — `angleRing`
- строка 1998 — `bestAreaRing`
- строка 2028 — `calcAreaPolygon`
- строка 2043 — `AREA_PALETTE`
- строка 2045 — `runAreaCalc`
- строка 2065 — `clearAreaCalc`
- строка 2072 — `drawAreaCalc`
- строка 2101 — `updateAreaCalcPanel`
- строка 2199 — `syncAreaCalcUI`
- строка 2234 — `updateQuickArea`
- строка 2236 — `setAreaCalcMode`
- строка 2252 — `wireFolds`
- строка 2273 — `wireAreaCalc`
- строка 2302 — `paramsAllowed`
- строка 2327 — `isReservedName`
- строка 2367 — `expandImplicitMul`
- строка 2413 — `visibleSvgText`
- строка 2439 — `chartLabelSource`
- строка 2449 — `chartLabelBase`
- строка 2466 — `chartLabelKind`
- строка 2478 — `typesetChartLabels`
- строка 2506 — `prepExpr`
- строка 2524 — `texToPlain`
- строка 2550 — `sceneReservedKey`
- строка 2554 — `freeSymbols`
- строка 2572 — `freeSymbolsUncached`
- строка 2600 — `sceneReserved`
- строка 2623 — `sceneExtraParams`
- строка 2629 — `paramValue`
- строка 2635 — `paramScope`
- строка 2645 — `scopeFor`
- строка 2652 — `evalWithParams`
- строка 2663 — `syncParams`
- строка 2719 — `buildParamChip`
- строка 2842 — `initSceneColorPickers`
- строка 2854 — `syncSceneColorPickers`
- строка 2862 — `syncAxisPlaceholders`
- строка 2877 — `titleAnchorPx`
- строка 2887 — `drawGraphTitle`
- строка 2926 — `editGraphTitleOnCanvas`
- строка 2971 — `normHex`
- строка 2993 — `paletteSix`
- строка 3001 — `closeColorMenu`
- строка 3015 — `onDocClosePick`
- строка 3019 — `onEscClosePick`
- строка 3026 — `makeColorPicker`
- строка 3113 — `autoCurveName`
- строка 3122 — `curveShortName`
- строка 3132 — `markCaption`
- строка 3141 — `drawMarks`
- строка 3228 — `snapTargets`
- строка 3314 — `macroSnapTargets`
- строка 3333 — `consumerSnapTargets`
- строка 3362 — `ineqSnapTargets`
- строка 3376 — `mathSnapTargets`
- строка 3428 — `tradeSnapTargets`
- строка 3448 — `axisSnapAt`
- строка 3467 — `snapDistPx`
- строка 3486 — `snapPointAt`
- строка 3527 — `showSnapHint`
- строка 3546 — `armMark`
- строка 3559 — `cancelMarkDraft`
- строка 3599 — `resetDecor`
- строка 3690 — `_undoCopyChild`
- строка 3704 — `_undoCopy`
- строка 3718 — `pushUndo`
- строка 3728 — `undoLast`
- строка 3744 — `clearUndo`
- строка 3751 — `forgetSceneSnapshot`
- строка 3753 — `resetSceneMemory`
- строка 3755 — `saveSceneSnapshot`
- строка 3764 — `restoreSceneSnapshot`
- строка 3783 — `addMarkAt`
- строка 3818 — `colorDist`
- строка 3827 — `drawnStrokeColors`
- строка 3843 — `nextMarkColor`
- строка 3859 — `newMark`
- строка 3871 — `pendingMark`
- строка 3874 — `startMarkDraft`
- строка 3883 — `markSnapFn`
- строка 3893 — `renderMarkList`
- строка 3906 — `ensureAddMarkButton`
- строка 3916 — `buildMarkRow`

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
- строка 1474 — `buildTex`
- строка 1817 — `exportTex`
- строка 1825 — `exportPDF`
- строка 1845 — `buildExportFields`
- строка 1862 — `refreshExportPreview`
- строка 1896 — `expValue`
- строка 1898 — `openExport`
- строка 1915 — `closeExport`
- строка 1934 — `updateGraphPanel`
- строка 1991 — `graphExplainNote`

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
- строка 75 — `pwCond`
- строка 84 — `pwRows`
- строка 105 — `pwPrefixOf`
- строка 110 — `pwFormula`
- строка 129 — `pwLatex`
- строка 151 — `pwVar`
- строка 164 — `casesToMath`
- строка 194 — `condToMath`
- строка 205 — `renderPw`
- строка 252 — `pwAttachKeyboard`
- строка 276 — `pwPreview`
- строка 299 — `pwVarForField`
- строка 326 — `openPiecewise`
- строка 340 — `closePiecewise`
- строка 349 — `insertIntoFormula`
- строка 379 — `mathfieldClass`
- строка 383 — `onMathliveReady`
- строка 418 — `fieldProblem`
- строка 468 — `unknownTexCommand`
- строка 477 — `texGroup`
- строка 487 — `latexToMath`
- строка 633 — `isUndefinedTailNode`
- строка 638 — `unwrapParens`
- строка 649 — `pwCondTex`
- строка 668 — `condChainToCases`
- строка 690 — `mathToLatexField`
- строка 712 — `upgradeFormulaField`
- строка 742 — `fieldOnScreen`
- строка 754 — `flushMathfieldsSoon`
- строка 760 — `flushMathfields`
- строка 794 — `katexSafe`
- строка 830 — `katexInto`
- строка 845 — `placeholderTex`
- строка 854 — `texSafeText`
- строка 858 — `buildMathfield`
- строка 1010 — `insertIntoField`
- строка 1081 — `mkbdKey`
- строка 1108 — `buildKeyboard`
- строка 1168 — `closeAllKeyboardsExcept`
- строка 1189 — `scheduleParamsSync`
- строка 1195 — `registerFormulaField`
- строка 1212 — `fieldActive`
- строка 1221 — `liveFormulaTexts`
- строка 1248 — `equipFormulaField`
- строка 1285 — `equipAllFormulaFields`
- строка 1289 — `attachFormulaHelp`
- строка 1479 — `makeEditableValue`
- строка 1584 — `makeToggle`
- строка 1626 — `segToToggle`
- строка 1658 — `closeAllSelectMenus`
- строка 1662 — `upgradeSelect`
- строка 1763 — `upgradeTextField`
- строка 1786 — `upgradeTextFieldsIn`

#### `calc2/static/calc2/84-picker.js`

- строка 8 — `loadScene`
- строка 139 — `closePicker`
- строка 158 — `setPickerBlockOpen`
- строка 163 — `openPicker`
- строка 326 — `baseScene`
- строка 335 — `applyCardScope`
- строка 413 — `blockSpec`
- строка 425 — `foldPickerGroups`
- строка 514 — `plural`
- строка 522 — `pickScene`

#### `calc2/static/calc2/86-workspace.js`

- строка 55 — `setFieldValue`
- строка 61 — `relocateForScene`
- строка 71 — `clearResultPanels`
- строка 78 — `toast`
- строка 85 — `dockActive`
- строка 92 — `setSideOpen`
- строка 113 — `setToolsOpen`
- строка 114 — `setParamsOpen`
- строка 124 — `hasAnalytics`
- строка 131 — `moveExplanations`
- строка 152 — `syncAnalyticsPanel`
- строка 233 — `sectionIcon`
- строка 240 — `cardifySections`
- строка 285 — `collapseCards`
- строка 301 — `syncLabelSizeSeg`
- строка 312 — `openSection`
- строка 346 — `cardWithFormula`
- строка 359 — `syncFirstCard`
- строка 378 — `wireScene`
- строка 540 — `resetCurrentScene`
- строка 548 — `setWrenchOpen`
- строка 558 — `applyViewBounds`
- строка 585 — `quadWindow`
- строка 590 — `quadSameWindow`
- строка 597 — `setFirstQuad`
- строка 636 — `setGridMode`
- строка 654 — `hintTip`
- строка 665 — `showHintTip`
- строка 715 — `hideHintTip`
- строка 740 — `tipText`
- строка 769 — `tipTex`
- строка 779 — `tipName`
- строка 787 — `tipExpr`
- строка 797 — `tipPlain`
- строка 799 — `showTipFor`
- строка 805 — `wireTips`
- строка 844 — `syncTipLabels`
- строка 857 — `hintAnchor`
- строка 896 — `hintsToDots`
- строка 934 — `wireHintButtons`
- строка 974 — `wireWrench`
- строка 1053 — `fillPrintBlocks`
- строка 1081 — `setPrintViewBox`

#### `calc2/static/calc2/88-params.js`

- строка 34 — `pultRegulatorIds`
- строка 112 — `pultCurveList`
- строка 123 — `pultExtraSig`
- строка 129 — `pultExtraSigBase`
- строка 141 — `pultShouldShow`
- строка 151 — `shiftChipLabel`
- строка 156 — `curveChipLabel`
- строка 163 — `pultCurveSig`
- строка 170 — `paintEqLabel`
- строка 184 — `texifyName`
- строка 200 — `editEqValue`
- строка 259 — `centerBandOn`
- строка 263 — `pullIntoBand`
- строка 267 — `attachBoundsEditor`
- строка 349 — `refreshRegulators`
- строка 360 — `makePchip`
- строка 388 — `curveShiftBase`
- строка 395 — `buildPultCurveChips`
- строка 476 — `syncPultCurveValues`
- строка 501 — `capturePultHome`
- строка 508 — `capturePultHomes`
- строка 513 — `returnPultHome`
- строка 525 — `syncPultRegulators`
- строка 544 — `upgradeRegulator`
- строка 674 — `shortRegulatorName`
- строка 688 — `ppfLinearFormula`
- строка 694 — `ppfInterceptsOf`
- строка 702 — `ppfSetSingle`
- строка 710 — `ppfSetSum`
- строка 727 — `addPultXChip`
- строка 738 — `buildPultExtra`
- строка 770 — `ineqParseIncomes`
- строка 773 — `ineqMasterRebase`
- строка 778 — `ineqMasterScale`
- строка 796 — `ineqMasterApply`
- строка 808 — `ineqMasterDetach`
- строка 813 — `buildIneqMasterChip`
- строка 821 — `showPult`
- строка 848 — `updatePult`
- строка 868 — `wireControls`

#### `calc2/static/calc2/90-explain.js`

- строка 375 — `sceneExplainHtml`

#### `calc2/static/calc2/99-boot.js`

- строка 13 — `lockNumberFields`
- строка 42 — `init`

**Итого функций в индексе: 893.**

<!-- AUTO:END -->
