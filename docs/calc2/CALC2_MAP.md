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

*Автоматически собрано командой `manage.py calc2_map`. Дата: 2026-08-21. HEAD: `f8e3506`. Не редактировать руками — вся эта часть файла, от отметки начала автосекции и до отметки её конца, перезаписывается заново при каждом запуске команды.*

### Файлы (маршрут → представление → шаблон → статика)

| Путь | Строк | КБ | Тип |
|---|---:|---:|---|
| `calc2/urls.py` | 19 | 0.6 | python |
| `calc2/views.py` | 181 | 10.0 | python |
| `calc2/templates/calc2/calc2.html` | 2421 | 193.9 | шаблон |
| `calc2/static/calc2/calc2.css` | 1942 | 131.2 | CSS |
| `calc2/static/calc2/00-config.js` | 478 | 39.3 | JS |
| `calc2/static/calc2/10-math-core.js` | 710 | 43.7 | JS |
| `calc2/static/calc2/20-plane.js` | 637 | 43.3 | JS |
| `calc2/static/calc2/30-curves.js` | 998 | 70.9 | JS |
| `calc2/static/calc2/40-scenes-market.js` | 1685 | 114.7 | JS |
| `calc2/static/calc2/42-scenes-mono.js` | 1203 | 84.8 | JS |
| `calc2/static/calc2/44-scenes-firm.js` | 1195 | 79.1 | JS |
| `calc2/static/calc2/46-scenes-labor.js` | 727 | 52.3 | JS |
| `calc2/static/calc2/48-scenes-consumer.js` | 261 | 15.7 | JS |
| `calc2/static/calc2/50-scenes-macro.js` | 414 | 28.3 | JS |
| `calc2/static/calc2/52-modes.js` | 788 | 51.6 | JS |
| `calc2/static/calc2/54-scenes-ppf.js` | 1842 | 121.4 | JS |
| `calc2/static/calc2/56-scenes-inequality.js` | 532 | 34.0 | JS |
| `calc2/static/calc2/60-overlays.js` | 3916 | 235.2 | JS |
| `calc2/static/calc2/70-scenes-math.js` | 2013 | 130.9 | JS |
| `calc2/static/calc2/80-ui.js` | 400 | 23.5 | JS |
| `calc2/static/calc2/82-input.js` | 1699 | 94.2 | JS |
| `calc2/static/calc2/84-picker.js` | 495 | 34.9 | JS |
| `calc2/static/calc2/86-workspace.js` | 1011 | 60.9 | JS |
| `calc2/static/calc2/88-params.js` | 1638 | 102.9 | JS |
| `calc2/static/calc2/90-explain.js` | 365 | 60.8 | JS |
| `calc2/static/calc2/99-boot.js` | 97 | 7.9 | JS |

**Итого: 26 файлов, 27667 строк, 1866.2 КБ.**

### Индекс функций (объявления верхнего уровня, по возрастанию строки)

#### `calc2/static/calc2/00-config.js`

- строка 53 — `fsStep`
- строка 381 — `cssVar`
- строка 385 — `refreshColors`
- строка 451 — `canvasMode`
- строка 456 — `canvasArmed`
- строка 462 — `roleColor`
- строка 468 — `setCalcTheme`
- строка 474 — `toggleCalcTheme`

#### `calc2/static/calc2/10-math-core.js`

- строка 16 — `axisScope`
- строка 22 — `compileFormula`
- строка 38 — `evalCurve`
- строка 56 — `detectLinear`
- строка 100 — `curveParamNames`
- строка 115 — `paramSignature`
- строка 120 — `refreshLinearForParams`
- строка 152 — `fmtLinear`
- строка 176 — `compileFormulaP`
- строка 187 — `evalQofP`
- строка 194 — `detectLinearP`
- строка 208 — `invertQofP`
- строка 227 — `buildCurveFromQP`
- строка 252 — `makeVerticalCurve`
- строка 256 — `isVertical`
- строка 265 — `findEquilibrium`
- строка 296 — `bisect`
- строка 308 — `integrate`
- строка 330 — `signChanges`
- строка 346 — `areaBetween`
- строка 357 — `crossingCount`
- строка 362 — `findRoot`
- строка 378 — `invCurve`
- строка 384 — `curveDeriv`
- строка 391 — `compileExt`
- строка 395 — `evalExt`
- строка 423 — `compileTwoVar`
- строка 433 — `compileTwoVarUncached`
- строка 443 — `evalTwoVar`
- строка 455 — `solveLevelB`
- строка 493 — `traceLevelCurve`
- строка 518 — `partialA`
- строка 523 — `partialB`
- строка 530 — `mrsAt`
- строка 542 — `optimizeAlongConstraint`
- строка 606 — `qtyHasCyrillic`
- строка 611 — `qtyIsQuantity`
- строка 625 — `qtyParts`
- строка 683 — `qtyLatex`

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
- строка 890 — `sceneDrawsCurveList`
- строка 899 — `syncCurveListVisibility`
- строка 914 — `curveDragAllowed`
- строка 924 — `roundDrag`
- строка 962 — `setCurveFreeTerm`

