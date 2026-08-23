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

*Автоматически собрано командой `manage.py calc2_map`. Дата: 2026-08-23. HEAD: `776984a`. Не редактировать руками — вся эта часть файла, от отметки начала автосекции и до отметки её конца, перезаписывается заново при каждом запуске команды.*

### Файлы (маршрут → представление → шаблон → статика)

| Путь | Строк | КБ | Тип |
|---|---:|---:|---|
| `calc2/urls.py` | 19 | 0.6 | python |
| `calc2/views.py` | 207 | 11.9 | python |
| `calc2/templates/calc2/calc2.html` | 2459 | 198.7 | шаблон |
| `calc2/static/calc2/calc2.css` | 1994 | 136.0 | CSS |
| `calc2/static/calc2/00-config.js` | 521 | 44.1 | JS |
| `calc2/static/calc2/10-math-core.js` | 734 | 45.4 | JS |
| `calc2/static/calc2/20-plane.js` | 637 | 43.3 | JS |
| `calc2/static/calc2/30-curves.js` | 1000 | 71.2 | JS |
| `calc2/static/calc2/40-scenes-market.js` | 2086 | 140.3 | JS |
| `calc2/static/calc2/42-scenes-mono.js` | 1199 | 84.3 | JS |
| `calc2/static/calc2/44-scenes-firm.js` | 1195 | 79.1 | JS |
| `calc2/static/calc2/46-scenes-labor.js` | 737 | 53.3 | JS |
| `calc2/static/calc2/48-scenes-consumer.js` | 261 | 15.7 | JS |
| `calc2/static/calc2/50-scenes-macro.js` | 414 | 28.3 | JS |
| `calc2/static/calc2/52-modes.js` | 820 | 54.7 | JS |
| `calc2/static/calc2/54-scenes-ppf.js` | 1864 | 123.5 | JS |
| `calc2/static/calc2/56-scenes-inequality.js` | 532 | 34.0 | JS |
| `calc2/static/calc2/60-overlays.js` | 3904 | 235.0 | JS |
| `calc2/static/calc2/70-scenes-math.js` | 2019 | 131.5 | JS |
| `calc2/static/calc2/80-ui.js` | 459 | 27.8 | JS |
| `calc2/static/calc2/82-input.js` | 1708 | 96.3 | JS |
| `calc2/static/calc2/84-picker.js` | 541 | 39.4 | JS |
| `calc2/static/calc2/86-workspace.js` | 1055 | 64.1 | JS |
| `calc2/static/calc2/88-params.js` | 1695 | 108.7 | JS |
| `calc2/static/calc2/90-explain.js` | 381 | 63.1 | JS |
| `calc2/static/calc2/99-boot.js` | 93 | 7.6 | JS |

**Итого: 26 файлов, 28534 строк, 1937.9 КБ.**

### Индекс функций (объявления верхнего уровня, по возрастанию строки)

#### `calc2/static/calc2/00-config.js`