#### `calc2/static/calc2/40-scenes-market.js`

- строка 7 — `curveByRole`
- строка 11 — `recompute`
- строка 287 — `recomputeOpenEconomy`
- строка 352 — `drawOpenAreas`
- строка 389 — `drawOpenLines`
- строка 436 — `attachOpenPwDrag`
- строка 444 — `setOpenPw`
- строка 454 — `setOpenTool`
- строка 466 — `updateOpenPanel`
- строка 502 — `drawEquilibrium`
- строка 540 — `mathTspans`
- строка 580 — `hasMathMarkup`
- строка 594 — `qtyTspans`
- строка 624 — `qtyGreekChar`
- строка 662 — `texToCanvasText`
- строка 671 — `renderLabelText`
- строка 690 — `haloText`
- строка 716 — `pointName`
- строка 731 — `yWageLabel`
- строка 736 — `yWageValue`
- строка 759 — `isMonopolyScene`
- строка 767 — `eqSectionTitle`
- строка 776 — `updateEqSectionTitle`
- строка 788 — `updateInfoPanel`
- строка 826 — `drawAreas`
- строка 854 — `beforeInterventionNote`
- строка 860 — `updateAreasPanel`
- строка 883 — `drawShiftedSupply`
- строка 912 — `drawTaxAreas`
- строка 944 — `drawTaxPoints`
- строка 993 — `attachTaxDrag`
- строка 1014 — `setTax`
- строка 1028 — `setType`
- строка 1068 — `applyTaxRateBounds`
- строка 1085 — `setTaxKind`
- строка 1095 — `updateTaxPanel`
- строка 1155 — `setTaxSide`
- строка 1170 — `drawElasticityZones`
- строка 1188 — `drawElasticityPoint`
- строка 1216 — `attachElastDrag`
- строка 1224 — `drawElasticityPointS`
- строка 1244 — `attachElastDragS`
- строка 1252 — `updateElasticityPanel`
- строка 1315 — `shiftMark`
- строка 1327 — `drawShiftScenario`
- строка 1349 — `updateShiftPanel`
- строка 1369 — `setShift`
- строка 1389 — `drawExtAreas`
- строка 1401 — `drawExtCurves`
- строка 1418 — `drawExtPoints`
- строка 1452 — `drawExtScenario`
- строка 1461 — `updateExtPanel`
- строка 1492 — `setExtSign`
- строка 1510 — `recompileExt`
- строка 1524 — `setPRegFields`
- строка 1532 — `setPReg`
- строка 1541 — `drawPcAreas`
- строка 1565 — `drawPriceControl`
- строка 1614 — `attachPcDrag`
- строка 1623 — `updatePcPanel`
- строка 1666 — `drawGhost`

#### `calc2/static/calc2/42-scenes-mono.js`