- строка 53 — `fsStep`
- строка 424 — `cssVar`
- строка 428 — `refreshColors`
- строка 494 — `canvasMode`
- строка 499 — `canvasArmed`
- строка 505 — `roleColor`
- строка 511 — `setCalcTheme`
- строка 517 — `toggleCalcTheme`

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
- строка 335 — `recomputeOpenEconomy`
- строка 400 — `drawOpenAreas`
- строка 437 — `drawOpenLines`
- строка 484 — `attachOpenPwDrag`
- строка 492 — `setOpenPw`
- строка 502 — `setOpenTool`
- строка 514 — `updateOpenPanel`
- строка 550 — `drawEquilibrium`
- строка 592 — `mathTspans`
- строка 632 — `hasMathMarkup`
- строка 646 — `qtyTspans`
- строка 676 — `qtyGreekChar`
- строка 714 — `texToCanvasText`
- строка 723 — `renderLabelText`
- строка 742 — `haloText`
- строка 775 — `pointName`
- строка 798 — `yWageLabel`
- строка 803 — `yWageValue`
- строка 826 — `isMonopolyScene`
- строка 834 — `eqSectionTitle`
- строка 843 — `updateEqSectionTitle`
- строка 855 — `updateInfoPanel`
- строка 893 — `drawAreas`
- строка 921 — `beforeInterventionNote`
- строка 927 — `updateAreasPanel`
- строка 950 — `drawShiftedSupply`
- строка 979 — `drawTaxAreas`
- строка 1011 — `drawTaxPoints`
- строка 1060 — `attachTaxDrag`
- строка 1081 — `setTax`
- строка 1111 — `syncTaxKind`
- строка 1118 — `applyIntervCascade`
- строка 1160 — `setTaxForm`
- строка 1176 — `setType`
- строка 1218 — `applyTaxRateBounds`
- строка 1248 — `setTaxKind`
- строка 1260 — `updateTaxPanel`
- строка 1320 — `setTaxSide`
- строка 1328 — `setTaxSideButtons`
- строка 1341 — `drawElasticityZones`
- строка 1359 — `drawElasticityPoint`
- строка 1387 — `attachElastDrag`
- строка 1395 — `drawElasticityPointS`
- строка 1415 — `attachElastDragS`
- строка 1423 — `updateElasticityPanel`
- строка 1486 — `shiftMark`
- строка 1498 — `drawShiftScenario`
- строка 1520 — `updateShiftPanel`
- строка 1540 — `setShift`
- строка 1560 — `drawExtAreas`
- строка 1572 — `drawExtCurves`
- строка 1596 — `drawExtPoints`
- строка 1630 — `drawExtScenario`
- строка 1639 — `updateExtPanel`
- строка 1680 — `setExtSign`
- строка 1689 — `syncSocialFields`
- строка 1721 — `socialDefaultExpr`
- строка 1727 — `recompileSocial`
- строка 1749 — `setPRegFields`
- строка 1757 — `setPReg`
- строка 1766 — `drawPcAreas`
- строка 1790 — `drawPriceControl`
- строка 1839 — `attachPcDrag`
- строка 1848 — `updatePcPanel`
- строка 1893 — `setQuotaFields`
- строка 1904 — `setQuota`
- строка 1911 — `setQuotaPos`
- строка 1921 — `updateQuotaPriceLabel`
- строка 1933 — `drawQuotaAreas`
- строка 1960 — `drawQuotaLines`
- строка 2005 — `attachQuotaDrag`
- строка 2018 — `updateQuotaPanel`
- строка 2067 — `drawGhost`

#### `calc2/static/calc2/42-scenes-mono.js`