- строка 11 — `mcSourceCurve`
- строка 16 — `mcAt`
- строка 31 — `marginalRevenue`
- строка 40 — `drawMonopolyAreas`
- строка 75 — `drawMonopoly`
- строка 96 — `drawMonopolyPoints`
- строка 133 — `updateMonoPanel`
- строка 162 — `setMarket`
- строка 204 — `monopolyCeiling`
- строка 247 — `drawMonoCeilingAreas`
- строка 266 — `drawMonoKinkedMR`
- строка 283 — `drawMonoCeilingPoints`
- строка 315 — `drawMonoCeilingLine`
- строка 339 — `monopolyTax`
- строка 356 — `monopolyFloor`
- строка 390 — `naturalATC`
- строка 401 — `findRootLast`
- строка 416 — `recomputeNatural`
- строка 445 — `drawNaturalAreas`
- строка 460 — `drawNaturalCurves`
- строка 480 — `drawNaturalPoints`
- строка 509 — `drawNaturalFull`
- строка 517 — `updateNaturalPanel`
- строка 546 — `drawMonoTaxAreas`
- строка 569 — `drawMonoTaxShiftedMC`
- строка 584 — `drawMonoTaxPoints`
- строка 605 — `drawMonoFloorAreas`
- строка 620 — `drawMonoFloorPoints`
- строка 640 — `drawMonoFloorLine`
- строка 655 — `updateMonoInterventionPanel`
- строка 730 — `makeCurve`
- строка 739 — `drawDiscr1`
- строка 763 — `updateDiscr1Panel`
- строка 788 — `allocateMR`
- строка 801 — `recomputeDiscr3`
- строка 821 — `drawMiniMarket`
- строка 908 — `redrawDiscr3`
- строка 931 — `updateDiscr3Panel`
- строка 978 — `applyD3WorldLabels`
- строка 1001 — `buildKinkedDemand`
- строка 1048 — `recomputeKinked`
- строка 1068 — `drawKinkedFull`
- строка 1108 — `updateKinkPanel`
- строка 1132 — `applyMonoVisibility`
- строка 1151 — `ensureMonopolyCurves`
- строка 1160 — `fillIfEmpty`
- строка 1163 — `ensureD3Fields`
- строка 1168 — `ensureKinkFields`
- строка 1174 — `ensureMonopolyPreset`
- строка 1181 — `setMonoMode`
- строка 1192 — `setKinkInput`

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
- строка 79 — `laborUnionMonopoly`
- строка 93 — `laborUnionWageFloor`
- строка 104 — `recomputeLabor`
- строка 186 — `laborPoint`
- строка 204 — `drawLaborGhost`
- строка 214 — `drawLaborSurpluses`
- строка 230 — `drawLaborMinWelfare`
- строка 259 — `drawLaborMCL`
- строка 289 — `drawLaborDWL`
- строка 302 — `drawLaborMonopsonyPoints`
- строка 358 — `drawLaborCompPoints`
- строка 384 — `drawLaborMinLine`
- строка 398 — `attachLaborMinDrag`
- строка 406 — `setLaborMinFields`
- строка 413 — `setLaborMin`
- строка 425 — `drawLaborUnionMRL`
- строка 437 — `drawLaborGapDWL`
- строка 447 — `drawLaborUnionPoints`
- строка 481 — `drawLaborUnionWageLine`
- строка 495 — `attachUnionWageDrag`
- строка 503 — `setUnionWageFields`
- строка 510 — `setUnionWage`
- строка 520 — `setUnionModel`
- строка 537 — `drawLaborBilateral`
- строка 565 — `updateLaborBilateralPanel`
- строка 583 — `setLaborStruct`
- строка 598 — `updateLaborPanel`
- строка 688 — `redrawLabor`

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
- строка 56 — `updateResetViewBtn`
- строка 69 — `markViewDirty`
- строка 89 — `prefersReducedMotion`
- строка 94 — `animateRanges`
- строка 125 — `applyTradeRanges`
- строка 148 — `scheduleRangeAnim`
- строка 167 — `padMax`
- строка 185 — `curveAxisBounds`
- строка 211 — `boundsOfDrawn`
- строка 251 — `redrawKeepingWindow`
- строка 256 — `applyAutoRanges`
- строка 281 — `zoomRound`
- строка 287 — `zoomBy`
- строка 360 — `panByPixels`
- строка 429 — `resetZoom`
- строка 469 — `flushWheel`
- строка 478 — `initZoom`
- строка 648 — `zoomStep`
- строка 657 — `cancelRangeAnim`
- строка 669 — `makeThrottle`
- строка 682 — `ineqRedraw`
- строка 685 — `setMode`
- строка 757 — `applyScenarioVisibility`
- строка 775 — `setScenario`

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
- строка 573 — `ppfSlopeOf`
- строка 581 — `ppfXmaxOf`
- строка 595 — `fitLinear`
- строка 609 — `classifyPpf`
- строка 635 — `niceMax`
- строка 643 — `singlePpfPoints`
- строка 650 — `findRootIn`
- строка 662 — `interpY`
- строка 676 — `maxAllocY`
- строка 701 — `combinedPpfPoints`
- строка 711 — `allocAt`
- строка 742 — `detectCombinedKinks`
- строка 795 — `combinedPpfFormula`
- строка 831 — `verifyFormula`
- строка 842 — `detectKinks`
- строка 867 — `showPaneError`
- строка 878 — `ppfSumCount`
- строка 879 — `ppfSumGet`
- строка 884 — `ppfSumSet`
- строка 889 — `ppfSumName`
- строка 893 — `ppfSumColor`
- строка 907 — `ppfSumSignature`
- строка 917 — `recomputePpfSum`
- строка 923 — `ensurePpfSum`
- строка 927 — `recomputePpfSumRaw`
- строка 999 — `renderPpfSumRows`
- строка 1045 — `detectSumKinks`
- строка 1063 — `drawPpfSumCurves`
- строка 1084 — `drawPpfSumMarks`
- строка 1110 — `updatePpfSumPanel`
- строка 1175 — `fmtRu`
- строка 1179 — `ppfSumSchemaData`
- строка 1213 — `schemaNote`
- строка 1220 — `drawPpfSumSchema`
- строка 1272 — `redrawPpfSum`
- строка 1285 — `setPpfSumView`
- строка 1296 — `cornerByValue`
- строка 1302 — `recomputePpfTrade`
- строка 1344 — `drawPpfTrade`
- строка 1369 — `drawPpfTradeMarks`
- строка 1397 — `updatePpfTradePanel`
- строка 1485 — `syncPpftPriceUI`
- строка 1496 — `redrawPpfTrade`
- строка 1517 — `recomputeTradeB`
- строка 1606 — `tradeCpfPoints`
- строка 1623 — `tradeBPanels`
- строка 1644 — `drawTradeB`
- строка 1709 — `drawTradeBMarks`
- строка 1712 — `tbName`
- строка 1718 — `updateTradeBPanel`
- строка 1788 — `syncTbPriceUI`
- строка 1801 — `redrawTradeB`
- строка 1816 — `setTradeScenario`
- строка 1828 — `setPpfSub`

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
- строка 165 — `redrawGraphMode`
- строка 176 — `renderMmRows`
- строка 217 — `graphRowsBox`
- строка 220 — `renderGraphRows`
- строка 238 — `graphError`
- строка 245 — `buildGraphRow`
- строка 327 — `equipGraphRows`
- строка 335 — `graphRowInput`
- строка 372 — `mainScales`
- строка 384 — `drawOverlays`
- строка 424 — `refreshAnalyticsPanel`
- строка 445 — `typesetStats`
- строка 492 — `addStatSign`
- строка 505 — `statToTex`
- строка 537 — `katexVisibleText`
- строка 543 — `restatWide`
- строка 583 — `statInkWidth`
- строка 591 — `statTooWide`
- строка 600 — `statPieces`
- строка 635 — `texAbbrev`
- строка 641 — `renderMathIn`
- строка 684 — `areaKey`
- строка 689 — `subDigits`
- строка 694 — `applyAreaColors`
- строка 704 — `currentAreas`
- строка 722 — `areaOfPathEl`
- строка 782 — `areaShort`
- строка 791 — `drawLegend`
- строка 854 — `floatRects`
- строка 871 — `legendCorner`
- строка 947 — `viewWindow`
- строка 959 — `axisWords`
- строка 965 — `crossPoints`
- строка 1063 — `invalidateKeyTargets`
- строка 1066 — `kinksOf`
- строка 1114 — `keyTargets`
- строка 1223 — `snapVertexAt`
- строка 1246 — `drawCrossPoints`
- строка 1384 — `armCurve`
- строка 1390 — `disarmCurve`
- строка 1398 — `keyPointLit`
- строка 1411 — `drawCurveHits`
- строка 1445 — `pinKeyPoint`
- строка 1465 — `hoverLabel`
- строка 1476 — `drawRoller`
- строка 1497 — `rollerTargetAt`
- строка 1522 — `rollerClampX`
- строка 1541 — `rollerMove`
- строка 1557 — `showRollTip`
- строка 1580 — `hideRollTip`
- строка 1589 — `rollerOff`
- строка 1600 — `curveRightEdge`
- строка 1625 — `axisXLetter`
- строка 1635 — `axisLetter`
- строка 1648 — `armVerts`
- строка 1682 — `syncCanvasMode`
- строка 1702 — `leaveCanvasMode`
- строка 1707 — `addAreaVert`
- строка 1714 — `clearAreaVerts`
- строка 1720 — `renderVertList`
- строка 1786 — `syncAreaCalcButton`
- строка 1798 — `areaPickedCurve`
- строка 1807 — `areaCurveRange`
- строка 1825 — `syncAreaRangeLabel`
- строка 1861 — `freshenVertNames`
- строка 1877 — `drawAreaVerts`
- строка 1937 — `areaTargets`
- строка 1941 — `calcAreaUnderCurve`
- строка 1954 — `ringArea`
- строка 1964 — `segCross`
- строка 1971 — `ringSelfCrosses`
- строка 1993 — `angleRing`
- строка 1999 — `bestAreaRing`
- строка 2029 — `calcAreaPolygon`
- строка 2044 — `AREA_PALETTE`
- строка 2046 — `runAreaCalc`
- строка 2066 — `clearAreaCalc`
- строка 2073 — `drawAreaCalc`
- строка 2102 — `updateAreaCalcPanel`
- строка 2200 — `syncAreaCalcUI`
- строка 2235 — `updateQuickArea`
- строка 2237 — `setAreaCalcMode`
- строка 2253 — `wireFolds`
- строка 2274 — `wireAreaCalc`
- строка 2303 — `paramsAllowed`
- строка 2328 — `isReservedName`
- строка 2341 — `expandImplicitMul`
- строка 2367 — `prepExpr`
- строка 2385 — `texToPlain`
- строка 2411 — `sceneReservedKey`
- строка 2415 — `freeSymbols`
- строка 2433 — `freeSymbolsUncached`
- строка 2461 — `sceneReserved`
- строка 2484 — `sceneExtraParams`
- строка 2490 — `paramValue`
- строка 2496 — `paramScope`
- строка 2506 — `scopeFor`
- строка 2513 — `evalWithParams`
- строка 2524 — `syncParams`
- строка 2580 — `buildParamChip`
- строка 2704 — `initSceneColorPickers`
- строка 2716 — `syncSceneColorPickers`
- строка 2724 — `syncAxisPlaceholders`
- строка 2739 — `titleAnchorPx`
- строка 2749 — `drawGraphTitle`
- строка 2788 — `editGraphTitleOnCanvas`
- строка 2833 — `normHex`
- строка 2855 — `paletteSix`
- строка 2863 — `closeColorMenu`
- строка 2877 — `onDocClosePick`
- строка 2881 — `onEscClosePick`
- строка 2888 — `makeColorPicker`
- строка 2976 — `autoCurveName`
- строка 2985 — `curveShortName`
- строка 2995 — `markCaption`
- строка 3004 — `drawMarks`
- строка 3091 — `snapTargets`
- строка 3177 — `macroSnapTargets`
- строка 3196 — `consumerSnapTargets`
- строка 3225 — `ineqSnapTargets`
- строка 3239 — `mathSnapTargets`
- строка 3291 — `tradeSnapTargets`
- строка 3311 — `axisSnapAt`
- строка 3330 — `snapDistPx`
- строка 3349 — `snapPointAt`
- строка 3390 — `showSnapHint`
- строка 3409 — `armMark`
- строка 3422 — `cancelMarkDraft`
- строка 3462 — `resetDecor`
- строка 3553 — `_undoCopyChild`
- строка 3567 — `_undoCopy`
- строка 3581 — `pushUndo`
- строка 3591 — `undoLast`
- строка 3607 — `clearUndo`
- строка 3614 — `forgetSceneSnapshot`
- строка 3616 — `resetSceneMemory`
- строка 3618 — `saveSceneSnapshot`
- строка 3627 — `restoreSceneSnapshot`
- строка 3646 — `addMarkAt`
- строка 3681 — `colorDist`
- строка 3690 — `drawnStrokeColors`
- строка 3706 — `nextMarkColor`
- строка 3722 — `newMark`
- строка 3734 — `pendingMark`
- строка 3737 — `startMarkDraft`
- строка 3746 — `markSnapFn`
- строка 3756 — `renderMarkList`
- строка 3769 — `ensureAddMarkButton`
- строка 3779 — `buildMarkRow`

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
- строка 655 — `mmSlots`
- строка 656 — `mmGet`
- строка 659 — `mmSet`
- строка 664 — `mmLabel`
- строка 666 — `mmColor`
- строка 673 — `drawMathMinMax`
- строка 734 — `compileAB`
- строка 747 — `parseConstraint`
- строка 765 — `constraintPointsIn`
- строка 784 — `constraintPoints`
- строка 789 — `optimizeAlongCurve`
- строка 802 — `constraintFit`
- строка 820 — `drawMathConstraint`
- строка 874 — `drawLevelCurveOn`
- строка 885 — `mathOptimumReasoning`
- строка 922 — `updateMathPanel`
- строка 1058 — `redrawMath`
- строка 1088 — `setMathSub`
- строка 1111 — `setMathWindow`
- строка 1125 — `setMathX0`
- строка 1150 — `downloadBlob`
- строка 1159 — `exportBaseName`
- строка 1165 — `exportPNG`
- строка 1192 — `texEscape`
- строка 1199 — `r2`
- строка 1230 — `texPlotSize`
- строка 1254 — `texText`
- строка 1267 — `labelPlainText`
- строка 1299 — `quantityTex`
- строка 1316 — `texHex`
- строка 1331 — `texSamplePath`
- строка 1363 — `texResample`
- строка 1406 — `mathToPgf`
- строка 1454 — `pgfStroke`
- строка 1468 — `buildTex`
- строка 1811 — `exportTex`
- строка 1819 — `exportPDF`
- строка 1839 — `buildExportFields`
- строка 1856 — `refreshExportPreview`
- строка 1890 — `expValue`
- строка 1892 — `openExport`
- строка 1909 — `closeExport`
- строка 1928 — `updateGraphPanel`
- строка 1985 — `graphExplainNote`