- строка 11 — `mcSourceCurve`
- строка 16 — `mcAt`
- строка 31 — `marginalRevenue`
- строка 40 — `drawMonopolyAreas`
- строка 75 — `drawMonopoly`
- строка 96 — `drawMonopolyPoints`
- строка 133 — `updateMonoPanel`
- строка 162 — `setMarket`
- строка 200 — `monopolyCeiling`
- строка 243 — `drawMonoCeilingAreas`
- строка 262 — `drawMonoKinkedMR`
- строка 279 — `drawMonoCeilingPoints`
- строка 311 — `drawMonoCeilingLine`
- строка 335 — `monopolyTax`
- строка 352 — `monopolyFloor`
- строка 386 — `naturalATC`
- строка 397 — `findRootLast`
- строка 412 — `recomputeNatural`
- строка 441 — `drawNaturalAreas`
- строка 456 — `drawNaturalCurves`
- строка 476 — `drawNaturalPoints`
- строка 505 — `drawNaturalFull`
- строка 513 — `updateNaturalPanel`
- строка 542 — `drawMonoTaxAreas`
- строка 565 — `drawMonoTaxShiftedMC`
- строка 580 — `drawMonoTaxPoints`
- строка 601 — `drawMonoFloorAreas`
- строка 616 — `drawMonoFloorPoints`
- строка 636 — `drawMonoFloorLine`
- строка 651 — `updateMonoInterventionPanel`
- строка 726 — `makeCurve`
- строка 735 — `drawDiscr1`
- строка 759 — `updateDiscr1Panel`
- строка 784 — `allocateMR`
- строка 797 — `recomputeDiscr3`
- строка 817 — `drawMiniMarket`
- строка 904 — `redrawDiscr3`
- строка 927 — `updateDiscr3Panel`
- строка 974 — `applyD3WorldLabels`
- строка 997 — `buildKinkedDemand`
- строка 1044 — `recomputeKinked`
- строка 1064 — `drawKinkedFull`
- строка 1104 — `updateKinkPanel`
- строка 1128 — `applyMonoVisibility`
- строка 1147 — `ensureMonopolyCurves`
- строка 1156 — `fillIfEmpty`
- строка 1159 — `ensureD3Fields`
- строка 1164 — `ensureKinkFields`
- строка 1170 — `ensureMonopolyPreset`
- строка 1177 — `setMonoMode`
- строка 1188 — `setKinkInput`

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
- строка 803 — `setScenario`

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
- строка 1316 — `recomputePpfTrade`
- строка 1358 — `drawPpfTrade`
- строка 1383 — `drawPpfTradeMarks`
- строка 1411 — `updatePpfTradePanel`
- строка 1507 — `syncPpftPriceUI`
- строка 1518 — `redrawPpfTrade`
- строка 1539 — `recomputeTradeB`
- строка 1628 — `tradeCpfPoints`
- строка 1645 — `tradeBPanels`
- строка 1666 — `drawTradeB`
- строка 1731 — `drawTradeBMarks`
- строка 1734 — `tbName`
- строка 1740 — `updateTradeBPanel`
- строка 1810 — `syncTbPriceUI`
- строка 1823 — `redrawTradeB`
- строка 1838 — `setTradeScenario`
- строка 1850 — `setPpfSub`

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
- строка 39 — `redrawScene`
- строка 169 — `redrawGraphMode`
- строка 180 — `renderMmRows`
- строка 221 — `graphRowsBox`
- строка 224 — `renderGraphRows`
- строка 242 — `graphError`
- строка 249 — `buildGraphRow`
- строка 331 — `equipGraphRows`
- строка 339 — `graphRowInput`
- строка 376 — `mainScales`
- строка 388 — `drawOverlays`
- строка 428 — `refreshAnalyticsPanel`
- строка 449 — `typesetStats`
- строка 496 — `addStatSign`
- строка 509 — `statToTex`
- строка 541 — `katexVisibleText`
- строка 547 — `restatWide`
- строка 587 — `statInkWidth`
- строка 595 — `statTooWide`
- строка 604 — `statPieces`
- строка 639 — `texAbbrev`
- строка 645 — `renderMathIn`
- строка 688 — `areaKey`
- строка 693 — `subDigits`
- строка 698 — `applyAreaColors`
- строка 708 — `currentAreas`
- строка 726 — `areaOfPathEl`
- строка 788 — `areaShort`
- строка 797 — `drawLegend`
- строка 860 — `floatRects`
- строка 877 — `legendCorner`
- строка 953 — `viewWindow`
- строка 965 — `axisWords`
- строка 971 — `crossPoints`
- строка 1069 — `invalidateKeyTargets`
- строка 1072 — `kinksOf`
- строка 1120 — `keyTargets`
- строка 1229 — `snapVertexAt`
- строка 1263 — `drawCrossPoints`
- строка 1372 — `armCurve`
- строка 1378 — `disarmCurve`
- строка 1386 — `keyPointLit`
- строка 1399 — `drawCurveHits`
- строка 1433 — `pinKeyPoint`
- строка 1453 — `hoverLabel`
- строка 1464 — `drawRoller`
- строка 1485 — `rollerTargetAt`
- строка 1510 — `rollerClampX`
- строка 1529 — `rollerMove`
- строка 1545 — `showRollTip`
- строка 1568 — `hideRollTip`
- строка 1577 — `rollerOff`
- строка 1588 — `curveRightEdge`
- строка 1613 — `axisXLetter`
- строка 1623 — `axisLetter`
- строка 1636 — `armVerts`
- строка 1670 — `syncCanvasMode`
- строка 1690 — `leaveCanvasMode`
- строка 1695 — `addAreaVert`
- строка 1702 — `clearAreaVerts`
- строка 1708 — `renderVertList`
- строка 1774 — `syncAreaCalcButton`
- строка 1786 — `areaPickedCurve`
- строка 1795 — `areaCurveRange`
- строка 1813 — `syncAreaRangeLabel`
- строка 1849 — `freshenVertNames`
- строка 1865 — `drawAreaVerts`
- строка 1925 — `areaTargets`
- строка 1929 — `calcAreaUnderCurve`
- строка 1942 — `ringArea`
- строка 1952 — `segCross`
- строка 1959 — `ringSelfCrosses`
- строка 1981 — `angleRing`
- строка 1987 — `bestAreaRing`
- строка 2017 — `calcAreaPolygon`
- строка 2032 — `AREA_PALETTE`
- строка 2034 — `runAreaCalc`
- строка 2054 — `clearAreaCalc`
- строка 2061 — `drawAreaCalc`
- строка 2090 — `updateAreaCalcPanel`
- строка 2188 — `syncAreaCalcUI`
- строка 2223 — `updateQuickArea`
- строка 2225 — `setAreaCalcMode`
- строка 2241 — `wireFolds`
- строка 2262 — `wireAreaCalc`
- строка 2291 — `paramsAllowed`
- строка 2316 — `isReservedName`
- строка 2329 — `expandImplicitMul`
- строка 2355 — `prepExpr`
- строка 2373 — `texToPlain`
- строка 2399 — `sceneReservedKey`
- строка 2403 — `freeSymbols`
- строка 2421 — `freeSymbolsUncached`
- строка 2449 — `sceneReserved`
- строка 2472 — `sceneExtraParams`
- строка 2478 — `paramValue`
- строка 2484 — `paramScope`
- строка 2494 — `scopeFor`
- строка 2501 — `evalWithParams`
- строка 2512 — `syncParams`
- строка 2568 — `buildParamChip`
- строка 2692 — `initSceneColorPickers`
- строка 2704 — `syncSceneColorPickers`
- строка 2712 — `syncAxisPlaceholders`
- строка 2727 — `titleAnchorPx`
- строка 2737 — `drawGraphTitle`
- строка 2776 — `editGraphTitleOnCanvas`
- строка 2821 — `normHex`
- строка 2843 — `paletteSix`
- строка 2851 — `closeColorMenu`
- строка 2865 — `onDocClosePick`
- строка 2869 — `onEscClosePick`
- строка 2876 — `makeColorPicker`
- строка 2964 — `autoCurveName`
- строка 2973 — `curveShortName`
- строка 2983 — `markCaption`
- строка 2992 — `drawMarks`
- строка 3079 — `snapTargets`
- строка 3165 — `macroSnapTargets`
- строка 3184 — `consumerSnapTargets`
- строка 3213 — `ineqSnapTargets`
- строка 3227 — `mathSnapTargets`
- строка 3279 — `tradeSnapTargets`
- строка 3299 — `axisSnapAt`
- строка 3318 — `snapDistPx`
- строка 3337 — `snapPointAt`
- строка 3378 — `showSnapHint`
- строка 3397 — `armMark`
- строка 3410 — `cancelMarkDraft`
- строка 3450 — `resetDecor`
- строка 3541 — `_undoCopyChild`
- строка 3555 — `_undoCopy`
- строка 3569 — `pushUndo`
- строка 3579 — `undoLast`
- строка 3595 — `clearUndo`
- строка 3602 — `forgetSceneSnapshot`
- строка 3604 — `resetSceneMemory`
- строка 3606 — `saveSceneSnapshot`
- строка 3615 — `restoreSceneSnapshot`
- строка 3634 — `addMarkAt`
- строка 3669 — `colorDist`
- строка 3678 — `drawnStrokeColors`
- строка 3694 — `nextMarkColor`
- строка 3710 — `newMark`
- строка 3722 — `pendingMark`
- строка 3725 — `startMarkDraft`
- строка 3734 — `markSnapFn`
- строка 3744 — `renderMarkList`
- строка 3757 — `ensureAddMarkButton`
- строка 3767 — `buildMarkRow`

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
- строка 41 — `addCurve`
- строка 81 — `addEmptyCurve`
- строка 100 — `updateCurveExpr`
- строка 125 — `setRole`
- строка 141 — `renderCurveList`

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
- строка 613 — `mathToLatexField`
- строка 628 — `upgradeFormulaField`
- строка 658 — `fieldOnScreen`
- строка 670 — `flushMathfieldsSoon`
- строка 676 — `flushMathfields`
- строка 710 — `katexSafe`
- строка 746 — `katexInto`
- строка 761 — `placeholderTex`
- строка 770 — `texSafeText`
- строка 774 — `buildMathfield`
- строка 926 — `insertIntoField`
- строка 997 — `mkbdKey`
- строка 1024 — `buildKeyboard`
- строка 1084 — `closeAllKeyboardsExcept`
- строка 1105 — `scheduleParamsSync`
- строка 1111 — `registerFormulaField`
- строка 1128 — `fieldActive`
- строка 1137 — `liveFormulaTexts`
- строка 1164 — `equipFormulaField`
- строка 1201 — `equipAllFormulaFields`
- строка 1205 — `attachFormulaHelp`
- строка 1393 — `makeEditableValue`
- строка 1498 — `makeToggle`
- строка 1540 — `segToToggle`
- строка 1572 — `closeAllSelectMenus`
- строка 1576 — `upgradeSelect`
- строка 1677 — `upgradeTextField`
- строка 1700 — `upgradeTextFieldsIn`