#### `calc2/static/calc2/80-ui.js`

- строка 7 — `showError`
- строка 11 — `hideError`
- строка 21 — `addCurve`
- строка 57 — `updateCurveExpr`
- строка 79 — `setRole`
- строка 95 — `renderCurveList`

#### `calc2/static/calc2/82-input.js`

- строка 11 — `texFallback`
- строка 18 — `mathToTex`
- строка 35 — `renderTex`
- строка 44 — `renderTexRaw`
- строка 53 — `onKatexReady`
- строка 75 — `pwCond`
- строка 84 — `pwRows`
- строка 93 — `pwFormula`
- строка 112 — `pwLatex`
- строка 134 — `pwVar`
- строка 147 — `casesToMath`
- строка 177 — `condToMath`
- строка 188 — `renderPw`
- строка 235 — `pwAttachKeyboard`
- строка 259 — `pwPreview`
- строка 264 — `openPiecewise`
- строка 278 — `closePiecewise`
- строка 287 — `insertIntoFormula`
- строка 317 — `mathfieldClass`
- строка 321 — `onMathliveReady`
- строка 356 — `fieldProblem`
- строка 406 — `unknownTexCommand`
- строка 415 — `texGroup`
- строка 425 — `latexToMath`
- строка 551 — `mathToLatexField`
- строка 566 — `upgradeFormulaField`
- строка 596 — `fieldOnScreen`
- строка 608 — `flushMathfieldsSoon`
- строка 614 — `flushMathfields`
- строка 648 — `katexSafe`
- строка 684 — `katexInto`
- строка 699 — `placeholderTex`
- строка 708 — `texSafeText`
- строка 712 — `buildMathfield`
- строка 864 — `insertIntoField`
- строка 935 — `mkbdKey`
- строка 962 — `buildKeyboard`
- строка 1022 — `closeAllKeyboardsExcept`
- строка 1043 — `scheduleParamsSync`
- строка 1049 — `registerFormulaField`
- строка 1066 — `fieldActive`
- строка 1075 — `liveFormulaTexts`
- строка 1102 — `equipFormulaField`
- строка 1139 — `equipAllFormulaFields`
- строка 1143 — `attachFormulaHelp`
- строка 1309 — `setCurveForm`
- строка 1320 — `newCurveRole`
- строка 1324 — `curveHelpKind`
- строка 1333 — `applyNewRoleUI`
- строка 1384 — `makeEditableValue`
- строка 1489 — `makeToggle`
- строка 1531 — `segToToggle`
- строка 1563 — `closeAllSelectMenus`
- строка 1567 — `upgradeSelect`
- строка 1668 — `upgradeTextField`
- строка 1691 — `upgradeTextFieldsIn`