#### `calc2/static/calc2/84-picker.js`

- строка 8 — `loadScene`
- строка 123 — `closePicker`
- строка 142 — `setPickerBlockOpen`
- строка 147 — `openPicker`
- строка 307 — `baseScene`
- строка 316 — `applyCardScope`
- строка 394 — `blockSpec`
- строка 406 — `foldPickerGroups`
- строка 495 — `plural`
- строка 503 — `pickScene`

#### `calc2/static/calc2/86-workspace.js`

- строка 54 — `setFieldValue`
- строка 60 — `relocateForScene`
- строка 70 — `clearResultPanels`
- строка 77 — `toast`
- строка 84 — `dockActive`
- строка 91 — `setSideOpen`
- строка 112 — `setToolsOpen`
- строка 113 — `setParamsOpen`
- строка 123 — `hasAnalytics`
- строка 130 — `moveExplanations`
- строка 151 — `syncAnalyticsPanel`
- строка 232 — `sectionIcon`
- строка 239 — `cardifySections`
- строка 284 — `collapseCards`
- строка 300 — `syncLabelSizeSeg`
- строка 311 — `openSection`
- строка 345 — `cardWithFormula`
- строка 358 — `syncFirstCard`
- строка 377 — `wireScene`
- строка 524 — `resetCurrentScene`
- строка 532 — `setWrenchOpen`
- строка 542 — `applyViewBounds`
- строка 569 — `quadWindow`
- строка 574 — `quadSameWindow`
- строка 581 — `setFirstQuad`
- строка 620 — `setGridMode`
- строка 638 — `hintTip`
- строка 649 — `showHintTip`
- строка 699 — `hideHintTip`
- строка 724 — `tipText`
- строка 726 — `showTipFor`
- строка 732 — `wireTips`
- строка 771 — `syncTipLabels`
- строка 784 — `hintAnchor`
- строка 823 — `hintsToDots`
- строка 861 — `wireHintButtons`
- строка 901 — `wireWrench`
- строка 980 — `fillPrintBlocks`
- строка 1008 — `setPrintViewBox`

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
- строка 376 — `buildPultCurveChips`
- строка 454 — `syncPultCurveValues`
- строка 480 — `capturePultHome`
- строка 487 — `capturePultHomes`
- строка 492 — `returnPultHome`
- строка 504 — `syncPultRegulators`
- строка 523 — `upgradeRegulator`
- строка 651 — `shortRegulatorName`
- строка 665 — `ppfLinearFormula`
- строка 671 — `ppfInterceptsOf`
- строка 679 — `ppfSetSingle`
- строка 687 — `ppfSetSum`
- строка 704 — `addPultXChip`
- строка 715 — `buildPultExtra`
- строка 747 — `ineqParseIncomes`
- строка 750 — `ineqMasterRebase`
- строка 755 — `ineqMasterScale`
- строка 773 — `ineqMasterApply`
- строка 785 — `ineqMasterDetach`
- строка 790 — `buildIneqMasterChip`
- строка 798 — `showPult`
- строка 825 — `updatePult`
- строка 845 — `wireControls`

#### `calc2/static/calc2/90-explain.js`

- строка 375 — `sceneExplainHtml`

#### `calc2/static/calc2/99-boot.js`

- строка 13 — `lockNumberFields`
- строка 42 — `init`

**Итого функций в индексе: 860.**

<!-- AUTO:END -->