#### `calc2/static/calc2/84-picker.js`

- строка 8 — `loadScene`
- строка 109 — `closePicker`
- строка 128 — `setPickerBlockOpen`
- строка 133 — `openPicker`
- строка 265 — `baseScene`
- строка 274 — `applyCardScope`
- строка 352 — `blockSpec`
- строка 364 — `foldPickerGroups`
- строка 453 — `plural`
- строка 461 — `pickScene`

#### `calc2/static/calc2/86-workspace.js`

- строка 52 — `setFieldValue`
- строка 58 — `relocateForScene`
- строка 68 — `clearResultPanels`
- строка 75 — `toast`
- строка 82 — `dockActive`
- строка 89 — `setSideOpen`
- строка 110 — `setToolsOpen`
- строка 111 — `setParamsOpen`
- строка 121 — `hasAnalytics`
- строка 128 — `moveExplanations`
- строка 149 — `syncAnalyticsPanel`
- строка 231 — `sectionIcon`
- строка 238 — `cardifySections`
- строка 283 — `collapseCards`
- строка 299 — `syncLabelSizeSeg`
- строка 310 — `openSection`
- строка 341 — `cardWithFormula`
- строка 354 — `syncFirstCard`
- строка 373 — `wireScene`
- строка 508 — `resetCurrentScene`
- строка 516 — `setWrenchOpen`
- строка 526 — `applyViewBounds`
- строка 553 — `quadWindow`
- строка 558 — `quadSameWindow`
- строка 565 — `setFirstQuad`
- строка 604 — `setGridMode`
- строка 622 — `hintTip`
- строка 633 — `showHintTip`
- строка 683 — `hideHintTip`
- строка 708 — `tipText`
- строка 710 — `showTipFor`
- строка 716 — `wireTips`
- строка 755 — `syncTipLabels`
- строка 768 — `hintAnchor`
- строка 807 — `hintsToDots`
- строка 845 — `wireHintButtons`
- строка 857 — `wireWrench`
- строка 936 — `fillPrintBlocks`
- строка 964 — `setPrintViewBox`

#### `calc2/static/calc2/88-params.js`

- строка 34 — `pultRegulatorIds`
- строка 103 — `pultCurveList`
- строка 114 — `pultExtraSig`
- строка 120 — `pultExtraSigBase`
- строка 132 — `pultShouldShow`
- строка 139 — `curveChipLabel`
- строка 146 — `pultCurveSig`
- строка 153 — `paintEqLabel`
- строка 167 — `texifyName`
- строка 178 — `editEqValue`
- строка 231 — `centerBandOn`
- строка 235 — `pullIntoBand`
- строка 239 — `attachBoundsEditor`
- строка 321 — `refreshRegulators`
- строка 332 — `makePchip`
- строка 348 — `buildPultCurveChips`
- строка 409 — `syncPultCurveValues`
- строка 426 — `capturePultHome`
- строка 433 — `capturePultHomes`
- строка 438 — `returnPultHome`
- строка 450 — `syncPultRegulators`
- строка 469 — `upgradeRegulator`
- строка 597 — `shortRegulatorName`
- строка 611 — `ppfLinearFormula`
- строка 617 — `ppfInterceptsOf`
- строка 625 — `ppfSetSingle`
- строка 633 — `ppfSetSum`
- строка 650 — `addPultXChip`
- строка 661 — `buildPultExtra`
- строка 693 — `ineqParseIncomes`
- строка 696 — `ineqMasterRebase`
- строка 701 — `ineqMasterScale`
- строка 719 — `ineqMasterApply`
- строка 731 — `ineqMasterDetach`
- строка 736 — `buildIneqMasterChip`
- строка 744 — `showPult`
- строка 771 — `updatePult`
- строка 791 — `wireControls`

#### `calc2/static/calc2/90-explain.js`

- строка 359 — `sceneExplainHtml`

#### `calc2/static/calc2/99-boot.js`

- строка 13 — `lockNumberFields`
- строка 42 — `init`

**Итого функций в индексе: 844.**

<!-- AUTO:END -->
