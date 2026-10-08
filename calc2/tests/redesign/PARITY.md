# Таблица паритета calc2: старый экран → новый экран

Собрана `calc2/tests/redesign/parity.mjs` из базового снимка `baseline/` (старый экран, `6b79758`), `INVENTORY.md`
и `COVERAGE.md` пакета. Судьбы — по `COVERAGE.md`, раздел 0, п. 2. Столбец «чем проверено» называет прибор;
«не проверено на…» — с причиной.

Моделей в снимке: **44**. Органов (уникальных ключей): **3250**. Строк ответа: **585**. Пунктов инвентаря: **81**. Строк сверки: **95**.

## 0. Закрытый список

| Буква | Что | Ключи органов базового снимка |
|---|---|---|
| а | 12 кнопок «Построить» → поля применяются при наборе | `#btn-costs-apply`, `#btn-cparts-apply`, `#ineq-incomes-apply`, `#ineq-formula-apply`, `#btn-d3-apply`, `#btn-kink-apply`, `#btn-pl-apply`, `#btn-ppf-apply`, `#btn-ppfsum-apply`, `#btn-prod-apply`, `#btn-ppft-apply`, `#btn-tb-apply` |
| б | переключатели подрежимов → отдельные модели, переход переключателем модели | — (в снимке не встречается: орган спрятан маршрутом или появится в новых фазах) |
| в | сворачивание боковых панелей и корешки → «Развернуть график» | `#tools-toggle`, `#params-toggle` |
| г | двухуровневое окно выбора → экран выбора одним экраном | `#picker-back`, `#pgrid-8>button.scard.adas`, `#pgrid-8>button.scard.islm`, `#pgrid-8>button.scard.phillips`, `#pgrid-8>button.scard.money`, `#pgrid-8>button.scard.loanable`, `#pgrid-8>button.scard.fx`, `#pgrid-8>button.scard.cycle`, `#pgrid-8>button.scard.cycle-adas`, `#pgrid-8>button.scard.macrolink`, `#pgrid-2>button.scard.sd`, `#pgrid-2>button.scard.sdsum`, `#pgrid-2>button.scard.taxes`, `#pgrid-2>button.scard.ceil`, `#pgrid-2>button.scard.quota`, `#pgrid-2>button.scard.elast`, `#pgrid-2>button.scard.ext`, `#pgrid-2>button.scard.firmmarket`, `#pgrid-7>button.scard.consumer`, `#pgrid-7>button.scard.cons-slutsky`, `#pgrid-7>button.scard.cons-demand`, `#pgrid-7>button.scard.cons-hicks`, `#pgrid-7>button.scard.cons-risk`, `#pgrid-7>button.scard.cons-icc`, `#pgrid-7>button.scard.cons-pcc`, `#pgrid-7>button.scard.cons-engel`, `#pgrid-7>button.scard.cons-marshall`, `#pgrid-3>button.scard.prod`, `#pgrid-3>button.scard.costs`, `#pgrid-3>button.scard.plants`, `#pgrid-3>button.scard.isoquant`, `#pgrid-9>button.scard.ineq`, `#pgrid-9>button.scard.laffer`, `#pgrid-9>button.scard.exchange`, `#pgrid-5>button.scard.labor`, `#pgrid-5>button.scard.labor-mono`, `#pgrid-5>button.scard.labor-union`, `#pgrid-5>button.scard.labor-bilat`, `#pgrid-0>button.scard.m-graph`, `#pgrid-0>button.scard.m-transform`, `#pgrid-0>button.scard.m-optimum`, `#pgrid-0>button.scard.m-tangent`, `#pgrid-0>button.scard.m-minmax`, `#pgrid-0>button.scard.m-constraint`, `#pgrid-4>button.scard.mono`, `#pgrid-4>button.scard.mono-nat`, `#pgrid-4>button.scard.mono-d1`, `#pgrid-4>button.scard.mono-d3`, `#pgrid-4>button.scard.mono-kink`, `#pgrid-4>button.scard.monopcomp`, `#pgrid-6>button.scard.smallopen`, `#pgrid-6>button.scard.monoexport`, `#pgrid-6>button.scard.bigopen`, `#pgrid-1>button.scard.ppf`, `#pgrid-1>button.scard.ppfsum`, `#pgrid-1>button.scard.trade`, `#pgrid-1>button.scard.tradeprice`, `#picker-blocks>button.bcard`, `#picker-blocks>button.bcard[1]`, `#picker-blocks>button.bcard[2]`, `#picker-blocks>button.bcard[3]`, `#picker-blocks>button.bcard[4]`, `#picker-blocks>button.bcard[5]`, `#picker-blocks>button.bcard[6]`, `#picker-blocks>button.bcard[7]`, `#picker-blocks>button.bcard[8]`, `#picker-blocks>button.bcard[9]` |
| д | сворачивание карточек-секций → секции всегда раскрыты, колонка прокручивается | `#sec-input>button.fold-btn`, `#marks-btn`, `#areascalc-btn`, `#sb-btn`, `#ex-btn` |
| е | общая галочка «Показать излишки» в гаечном ключе → отдельные галочки CS и PS в «Показать на графике» | `#chk-areas` |
| ж | галочка видимости кривой в списке → глаз в карточке функции | `#curve-list>input`, `#curve-list>input[2]`, `#curve-list>input[1]`, `#curve-list>input[4]`, `#curve-list>input[6]`, `#curve-list>input[8]`, `#curve-list>input[10]`, `#curve-list>input[12]`, `#curve-list>input[3]`, `#curve-list>input[5]`, `#curve-list>input[7]`, `#curve-list>input[9]` |
| з | перенос регуляторов в правую панель → регулятор рядом со своим смыслом в «Условии» | — (в снимке не встречается: орган спрятан маршрутом или появится в новых фазах) |
| и | «Вернуть исходный вид» → «Сбросить»; гаечный ключ → «Вид графика» | `#btn-scene-reset`, `#btn-wrench` |
| к | три кнопки окна экспорта → выбор формата и одна кнопка «Скачать …» | `#exp-png`, `#exp-tex` |
| л | пустое состояние «Ползунков в этой модели нет» (без замены) | — (в снимке не встречается: орган спрятан маршрутом или появится в новых фазах) |
| м | сегмент из одной кнопки «Квота» (без замены) | `#seg-quota` |

## 1. Органы управления (базовый снимок, все модели)

| Ключ | Вид | Подпись | Где было | Моделей | Судьба | Чем заменён | Чем проверено |
|---|---|---|---|---|---|---|---|
| `#ac-calc` | button | Сначала выберите кривую | #sec-areascalc | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ac-clear` | button | Убрать всё | #sec-areascalc | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ac-pane-curve>button.sel-btn` | button | Кривая, под которой считается площадь | #sec-areascalc | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ac-range>span.edval` | edval | Начало отрезка | #sec-areascalc (через #ac-pane-curve>button.sel-btn → >button.sel-item~1) | 41 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ac-range>span.edval[1]` | edval | Конец отрезка | #sec-areascalc (через #ac-pane-curve>button.sel-btn → >button.sel-item~1) | 41 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#areascalc-body>button.hint-btn` | button | Как этим пользоваться | #sec-areascalc | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#areascalc-body>button.tgl-sw` | switch | Под кривой | #sec-areascalc | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#areascalc-btn` | button | Площади | #sec-areascalc | 44 | заменён (д) | секции всегда раскрыты, колонка прокручивается | compare.mjs: органы секции видны без раскрытия |
| `#btn-add-curve` | button | Добавить кривую | #sec-curves | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#btn-costs-apply` | button | Построить | #sec-costs | 1 | заменён (а) | набор в поле над кнопкой применяется сам (живое применение) | formula_input_probe.mjs (расширенный) + compare.mjs: шаг «набор» без нажатия |
| `#btn-costs-preset` | button | Стандартные издержки | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#btn-cparts-apply` | button | Построить | #sec-costs (через #costs-pane-costs>button.tgl-sw) | 1 | заменён (а) | набор в поле над кнопкой применяется сам (живое применение) | formula_input_probe.mjs (расширенный) + compare.mjs: шаг «набор» без нажатия |
| `#btn-d3-apply` | button | Построить | #sec-mono | 2 | заменён (а) | набор в поле над кнопкой применяется сам (живое применение) | formula_input_probe.mjs (расширенный) + compare.mjs: шаг «набор» без нажатия |
| `#btn-kink-apply` | button | Построить | #sec-mono | 1 | заменён (а) | набор в поле над кнопкой применяется сам (живое применение) | formula_input_probe.mjs (расширенный) + compare.mjs: шаг «набор» без нажатия |
| `#btn-pl-apply` | button | Построить | #sec-costs | 1 | заменён (а) | набор в поле над кнопкой применяется сам (живое применение) | formula_input_probe.mjs (расширенный) + compare.mjs: шаг «набор» без нажатия |
| `#btn-ppf-apply` | button | Построить | #sec-ppf | 1 | заменён (а) | набор в поле над кнопкой применяется сам (живое применение) | formula_input_probe.mjs (расширенный) + compare.mjs: шаг «набор» без нажатия |
| `#btn-ppf-compare` | button | Сравнить с другой КПВ | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#btn-ppfsum-apply` | button | Построить сумму | #sec-ppf | 1 | заменён (а) | набор в поле над кнопкой применяется сам (живое применение) | formula_input_probe.mjs (расширенный) + compare.mjs: шаг «набор» без нажатия |
| `#btn-ppft-apply` | button | Построить КТВ | #sec-ppf | 1 | заменён (а) | набор в поле над кнопкой применяется сам (живое применение) | formula_input_probe.mjs (расширенный) + compare.mjs: шаг «набор» без нажатия |
| `#btn-prod-apply` | button | Построить | #sec-costs | 1 | заменён (а) | набор в поле над кнопкой применяется сам (живое применение) | formula_input_probe.mjs (расширенный) + compare.mjs: шаг «набор» без нажатия |
| `#btn-resetview` | button | Вернуться к изначальному масштабу (или двойной клик) | .graph-tools (через #btn-wrench → #inp-qmin) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#btn-scene-reset` | button | Вернуть исходный вид | .side-reset | 44 | заменён (и) | «Сбросить» в шапке модели (#btn-model-reset) | compare.mjs: шаг «Сбросить» + история |
| `#btn-tb-apply` | button | Построить торговлю | #sec-ppf | 1 | заменён (а) | набор в поле над кнопкой применяется сам (живое применение) | formula_input_probe.mjs (расширенный) + compare.mjs: шаг «набор» без нажатия |
| `#btn-tb-reset` | button | Pw​=1,42 | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#btn-wrench` | button | Настройки координатной плоскости | .graph-tools | 44 | заменён (и) | «Вид графика» в панели холста (#btn-view) | compare.mjs: органы «Вида графика» |
| `#btn-zoomin` | button | Приблизить (клавиша «+») | .graph-tools | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#btn-zoomout` | button | Отдалить (клавиша «−») | .graph-tools | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-afc` | input:checkbox | AFC, средние постоянные затраты | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-ap` | input:checkbox | AP (средний продукт) | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-areas` | input:checkbox | Показать излишки | #wrench-pop (через #btn-wrench) | 44 | заменён (е) | галочки #chk-cs и #chk-ps в «Показать на графике» | compare.mjs: шаги CS/PS |
| `#chk-atc` | input:checkbox | ATC, средние общие затраты | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-avc` | input:checkbox | AVC, средние переменные затраты | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-bundle-1` | input:checkbox | Кривая комплектов | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-bundle-2` | input:checkbox | Кривая комплектов | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-bundle-t` | input:checkbox | Кривая комплектов | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-cons-fan` | input:checkbox | Веер кривых безразличия | #sec-consumer | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-convex` | input:checkbox | Выпуклость и вогнутость | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-elast-s` | input:checkbox | Точка на предложении (Es) | #sec-input | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-fc` | input:checkbox | FC, постоянные затраты | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-ghost` | input:checkbox | Исходное состояние (было → стало) | #sec-tax | 6 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-inflect` | input:checkbox | Точки перегиба | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-iso-fan` | input:checkbox | Веер изоквант | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-lab-ghost` | input:checkbox | Конкурентный ориентир | #sec-labor | 4 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-labmin` | input:checkbox | Минимальная зарплата (МРОТ) | #sec-labor | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-legend` | input:checkbox | Легенда закрашенных областей | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-lr` | input:checkbox | Рыночная цена P и прибыль | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-lr-area` | input:checkbox | Прямоугольник прибыли / убытка | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-mc` | input:checkbox | MC, предельные затраты | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-mono-cs` | input:checkbox | Показывать CS | #sec-mono | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-mono-ps` | input:checkbox | Показывать PS (TR − VC) | #sec-mono | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-mono-vc` | input:checkbox | Показывать VC | #sec-mono | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-mp` | input:checkbox | MP (предельный продукт) | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-msb` | input:checkbox | MSB | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-msc` | input:checkbox | MSC | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-nat-loss` | input:checkbox | Убыток при P = MC | #sec-mono | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-nat-profit` | input:checkbox | Прибыль монополии | #sec-mono | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-open-dwl` | input:checkbox | Потери общества | #sec-input | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-open-money` | input:checkbox | Доход бюджета / рента квоты | #sec-input | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-ppf-in` | input:checkbox | Достижимые наборы | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-ppf-out` | input:checkbox | Недостижимые наборы | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-quad` | input:checkbox | Только первая четверть | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-secant` | input:checkbox | Секущая через две точки | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-tc` | input:checkbox | TC, общие затраты | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-tp` | input:checkbox | TP (общий продукт) | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#chk-vc` | input:checkbox | VC, переменные затраты | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#cons-a` | input:number | a (степень x) | #sec-consumer | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#cons-b` | input:number | b (степень y) | #sec-consumer | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#cons-i` | input:number | Доход I | #sec-consumer | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#cons-px` | input:number | Цена Px​ | #sec-consumer | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#cons-px1-row>button.param-bound` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#cons-px1-row>button.param-bound[1]` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#cons-px1-row>span.pchip-label` | exact | Новая цена Px1​. Щёлкните, чтобы ввести точное значение | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#cons-px1-slider` | input:range | Новая цена …=4 | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#cons-py` | input:number | Цена Py​ | #sec-consumer | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#cons-type` | select | Тип предпочтений | #sec-consumer | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[100]` | button | π | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[101]` | button | ρ | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[102]` | button | σ | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[103]` | button | τ | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[104]` | button | φ | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[105]` | button | ω | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[106]` | button | Δ | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[107]` | button | Σ | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[108]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[109]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[10]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[110]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[11]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[12]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[13]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[14]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[15]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[16]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[17]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[18]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[19]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[1]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[20]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[21]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[22]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[23]` | button | Стереть символ | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[24]` | button | Очистить поле | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[25]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[26]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[27]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[28]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[29]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[2]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[30]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[31]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[32]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[33]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[34]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[35]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[36]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[37]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[38]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[39]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[3]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[40]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[41]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[42]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[43]` | button | a | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[44]` | button | b | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[45]` | button | c | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[46]` | button | d | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[47]` | button | e | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[48]` | button | f | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[49]` | button | g | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[4]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[50]` | button | h | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[51]` | button | i | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[52]` | button | j | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[53]` | button | k | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[54]` | button | l | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[55]` | button | m | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[56]` | button | n | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[57]` | button | o | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[58]` | button | p | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[59]` | button | q | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[5]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[60]` | button | r | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[61]` | button | s | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[62]` | button | t | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[63]` | button | u | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[64]` | button | v | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[65]` | button | w | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[66]` | button | x | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[67]` | button | y | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[68]` | button | z | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[69]` | button | A | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[6]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[70]` | button | B | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[71]` | button | C | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[72]` | button | D | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[73]` | button | E | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[74]` | button | F | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[75]` | button | G | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[76]` | button | H | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[77]` | button | I | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[78]` | button | K | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[79]` | button | L | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[7]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[80]` | button | M | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[81]` | button | N | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[82]` | button | P | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[83]` | button | Q | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[84]` | button | R | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[85]` | button | S | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[86]` | button | T | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[87]` | button | V | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[88]` | button | W | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[89]` | button | X | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[8]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[90]` | button | Y | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[91]` | button | Z | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[92]` | button | α | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[93]` | button | β | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[94]` | button | γ | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[95]` | button | δ | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[96]` | button | ε | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[97]` | button | θ | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[98]` | button | λ | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[99]` | button | μ | #sec-costs (через #fh-tc → #costs-input-tc>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mk[9]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mkbd-tab` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mkbd-tab[1]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-input-tc>button.mkbd-tab[2]` | button | Суммарные затраты TC(Q) | #sec-costs (через #fh-tc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-costs>button.swatch` | button | Цвет кривой | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-costs>button.swatch[1]` | button | Цвет кривой | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-costs>button.swatch[2]` | button | Цвет кривой | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-costs>button.swatch[3]` | button | Цвет кривой | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-costs>button.swatch[4]` | button | Цвет кривой | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-costs>button.swatch[5]` | button | Цвет кривой | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-costs>button.swatch[6]` | button | Цвет кривой | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-costs>button.tgl-sw` | switch | Задам TC | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[100]` | button | π | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[101]` | button | ρ | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[102]` | button | σ | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[103]` | button | τ | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[104]` | button | φ | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[105]` | button | ω | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[106]` | button | Δ | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[107]` | button | Σ | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[108]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[109]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[10]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[110]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[11]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[12]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[13]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[14]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[15]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[16]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[17]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[18]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[19]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[1]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[20]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[21]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[22]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[23]` | button | Стереть символ | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[24]` | button | Очистить поле | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[25]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[26]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[27]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[28]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[29]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[2]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[30]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[31]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[32]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[33]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[34]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[35]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[36]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[37]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[38]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[39]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[3]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[40]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[41]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[42]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[43]` | button | a | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[44]` | button | b | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[45]` | button | c | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[46]` | button | d | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[47]` | button | e | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[48]` | button | f | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[49]` | button | g | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[4]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[50]` | button | h | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[51]` | button | i | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[52]` | button | j | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[53]` | button | k | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[54]` | button | l | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[55]` | button | m | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[56]` | button | n | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[57]` | button | o | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[58]` | button | p | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[59]` | button | q | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[5]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[60]` | button | r | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[61]` | button | s | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[62]` | button | t | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[63]` | button | u | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[64]` | button | v | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[65]` | button | w | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[66]` | button | x | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[67]` | button | y | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[68]` | button | z | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[69]` | button | A | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[6]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[70]` | button | B | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[71]` | button | C | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[72]` | button | D | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[73]` | button | E | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[74]` | button | F | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[75]` | button | G | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[76]` | button | H | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[77]` | button | I | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[78]` | button | K | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[79]` | button | L | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[7]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[80]` | button | M | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[81]` | button | N | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[82]` | button | P | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[83]` | button | Q | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[84]` | button | R | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[85]` | button | S | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[86]` | button | T | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[87]` | button | V | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[88]` | button | W | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[89]` | button | X | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[8]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[90]` | button | Y | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[91]` | button | Z | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[92]` | button | α | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[93]` | button | β | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[94]` | button | γ | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[95]` | button | δ | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[96]` | button | ε | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[97]` | button | θ | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[98]` | button | λ | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[99]` | button | μ | #sec-costs (через #fh-iso → #costs-pane-iso>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mk[9]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mkbd-tab` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mkbd-tab[1]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.mkbd-tab[2]` | button | Производственная функция Q(L, K) | #sec-costs (через #fh-iso) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-iso>button.swatch` | button | Цвет кривой | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[100]` | button | π | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[101]` | button | ρ | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[102]` | button | σ | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[103]` | button | τ | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[104]` | button | φ | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[105]` | button | ω | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[106]` | button | Δ | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[107]` | button | Σ | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[108]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[109]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[10]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[110]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[11]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[12]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[13]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[14]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[15]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[16]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[17]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[18]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[19]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[1]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[20]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[21]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[22]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[23]` | button | Стереть символ | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[24]` | button | Очистить поле | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[25]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[26]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[27]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[28]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[29]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[2]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[30]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[31]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[32]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[33]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[34]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[35]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[36]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[37]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[38]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[39]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[3]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[40]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[41]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[42]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[43]` | button | a | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[44]` | button | b | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[45]` | button | c | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[46]` | button | d | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[47]` | button | e | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[48]` | button | f | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[49]` | button | g | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[4]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[50]` | button | h | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[51]` | button | i | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[52]` | button | j | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[53]` | button | k | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[54]` | button | l | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[55]` | button | m | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[56]` | button | n | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[57]` | button | o | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[58]` | button | p | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[59]` | button | q | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[5]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[60]` | button | r | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[61]` | button | s | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[62]` | button | t | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[63]` | button | u | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[64]` | button | v | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[65]` | button | w | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[66]` | button | x | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[67]` | button | y | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[68]` | button | z | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[69]` | button | A | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[6]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[70]` | button | B | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[71]` | button | C | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[72]` | button | D | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[73]` | button | E | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[74]` | button | F | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[75]` | button | G | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[76]` | button | H | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[77]` | button | I | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[78]` | button | K | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[79]` | button | L | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[7]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[80]` | button | M | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[81]` | button | N | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[82]` | button | P | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[83]` | button | Q | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[84]` | button | R | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[85]` | button | S | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[86]` | button | T | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[87]` | button | V | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[88]` | button | W | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[89]` | button | X | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[8]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[90]` | button | Y | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[91]` | button | Z | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[92]` | button | α | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[93]` | button | β | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[94]` | button | γ | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[95]` | button | δ | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[96]` | button | ε | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[97]` | button | θ | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[98]` | button | λ | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[99]` | button | μ | #sec-costs (через #fh-auto-inp-pl1 → #costs-pane-plants>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mk[9]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mkbd-tab` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mkbd-tab[1]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.mkbd-tab[2]` | button | Затраты завода 1: TC1​(Q1​) | #sec-costs (через #fh-auto-inp-pl1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-plants>button.tgl-sw` | switch | Суммарные TC | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[100]` | button | π | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[101]` | button | ρ | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[102]` | button | σ | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[103]` | button | τ | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[104]` | button | φ | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[105]` | button | ω | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[106]` | button | Δ | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[107]` | button | Σ | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[108]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[109]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[10]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[110]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[11]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[12]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[13]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[14]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[15]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[16]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[17]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[18]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[19]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[1]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[20]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[21]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[22]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[23]` | button | Стереть символ | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[24]` | button | Очистить поле | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[25]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[26]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[27]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[28]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[29]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[2]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[30]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[31]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[32]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[33]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[34]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[35]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[36]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[37]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[38]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[39]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[3]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[40]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[41]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[42]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[43]` | button | a | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[44]` | button | b | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[45]` | button | c | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[46]` | button | d | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[47]` | button | e | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[48]` | button | f | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[49]` | button | g | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[4]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[50]` | button | h | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[51]` | button | i | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[52]` | button | j | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[53]` | button | k | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[54]` | button | l | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[55]` | button | m | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[56]` | button | n | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[57]` | button | o | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[58]` | button | p | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[59]` | button | q | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[5]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[60]` | button | r | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[61]` | button | s | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[62]` | button | t | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[63]` | button | u | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[64]` | button | v | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[65]` | button | w | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[66]` | button | x | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[67]` | button | y | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[68]` | button | z | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[69]` | button | A | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[6]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[70]` | button | B | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[71]` | button | C | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[72]` | button | D | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[73]` | button | E | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[74]` | button | F | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[75]` | button | G | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[76]` | button | H | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[77]` | button | I | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[78]` | button | K | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[79]` | button | L | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[7]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[80]` | button | M | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[81]` | button | N | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[82]` | button | P | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[83]` | button | Q | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[84]` | button | R | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[85]` | button | S | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[86]` | button | T | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[87]` | button | V | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[88]` | button | W | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[89]` | button | X | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[8]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[90]` | button | Y | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[91]` | button | Z | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[92]` | button | α | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[93]` | button | β | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[94]` | button | γ | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[95]` | button | δ | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[96]` | button | ε | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[97]` | button | θ | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[98]` | button | λ | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[99]` | button | μ | #sec-costs (через #fh-prod → #costs-pane-prod>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mk[9]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mkbd-tab` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mkbd-tab[1]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.mkbd-tab[2]` | button | Выпуск Q = f(L) | #sec-costs (через #fh-prod) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.swatch` | button | Цвет кривой | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.swatch[1]` | button | Цвет кривой | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#costs-pane-prod>button.swatch[2]` | button | Цвет кривой | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button` | button | Кусочная функция | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon` | button | Имя на графике и роль кривой | #sec-curves | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[10]` | button | Имя на графике и роль кривой | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[11]` | button | Убрать кривую с графика (вернуть галочкой слева) | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[12]` | button | Имя на графике и роль кривой | #sec-curves (через #sum-nd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[13]` | button | Убрать кривую с графика (вернуть галочкой слева) | #sec-curves (через #sum-nd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[1]` | button | Убрать кривую с графика (вернуть галочкой слева) | #sec-curves | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[2]` | button | Имя на графике и роль кривой | #sec-curves | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[3]` | button | Убрать кривую с графика (вернуть галочкой слева) | #sec-curves | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[4]` | button | Имя на графике и роль кривой | #sec-curves (через #btn-add-curve) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[5]` | button | Удалить кривую | #sec-curves (через #btn-add-curve) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[6]` | button | Имя на графике и роль кривой | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[7]` | button | Удалить кривую | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[8]` | button | Имя на графике и роль кривой | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.btn-icon[9]` | button | Удалить кривую | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk` | button | 7 | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[100]` | button | π | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[101]` | button | ρ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[102]` | button | σ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[103]` | button | τ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[104]` | button | φ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[105]` | button | ω | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[106]` | button | Δ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[107]` | button | Σ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[108]` | button | ∞ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[109]` | button | % | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[10]` | button | 1 | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[110]` | button | ≈ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[11]` | button | 2 | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[12]` | button | 3 | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[13]` | button | − | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[14]` | button | + | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[15]` | button | 0 | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[16]` | button | , | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[17]` | button | = | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[18]` | button | x² | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[19]` | button | xⁿ | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[1]` | button | 8 | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[20]` | button | xₙ | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[21]` | button | √ | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[22]` | button | \|x\| | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[23]` | button | Стереть символ | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[24]` | button | Очистить поле | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[25]` | button | √ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[26]` | button | ⁿ√ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[27]` | button | \|x\| | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[28]` | button | xⁿ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[29]` | button | eˣ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[2]` | button | 9 | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[30]` | button | ln | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[31]` | button | log | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[32]` | button | sin | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[33]` | button | cos | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[34]` | button | tan | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[35]` | button | < | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[36]` | button | > | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[37]` | button | ≤ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[38]` | button | ≥ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[39]` | button | ≠ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[3]` | button | ( | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[40]` | button | min | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[41]` | button | max | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[42]` | button | если | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[1]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[43]` | button | a | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[44]` | button | b | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[45]` | button | c | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[46]` | button | d | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[47]` | button | e | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[48]` | button | f | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[49]` | button | g | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[4]` | button | ) | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[50]` | button | h | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[51]` | button | i | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[52]` | button | j | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[53]` | button | k | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[54]` | button | l | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[55]` | button | m | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[56]` | button | n | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[57]` | button | o | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[58]` | button | p | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[59]` | button | q | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[5]` | button | 4 | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[60]` | button | r | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[61]` | button | s | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[62]` | button | t | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[63]` | button | u | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[64]` | button | v | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[65]` | button | w | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[66]` | button | x | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[67]` | button | y | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[68]` | button | z | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[69]` | button | A | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[6]` | button | 5 | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[70]` | button | B | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[71]` | button | C | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[72]` | button | D | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[73]` | button | E | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[74]` | button | F | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[75]` | button | G | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[76]` | button | H | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[77]` | button | I | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[78]` | button | K | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[79]` | button | L | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[7]` | button | 6 | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[80]` | button | M | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[81]` | button | N | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[82]` | button | P | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[83]` | button | Q | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[84]` | button | R | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[85]` | button | S | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[86]` | button | T | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[87]` | button | V | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[88]` | button | W | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[89]` | button | X | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[8]` | button | × | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[90]` | button | Y | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[91]` | button | Z | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[92]` | button | α | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[93]` | button | β | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[94]` | button | γ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[95]` | button | δ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[96]` | button | ε | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[97]` | button | θ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[98]` | button | λ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[99]` | button | μ | #sec-curves (через #fh-auto-curve-expr-1 → #curve-list>button.mkbd-tab[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mk[9]` | button | ÷ | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mkbd-tab` | button | 123 | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mkbd-tab[1]` | button | Функции | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.mkbd-tab[2]` | button | Буквы | #sec-curves (через #fh-auto-curve-expr-1) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.swatch` | button | Цвет кривой | #sec-curves | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.swatch[1]` | button | Цвет кривой | #sec-curves | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.swatch[2]` | button | Цвет кривой | #sec-curves (через #btn-add-curve) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.swatch[3]` | button | Цвет кривой | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.swatch[4]` | button | Цвет кривой | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.swatch[5]` | button | Цвет кривой | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>button.swatch[6]` | button | Цвет кривой | #sec-curves (через #sum-nd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>input` | input:checkbox | Показать/скрыть | #sec-curves | 17 | заменён (ж) | глаз в карточке функции (.fc-eye) | compare.mjs: шаг «глаз» |
| `#curve-list>input[10]` | input:checkbox | Показать/скрыть | #sec-curves | 1 | заменён (ж) | глаз в карточке функции (.fc-eye) | compare.mjs: шаг «глаз» |
| `#curve-list>input[12]` | input:checkbox | Показать/скрыть | #sec-curves (через #sum-nd) | 1 | заменён (ж) | глаз в карточке функции (.fc-eye) | compare.mjs: шаг «глаз» |
| `#curve-list>input[1]` | input:checkbox | Показать/скрыть | #sec-curves (через #curve-list>button.swatch) | 17 | заменён (ж) | глаз в карточке функции (.fc-eye) | compare.mjs: шаг «глаз» |
| `#curve-list>input[2]` | input:checkbox | Показать/скрыть | #sec-curves | 17 | заменён (ж) | глаз в карточке функции (.fc-eye) | compare.mjs: шаг «глаз» |
| `#curve-list>input[3]` | input:checkbox | Показать/скрыть | #sec-curves (через #curve-list>button.swatch) | 1 | заменён (ж) | глаз в карточке функции (.fc-eye) | compare.mjs: шаг «глаз» |
| `#curve-list>input[4]` | input:checkbox | Показать/скрыть | #sec-curves (через #btn-add-curve) | 17 | заменён (ж) | глаз в карточке функции (.fc-eye) | compare.mjs: шаг «глаз» |
| `#curve-list>input[5]` | input:checkbox | Показать/скрыть | #sec-curves (через #curve-list>button.swatch) | 1 | заменён (ж) | глаз в карточке функции (.fc-eye) | compare.mjs: шаг «глаз» |
| `#curve-list>input[6]` | input:checkbox | Показать/скрыть | #sec-curves | 1 | заменён (ж) | глаз в карточке функции (.fc-eye) | compare.mjs: шаг «глаз» |
| `#curve-list>input[7]` | input:checkbox | Показать/скрыть | #sec-curves (через #curve-list>button.swatch) | 1 | заменён (ж) | глаз в карточке функции (.fc-eye) | compare.mjs: шаг «глаз» |
| `#curve-list>input[8]` | input:checkbox | Показать/скрыть | #sec-curves | 1 | заменён (ж) | глаз в карточке функции (.fc-eye) | compare.mjs: шаг «глаз» |
| `#curve-list>input[9]` | input:checkbox | Показать/скрыть | #sec-curves (через #curve-list>button.swatch) | 1 | заменён (ж) | глаз в карточке функции (.fc-eye) | compare.mjs: шаг «глаз» |
| `#curve-list>select.role-sel` | select | обычная криваяD, спросS, предложениеMC, предельные издержкиTC, суммарные затраты | #sec-curves (через #curve-list>button.btn-icon) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>select.role-sel[1]` | select | обычная криваяD, спросS, предложениеMC, предельные издержкиTC, суммарные затраты | #sec-curves (через #curve-list>button.btn-icon[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>select.role-sel[2]` | select | обычная криваяD, спросS, предложениеMC, предельные издержкиTC, суммарные затраты | #sec-curves (через #curve-list>button.btn-icon[4]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>select.role-sel[3]` | select | обычная криваяD, спросS, предложениеMC, предельные издержкиTC, суммарные затраты | #sec-curves (через #curve-list>button.btn-icon[6]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>select.role-sel[4]` | select | обычная криваяD, спросS, предложениеMC, предельные издержкиTC, суммарные затраты | #sec-curves (через #curve-list>button.btn-icon[8]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>select.role-sel[5]` | select | обычная криваяD, спросS, предложениеMC, предельные издержкиTC, суммарные затраты | #sec-curves (через #curve-list>button.btn-icon[10]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>span.edval` | edval | Щёлкните, чтобы изменить | #sec-curves (через #curve-list>button.btn-icon) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>span.edval[1]` | edval | Щёлкните, чтобы изменить | #sec-curves (через #curve-list>button.btn-icon[2]) | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>span.edval[2]` | edval | Щёлкните, чтобы изменить | #sec-curves (через #curve-list>button.btn-icon[4]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>span.edval[3]` | edval | Щёлкните, чтобы изменить | #sec-curves (через #curve-list>button.btn-icon[6]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>span.edval[4]` | edval | Щёлкните, чтобы изменить | #sec-curves (через #curve-list>button.btn-icon[8]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#curve-list>span.edval[5]` | edval | Щёлкните, чтобы изменить | #sec-curves (через #curve-list>button.btn-icon[10]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#cv-mode-stop` | button | Готово |  (через #areascalc-body>button.tgl-sw) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#dock-export` | button | Скачать график | .dock | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ex-btn` | button | Объяснение модели | #explain | 44 | заменён (д) | секции всегда раскрыты, колонка прокручивается | compare.mjs: органы секции видны без раскрытия |
| `#exp-close` | button | Закрыть | #export-modal (через #dock-export) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#exp-label-slot>span.edval` | edval | Щёлкните, чтобы изменить | #export-modal (через #dock-export) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#exp-png` | button | Скачать PNG | #export-modal (через #dock-export) | 44 | заменён (к) | выбор формата и кнопка «Скачать …» (#exp-go) | export_audit.mjs + compare.mjs |
| `#exp-tex` | button | Скачать .tex | #export-modal (через #dock-export) | 44 | заменён (к) | выбор формата и кнопка «Скачать …» (#exp-go) | export_audit.mjs + compare.mjs |
| `#exp-title-slot>span.edval` | edval | Щёлкните, чтобы изменить | #export-modal (через #dock-export) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#export-modal>button.hint-btn` | button | Зачем метка | #export-modal (через #dock-export) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ext-pigou` | input:checkbox | Применить корректирующий налог или субсидию | #sec-input | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ff-modal-close` | button | Закрыть | #ff-modal (через #info-final>button.ff-expand) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ff-modal-copy` | button | Копировать запись | #ff-modal (через #info-final>button.ff-expand) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ff-modal-x` | button | Закрыть | #ff-modal (через #info-final>button.ff-expand) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-curve-expr-1` | button | Клавиатура и примеры формул | #sec-curves | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-curve-expr-2` | button | Клавиатура и примеры формул | #sec-curves | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-curve-expr-3` | button | Открыть математическую клавиатуру | #sec-curves (через #btn-add-curve) | 16 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-curve-expr-4` | button | Клавиатура и примеры формул | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-curve-expr-5` | button | Клавиатура и примеры формул | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-curve-expr-7` | button | Открыть математическую клавиатуру | #sec-curves (через #sum-nd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-graph-f-1` | button | Клавиатура и примеры формул | #sec-graph | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-graph-f-2` | button | Клавиатура и примеры формул | #sec-graph | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-graph-f-3` | button | Клавиатура и примеры формул | #sec-graph (через #btn-scene-reset) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-graph-f-4` | button | Клавиатура и примеры формул | #sec-graph (через #btn-scene-reset) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-graph-f-5` | button | Открыть математическую клавиатуру | #sec-graph (через #btn-scene-reset → mf:#graph-f-4) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-ineq-formula` | button | Клавиатура и примеры формул | #sec-inequality (через #ineq-in-formula) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-catc` | button | Клавиатура и примеры формул | #sec-costs (через #costs-pane-costs>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-cavc` | button | Клавиатура и примеры формул | #sec-costs (через #costs-pane-costs>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-cmc` | button | Клавиатура и примеры формул | #sec-costs (через #costs-pane-costs>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-d3-1` | button | Клавиатура и примеры формул | #sec-mono | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-d3-2` | button | Клавиатура и примеры формул | #sec-mono | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-d3-mc` | button | Клавиатура и примеры формул | #sec-mono | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-ki-1` | button | Клавиатура и примеры формул | #sec-mono | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-ki-2` | button | Клавиатура и примеры формул | #sec-mono | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-ki-3` | button | Клавиатура и примеры формул | #sec-mono | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-kink-mc` | button | Клавиатура и примеры формул | #sec-mono | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-kp-1` | button | Клавиатура и примеры формул | #sec-mono (через #mono-kink-pane>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-kp-2` | button | Клавиатура и примеры формул | #sec-mono (через #mono-kink-pane>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-msb` | button | Клавиатура и примеры формул | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-msc` | button | Клавиатура и примеры формул | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-pl1` | button | Клавиатура и примеры формул | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-pl2` | button | Клавиатура и примеры формул | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-ppfsum-0` | button | Клавиатура и примеры формул | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-ppfsum-1` | button | Клавиатура и примеры формул | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-ppfsum-2` | button | Открыть математическую клавиатуру | #sec-ppf (через #inp-ppfsum-n) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-ppft` | button | Клавиатура и примеры формул | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-tb1` | button | Клавиатура и примеры формул | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-inp-tb2` | button | Клавиатура и примеры формул | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-ma-ad` | button | Клавиатура и примеры формул | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-ma-fxd` | button | Клавиатура и примеры формул | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-ma-fxs` | button | Клавиатура и примеры формул | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-ma-is` | button | Клавиатура и примеры формул | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-ma-lafd` | button | Клавиатура и примеры формул | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-ma-lafs` | button | Клавиатура и примеры формул | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-ma-ld` | button | Клавиатура и примеры формул | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-ma-lm` | button | Клавиатура и примеры формул | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-ma-ls` | button | Клавиатура и примеры формул | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-ma-md` | button | Клавиатура и примеры формул | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-ma-sras` | button | Клавиатура и примеры формул | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-mm-f0` | button | Клавиатура и примеры формул | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-mm-f1` | button | Клавиатура и примеры формул | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-auto-mm-f2` | button | Открыть математическую клавиатуру | #sec-math (через #mm-count) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-iso` | button | Клавиатура и примеры формул | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-mathf` | button | Клавиатура и примеры формул | #sec-math | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-mathfc` | button | Клавиатура и примеры формул | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-mathgc` | button | Клавиатура и примеры формул | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-ppf` | button | Клавиатура и примеры формул | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-prod` | button | Клавиатура и примеры формул | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#fh-tc` | button | Клавиатура и примеры формул | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button` | button | Кусочная функция | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.btn-icon` | button | Убрать функцию | #sec-graph | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.btn-icon[1]` | button | Убрать функцию | #sec-graph (через #btn-scene-reset → mf:#graph-f-4) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk` | button | 7 | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[100]` | button | π | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[101]` | button | ρ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[102]` | button | σ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[103]` | button | τ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[104]` | button | φ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[105]` | button | ω | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[106]` | button | Δ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[107]` | button | Σ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[108]` | button | ∞ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[109]` | button | % | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[10]` | button | 1 | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[110]` | button | ≈ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[11]` | button | 2 | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[12]` | button | 3 | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[13]` | button | − | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[14]` | button | + | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[15]` | button | 0 | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[16]` | button | , | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[17]` | button | = | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[18]` | button | x² | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[19]` | button | xⁿ | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[1]` | button | 8 | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[20]` | button | xₙ | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[21]` | button | √ | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[22]` | button | \|x\| | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[23]` | button | Стереть символ | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[24]` | button | Очистить поле | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[25]` | button | √ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[26]` | button | ⁿ√ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[27]` | button | \|x\| | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[28]` | button | xⁿ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[29]` | button | eˣ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[2]` | button | 9 | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[30]` | button | ln | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[31]` | button | log | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[32]` | button | sin | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[33]` | button | cos | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[34]` | button | tan | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[35]` | button | < | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[36]` | button | > | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[37]` | button | ≤ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[38]` | button | ≥ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[39]` | button | ≠ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[3]` | button | ( | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[40]` | button | min | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[41]` | button | max | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[42]` | button | если | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[43]` | button | a | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[44]` | button | b | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[45]` | button | c | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[46]` | button | d | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[47]` | button | e | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[48]` | button | f | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[49]` | button | g | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[4]` | button | ) | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[50]` | button | h | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[51]` | button | i | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[52]` | button | j | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[53]` | button | k | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[54]` | button | l | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[55]` | button | m | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[56]` | button | n | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[57]` | button | o | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[58]` | button | p | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[59]` | button | q | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[5]` | button | 4 | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[60]` | button | r | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[61]` | button | s | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[62]` | button | t | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[63]` | button | u | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[64]` | button | v | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[65]` | button | w | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[66]` | button | x | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[67]` | button | y | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[68]` | button | z | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[69]` | button | A | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[6]` | button | 5 | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[70]` | button | B | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[71]` | button | C | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[72]` | button | D | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[73]` | button | E | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[74]` | button | F | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[75]` | button | G | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[76]` | button | H | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[77]` | button | I | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[78]` | button | K | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[79]` | button | L | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[7]` | button | 6 | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[80]` | button | M | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[81]` | button | N | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[82]` | button | P | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[83]` | button | Q | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[84]` | button | R | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[85]` | button | S | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[86]` | button | T | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[87]` | button | V | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[88]` | button | W | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[89]` | button | X | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[8]` | button | × | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[90]` | button | Y | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[91]` | button | Z | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[92]` | button | α | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[93]` | button | β | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[94]` | button | γ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[95]` | button | δ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[96]` | button | ε | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[97]` | button | θ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[98]` | button | λ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[99]` | button | μ | #sec-graph (через #fh-auto-graph-f-1 → #graph-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mk[9]` | button | ÷ | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mkbd-tab` | button | 123 | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mkbd-tab[1]` | button | Функции | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.mkbd-tab[2]` | button | Буквы | #sec-graph (через #btn-scene-reset → #fh-auto-graph-f-3) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.swatch` | button | Цвет кривой | #sec-graph | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.swatch[1]` | button | Цвет кривой | #sec-graph | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>button.swatch[2]` | button | Цвет кривой | #sec-graph (через #btn-scene-reset → mf:#graph-f-4) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>span.edval` | edval | Щёлкните, чтобы изменить | #sec-graph | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>span.edval[1]` | edval | Щёлкните, чтобы изменить | #sec-graph | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#graph-rows>span.edval[2]` | edval | Щёлкните, чтобы изменить | #sec-graph (через #btn-scene-reset → mf:#graph-f-4) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#grid-dense` | button | Подробная | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#grid-off` | button | Нет | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#grid-plain` | button | Упрощённая | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#gtitle-color-slot>button.swatch` | button | Цвет названия графика | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-alpha` | input:range | alpha​=2 | #params-body (через #ineq-in-formula) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-alpha-field>button.param-bound` | bounds | Границы и шаг | #params-body (через #ineq-in-formula) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-alpha-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body (через #ineq-in-formula) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-alpha-field>span.pchip-label` | exact | Параметр α. Щёлкните, чтобы ввести точное значение | #params-body (через #ineq-in-formula) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-formula-apply` | button | Построить | #sec-inequality (через #ineq-in-formula) | 1 | заменён (а) | набор в поле над кнопкой применяется сам (живое применение) | formula_input_probe.mjs (расширенный) + compare.mjs: шаг «набор» без нажатия |
| `#ineq-groups-table>input` | input:number |  | #sec-inequality | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-groups-table>input[1]` | input:number |  | #sec-inequality | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-groups-table>input[2]` | input:number |  | #sec-inequality | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-groups-table>input[3]` | input:number |  | #sec-inequality | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-groups-table>input[4]` | input:number |  | #sec-inequality | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-groups-table>input[5]` | input:number |  | #sec-inequality (через #ineq-pane-groups>button.sel-btn → >button.sel-item~1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-groups-table>input[6]` | input:number |  | #sec-inequality (через #ineq-pane-groups>button.sel-btn → >button.sel-item~1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-groups-table>input[7]` | input:number |  | #sec-inequality (через #ineq-pane-groups>button.sel-btn → >button.sel-item~1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-groups-table>input[8]` | input:number |  | #sec-inequality (через #ineq-pane-groups>button.sel-btn → >button.sel-item~1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-groups-table>input[9]` | input:number |  | #sec-inequality (через #ineq-pane-groups>button.sel-btn → >button.sel-item~1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-in-formula` | button | Формула | #sec-inequality | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-in-groups` | button | Доли по группам | #sec-inequality | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-in-incomes` | button | Доходы | #sec-inequality | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-incomes-apply` | button | Построить | #sec-inequality (через #ineq-in-incomes) | 1 | заменён (а) | набор в поле над кнопкой применяется сам (живое применение) | formula_input_probe.mjs (расширенный) + compare.mjs: шаг «набор» без нажатия |
| `#ineq-master-slider` | input:range | Сила неравенства | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-master-slider-val` | exact | Щёлкните, чтобы ввести точное значение | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-pane-groups>button.sel-btn` | button | Сколько групп населения | #sec-inequality | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-pane-incomes>span.edval` | edval | Щёлкните, чтобы изменить | #sec-inequality (через #ineq-in-incomes) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-redist` | input:checkbox | Перераспределение | #sec-inequality | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-redist-pane>button.tgl-sw` | switch | Проп. налог | #sec-inequality (через #ineq-redist) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ineq-tau` | input:range | Прогрессивность τ = 0 | #sec-inequality (через #ineq-redist) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#info-areacalc>button.swatch` | button | Цвет области: Излишек покупателя (CS) | #sec-areascalc | 20 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#info-areacalc>button.swatch[1]` | button | Цвет области: Излишек продавца (PS) | #sec-areascalc | 13 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#info-areacalc>button.swatch[2]` | button | Цвет области: Потери общества (DWL) | #sec-areascalc | 10 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#info-areacalc>button.swatch[3]` | button | Цвет области: Потери общества ($DWL$) | #sec-areascalc (через #tax-field>span.pchip-label) | 6 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#info-final>button.ff-copy` | button | Скопировать запись | #scoreboard | 6 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#info-final>button.ff-copy[1]` | button | Скопировать запись | #scoreboard | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#info-final>button.ff-expand` | button | Показать запись целиком | #scoreboard | 5 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#info-final>button.ff-expand[1]` | button | Показать запись целиком | #scoreboard | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-bundle-x` | input:number | Единиц X | #sec-ppf (через #chk-bundle-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-bundle-x2` | input:number | Единиц X | #sec-ppf (через #chk-bundle-2) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-bundle-xt` | input:number | Единиц X | #sec-ppf (через #chk-bundle-t) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-bundle-y` | input:number | Единиц Y | #sec-ppf (через #chk-bundle-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-bundle-y2` | input:number | Единиц Y | #sec-ppf (через #chk-bundle-2) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-bundle-yt` | input:number | Единиц Y | #sec-ppf (через #chk-bundle-t) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-gtitle` | input:text | Название графика | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-nat-fc` | input:number | Постоянные издержки FC | #sec-mono | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-pmax` | input:number | До | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-pmin` | input:number | От | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-ppfsum-n` | input:number | Сколько кривых | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-qmax` | input:number | До | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-qmin` | input:number | От | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-xname` | input:text | Название оси | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-xstep` | input:number | Шаг делений | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-yname` | input:text | Название оси | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#inp-ystep` | input:number | Шаг делений | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#iso-c` | input:number | Бюджет C | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#iso-r` | input:number | Цена капитала r | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#iso-w` | input:number | Цена труда w | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[100]` | button | π | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[101]` | button | ρ | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[102]` | button | σ | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[103]` | button | τ | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[104]` | button | φ | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[105]` | button | ω | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[106]` | button | Δ | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[107]` | button | Σ | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[108]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[109]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[10]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[110]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[11]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[12]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[13]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[14]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[15]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[16]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[17]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[18]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[19]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[1]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[20]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[21]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[22]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[23]` | button | Стереть символ | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[24]` | button | Очистить поле | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[25]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[26]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[27]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[28]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[29]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[2]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[30]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[31]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[32]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[33]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[34]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[35]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[36]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[37]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[38]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[39]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[3]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[40]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[41]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[42]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[43]` | button | a | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[44]` | button | b | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[45]` | button | c | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[46]` | button | d | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[47]` | button | e | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[48]` | button | f | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[49]` | button | g | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[4]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[50]` | button | h | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[51]` | button | i | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[52]` | button | j | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[53]` | button | k | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[54]` | button | l | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[55]` | button | m | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[56]` | button | n | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[57]` | button | o | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[58]` | button | p | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[59]` | button | q | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[5]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[60]` | button | r | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[61]` | button | s | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[62]` | button | t | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[63]` | button | u | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[64]` | button | v | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[65]` | button | w | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[66]` | button | x | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[67]` | button | y | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[68]` | button | z | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[69]` | button | A | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[6]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[70]` | button | B | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[71]` | button | C | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[72]` | button | D | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[73]` | button | E | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[74]` | button | F | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[75]` | button | G | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[76]` | button | H | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[77]` | button | I | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[78]` | button | K | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[79]` | button | L | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[7]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[80]` | button | M | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[81]` | button | N | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[82]` | button | P | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[83]` | button | Q | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[84]` | button | R | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[85]` | button | S | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[86]` | button | T | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[87]` | button | V | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[88]` | button | W | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[89]` | button | X | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[8]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[90]` | button | Y | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[91]` | button | Z | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[92]` | button | α | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[93]` | button | β | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[94]` | button | γ | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[95]` | button | δ | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[96]` | button | ε | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[97]` | button | θ | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[98]` | button | λ | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[99]` | button | μ | #sec-mono (через #fh-auto-inp-ki-1 → #kink-indiv>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mk[9]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mkbd-tab` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mkbd-tab[1]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#kink-indiv>button.mkbd-tab[2]` | button | Спрос 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-ki-1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#labmin-field>button.param-bound` | bounds | Границы и шаг | #params-body | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#labmin-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#labmin-field>span.pchip-label` | exact | W_min. Щёлкните, чтобы ввести точное значение | #params-body | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#labmin-slider` | input:range | Wmin​=65 | #params-body | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#lbl-l` | button | Крупные подписи | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#lbl-m` | button | Средние подписи | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#lbl-s` | button | Мелкие подписи | #wrench-pop (через #btn-wrench) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#lr-price-field>button.param-bound` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#lr-price-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#lr-price-field>span.pchip-label` | exact | Цена $P$. Щёлкните, чтобы ввести точное значение | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#lr-price-slider` | input:range | Цена P=15 | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-beta` | input:number | Наклон β | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-dg-field>button.param-bound` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-dg-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-dg-field>span.pchip-label` | exact | Дефицит бюджета ΔG. Щёлкните, чтобы ввести точное значение | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-dg-slider` | input:range | G=0 | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-fx-fixed` | input:checkbox | Фиксированный курс | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-fx-fixed-field>button.param-bound` | bounds | Границы и шаг | #params-body (через #ma-fx-fixed) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-fx-fixed-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body (через #ma-fx-fixed) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-fx-fixed-field>span.pchip-label` | exact | Курс e. Щёлкните, чтобы ввести точное значение | #params-body (через #ma-fx-fixed) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-fxe-slider` | input:range | Курс e=20 | #params-body (через #ma-fx-fixed) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-lafmax` | input:number | Максимальная ставка на оси | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-lras` | input:number | Потенциальный выпуск Y* (LRAS, вертикаль) | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-ms` | input:number | Предложение Ms (ЦБ, вертикаль) | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-pe` | input:number | Ожидания πe | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ma-ustar` | input:number | Естественный u* | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[100]` | button | π | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[101]` | button | ρ | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[102]` | button | σ | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[103]` | button | τ | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[104]` | button | φ | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[105]` | button | ω | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[106]` | button | Δ | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[107]` | button | Σ | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[108]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[109]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[10]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[110]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[11]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[12]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[13]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[14]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[15]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[16]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[17]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[18]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[19]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[1]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[20]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[21]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[22]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[23]` | button | Стереть символ | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[24]` | button | Очистить поле | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[25]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[26]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[27]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[28]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[29]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[2]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[30]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[31]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[32]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[33]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[34]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[35]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[36]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[37]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[38]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[39]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[3]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[40]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[41]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[42]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[43]` | button | a | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[44]` | button | b | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[45]` | button | c | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[46]` | button | d | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[47]` | button | e | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[48]` | button | f | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[49]` | button | g | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[4]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[50]` | button | h | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[51]` | button | i | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[52]` | button | j | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[53]` | button | k | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[54]` | button | l | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[55]` | button | m | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[56]` | button | n | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[57]` | button | o | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[58]` | button | p | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[59]` | button | q | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[5]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[60]` | button | r | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[61]` | button | s | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[62]` | button | t | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[63]` | button | u | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[64]` | button | v | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[65]` | button | w | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[66]` | button | x | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[67]` | button | y | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[68]` | button | z | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[69]` | button | A | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[6]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[70]` | button | B | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[71]` | button | C | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[72]` | button | D | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[73]` | button | E | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[74]` | button | F | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[75]` | button | G | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[76]` | button | H | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[77]` | button | I | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[78]` | button | K | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[79]` | button | L | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[7]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[80]` | button | M | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[81]` | button | N | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[82]` | button | P | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[83]` | button | Q | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[84]` | button | R | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[85]` | button | S | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[86]` | button | T | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[87]` | button | V | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[88]` | button | W | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[89]` | button | X | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[8]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[90]` | button | Y | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[91]` | button | Z | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[92]` | button | α | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[93]` | button | β | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[94]` | button | γ | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[95]` | button | δ | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[96]` | button | ε | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[97]` | button | θ | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[98]` | button | λ | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[99]` | button | μ | #sec-macro (через #fh-auto-ma-sras → #macro-pane-adas>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mk[9]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mkbd-tab` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mkbd-tab[1]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-adas>button.mkbd-tab[2]` | button | SRAS: P = f(Y) | #sec-macro (через #fh-auto-ma-sras) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[100]` | button | π | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[101]` | button | ρ | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[102]` | button | σ | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[103]` | button | τ | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[104]` | button | φ | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[105]` | button | ω | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[106]` | button | Δ | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[107]` | button | Σ | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[108]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[109]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[10]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[110]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[11]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[12]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[13]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[14]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[15]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[16]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[17]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[18]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[19]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[1]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[20]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[21]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[22]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[23]` | button | Стереть символ | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[24]` | button | Очистить поле | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[25]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[26]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[27]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[28]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[29]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[2]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[30]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[31]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[32]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[33]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[34]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[35]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[36]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[37]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[38]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[39]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[3]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[40]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[41]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[42]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[43]` | button | a | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[44]` | button | b | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[45]` | button | c | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[46]` | button | d | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[47]` | button | e | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[48]` | button | f | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[49]` | button | g | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[4]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[50]` | button | h | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[51]` | button | i | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[52]` | button | j | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[53]` | button | k | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[54]` | button | l | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[55]` | button | m | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[56]` | button | n | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[57]` | button | o | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[58]` | button | p | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[59]` | button | q | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[5]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[60]` | button | r | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[61]` | button | s | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[62]` | button | t | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[63]` | button | u | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[64]` | button | v | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[65]` | button | w | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[66]` | button | x | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[67]` | button | y | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[68]` | button | z | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[69]` | button | A | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[6]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[70]` | button | B | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[71]` | button | C | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[72]` | button | D | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[73]` | button | E | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[74]` | button | F | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[75]` | button | G | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[76]` | button | H | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[77]` | button | I | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[78]` | button | K | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[79]` | button | L | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[7]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[80]` | button | M | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[81]` | button | N | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[82]` | button | P | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[83]` | button | Q | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[84]` | button | R | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[85]` | button | S | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[86]` | button | T | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[87]` | button | V | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[88]` | button | W | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[89]` | button | X | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[8]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[90]` | button | Y | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[91]` | button | Z | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[92]` | button | α | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[93]` | button | β | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[94]` | button | γ | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[95]` | button | δ | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[96]` | button | ε | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[97]` | button | θ | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[98]` | button | λ | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[99]` | button | μ | #sec-macro (через #fh-auto-ma-fxd → #macro-pane-fx>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mk[9]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mkbd-tab` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mkbd-tab[1]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-fx>button.mkbd-tab[2]` | button | Спрос на валюту: Q = f(e) | #sec-macro (через #fh-auto-ma-fxd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[100]` | button | π | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[101]` | button | ρ | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[102]` | button | σ | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[103]` | button | τ | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[104]` | button | φ | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[105]` | button | ω | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[106]` | button | Δ | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[107]` | button | Σ | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[108]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[109]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[10]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[110]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[11]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[12]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[13]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[14]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[15]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[16]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[17]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[18]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[19]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[1]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[20]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[21]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[22]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[23]` | button | Стереть символ | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[24]` | button | Очистить поле | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[25]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[26]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[27]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[28]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[29]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[2]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[30]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[31]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[32]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[33]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[34]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[35]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[36]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[37]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[38]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[39]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[3]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[40]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[41]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[42]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[43]` | button | a | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[44]` | button | b | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[45]` | button | c | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[46]` | button | d | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[47]` | button | e | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[48]` | button | f | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[49]` | button | g | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[4]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[50]` | button | h | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[51]` | button | i | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[52]` | button | j | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[53]` | button | k | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[54]` | button | l | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[55]` | button | m | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[56]` | button | n | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[57]` | button | o | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[58]` | button | p | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[59]` | button | q | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[5]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[60]` | button | r | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[61]` | button | s | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[62]` | button | t | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[63]` | button | u | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[64]` | button | v | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[65]` | button | w | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[66]` | button | x | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[67]` | button | y | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[68]` | button | z | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[69]` | button | A | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[6]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[70]` | button | B | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[71]` | button | C | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[72]` | button | D | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[73]` | button | E | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[74]` | button | F | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[75]` | button | G | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[76]` | button | H | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[77]` | button | I | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[78]` | button | K | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[79]` | button | L | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[7]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[80]` | button | M | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[81]` | button | N | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[82]` | button | P | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[83]` | button | Q | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[84]` | button | R | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[85]` | button | S | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[86]` | button | T | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[87]` | button | V | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[88]` | button | W | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[89]` | button | X | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[8]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[90]` | button | Y | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[91]` | button | Z | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[92]` | button | α | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[93]` | button | β | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[94]` | button | γ | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[95]` | button | δ | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[96]` | button | ε | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[97]` | button | θ | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[98]` | button | λ | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[99]` | button | μ | #sec-macro (через #fh-auto-ma-is → #macro-pane-islm>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mk[9]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mkbd-tab` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mkbd-tab[1]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-islm>button.mkbd-tab[2]` | button | IS: r = f(Y) | #sec-macro (через #fh-auto-ma-is) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[100]` | button | π | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[101]` | button | ρ | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[102]` | button | σ | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[103]` | button | τ | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[104]` | button | φ | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[105]` | button | ω | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[106]` | button | Δ | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[107]` | button | Σ | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[108]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[109]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[10]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[110]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[11]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[12]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[13]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[14]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[15]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[16]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[17]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[18]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[19]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[1]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[20]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[21]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[22]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[23]` | button | Стереть символ | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[24]` | button | Очистить поле | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[25]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[26]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[27]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[28]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[29]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[2]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[30]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[31]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[32]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[33]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[34]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[35]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[36]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[37]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[38]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[39]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[3]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[40]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[41]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[42]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[43]` | button | a | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[44]` | button | b | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[45]` | button | c | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[46]` | button | d | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[47]` | button | e | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[48]` | button | f | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[49]` | button | g | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[4]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[50]` | button | h | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[51]` | button | i | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[52]` | button | j | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[53]` | button | k | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[54]` | button | l | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[55]` | button | m | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[56]` | button | n | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[57]` | button | o | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[58]` | button | p | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[59]` | button | q | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[5]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[60]` | button | r | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[61]` | button | s | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[62]` | button | t | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[63]` | button | u | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[64]` | button | v | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[65]` | button | w | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[66]` | button | x | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[67]` | button | y | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[68]` | button | z | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[69]` | button | A | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[6]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[70]` | button | B | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[71]` | button | C | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[72]` | button | D | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[73]` | button | E | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[74]` | button | F | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[75]` | button | G | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[76]` | button | H | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[77]` | button | I | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[78]` | button | K | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[79]` | button | L | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[7]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[80]` | button | M | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[81]` | button | N | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[82]` | button | P | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[83]` | button | Q | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[84]` | button | R | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[85]` | button | S | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[86]` | button | T | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[87]` | button | V | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[88]` | button | W | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[89]` | button | X | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[8]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[90]` | button | Y | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[91]` | button | Z | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[92]` | button | α | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[93]` | button | β | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[94]` | button | γ | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[95]` | button | δ | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[96]` | button | ε | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[97]` | button | θ | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[98]` | button | λ | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[99]` | button | μ | #sec-macro (через #fh-auto-ma-lafd → #macro-pane-laffer>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mk[9]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mkbd-tab` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mkbd-tab[1]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-laffer>button.mkbd-tab[2]` | button | Спрос: P = f(Q) | #sec-macro (через #fh-auto-ma-lafd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[100]` | button | π | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[101]` | button | ρ | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[102]` | button | σ | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[103]` | button | τ | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[104]` | button | φ | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[105]` | button | ω | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[106]` | button | Δ | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[107]` | button | Σ | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[108]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[109]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[10]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[110]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[11]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[12]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[13]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[14]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[15]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[16]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[17]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[18]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[19]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[1]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[20]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[21]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[22]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[23]` | button | Стереть символ | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[24]` | button | Очистить поле | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[25]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[26]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[27]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[28]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[29]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[2]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[30]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[31]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[32]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[33]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[34]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[35]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[36]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[37]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[38]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[39]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[3]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[40]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[41]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[42]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[43]` | button | a | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[44]` | button | b | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[45]` | button | c | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[46]` | button | d | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[47]` | button | e | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[48]` | button | f | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[49]` | button | g | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[4]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[50]` | button | h | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[51]` | button | i | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[52]` | button | j | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[53]` | button | k | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[54]` | button | l | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[55]` | button | m | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[56]` | button | n | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[57]` | button | o | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[58]` | button | p | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[59]` | button | q | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[5]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[60]` | button | r | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[61]` | button | s | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[62]` | button | t | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[63]` | button | u | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[64]` | button | v | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[65]` | button | w | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[66]` | button | x | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[67]` | button | y | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[68]` | button | z | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[69]` | button | A | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[6]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[70]` | button | B | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[71]` | button | C | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[72]` | button | D | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[73]` | button | E | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[74]` | button | F | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[75]` | button | G | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[76]` | button | H | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[77]` | button | I | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[78]` | button | K | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[79]` | button | L | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[7]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[80]` | button | M | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[81]` | button | N | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[82]` | button | P | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[83]` | button | Q | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[84]` | button | R | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[85]` | button | S | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[86]` | button | T | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[87]` | button | V | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[88]` | button | W | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[89]` | button | X | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[8]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[90]` | button | Y | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[91]` | button | Z | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[92]` | button | α | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[93]` | button | β | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[94]` | button | γ | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[95]` | button | δ | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[96]` | button | ε | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[97]` | button | θ | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[98]` | button | λ | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[99]` | button | μ | #sec-macro (через #fh-auto-ma-ls → #macro-pane-loanable>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mk[9]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mkbd-tab` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mkbd-tab[1]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-loanable>button.mkbd-tab[2]` | button | Сбережения: S = f(r) | #sec-macro (через #fh-auto-ma-ls) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[100]` | button | π | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[101]` | button | ρ | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[102]` | button | σ | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[103]` | button | τ | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[104]` | button | φ | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[105]` | button | ω | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[106]` | button | Δ | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[107]` | button | Σ | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[108]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[109]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[10]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[110]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[11]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[12]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[13]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[14]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[15]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[16]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[17]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[18]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[19]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[1]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[20]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[21]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[22]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[23]` | button | Стереть символ | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[24]` | button | Очистить поле | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[25]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[26]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[27]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[28]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[29]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[2]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[30]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[31]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[32]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[33]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[34]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[35]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[36]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[37]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[38]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[39]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[3]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[40]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[41]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[42]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[43]` | button | a | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[44]` | button | b | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[45]` | button | c | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[46]` | button | d | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[47]` | button | e | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[48]` | button | f | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[49]` | button | g | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[4]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[50]` | button | h | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[51]` | button | i | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[52]` | button | j | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[53]` | button | k | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[54]` | button | l | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[55]` | button | m | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[56]` | button | n | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[57]` | button | o | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[58]` | button | p | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[59]` | button | q | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[5]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[60]` | button | r | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[61]` | button | s | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[62]` | button | t | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[63]` | button | u | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[64]` | button | v | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[65]` | button | w | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[66]` | button | x | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[67]` | button | y | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[68]` | button | z | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[69]` | button | A | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[6]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[70]` | button | B | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[71]` | button | C | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[72]` | button | D | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[73]` | button | E | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[74]` | button | F | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[75]` | button | G | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[76]` | button | H | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[77]` | button | I | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[78]` | button | K | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[79]` | button | L | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[7]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[80]` | button | M | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[81]` | button | N | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[82]` | button | P | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[83]` | button | Q | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[84]` | button | R | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[85]` | button | S | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[86]` | button | T | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[87]` | button | V | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[88]` | button | W | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[89]` | button | X | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[8]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[90]` | button | Y | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[91]` | button | Z | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[92]` | button | α | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[93]` | button | β | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[94]` | button | γ | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[95]` | button | δ | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[96]` | button | ε | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[97]` | button | θ | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[98]` | button | λ | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[99]` | button | μ | #sec-macro (через #fh-auto-ma-md → #macro-pane-money>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mk[9]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mkbd-tab` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mkbd-tab[1]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#macro-pane-money>button.mkbd-tab[2]` | button | Спрос на деньги: M = f(i) | #sec-macro (через #fh-auto-ma-md) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mark-list>button.btn-icon` | button | Поставить точку | #sec-view (через #mark-list>button.btn-sm) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mark-list>button.btn-sm` | button | Добавить точку | #sec-view | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mark-list>button.tgl-sw` | switch | Ввести координаты | #sec-view (через #mark-list>button.btn-sm) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mark-list>span.edval` | edval | Координата Y | #sec-view (через #mark-list>button.btn-sm) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mark-list>span.edval[1]` | edval | Координата P | #sec-view (через #mark-list>button.btn-sm) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#marks-body>button.hint-btn` | button | Как этим пользоваться | #sec-view | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#marks-btn` | button | Точки на графике | #sec-view | 44 | заменён (д) | секции всегда раскрыты, колонка прокручивается | compare.mjs: органы секции видны без раскрытия |
| `#math-pane-constraint>button` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.hint-btn` | button | Как это работает | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[100]` | button | π | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[101]` | button | ρ | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[102]` | button | σ | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[103]` | button | τ | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[104]` | button | φ | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[105]` | button | ω | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[106]` | button | Δ | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[107]` | button | Σ | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[108]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[109]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[10]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[110]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[11]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[12]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[13]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[14]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[15]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[16]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[17]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[18]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[19]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[1]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[20]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[21]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[22]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[23]` | button | Стереть символ | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[24]` | button | Очистить поле | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[25]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[26]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[27]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[28]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[29]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[2]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[30]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[31]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[32]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[33]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[34]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[35]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[36]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[37]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[38]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[39]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[3]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[40]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[41]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[42]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[43]` | button | a | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[44]` | button | b | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[45]` | button | c | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[46]` | button | d | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[47]` | button | e | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[48]` | button | f | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[49]` | button | g | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[4]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[50]` | button | h | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[51]` | button | i | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[52]` | button | j | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[53]` | button | k | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[54]` | button | l | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[55]` | button | m | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[56]` | button | n | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[57]` | button | o | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[58]` | button | p | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[59]` | button | q | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[5]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[60]` | button | r | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[61]` | button | s | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[62]` | button | t | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[63]` | button | u | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[64]` | button | v | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[65]` | button | w | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[66]` | button | x | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[67]` | button | y | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[68]` | button | z | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[69]` | button | A | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[6]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[70]` | button | B | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[71]` | button | C | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[72]` | button | D | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[73]` | button | E | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[74]` | button | F | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[75]` | button | G | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[76]` | button | H | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[77]` | button | I | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[78]` | button | K | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[79]` | button | L | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[7]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[80]` | button | M | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[81]` | button | N | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[82]` | button | P | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[83]` | button | Q | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[84]` | button | R | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[85]` | button | S | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[86]` | button | T | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[87]` | button | V | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[88]` | button | W | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[89]` | button | X | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[8]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[90]` | button | Y | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[91]` | button | Z | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[92]` | button | α | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[93]` | button | β | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[94]` | button | γ | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[95]` | button | δ | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[96]` | button | ε | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[97]` | button | θ | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[98]` | button | λ | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[99]` | button | μ | #sec-math (через #fh-mathfc → #math-pane-constraint>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mk[9]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mkbd-tab` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mkbd-tab[1]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.mkbd-tab[2]` | button | Целевая функция f(x, y) | #sec-math (через #fh-mathfc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-constraint>button.tgl-sw` | switch | Максимум | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-minmax>button.hint-btn` | button | Как это работает | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-minmax>button.swatch` | button | Цвет кривой | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-minmax>button.tgl-sw` | switch | min | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-minmax>span.edval` | edval | Щёлкните, чтобы изменить | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-optimum>button.hint-btn` | button | Что здесь считается | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-tangent>button.hint-btn` | button | Как этим пользоваться | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-tangent>button.swatch` | button | Цвет кривой | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-tangent>button.swatch[1]` | button | Цвет кривой | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-pane-transform>button.sel-btn` | button | Что делаем с графиком | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[100]` | button | π | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[101]` | button | ρ | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[102]` | button | σ | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[103]` | button | τ | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[104]` | button | φ | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[105]` | button | ω | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[106]` | button | Δ | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[107]` | button | Σ | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[108]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[109]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[10]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[110]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[11]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[12]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[13]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[14]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[15]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[16]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[17]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[18]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[19]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[1]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[20]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[21]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[22]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[23]` | button | Стереть символ | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[24]` | button | Очистить поле | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[25]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[26]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[27]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[28]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[29]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[2]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[30]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[31]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[32]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[33]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[34]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[35]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[36]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[37]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[38]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[39]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[3]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[40]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[41]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[42]` | button | Функция y = f(x) | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[1]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[43]` | button | a | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[44]` | button | b | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[45]` | button | c | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[46]` | button | d | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[47]` | button | e | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[48]` | button | f | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[49]` | button | g | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[4]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[50]` | button | h | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[51]` | button | i | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[52]` | button | j | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[53]` | button | k | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[54]` | button | l | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[55]` | button | m | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[56]` | button | n | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[57]` | button | o | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[58]` | button | p | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[59]` | button | q | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[5]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[60]` | button | r | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[61]` | button | s | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[62]` | button | t | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[63]` | button | u | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[64]` | button | v | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[65]` | button | w | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[66]` | button | x | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[67]` | button | y | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[68]` | button | z | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[69]` | button | A | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[6]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[70]` | button | B | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[71]` | button | C | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[72]` | button | D | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[73]` | button | E | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[74]` | button | F | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[75]` | button | G | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[76]` | button | H | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[77]` | button | I | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[78]` | button | K | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[79]` | button | L | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[7]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[80]` | button | M | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[81]` | button | N | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[82]` | button | P | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[83]` | button | Q | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[84]` | button | R | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[85]` | button | S | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[86]` | button | T | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[87]` | button | V | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[88]` | button | W | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[89]` | button | X | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[8]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[90]` | button | Y | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[91]` | button | Z | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[92]` | button | α | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[93]` | button | β | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[94]` | button | γ | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[95]` | button | δ | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[96]` | button | ε | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[97]` | button | θ | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[98]` | button | λ | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[99]` | button | μ | #sec-math (через #fh-mathf → #math-row-f>button.mkbd-tab[2]) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mk[9]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mkbd-tab` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mkbd-tab[1]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#math-row-f>button.mkbd-tab[2]` | button | Функция y = f(x) | #sec-math (через #fh-mathf) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mathdx-slider` | input:range | Шаг Δx = 1 | #params-body (через #chk-secant) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mathx0-field>button.param-bound` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mathx0-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mathx0-field>span.pchip-label` | exact | Точка x₀. Щёлкните, чтобы ввести точное значение | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mathx0-slider` | input:range | Точка x₀=1,02 | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-count` | input:number | Сколько функций | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[100]` | button | π | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[101]` | button | ρ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[102]` | button | σ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[103]` | button | τ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[104]` | button | φ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[105]` | button | ω | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[106]` | button | Δ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[107]` | button | Σ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[108]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[109]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[10]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[110]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[11]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[12]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[13]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[14]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[15]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[16]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[17]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[18]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[19]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[1]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[20]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[21]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[22]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[23]` | button | Стереть символ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[24]` | button | Очистить поле | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[25]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[26]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[27]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[28]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[29]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[2]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[30]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[31]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[32]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[33]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[34]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[35]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[36]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[37]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[38]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[39]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[3]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[40]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[41]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[42]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[43]` | button | a | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[44]` | button | b | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[45]` | button | c | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[46]` | button | d | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[47]` | button | e | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[48]` | button | f | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[49]` | button | g | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[4]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[50]` | button | h | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[51]` | button | i | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[52]` | button | j | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[53]` | button | k | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[54]` | button | l | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[55]` | button | m | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[56]` | button | n | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[57]` | button | o | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[58]` | button | p | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[59]` | button | q | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[5]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[60]` | button | r | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[61]` | button | s | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[62]` | button | t | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[63]` | button | u | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[64]` | button | v | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[65]` | button | w | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[66]` | button | x | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[67]` | button | y | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[68]` | button | z | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[69]` | button | A | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[6]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[70]` | button | B | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[71]` | button | C | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[72]` | button | D | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[73]` | button | E | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[74]` | button | F | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[75]` | button | G | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[76]` | button | H | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[77]` | button | I | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[78]` | button | K | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[79]` | button | L | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[7]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[80]` | button | M | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[81]` | button | N | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[82]` | button | P | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[83]` | button | Q | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[84]` | button | R | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[85]` | button | S | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[86]` | button | T | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[87]` | button | V | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[88]` | button | W | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[89]` | button | X | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[8]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[90]` | button | Y | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[91]` | button | Z | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[92]` | button | α | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[93]` | button | β | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[94]` | button | γ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[95]` | button | δ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[96]` | button | ε | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[97]` | button | θ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[98]` | button | λ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[99]` | button | μ | #sec-math (через #fh-auto-mm-f0 → #mm-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mk[9]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mkbd-tab` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mkbd-tab[1]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.mkbd-tab[2]` | button | Функция f₁ | #sec-math (через #fh-auto-mm-f0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.swatch` | button | Цвет f₁ | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.swatch[1]` | button | Цвет f₂ | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mm-rows>button.swatch[2]` | button | Цвет f₃ | #sec-math (через #mm-count) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[100]` | button | π | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[101]` | button | ρ | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[102]` | button | σ | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[103]` | button | τ | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[104]` | button | φ | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[105]` | button | ω | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[106]` | button | Δ | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[107]` | button | Σ | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[108]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[109]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[10]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[110]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[11]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[12]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[13]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[14]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[15]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[16]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[17]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[18]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[19]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[1]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[20]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[21]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[22]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[23]` | button | Стереть символ | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[24]` | button | Очистить поле | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[25]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[26]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[27]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[28]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[29]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[2]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[30]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[31]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[32]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[33]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[34]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[35]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[36]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[37]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[38]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[39]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[3]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[40]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[41]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[42]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[1]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[43]` | button | a | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[44]` | button | b | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[45]` | button | c | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[46]` | button | d | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[47]` | button | e | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[48]` | button | f | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[49]` | button | g | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[4]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[50]` | button | h | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[51]` | button | i | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[52]` | button | j | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[53]` | button | k | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[54]` | button | l | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[55]` | button | m | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[56]` | button | n | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[57]` | button | o | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[58]` | button | p | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[59]` | button | q | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[5]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[60]` | button | r | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[61]` | button | s | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[62]` | button | t | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[63]` | button | u | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[64]` | button | v | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[65]` | button | w | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[66]` | button | x | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[67]` | button | y | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[68]` | button | z | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[69]` | button | A | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[6]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[70]` | button | B | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[71]` | button | C | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[72]` | button | D | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[73]` | button | E | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[74]` | button | F | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[75]` | button | G | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[76]` | button | H | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[77]` | button | I | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[78]` | button | K | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[79]` | button | L | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[7]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[80]` | button | M | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[81]` | button | N | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[82]` | button | P | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[83]` | button | Q | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[84]` | button | R | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[85]` | button | S | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[86]` | button | T | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[87]` | button | V | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[88]` | button | W | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[89]` | button | X | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[8]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[90]` | button | Y | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[91]` | button | Z | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[92]` | button | α | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[93]` | button | β | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[94]` | button | γ | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[95]` | button | δ | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[96]` | button | ε | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[97]` | button | θ | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[98]` | button | λ | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[99]` | button | μ | #sec-mono (через #fh-auto-inp-d3-1 → #mono-d3-pane>button.mkbd-tab[2]) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mk[9]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mkbd-tab` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mkbd-tab[1]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-d3-pane>button.mkbd-tab[2]` | button | Спрос рынка 1: P = f₁(Q) | #sec-mono (через #fh-auto-inp-d3-1) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[100]` | button | π | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[101]` | button | ρ | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[102]` | button | σ | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[103]` | button | τ | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[104]` | button | φ | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[105]` | button | ω | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[106]` | button | Δ | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[107]` | button | Σ | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[108]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[109]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[10]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[110]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[11]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[12]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[13]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[14]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[15]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[16]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[17]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[18]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[19]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[1]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[20]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[21]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[22]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[23]` | button | Стереть символ | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[24]` | button | Очистить поле | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[25]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[26]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[27]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[28]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[29]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[2]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[30]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[31]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[32]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[33]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[34]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[35]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[36]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[37]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[38]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[39]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[3]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[40]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[41]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[42]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[43]` | button | a | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[44]` | button | b | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[45]` | button | c | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[46]` | button | d | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[47]` | button | e | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[48]` | button | f | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[49]` | button | g | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[4]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[50]` | button | h | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[51]` | button | i | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[52]` | button | j | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[53]` | button | k | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[54]` | button | l | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[55]` | button | m | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[56]` | button | n | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[57]` | button | o | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[58]` | button | p | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[59]` | button | q | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[5]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[60]` | button | r | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[61]` | button | s | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[62]` | button | t | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[63]` | button | u | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[64]` | button | v | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[65]` | button | w | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[66]` | button | x | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[67]` | button | y | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[68]` | button | z | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[69]` | button | A | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[6]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[70]` | button | B | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[71]` | button | C | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[72]` | button | D | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[73]` | button | E | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[74]` | button | F | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[75]` | button | G | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[76]` | button | H | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[77]` | button | I | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[78]` | button | K | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[79]` | button | L | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[7]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[80]` | button | M | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[81]` | button | N | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[82]` | button | P | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[83]` | button | Q | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[84]` | button | R | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[85]` | button | S | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[86]` | button | T | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[87]` | button | V | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[88]` | button | W | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[89]` | button | X | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[8]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[90]` | button | Y | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[91]` | button | Z | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[92]` | button | α | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[93]` | button | β | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[94]` | button | γ | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[95]` | button | δ | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[96]` | button | ε | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[97]` | button | θ | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[98]` | button | λ | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[99]` | button | μ | #sec-mono (через #fh-auto-inp-kink-mc → #mono-kink-pane>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mk[9]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mkbd-tab` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mkbd-tab[1]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.mkbd-tab[2]` | button | Предельные издержки MC (число или f(Q)) | #sec-mono (через #fh-auto-inp-kink-mc) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#mono-kink-pane>button.tgl-sw` | switch | Инд. спросы | #sec-mono | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#oi-none` | button | Без вмешательства | #sec-input | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#oi-quota` | button | Квота | #sec-input | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#oi-tariff` | button | Тариф | #sec-input | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#open-pw-field>button.param-bound` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#open-pw-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#open-pw-field>span.pchip-label` | exact | Мировая цена $P_{\text{w}}$​. Щёлкните, чтобы ввести точное значение | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#open-pw-slider` | input:range | Pw​=30 | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#open-quota-field>button.param-bound` | bounds | Границы и шаг | #params-body (через #oi-quota) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#open-quota-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body (через #oi-quota) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#open-quota-field>span.pchip-label` | exact | Квота: сколько товара разрешено провезти через границу. Щёлкните, чтобы ввести точное знач | #params-body (через #oi-quota) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#open-quota-slider` | input:range | Квота ввоза=20 | #params-body (через #oi-quota) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#open-tariff-field>button.param-bound` | bounds | Границы и шаг | #params-body (через #oi-tariff) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#open-tariff-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body (через #oi-tariff) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#open-tariff-field>span.pchip-label` | exact | Тариф t. Щёлкните, чтобы ввести точное значение | #params-body (через #oi-tariff) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#open-tariff-slider` | input:range | Тариф t=10 | #params-body (через #oi-tariff) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>button.param-bound` | bounds | Границы и шаг | #params-body | 13 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>button.param-bound[1]` | bounds | Границы и шаг | #params-body | 13 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>button.param-bound[2]` | bounds | Границы и шаг | #params-body | 13 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>button.param-bound[3]` | bounds | Границы и шаг | #params-body | 13 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>button.param-bound[4]` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>button.param-bound[5]` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>button.param-bound[6]` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>button.param-bound[7]` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>button.param-bound[8]` | bounds | Границы и шаг | #params-body (через #sum-nd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>button.param-bound[9]` | bounds | Границы и шаг | #params-body (через #sum-nd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>input` | input:range | Параллельный сдвиг кривой по вертикали | #params-body | 13 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>input[1]` | input:range | Параллельный сдвиг кривой по вертикали | #params-body | 13 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>input[2]` | input:range | Параллельный сдвиг кривой по вертикали | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>input[3]` | input:range | Параллельный сдвиг кривой по вертикали | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>input[4]` | input:range | Параллельный сдвиг кривой по вертикали | #params-body (через #sum-nd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>span.pchip-label` | exact | Сдвиг кривой $D$. Щёлкните, чтобы ввести точное значение | #params-body | 13 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>span.pchip-label[1]` | exact | Сдвиг кривой $S$. Щёлкните, чтобы ввести точное значение | #params-body | 13 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>span.pchip-label[2]` | exact | Сдвиг кривой предложение первой группы. Щёлкните, чтобы ввести точное значение | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>span.pchip-label[3]` | exact | Сдвиг кривой предложение второй группы. Щёлкните, чтобы ввести точное значение | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-curves>span.pchip-label[4]` | exact | Сдвиг кривой предложение второй группы. Щёлкните, чтобы ввести точное значение | #params-body (через #sum-nd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-extra>button.param-bound` | bounds | Границы и шаг | #params-body | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-extra>button.param-bound[1]` | bounds | Границы и шаг | #params-body | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-extra>button.param-kill` | button | Свернуть ползунок (буква останется с этим значением) | #params-body | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-extra>input` | input:range | r=1 | #params-body | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-extra>span.pchip-label` | exact | Щёлкните, чтобы ввести точное значение | #params-body | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#params-toggle` | button | Закрыть меню | #params-panel | 44 | заменён (в) | «Развернуть график» в панели холста | compare.mjs: шаг «Развернуть график» |
| `#pc-field>button.param-bound` | bounds | Границы и шаг | #sec-tax | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pc-field>button.param-bound[1]` | bounds | Границы и шаг | #sec-tax | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pc-field>span.pchip-label` | exact | Цена $P_{\text{c}}$. Щёлкните, чтобы ввести точное значение | #sec-tax | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pc-slider` | input:range | Preg​=30 | #sec-tax | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pgrid-0>button.scard.m-constraint` | button | Оптимум при ограничении Максимум или минимум цели при заданном ограничении: каса |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-0>button.scard.m-graph` | button | Построение графиков Любое число кривых, свои точки, подписи и масштаб. Без эконо |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-0>button.scard.m-minmax` | button | Функции min и max Нижняя или верхняя огибающая нескольких функций; излом в точке |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-0>button.scard.m-optimum` | button | Максимумы и минимумы Экстремумы, точки перегиба, выпуклые и вогнутые участки раз |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-0>button.scard.m-tangent` | button | Функция и её производная наглядно Точка на кривой, треугольник Δx и Δy, график п |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-0>button.scard.m-transform` | button | Деформации графика Сдвиги, растяжения, отражения и модули; один ползунок и обе к |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-1>button.scard.ppf` | button | Построение КПВ Граница производства, альтернативные издержки, выпуклость. |  (через #scene-back) | 4 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-1>button.scard.ppfsum` | button | Сложение КПВ Совместная граница с изломом: сравнительное преимущество каждой сто |  (через #scene-back) | 4 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-1>button.scard.trade` | button | КТВ. Одна страна Точка производства на КПВ и выигрыш от торговли при известной м |  (через #scene-back) | 4 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-1>button.scard.tradeprice` | button | КТВ. Две страны-партнёра Мировая цена не задана, а найдена: точка внутри промежу |  (через #scene-back) | 4 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-2>button.scard.ceil` | button | Пол и потолок цены Фиксированная цена, дефицит или избыток, объём торговли по ко |  (через #scene-back) | 7 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-2>button.scard.elast` | button | Эластичность Точечная \|Ed\| и \|Es\|, единичная точка, связь с выручкой. |  (через #scene-back) | 7 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-2>button.scard.ext` | button | Внешние эффекты MSC или MSB против частных, потери DWL, налог или субсидия Пигу. |  (через #scene-back) | 7 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-2>button.scard.firmmarket` | button | Рынок и фирма в СКСкоро Два графика рядом: цена рынка и она же горизонтальный сп |  (через #scene-back) | 7 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-2>button.scard.quota` | button | Квоты Прямое ограничение объёма: цена не определена однозначно, а лежит в коридо |  (через #scene-back) | 7 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-2>button.scard.sd` | button | Спрос и предложение Равновесие, излишки CS и PS, общественное благосостояние. |  (через #scene-back) | 7 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-2>button.scard.sdsum` | button | Сложение спросов и предложений Горизонтальное сложение по количеству: рыночная к |  (через #scene-back) | 7 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-2>button.scard.taxes` | button | Налоги и субсидии Потоварный налог, НДС, акциз и субсидии: клин между ценами, сб |  (через #scene-back) | 7 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-3>button.scard.costs` | button | Издержки фирмы MC, ATC, AVC, AFC; точки закрытия и безубыточности, прибыль при ц |  (через #scene-back) | 4 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-3>button.scard.isoquant` | button | Изокванта и изокоста Один выпуск разными наборами L и K, касание в точке MRTS =  |  (через #scene-back) | 4 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-3>button.scard.plants` | button | Сложение заводов Горизонтальная сумма предельных издержек, условие MC₁ = MC₂. |  (через #scene-back) | 4 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-3>button.scard.prod` | button | Производственная функция TP, MP и AP от труда: точка перегиба и убывающая предел |  (через #scene-back) | 4 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-4>button.scard.mono` | button | Стандартная монополия MR = MC, монопольная цена, потери общества против конкурен |  (через #scene-back) | 5 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-4>button.scard.mono-d1` | button | Дискриминация 1-й степени Каждая единица по своей цене спроса: нулевой излишек п |  (через #scene-back) | 5 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-4>button.scard.mono-d3` | button | Дискриминация 3-й степени Два сегмента рынка, общие издержки: MR1 = MR2 = MC, це |  (через #scene-back) | 5 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-4>button.scard.mono-kink` | button | Составной спрос Спрос из двух сегментов, излом кривой и разрыв предельной выручк |  (через #scene-back) | 5 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-4>button.scard.mono-nat` | button | Естественная монополия Большие постоянные издержки, убывающая ATC, ориентиры P = |  (через #scene-back) | 5 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-4>button.scard.monopcomp` | button | Монополистическая конкуренцияСкоро Долгий период: касание спроса и ATC, нулевая  |  (через #scene-back) | 5 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-5>button.scard.labor` | button | Конкурентный рынок труда Спрос на труд как MRPL и предложение труда: оси L и W. |  (через #scene-back) | 4 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-5>button.scard.labor-bilat` | button | Двусторонняя монополия Наниматель против профсоюза: диапазон зарплат вместо един |  (через #scene-back) | 4 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-5>button.scard.labor-mono` | button | Монопсония Один наниматель: предельные издержки труда выше предложения, занятост |  (через #scene-back) | 4 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-5>button.scard.labor-union` | button | Вмешательство профсоюза Профсоюз как монополист труда или заданный пол зарплаты; |  (через #scene-back) | 4 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-6>button.scard.bigopen` | button | Большие открытые экономикиСкоро Три графика: два внутренних рынка и мировой, вст |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-6>button.scard.monoexport` | button | Монополист и внешний рынок Дома своя цена, за рубежом мировая: MR внутри = Pw =  |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-6>button.scard.smallopen` | button | Малая открытая экономика Мировая цена, импорт или экспорт, тариф и квота, потери |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-7>button.scard.cons-demand` | button | Оптимальное потребление и спросСкоро Оптимумы при разных ценах и собранная по ни |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-7>button.scard.cons-engel` | button | Кривая ЭнгеляСкоро Количество блага при разном доходе: нормальное благо и товар  |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-7>button.scard.cons-hicks` | button | Декомпозиция по ХиксуСкоро Компенсация до прежней полезности, а не до прежнего н |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-7>button.scard.cons-icc` | button | Кривая доход-потреблениеСкоро Рост дохода при прежних ценах, линия оптимумов ICC |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-7>button.scard.cons-marshall` | button | Связь кривых и маршаллианского спросаСкоро Два графика друг под другом: точка PC |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-7>button.scard.cons-pcc` | button | Кривая цена-потреблениеСкоро Поворот бюджетной линии при смене цены, линия оптим |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-7>button.scard.cons-risk` | button | Выбор в условиях неопределённости и рискСкоро Вогнутая полезность денег: надёжны |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-7>button.scard.cons-slutsky` | button | Декомпозиция по Слуцкому Три бюджетные линии: эффект замещения и эффект дохода п |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-7>button.scard.consumer` | button | Кривые безразличия Бюджетная линия, веер кривых безразличия, оптимум и MRS в нём |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-8>button.scard.adas` | button | AD–AS Совокупный спрос и предложение, потенциал LRAS, разрыв выпуска. |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-8>button.scard.cycle` | button | Деловой циклСкоро Колебания выпуска вокруг тренда: подъём, пик, спад, дно и фазы |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-8>button.scard.cycle-adas` | button | Связь делового цикла с AD–ASСкоро Фаза цикла сверху и соответствующее ей положен |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-8>button.scard.fx` | button | Валютный рынок Плавающий и фиксированный курс; интервенции при разрыве. |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-8>button.scard.islm` | button | IS–LM Товарный и денежный рынок вместе: пара (Y, r), равновесная для обоих. |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-8>button.scard.loanable` | button | Рынок заёмных средств Дефицит бюджета, рост ставки, вытеснение частных инвестици |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-8>button.scard.macrolink` | button | Связка четырёх моделейСкоро Цикл, IS–LM–BP, денежный рынок и AD–AS на одном экра |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-8>button.scard.money` | button | Денежный рынок Спрос на деньги, фиксированное предложение ЦБ, равновесная ставка |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-8>button.scard.phillips` | button | Кривая Филлипса Размен инфляции и безработицы в коротком периоде и его исчезнове |  (через #scene-back) | 6 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-9>button.scard.exchange` | button | Экономика обменаСкоро Коробка Эджворта: два участника, кривая контрактов, област |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-9>button.scard.ineq` | button | Неравенство доходов Кривая Лоренца, коэффициент Джини, коэффициент фондов, перер |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pgrid-9>button.scard.laffer` | button | Кривая Лаффера Поступления бюджета как функция ставки; строится прогоном самой м |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#picker-back` | button | Назад ко всем блокам |  (через #scene-back) | 42 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#picker-blocks>button.bcard` | button | Математика6 моделей |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#picker-blocks>button.bcard[1]` | button | КПВ и КТВ4 модели |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#picker-blocks>button.bcard[2]` | button | Совершенная конкуренция7 моделей из 8 |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#picker-blocks>button.bcard[3]` | button | Теория фирмы4 модели |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#picker-blocks>button.bcard[4]` | button | Несовершенная конкуренция5 моделей из 6 |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#picker-blocks>button.bcard[5]` | button | Рынок труда4 модели |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#picker-blocks>button.bcard[6]` | button | Международная торговля2 модели из 3 |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#picker-blocks>button.bcard[7]` | button | Выбор потребителя2 модели из 9 |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#picker-blocks>button.bcard[8]` | button | Макроэкономика6 моделей из 9 |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#picker-blocks>button.bcard[9]` | button | Избранные сюжеты2 модели из 3 |  (через #scene-back) | 2 | заменён (г) | экран выбора одним экраном (поиск, блоки, «Продолжить») | snapshot.mjs: все 44 ключа, ручная приёмка п. 1 |
| `#pl-q-field>button.param-bound` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pl-q-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pl-q-field>span.pchip-label` | exact | Совокупный выпуск $Q$. Щёлкните, чтобы ввести точное значение | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pl-q-slider` | input:range | Q=30 | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-name1-row>span.edval` | edval | Щёлкните, чтобы изменить | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[100]` | button | π | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[101]` | button | ρ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[102]` | button | σ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[103]` | button | τ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[104]` | button | φ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[105]` | button | ω | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[106]` | button | Δ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[107]` | button | Σ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[108]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[109]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[10]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[110]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[11]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[12]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[13]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[14]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[15]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[16]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[17]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[18]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[19]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[1]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[20]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[21]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[22]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[23]` | button | Стереть символ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[24]` | button | Очистить поле | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[25]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[26]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[27]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[28]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[29]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[2]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[30]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[31]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[32]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[33]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[34]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[35]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[36]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[37]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[38]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[39]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[3]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[40]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[41]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[42]` | button | КПВ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[43]` | button | a | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[44]` | button | b | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[45]` | button | c | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[46]` | button | d | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[47]` | button | e | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[48]` | button | f | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[49]` | button | g | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[4]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[50]` | button | h | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[51]` | button | i | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[52]` | button | j | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[53]` | button | k | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[54]` | button | l | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[55]` | button | m | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[56]` | button | n | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[57]` | button | o | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[58]` | button | p | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[59]` | button | q | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[5]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[60]` | button | r | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[61]` | button | s | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[62]` | button | t | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[63]` | button | u | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[64]` | button | v | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[65]` | button | w | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[66]` | button | x | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[67]` | button | y | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[68]` | button | z | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[69]` | button | A | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[6]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[70]` | button | B | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[71]` | button | C | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[72]` | button | D | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[73]` | button | E | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[74]` | button | F | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[75]` | button | G | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[76]` | button | H | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[77]` | button | I | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[78]` | button | K | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[79]` | button | L | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[7]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[80]` | button | M | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[81]` | button | N | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[82]` | button | P | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[83]` | button | Q | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[84]` | button | R | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[85]` | button | S | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[86]` | button | T | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[87]` | button | V | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[88]` | button | W | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[89]` | button | X | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[8]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[90]` | button | Y | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[91]` | button | Z | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[92]` | button | α | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[93]` | button | β | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[94]` | button | γ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[95]` | button | δ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[96]` | button | ε | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[97]` | button | θ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[98]` | button | λ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[99]` | button | μ | #sec-ppf (через #fh-ppf → #ppf-pane-single>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mk[9]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mkbd-tab` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mkbd-tab[1]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.mkbd-tab[2]` | button | КПВ | #sec-ppf (через #fh-ppf) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.swatch` | button | Цвет кривой | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-single>button.swatch[1]` | button | Цвет кривой | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-pane-sum>span.edval` | edval | Щёлкните, чтобы изменить | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-second>span.edval` | edval | Щёлкните, чтобы изменить | #sec-ppf (через #btn-ppf-compare) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppf-second>span.edval[1]` | edval | Щёлкните, чтобы изменить | #sec-ppf (через #btn-ppf-compare) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[100]` | button | π | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[101]` | button | ρ | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[102]` | button | σ | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[103]` | button | τ | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[104]` | button | φ | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[105]` | button | ω | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[106]` | button | Δ | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[107]` | button | Σ | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[108]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[109]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[10]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[110]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[11]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[12]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[13]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[14]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[15]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[16]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[17]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[18]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[19]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[1]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[20]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[21]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[22]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[23]` | button | Стереть символ | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[24]` | button | Очистить поле | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[25]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[26]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[27]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[28]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[29]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[2]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[30]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[31]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[32]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[33]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[34]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[35]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[36]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[37]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[38]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[39]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[3]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[40]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[41]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[42]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[43]` | button | a | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[44]` | button | b | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[45]` | button | c | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[46]` | button | d | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[47]` | button | e | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[48]` | button | f | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[49]` | button | g | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[4]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[50]` | button | h | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[51]` | button | i | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[52]` | button | j | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[53]` | button | k | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[54]` | button | l | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[55]` | button | m | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[56]` | button | n | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[57]` | button | o | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[58]` | button | p | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[59]` | button | q | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[5]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[60]` | button | r | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[61]` | button | s | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[62]` | button | t | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[63]` | button | u | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[64]` | button | v | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[65]` | button | w | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[66]` | button | x | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[67]` | button | y | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[68]` | button | z | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[69]` | button | A | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[6]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[70]` | button | B | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[71]` | button | C | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[72]` | button | D | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[73]` | button | E | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[74]` | button | F | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[75]` | button | G | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[76]` | button | H | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[77]` | button | I | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[78]` | button | K | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[79]` | button | L | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[7]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[80]` | button | M | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[81]` | button | N | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[82]` | button | P | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[83]` | button | Q | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[84]` | button | R | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[85]` | button | S | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[86]` | button | T | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[87]` | button | V | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[88]` | button | W | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[89]` | button | X | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[8]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[90]` | button | Y | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[91]` | button | Z | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[92]` | button | α | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[93]` | button | β | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[94]` | button | γ | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[95]` | button | δ | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[96]` | button | ε | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[97]` | button | θ | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[98]` | button | λ | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[99]` | button | μ | #sec-ppf (через #fh-auto-inp-ppfsum-0 → #ppfsum-rows>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mk[9]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mkbd-tab` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mkbd-tab[1]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.mkbd-tab[2]` | button | КПВ 1 | #sec-ppf (через #fh-auto-inp-ppfsum-0) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.swatch` | button | Цвет кривой 1 | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.swatch[1]` | button | Цвет кривой 2 | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>button.swatch[2]` | button | Цвет кривой 3 | #sec-ppf (через #inp-ppfsum-n) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>span.edval` | edval | Щёлкните, чтобы изменить | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>span.edval[1]` | edval | Щёлкните, чтобы изменить | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppfsum-rows>span.edval[2]` | edval | Щёлкните, чтобы изменить | #sec-ppf (через #inp-ppfsum-n) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppft-price-field>button.param-bound` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppft-price-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppft-price-field>span.pchip-label` | exact | Мировая цена $P_{\text{x}}$​/$P_{\text{y}}$​. Щёлкните, чтобы ввести точное значение | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#ppft-price-slider` | input:range | Pw​=2 | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-apply` | button | Поставить в поле | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-close` | button | Отмена | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-count` | input:number | Сколько кусков | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd-btn` | button | Открыть математическую клавиатуру | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button` | button | Кусочная функция | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk` | button | 7 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[10]` | button | 1 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[11]` | button | 2 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[12]` | button | 3 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[13]` | button | − | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[14]` | button | + | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[15]` | button | 0 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[16]` | button | , | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[17]` | button | = | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[18]` | button | x² | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[19]` | button | xⁿ | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[1]` | button | 8 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[20]` | button | xₙ | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[21]` | button | √ | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[22]` | button | \|x\| | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[23]` | button | Стереть символ | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[24]` | button | Очистить поле | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[2]` | button | 9 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[3]` | button | ( | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[4]` | button | ) | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[5]` | button | 4 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[6]` | button | 5 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[7]` | button | 6 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[8]` | button | × | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mk[9]` | button | ÷ | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mkbd-tab` | button | 123 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mkbd-tab[1]` | button | Функции | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-kbd>button.mkbd-tab[2]` | button | Буквы | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-kbd-btn) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-rows>input.pw-bound` | input:text | Начало участка 1 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-rows>input.pw-bound[1]` | input:text | Конец участка 1 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-rows>input.pw-bound[2]` | input:text | Начало участка 2 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-rows>input.pw-bound[3]` | input:text | Конец участка 2 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-rows>input.pw-bound[4]` | input:text | Начало участка 3 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-count) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-rows>input.pw-bound[5]` | input:text | Конец участка 3 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-count) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-rows>math-field` | math-field | Формула куска 1 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-rows>math-field[1]` | math-field | Формула куска 2 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#pw-rows>math-field[2]` | math-field | Формула куска 3 | #pw-modal (через #fh-auto-ma-sras → #macro-pane-adas>button → #pw-count) | 40 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#quota-field>button.param-bound` | bounds | Границы и шаг | #sec-tax (через #seg-quota) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#quota-field>button.param-bound[1]` | bounds | Границы и шаг | #sec-tax (через #seg-quota) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#quota-field>span.pchip-label` | exact | Квота Qк. Щёлкните, чтобы ввести точное значение | #sec-tax (через #seg-quota) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#quota-price-field>button.param-bound` | bounds | Границы и шаг | #sec-tax | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#quota-price-field>button.param-bound[1]` | bounds | Границы и шаг | #sec-tax | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#quota-price-field>span.pchip-label` | exact | Цена внутри коридора. Щёлкните, чтобы ввести точное значение | #sec-tax | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#quota-price-slider` | input:range | Pk​=50 | #sec-tax | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#quota-slider` | input:range | Квота Qк=0 | #sec-tax (через #seg-quota) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#sb-btn` | button | Ключевые значения | #scoreboard | 44 | заменён (д) | секции всегда раскрыты, колонка прокручивается | compare.mjs: органы секции видны без раскрытия |
| `#scene-back` | button | Ко всем моделям | .dock | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#sec-consumer>button.swatch` | button | Цвет кривой | #sec-consumer | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#sec-graph>button.hint-btn` | button | Как этим пользоваться | #sec-graph | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#sec-input>button.fold-btn` | button | Ввод функций | #sec-input | 44 | заменён (д) | секции всегда раскрыты, колонка прокручивается | compare.mjs: органы секции видны без раскрытия |
| `#sec-input>button.help-dot` | button | Подсказка | #sec-input | 20 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#sec-labor>button.hint-btn` | button | Как этим пользоваться | #sec-labor | 4 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#seg-ceil` | button | Потолок | #sec-tax | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#seg-floor` | button | Пол | #sec-tax | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#seg-quota` | button | Квота | #sec-tax | 2 | убран (м) |  | compare.mjs: в «Квотах» сегмента нет, квота задаётся ползунком |
| `#seg-sub` | button | Субсидия | #sec-tax | 4 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#seg-tax` | button | Налог | #sec-tax | 4 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button` | button | Кусочная функция | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk` | button | 7 | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[100]` | button | π | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[101]` | button | ρ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[102]` | button | σ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[103]` | button | τ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[104]` | button | φ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[105]` | button | ω | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[106]` | button | Δ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[107]` | button | Σ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[108]` | button | ∞ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[109]` | button | % | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[10]` | button | 1 | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[110]` | button | ≈ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[11]` | button | 2 | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[12]` | button | 3 | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[13]` | button | − | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[14]` | button | + | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[15]` | button | 0 | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[16]` | button | , | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[17]` | button | = | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[18]` | button | x² | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[19]` | button | xⁿ | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[1]` | button | 8 | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[20]` | button | xₙ | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[21]` | button | √ | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[22]` | button | \|x\| | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[23]` | button | Стереть символ | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[24]` | button | Очистить поле | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[25]` | button | √ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[26]` | button | ⁿ√ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[27]` | button | \|x\| | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[28]` | button | xⁿ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[29]` | button | eˣ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[2]` | button | 9 | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[30]` | button | ln | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[31]` | button | log | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[32]` | button | sin | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[33]` | button | cos | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[34]` | button | tan | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[35]` | button | < | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[36]` | button | > | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[37]` | button | ≤ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[38]` | button | ≥ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[39]` | button | ≠ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[3]` | button | ( | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[40]` | button | min | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[41]` | button | max | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[42]` | button | если | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[43]` | button | a | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[44]` | button | b | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[45]` | button | c | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[46]` | button | d | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[47]` | button | e | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[48]` | button | f | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[49]` | button | g | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[4]` | button | ) | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[50]` | button | h | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[51]` | button | i | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[52]` | button | j | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[53]` | button | k | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[54]` | button | l | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[55]` | button | m | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[56]` | button | n | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[57]` | button | o | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[58]` | button | p | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[59]` | button | q | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[5]` | button | 4 | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[60]` | button | r | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[61]` | button | s | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[62]` | button | t | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[63]` | button | u | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[64]` | button | v | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[65]` | button | w | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[66]` | button | x | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[67]` | button | y | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[68]` | button | z | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[69]` | button | A | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[6]` | button | 5 | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[70]` | button | B | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[71]` | button | C | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[72]` | button | D | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[73]` | button | E | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[74]` | button | F | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[75]` | button | G | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[76]` | button | H | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[77]` | button | I | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[78]` | button | K | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[79]` | button | L | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[7]` | button | 6 | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[80]` | button | M | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[81]` | button | N | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[82]` | button | P | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[83]` | button | Q | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[84]` | button | R | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[85]` | button | S | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[86]` | button | T | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[87]` | button | V | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[88]` | button | W | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[89]` | button | X | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[8]` | button | × | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[90]` | button | Y | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[91]` | button | Z | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[92]` | button | α | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[93]` | button | β | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[94]` | button | γ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[95]` | button | δ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[96]` | button | ε | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[97]` | button | θ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[98]` | button | λ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[99]` | button | μ | #sec-curves (через #fh-auto-inp-msb → #social-curves>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mk[9]` | button | ÷ | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mkbd-tab` | button | 123 | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mkbd-tab[1]` | button | Функции | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#social-curves>button.mkbd-tab[2]` | button | Буквы | #sec-curves (через #fh-auto-inp-msb) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#sum-nd` | input:number | Сколько групп спроса | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#sum-ns` | input:number | Сколько групп предложения | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#tax-field>button.param-bound` | bounds | Границы и шаг | #sec-tax | 4 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#tax-field>button.param-bound[1]` | bounds | Границы и шаг | #sec-tax | 4 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#tax-field>span.pchip-label` | exact | Ставка t. Щёлкните, чтобы ввести точное значение | #sec-tax | 4 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#tax-slider` | input:range | t=0 | #sec-tax | 4 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#taxside-row>button.tgl-sw` | switch | Продавец | #sec-tax (через #seg-sub) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#tb-price-field>button.param-bound` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#tb-price-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#tb-price-field>span.pchip-label` | exact | Мировая цена $P_{\text{w}}$​. Щёлкните, чтобы ввести точное значение | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#tb-price-slider` | input:range | Pw​=1,42 | #params-body | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#tk-exc` | button | Акциз | #sec-tax | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#tk-unit` | button | Потоварный | #sec-tax | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#tk-vat` | button | НДС | #sec-tax | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#tools-toggle` | button | Закрыть меню | #tools-panel | 44 | заменён (в) | «Развернуть график» в панели холста | compare.mjs: шаг «Развернуть график» |
| `#trade-pane-a>button` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[100]` | button | π | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[101]` | button | ρ | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[102]` | button | σ | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[103]` | button | τ | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[104]` | button | φ | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[105]` | button | ω | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[106]` | button | Δ | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[107]` | button | Σ | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[108]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[109]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[10]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[110]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[11]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[12]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[13]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[14]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[15]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[16]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[17]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[18]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[19]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[1]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[20]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[21]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[22]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[23]` | button | Стереть символ | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[24]` | button | Очистить поле | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[25]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[26]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[27]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[28]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[29]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[2]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[30]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[31]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[32]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[33]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[34]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[35]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[36]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[37]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[38]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[39]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[3]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[40]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[41]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[42]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[43]` | button | a | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[44]` | button | b | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[45]` | button | c | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[46]` | button | d | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[47]` | button | e | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[48]` | button | f | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[49]` | button | g | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[4]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[50]` | button | h | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[51]` | button | i | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[52]` | button | j | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[53]` | button | k | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[54]` | button | l | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[55]` | button | m | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[56]` | button | n | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[57]` | button | o | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[58]` | button | p | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[59]` | button | q | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[5]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[60]` | button | r | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[61]` | button | s | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[62]` | button | t | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[63]` | button | u | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[64]` | button | v | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[65]` | button | w | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[66]` | button | x | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[67]` | button | y | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[68]` | button | z | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[69]` | button | A | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[6]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[70]` | button | B | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[71]` | button | C | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[72]` | button | D | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[73]` | button | E | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[74]` | button | F | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[75]` | button | G | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[76]` | button | H | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[77]` | button | I | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[78]` | button | K | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[79]` | button | L | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[7]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[80]` | button | M | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[81]` | button | N | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[82]` | button | P | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[83]` | button | Q | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[84]` | button | R | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[85]` | button | S | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[86]` | button | T | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[87]` | button | V | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[88]` | button | W | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[89]` | button | X | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[8]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[90]` | button | Y | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[91]` | button | Z | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[92]` | button | α | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[93]` | button | β | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[94]` | button | γ | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[95]` | button | δ | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[96]` | button | ε | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[97]` | button | θ | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[98]` | button | λ | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[99]` | button | μ | #sec-ppf (через #fh-auto-inp-ppft → #trade-pane-a>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mk[9]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mkbd-tab` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mkbd-tab[1]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-a>button.mkbd-tab[2]` | button | КПВ страны: Y = f(X) | #sec-ppf (через #fh-auto-inp-ppft) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[100]` | button | π | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[101]` | button | ρ | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[102]` | button | σ | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[103]` | button | τ | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[104]` | button | φ | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[105]` | button | ω | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[106]` | button | Δ | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[107]` | button | Σ | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[108]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[109]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[10]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[110]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[11]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[12]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[13]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[14]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[15]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[16]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[17]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[18]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[19]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[1]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[20]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[21]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[22]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[23]` | button | Стереть символ | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[24]` | button | Очистить поле | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[25]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[26]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[27]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[28]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[29]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[2]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[30]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[31]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[32]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[33]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[34]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[35]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[36]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[37]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[38]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[39]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[3]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[40]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[41]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[42]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[1]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[43]` | button | a | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[44]` | button | b | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[45]` | button | c | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[46]` | button | d | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[47]` | button | e | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[48]` | button | f | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[49]` | button | g | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[4]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[50]` | button | h | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[51]` | button | i | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[52]` | button | j | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[53]` | button | k | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[54]` | button | l | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[55]` | button | m | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[56]` | button | n | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[57]` | button | o | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[58]` | button | p | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[59]` | button | q | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[5]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[60]` | button | r | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[61]` | button | s | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[62]` | button | t | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[63]` | button | u | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[64]` | button | v | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[65]` | button | w | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[66]` | button | x | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[67]` | button | y | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[68]` | button | z | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[69]` | button | A | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[6]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[70]` | button | B | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[71]` | button | C | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[72]` | button | D | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[73]` | button | E | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[74]` | button | F | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[75]` | button | G | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[76]` | button | H | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[77]` | button | I | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[78]` | button | K | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[79]` | button | L | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[7]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[80]` | button | M | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[81]` | button | N | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[82]` | button | P | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[83]` | button | Q | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[84]` | button | R | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[85]` | button | S | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[86]` | button | T | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[87]` | button | V | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[88]` | button | W | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[89]` | button | X | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[8]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[90]` | button | Y | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[91]` | button | Z | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[92]` | button | α | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[93]` | button | β | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[94]` | button | γ | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[95]` | button | δ | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[96]` | button | ε | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[97]` | button | θ | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[98]` | button | λ | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[99]` | button | μ | #sec-ppf (через #fh-auto-inp-tb1 → #trade-pane-b>button.mkbd-tab[2]) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mk[9]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mkbd-tab` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mkbd-tab[1]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#trade-pane-b>button.mkbd-tab[2]` | button | КПВ страны 1: Y = f₁(X) | #sec-ppf (через #fh-auto-inp-tb1) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#union-pane>button.tgl-sw` | switch | Монопсония | #sec-labor | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#union-wage-field>button.param-bound` | bounds | Границы и шаг | #params-body (через #union-pane>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#union-wage-field>button.param-bound[1]` | bounds | Границы и шаг | #params-body (через #union-pane>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#union-wage-field>span.pchip-label` | exact | Зарплата профсоюза $W$. Щёлкните, чтобы ввести точное значение | #params-body (через #union-pane>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `#union-wage-slider` | input:range | Wu​=65 | #params-body (через #union-pane>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.cpick-sw` | button | #c74440 |  (через #btn-wrench → #gtitle-color-slot>button.swatch) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.cpick-sw~1` | button | #2d70b3 |  (через #btn-wrench → #gtitle-color-slot>button.swatch) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.cpick-sw~2` | button | #348543 |  (через #btn-wrench → #gtitle-color-slot>button.swatch) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.cpick-sw~3` | button | #fa7e19 |  (через #btn-wrench → #gtitle-color-slot>button.swatch) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.cpick-sw~4` | button | #6042a6 |  (через #btn-wrench → #gtitle-color-slot>button.swatch) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.cpick-sw~5` | button | #000000 |  (через #btn-wrench → #gtitle-color-slot>button.swatch) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.sel-item` | button | Выберите кривую |  (через #ac-pane-curve>button.sel-btn) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.sel-item~1` | button | AD\mathrm{AD}AD |  (через #ac-pane-curve>button.sel-btn) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.sel-item~2` | button | SRAS\mathrm{SRAS}SRAS |  (через #ac-pane-curve>button.sel-btn) | 32 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.sel-item~3` | button | бюджет: новый |  (через #ac-pane-curve>button.sel-btn) | 6 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.sel-item~4` | button | UUU исходная |  (через #ac-pane-curve>button.sel-btn) | 4 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.sel-item~5` | button | UUU новая |  (через #ac-pane-curve>button.sel-btn) | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.sel-item~6` | button | \|f(x)\| |  (через #math-pane-transform>button.sel-btn) | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>button.sel-item~7` | button | f(\|x\|) |  (через #math-pane-transform>button.sel-btn) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `>input` | input:color | Свой цвет |  (через #btn-wrench → #gtitle-color-slot>button.swatch) | 44 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#curve-expr-1` | math-field | Формула кривой: правится на месте | #sec-curves | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#curve-expr-2` | math-field | Формула кривой: правится на месте | #sec-curves | 17 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#curve-expr-3` | math-field | Формула | #sec-curves (через #btn-add-curve) | 16 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#curve-expr-4` | math-field | Формула кривой: правится на месте | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#curve-expr-5` | math-field | Формула кривой: правится на месте | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#curve-expr-7` | math-field | Формула | #sec-curves (через #sum-nd) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#graph-f-1` | math-field | Формула функции | #sec-graph | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#graph-f-2` | math-field | Формула функции | #sec-graph | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#graph-f-3` | math-field | Формула функции | #sec-graph (через #btn-scene-reset) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#graph-f-4` | math-field | Формула функции | #sec-graph (через #btn-scene-reset) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#graph-f-5` | math-field | Формула функции | #sec-graph (через #btn-scene-reset → mf:#graph-f-4) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#ineq-formula` | math-field | Формула | #sec-inequality (через #ineq-in-formula) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-catc` | math-field | Формула | #sec-costs (через #costs-pane-costs>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-cavc` | math-field | Формула | #sec-costs (через #costs-pane-costs>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-cmc` | math-field | Формула | #sec-costs (через #costs-pane-costs>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-d3-1` | math-field | Формула | #sec-mono | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-d3-2` | math-field | Формула | #sec-mono | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-d3-mc` | math-field | Формула | #sec-mono | 2 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-iso` | math-field | Формула | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-ki-1` | math-field | Формула | #sec-mono | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-ki-2` | math-field | Формула | #sec-mono | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-ki-3` | math-field | Формула | #sec-mono | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-kink-mc` | math-field | Формула | #sec-mono | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-kp-1` | math-field | Формула | #sec-mono (через #mono-kink-pane>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-kp-2` | math-field | Формула | #sec-mono (через #mono-kink-pane>button.tgl-sw) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-mathf` | math-field | Формула | #sec-math | 3 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-mathfc` | math-field | Формула | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-mathgc` | math-field | Формула | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-msb` | math-field | Формула | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-msc` | math-field | Формула | #sec-curves | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-pl1` | math-field | Формула | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-pl2` | math-field | Формула | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-ppf` | math-field | Формула | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-ppfsum-0` | math-field | Формула | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-ppfsum-1` | math-field | Формула | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-ppfsum-2` | math-field | Формула | #sec-ppf (через #inp-ppfsum-n) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-ppft` | math-field | Формула | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-prod` | math-field | Формула | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-tb1` | math-field | Формула | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-tb2` | math-field | Формула | #sec-ppf | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#inp-tc` | math-field | Формула | #sec-costs | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#ma-ad` | math-field | Формула | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#ma-fxd` | math-field | Формула | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#ma-fxs` | math-field | Формула | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#ma-is` | math-field | Формула | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#ma-lafd` | math-field | Формула | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#ma-lafs` | math-field | Формула | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#ma-ld` | math-field | Формула | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#ma-lm` | math-field | Формула | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#ma-ls` | math-field | Формула | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#ma-md` | math-field | Формула | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#ma-sras` | math-field | Формула | #sec-macro | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#mm-f0` | math-field | Функция f₁ | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#mm-f1` | math-field | Функция f₂ | #sec-math | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |
| `mf:#mm-f2` | math-field | Функция f₃ | #sec-math (через #mm-count) | 1 | на месте |  | snapshot.mjs (layer new) + compare.mjs |

## 2. Ответ: строки табло, пояснения, разборы (стартовое состояние)

| Модель | Блок | № | Подпись | Значение | Судьба | Место на новом экране | Чем проверено |
|---|---|---|---|---|---|---|---|
| adas | info-macro | 0 | Краткосрочно: (Y; P) | (100;60) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| adas | info-macro | 1 | Потенциальный выпуск Y∗ | 100 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| adas | info-macro | 2 | Разрыв выпуска | 0 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| adas | info-macro | n0 | пояснение | Экономика ровно на потенциале: краткосрочное равновесие совп | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| adas | #ex-body | p0 | абзац разбора | Что по осям в этой модели? Совокупный выпуск и общий уровень | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| adas | #ex-body | p1 | абзац разбора | Почему AD убывает? При более высоком уровне цен реальные зап | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| adas | #ex-body | p2 | абзац разбора | Что такое разрыв выпуска? Отклонение фактического выпуска от | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| adas | #ex-body | p3 | абзац разбора | Чем короткий период отличается от длинного? В коротком цены  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| adas | #ex-body | p4 | абзац разбора | Вывод: В долгом периоде выпуск возвращается к потенциальному | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ceil | sec-eq | 0 | Pc​ (потолок цены) | 30 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ceil | sec-eq | 1 | Qd​ (величина спроса) | 70 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ceil | sec-eq | 2 | Qs​ (величина предложения) | 30 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ceil | sec-eq | 3 | Дефицит | 40 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ceil | sec-eq | 4 | DWL (потери общества) | 400 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ceil | sec-eq | n0 | пояснение | Цену назначило государство, поэтому равновесия нет: по цене  | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| ceil | info-areas | 0 | CS (потребитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ceil | info-areas | 1 | PS (производитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ceil | info-areas | 2 | SW=CS+PS | 2500 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ceil | info-areas | n0 | пояснение | до вмешательства государства | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| ceil | info-tax | 0 | Потолок Pc​ | 30 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ceil | info-tax | 1 | Дефицит | 40 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ceil | info-tax | t | таблица (1) |  | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ceil | #sec-eq | title | заголовок группы | Рынок при потолке цены | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| ceil | #ex-body | p0 | абзац разбора | Потолок цены это верхняя граница: продавать дороже нельзя. П | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ceil | #ex-body | p1 | абзац разбора | Что такое потолок и пол цены? Потолок это запрет продавать д | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ceil | #ex-body | p2 | абзац разбора | Почему возникает дефицит или излишек? При потолке ниже равно | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ceil | #ex-body | p3 | абзац разбора | Кто выигрывает и кто теряет? Часть излишка переходит от одно | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ceil | #ex-body | p4 | абзац разбора | Вывод: Ограничение цены перераспределяет выигрыш и одновреме | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| cons-slutsky | info-consumer | 0 | Оптимум (x∗;y∗) | (50;25) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| cons-slutsky | info-consumer | 1 | Полезность U | 35,36 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| cons-slutsky | info-consumer | 2 | MRS в оптимуме | 0,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| cons-slutsky | info-consumer | 3 | Py​Px​​ | 0,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| cons-slutsky | info-consumer | 4 | Перехваты I/Px​, I/Py​ | 100;50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| cons-slutsky | info-consumer | 5 | A: старый выбор (Px​=1) | 50/25 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| cons-slutsky | info-consumer | 6 | B: компенсированный (I′=250) | 31,25/62,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| cons-slutsky | info-consumer | 7 | C: новый выбор (Px​=4) | 12,5/25 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| cons-slutsky | info-consumer | t | таблица (1) |  | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| cons-slutsky | info-consumer | n0 | пояснение | Компенсированный доход по Слуцкому I′=Px1​​x0​+Py​y0​=250: с | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| cons-slutsky | #ex-body | p0 | абзац разбора | Зачем раскладывать изменение спроса? Когда цена меняется, пр | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| cons-slutsky | #ex-body | p1 | абзац разбора | Что такое эффект замещения? Реакция на изменение относительн | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| cons-slutsky | #ex-body | p2 | абзац разбора | Что такое эффект дохода? Реакция на изменение реального дохо | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| cons-slutsky | #ex-body | p3 | абзац разбора | Зачем вообще делить эффект на два? Затем, что они могут тяну | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| cons-slutsky | #ex-body | p4 | абзац разбора | Вывод: Итоговое изменение это сумма двух эффектов. По Слуцко | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| consumer | info-consumer | 0 | Оптимум (x∗;y∗) | (50;25) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| consumer | info-consumer | 1 | Полезность U | 35,36 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| consumer | info-consumer | 2 | MRS в оптимуме | 0,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| consumer | info-consumer | 3 | Py​Px​​ | 0,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| consumer | info-consumer | 4 | Перехваты I/Px​, I/Py​ | 100;50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| consumer | #ex-body | p0 | абзац разбора | Что такое кривая безразличия? Набор корзин, между которыми ч | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| consumer | #ex-body | p1 | абзац разбора | Что такое бюджетная линия? Граница доступного: Px​x+Py​y=I.  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| consumer | #ex-body | p2 | абзац разбора | Почему оптимум это касание? В точке касания личная готовност | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| consumer | #ex-body | p3 | абзац разбора | Что будет, если предпочтения не обычные? У совершенных замен | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| consumer | #ex-body | p4 | абзац разбора | Вывод: Условие оптимума MRS=Px​/Py​ и есть смысл всей картин | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| costs | info-costs | 0 | Постоянные затраты FC=TC(0) | 18 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| costs | info-costs | 1 | Безубыточность (min ATC) | Q = 3,67, ATC = 11,35 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| costs | info-costs | 2 | Закрытие (min AVC) | Q = 3, AVC = 6 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| costs | info-costs | 3 | Цена P | 15 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| costs | info-costs | 4 | Выпуск Q (P = MC) | 4 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| costs | info-costs | 5 | ATC(Q) | 11,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| costs | info-costs | 6 | Прибыль (P − ATC)·Q | 14 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| costs | info-costs | 7 | Вход/выход: P = min ATC | 11,35 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| costs | info-costs | n0 | пояснение | В точках закрытия и безубыточности MC пересекает соответстве | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| costs | info-costs | n1 | пояснение | Прибыль положительна, поэтому в долгом периоде в отрасль вхо | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| costs | #ex-body | p0 | абзац разбора | Откуда берутся все эти кривые? Из одной функции общих издерж | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| costs | #ex-body | p1 | абзац разбора | Почему MC пересекает ATC ровно в её минимуме? Пока последняя | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| costs | #ex-body | p2 | абзац разбора | Что решает фирма по этим кривым? Сколько выпускать: при сове | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| costs | #ex-body | p3 | абзац разбора | Почему средние постоянные издержки нигде не пересекаются с о | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| costs | #ex-body | p4 | абзац разбора | Вывод: Форма кривых не произвольна: она целиком следует из T | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| elast | sec-eq | 0 | Q∗ (количество) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | sec-eq | 1 | P∗ (цена) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-areas | 0 | CS (потребитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-areas | 1 | PS (производитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-areas | 2 | SW=CS+PS | 2500 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-elast | 0 | Точка спроса (Q, P) | 50;50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-elast | 1 | ∣Ed​∣ | 1 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-elast | 2 | Зона спроса | единичная, ∣Ed​∣=1 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-elast | 3 | Выручка TR = P·Q | 2500 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-elast | 4 | Единичная точка | Q = 50, P = 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-elast | 5 | Макс выручка TR | 2500 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-elast | 6 | Точка предложения (Q, P) | 65;65 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-elast | 7 | ∣Es​∣ | 1 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-elast | 8 | Зона предложения | единичная, ∣Es​∣=1 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| elast | info-elast | n0 | пояснение | Единичная эластичность: выручка в максимуме, малое изменение | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| elast | info-elast | n1 | пояснение | Прямое предложение через начало координат даёт \|Es\| = 1 в лю | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| elast | #sec-eq | title | заголовок группы | Равновесие D=S | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| elast | #ex-body | p0 | абзац разбора | Что измеряет эластичность? На сколько процентов изменится ко | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| elast | #ex-body | p1 | абзац разбора | Почему эластичность разная в разных точках одной прямой? Нак | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| elast | #ex-body | p2 | абзац разбора | Как эластичность связана с выручкой? Если спрос эластичен (∣ | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| elast | #ex-body | p3 | абзац разбора | Вывод: Продавцу важна не сама эластичность, а то, по какую с | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ext | sec-eq | 0 | Q∗ (количество) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ext | sec-eq | 1 | P∗ (цена) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ext | info-areas | 0 | CS (потребитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ext | info-areas | 1 | PS (производитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ext | info-areas | 2 | SW=CS+PS | 2500 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ext | info-ext | 0 | Рынок (D = S) | Q = 50, P = 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ext | info-ext | 1 | Оптимум (MSB = MSC) | Q = 50, P = 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ext | info-ext | 2 | DWL (потери) | 0 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ext | info-ext | n0 | пояснение | MSB и MSC пока совпадают с частными кривыми: внешнего эффект | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| ext | #sec-eq | title | заголовок группы | Равновесие D=S | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| ext | #ex-body | p0 | абзац разбора | Что такое внешний эффект? Это выгода или издержка, которая д | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ext | #ex-body | p1 | абзац разбора | Почему рынок ошибается с объёмом? Частная кривая учитывает т | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ext | #ex-body | p2 | абзац разбора | Как это лечится? Налогом Пигу при вреде и субсидией при поль | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ext | #ex-body | p3 | абзац разбора | Как отличить внешний эффект от обычных издержек? Проверьте,  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ext | #ex-body | p4 | абзац разбора | Вывод: Задача вмешательства здесь не «наказать», а показать  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| fx | info-macro | 0 | Плавающий курс e | 16 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| fx | info-macro | 1 | Объём при плавающем | 68 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| fx | info-macro | n0 | пояснение | Включите фиксированный курс, чтобы увидеть дефицит или избыт | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| fx | #ex-body | p0 | абзац разбора | Чем торгуют на валютном рынке? Национальной валютой. Спрос н | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| fx | #ex-body | p1 | абзац разбора | Что такое плавающий курс? Курс, который сам приходит к перес | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| fx | #ex-body | p2 | абзац разбора | Что происходит при фиксированном курсе? Если центральный бан | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| fx | #ex-body | p3 | абзац разбора | Кто создаёт спрос на валюту, а кто предложение? Спрос на ино | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| fx | #ex-body | p4 | абзац разбора | Вывод: Фиксированный курс это то же ценовое ограничение, что | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ineq | info-inequality | 0 | Коэффициент Джини | 0,3 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ineq | info-inequality | 1 | Робин Гуда (Гувера) | 0,24 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ineq | info-inequality | 2 | Коэф. фондов (децильный) | 5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ineq | info-inequality | 3 | Квинтильный коэф. фондов | 5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ineq | info-inequality | n0 | пояснение | Показан коэффициент фондов: отношение суммарного дохода верх | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| ineq | info-inequality | n1 | пояснение | Джини: 0 значит полное равенство, 1 значит весь доход у одно | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| ineq | #ex-body | p0 | абзац разбора | Что показывает кривая Лоренца? Какая доля общего дохода дост | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ineq | #ex-body | p1 | абзац разбора | Что такое коэффициент Джини? Отношение площади между диагона | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ineq | #ex-body | p2 | абзац разбора | Чем отличается коэффициент фондов? Он сравнивает СУММЫ доход | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ineq | #ex-body | p3 | абзац разбора | Как читать кривую Лоренца? По горизонтали идут люди, отсорти | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ineq | #ex-body | p4 | абзац разбора | Вывод: Один индекс не описывает неравенство целиком: две раз | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| islm | info-macro | 0 | Равновесный выпуск Y | 166,67 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| islm | info-macro | 1 | Равновесная ставка r | 3,33 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| islm | info-macro | n0 | пояснение | IS это сочетания Y и r, при которых равновесен товарный рыно | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| islm | #ex-body | p0 | абзац разбора | Что описывают эти две линии? IS показывает сочетания ставки  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| islm | #ex-body | p1 | абзац разбора | Почему IS убывает? Ниже ставка, значит дешевле кредит, значи | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| islm | #ex-body | p2 | абзац разбора | Почему LM растёт? Больше выпуск, значит больше сделок и выше | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| islm | #ex-body | p3 | абзац разбора | Что двигает каждую из кривых? IS двигают всё, что меняет рас | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| islm | #ex-body | p4 | абзац разбора | Вывод: Фискальная политика двигает IS, монетарная LM. Пересе | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| isoquant | info-iso | 0 | Оптимум (L∗;K∗) | (50;25) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| isoquant | info-iso | 1 | Выпуск Q | 35,36 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| isoquant | info-iso | 2 | MRTS в оптимуме | 0,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| isoquant | info-iso | 3 | rw​ | 0,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| isoquant | info-iso | 4 | Потрачено | 100 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| isoquant | info-iso | n0 | пояснение | Условие оптимума то же, что у потребителя, только вместо пол | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| isoquant | #ex-body | p0 | абзац разбора | Откуда берутся все эти кривые? Из одной функции общих издерж | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| isoquant | #ex-body | p1 | абзац разбора | Почему MC пересекает ATC ровно в её минимуме? Пока последняя | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| isoquant | #ex-body | p2 | абзац разбора | Что решает фирма по этим кривым? Сколько выпускать: при сове | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| isoquant | #ex-body | p3 | абзац разбора | Почему средние постоянные издержки нигде не пересекаются с о | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| isoquant | #ex-body | p4 | абзац разбора | Вывод: Форма кривых не произвольна: она целиком следует из T | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-bilat | info-labor | 0 | Нижняя граница Wм (монопсония) | 33,33 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-bilat | info-labor | 1 | Верхняя граница Wп (профсоюз) | 66,67 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-bilat | info-labor | 2 | Диапазон зарплаты | 33,33…66,67 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-bilat | info-labor | 3 | Конкурентный ориентир Wk | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-bilat | info-labor | 4 | Занятость на границах | 33,33 и 33,33 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-bilat | info-labor | n0 | пояснение | Один наниматель против одного профсоюза. У этой модели нет е | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| labor-bilat | #ex-body | p0 | абзац разбора | Что такое двусторонняя монополия? Один покупатель труда прот | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-bilat | #ex-body | p1 | абзац разбора | Почему модель не даёт одного числа? Монопсонист тянет ставку | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-bilat | #ex-body | p2 | абзац разбора | От чего зависит итог внутри диапазона? От переговорной силы  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-bilat | #ex-body | p3 | абзац разбора | Как тогда решать такую задачу? Считают обе границы: ставку,  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-bilat | #ex-body | p4 | абзац разбора | Вывод: Честный ответ здесь это интервал, а не точка. Выдумыв | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | 0 | Lм​ (занятость) | 33,33 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | 1 | Wм​ (зарплата) | 33,33 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | 2 | Lk​ (конкуренция) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | 3 | Wk​ (конкуренция) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | 4 | DWL (недозанятость) | 277,78 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | 5 | МРОТ W_min | 65 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | 6 | Занятость с МРОТ | 35 (было 33,33) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | 7 | Зарплата | 65 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | 8 | Безработица | 30 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | 9 | Излишек рабочих | 1662,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | 10 | Излишек фирм | 612,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | 11 | DWL (потери) | 225 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | n0 | пояснение | Монопсония занижает и занятость, и зарплату против конкуренц | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| labor-mono | info-labor | n1 | пояснение | МРОТ увеличил занятость (парадокс монопсонии). | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| labor-mono | #ex-body | p0 | абзац разбора | Что такое монопсония? Рынок с единственным покупателем труда | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-mono | #ex-body | p1 | абзац разбора | Как монопсонист выбирает занятость? По правилу «предельная в | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-mono | #ex-body | p2 | абзац разбора | Почему занятость меньше конкурентной? Наниматель учитывает,  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-mono | #ex-body | p3 | абзац разбора | Почему минимальная зарплата здесь помогает? Она отнимает у м | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-mono | #ex-body | p4 | абзац разбора | Вывод: Монопсония занижает и зарплату, и занятость одновреме | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-union | info-labor | 0 | Lп​ (занятость) | 33,33 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-union | info-labor | 1 | Wп​ (зарплата) | 66,67 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-union | info-labor | 2 | Lk​ (конкуренция) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-union | info-labor | 3 | Wk​ (конкуренция) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-union | info-labor | 4 | DWL (недозанятость) | 277,78 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor-union | info-labor | n0 | пояснение | Профсоюз-монополист продаёт труд там, где MRL = S, и берёт з | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| labor-union | #ex-body | p0 | абзац разбора | Что делает профсоюз? Ставит нижнюю границу зарплаты. Это тот | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-union | #ex-body | p1 | абзац разбора | Почему появляется безработица? При ставке выше равновесной ж | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-union | #ex-body | p2 | абзац разбора | Кто выигрывает? Те, кто сохранил место: их зарплата выросла. | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-union | #ex-body | p3 | абзац разбора | Что выбирает сам профсоюз? Это зависит от цели. Максимум общ | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-union | #ex-body | p4 | абзац разбора | Чем это отличается от минимальной зарплаты? Геометрия одна и | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor-union | #ex-body | p5 | абзац разбора | Вывод: Итог зависит от того, насколько круто идёт спрос на т | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor | info-labor | 0 | Lk​ (занятость) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor | info-labor | 1 | Wk​ (зарплата) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor | info-labor | 2 | Излишек рабочих | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor | info-labor | 3 | Излишек фирм | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor | info-labor | 4 | МРОТ W_min | 65 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor | info-labor | 5 | Занятость | 35 (было 50) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor | info-labor | 6 | Безработица | 30 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor | info-labor | 7 | Излишек рабочих | 1662,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor | info-labor | 8 | Излишек фирм | 612,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor | info-labor | 9 | DWL (потери) | 225 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| labor | info-labor | n0 | пояснение | МРОТ выше равновесия: занятость падает до спроса при W_min,  | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| labor | #ex-body | p0 | абзац разбора | Кто здесь покупатель, а кто продавец? Труд покупают фирмы, п | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor | #ex-body | p1 | абзац разбора | Почему спрос на труд это предельный продукт в деньгах? Фирма | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor | #ex-body | p2 | абзац разбора | Что задаёт равновесную зарплату? Пересечение: при более высо | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor | #ex-body | p3 | абзац разбора | Что двигает спрос на труд? Всё, что меняет MRP=MP⋅P: цена пр | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| labor | #ex-body | p4 | абзац разбора | Вывод: Рынок труда устроен как обычный рынок, просто стороны | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| laffer | info-macro | 0 | Ставка максимума t | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| laffer | info-macro | 1 | Максимальные поступления | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| laffer | info-macro | 2 | Объём рынка при ней | 25 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| laffer | info-macro | n0 | пояснение | Кривая построена НЕ отдельной формулой: для каждой ставки пр | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| laffer | #ex-body | p0 | абзац разбора | Что показывает кривая Лаффера? Как сбор бюджета зависит от с | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| laffer | #ex-body | p1 | абзац разбора | Почему у кривой есть вершина? Сбор это ставка, умноженная на | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| laffer | #ex-body | p2 | абзац разбора | Как построен этот график? Не отдельной формулой: тот же расч | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| laffer | #ex-body | p3 | абзац разбора | Почему кривая заворачивается вниз? Сбор это ставка, умноженн | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| laffer | #ex-body | p4 | абзац разбора | Вывод: Из существования вершины НЕ следует, что мы правее не | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| loanable | info-macro | 0 | База: (r; объём) | (20;90) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| loanable | info-macro | n0 | пояснение | Задайте дефицит бюджета ΔG, чтобы увидеть эффект вытеснения. | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| loanable | #ex-body | p0 | абзац разбора | Что продаётся на этом рынке? Заёмные средства. Предложение э | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| loanable | #ex-body | p1 | абзац разбора | Как государство влияет на ставку? Занимая на том же рынке, о | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| loanable | #ex-body | p2 | абзац разбора | Что такое вытеснение? Часть частных инвестиций не состоится  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| loanable | #ex-body | p3 | абзац разбора | Что здесь вытесняется и чем? Государство, заняв на этом же р | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| loanable | #ex-body | p4 | абзац разбора | Вывод: Государственные расходы не появляются из ниоткуда: пр | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-constraint | info-math | 0 | x∗ | 5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-constraint | info-math | 1 | y∗ | 5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-constraint | info-math | 2 | f(x∗,,y∗) | 5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-constraint | #ex-body | p0 | абзац разбора | Что такое ограничение на графике? Это кривая: точки, где g(x | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-constraint | #ex-body | p1 | абзац разбора | Как ищется оптимум? Вдоль этой кривой перебирается значение  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-constraint | #ex-body | p2 | абзац разбора | Почему именно касание? Линия уровня касается ограничения, а  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-constraint | #ex-body | p3 | абзац разбора | Почему это одна и та же задача во всей микроэкономике? Потре | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-constraint | #ex-body | p4 | абзац разбора | Когда касания не будет? Когда оптимум упирается в угол: у со | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-constraint | #ex-body | p5 | абзац разбора | Вывод. Сначала проверяют, есть ли внутреннее решение по каса | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-graph | info-graph | 0 | Кривая | f | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-graph | info-graph | 1 | Пересекает ось x | −2;2 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-graph | info-graph | 2 | Пересекает ось y | −4 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-graph | info-graph | 3 | Вершины | (0;−4) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-graph | #ex-body | p0 | абзац разбора | Что такое график функции? Это множество точек, у которых вто | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-graph | #ex-body | p1 | абзац разбора | Зачем нужны нули функции? Ноль это высота оси x. Значит корн | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-graph | #ex-body | p2 | абзац разбора | Откуда берутся вершины? В вершине кривая перестаёт расти и н | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-graph | #ex-body | p3 | абзац разбора | Почему точка пересечения двух кривых важнее остальных? В ней | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-graph | #ex-body | p4 | абзац разбора | Вывод. График переводит формулу в картинку, а вопросы про ур | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-minmax | info-math | 0 | Строим | Z = min(f₁, f₂) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-minmax | info-math | 1 | Функций участвует | 2 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-minmax | info-math | 2 | Кривые меняются местами | −2,56;1,56 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-minmax | #ex-body | p0 | абзац разбора | Как строится итоговая кривая? В каждой точке x берётся наиме | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-minmax | #ex-body | p1 | абзац разбора | Откуда берутся изломы? Точки перелома это корни разности пар | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-minmax | #ex-body | p2 | абзац разбора | Экономический смысл тот же у нижней огибающей средних издерж | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-minmax | #ex-body | p3 | абзац разбора | Где ещё встречается такая огибающая? В спросе на билеты с дв | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-minmax | #ex-body | p4 | абзац разбора | Вывод. Изломы на такой кривой это не дефект и не ошибка счёт | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-optimum | info-math | 0 | Наибольшее на отрезке | y∗=18 при x∗=3 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-optimum | info-math | 1 | Наименьшее на отрезке | y∗=−18 при x∗=−3 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-optimum | info-math | 2 | Локальный максимум | (x∗;y∗)=(−1;2) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-optimum | info-math | 3 | Локальный минимум | (x∗;y∗)=(1;−2) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-optimum | info-math | 4 | Перегиб | (x∗;y∗)=(0;0) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-optimum | #ex-body | p0 | абзац разбора | По чему ищутся экстремумы? Экстремум там, где касательная го | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-optimum | #ex-body | p1 | абзац разбора | x∗=−1: здесь f′=0, а f′′=−6, то есть меньше нуля. Значит, ма | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-optimum | #ex-body | p2 | абзац разбора | x∗=1: здесь f′=0, а f′′=6, то есть больше нуля. Значит, мини | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-optimum | #ex-body | p3 | абзац разбора | Перегиб это смена знака второй производной f′′: до него крив | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-optimum | #ex-body | p4 | абзац разбора | Найдено: x∗=0. | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-optimum | #ex-body | p5 | абзац разбора | Наибольшее и наименьшее на отрезке берутся не только по этим | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-optimum | #ex-body | p6 | абзац разбора | Зачем экономисту вторая производная? Она отличает максимум о | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-optimum | #ex-body | p7 | абзац разбора | Вывод. Порядок один и тот же в любой задаче на оптимум: найт | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-tangent | info-math | 0 | Точка x0​ | 1 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-tangent | info-math | 1 | f(x0​) | 1 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-tangent | info-math | 2 | Наклон касательной f′(x0​) | 2 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-tangent | info-math | 3 | Угол наклона | 63,43textcirc | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-tangent | info-math | 4 | Касательная | y = 1 + 2·(x - 1) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-tangent | #ex-body | p0 | абзац разбора | Что вообще такое производная? Это скорость: на сколько меняе | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-tangent | #ex-body | p1 | абзац разбора | При чём здесь треугольник? Он и есть это отношение: горизонт | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-tangent | #ex-body | p2 | абзац разбора | Включите секущую, и будет видно, как при уменьшении Δx она л | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-tangent | #ex-body | p3 | абзац разбора | Внизу нарисована f′(x) целиком: там, где она выше нуля, функ | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-tangent | #ex-body | p4 | абзац разбора | Где это встречается в экономике? Почти везде, где есть слово | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-tangent | #ex-body | p5 | абзац разбора | Вывод. Наклон касательной, скорость изменения и предельная в | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-transform | info-math | 0 | Преобразование | f(x) + a | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-transform | info-math | 1 | Параметр a | 1 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| m-transform | info-math | n0 | пояснение | Плюс a поднимает график, минус опускает. | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| m-transform | #ex-body | p0 | абзац разбора | Что вообще делает преобразование? Оно не меняет саму функцию | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-transform | #ex-body | p1 | абзац разбора | Почему сдвиг по горизонтали работает наоборот? В записи f(x+ | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-transform | #ex-body | p2 | абзац разбора | Чем растяжение отличается от сдвига? Сдвиг двигает всю криву | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-transform | #ex-body | p3 | абзац разбора | Зачем это экономисту? Почти все сдвиги кривых в экономике эт | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| m-transform | #ex-body | p4 | абзац разбора | Вывод. Прибавление снаружи двигает вверх, прибавление внутри | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| money | info-macro | 0 | Предложение денег Ms | 120 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| money | info-macro | 1 | Равновесная ставка i | 20 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| money | info-macro | n0 | пояснение | Предложение денег задаёт ЦБ, оно не зависит от ставки и поэт | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| money | #ex-body | p0 | абзац разбора | Что такое спрос на деньги? Желание держать богатство именно  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| money | #ex-body | p1 | абзац разбора | Почему предложение денег вертикально? Его задаёт центральный | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| money | #ex-body | p2 | абзац разбора | Что уравновешивает рынок? Ставка процента. При ставке выше р | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| money | #ex-body | p3 | абзац разбора | Почему предложение денег нарисовано вертикальным? Потому что | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| money | #ex-body | p4 | абзац разбора | Вывод: Увеличивая предложение денег, банк сдвигает вертикаль | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-d1 | info-mono | 0 | Выпуск (= конкурентному) | 80 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-d1 | info-mono | 1 | Прибыль (весь излишек) | 3200 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-d1 | info-mono | 2 | CS (потребитель) | 0 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-d1 | info-mono | 3 | DWL (потери) | 0 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-d1 | info-mono | 4 | Простая монополия: Qm​ | 40 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-d1 | info-mono | 5 | Простая монополия: излишек (TR−VC) | 1600 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-d1 | info-mono | 6 | Простая монополия: DWL | 800 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-d1 | info-mono | n0 | пояснение | Совершенная дискриминация: выпуск растёт до конкурентного, п | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| mono-d1 | #sec-eq | title | заголовок группы | Оптимум монополии: MR=MC | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| mono-d1 | #ex-body | p0 | абзац разбора | Что такое дискриминация первой степени? Продажа каждой едини | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-d1 | #ex-body | p1 | абзац разбора | Почему объём при этом эффективен? Раз каждая единица продаёт | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-d1 | #ex-body | p2 | абзац разбора | Где тогда потери? Потерь общества нет вовсе: весь выигрыш до | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-d1 | #ex-body | p3 | абзац разбора | Бывает ли такое на самом деле? В чистом виде почти нет: нужн | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-d1 | #ex-body | p4 | абзац разбора | Вывод: Совершенная дискриминация максимизирует размер пирога | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-d3 | info-d3 | 0 | Рынок 1: (q₁; P1​) | (40;60) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-d3 | info-d3 | 1 | Рынок 2: (q₂; P2​) | (15;50) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-d3 | info-d3 | 2 | Σ выпуск | 55 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-d3 | info-d3 | 3 | MR1​=MR2​=MC | 20 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-d3 | info-d3 | n0 | пояснение | Цена выше на менее эластичном рынке (здесь это рынок 1). Фир | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| mono-d3 | #sec-eq | title | заголовок группы | Оптимум монополии: MR=MC | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| mono-d3 | #ex-body | p0 | абзац разбора | Потоварный налог на стороне производителя: кривая предложени | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-d3 | #ex-body | p1 | абзац разбора | Чем монополист отличается от конкурентной фирмы? Он видит пе | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-d3 | #ex-body | p2 | абзац разбора | Почему оптимум там, где MR=MC? Пока последняя единица принос | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-d3 | #ex-body | p3 | абзац разбора | Откуда потери общества? Монополист останавливается раньше, ч | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-d3 | #ex-body | p4 | абзац разбора | Откуда берётся MR ниже спроса? Продавая лишнюю единицу, моно | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-d3 | #ex-body | p5 | абзац разбора | Вывод: Вред монополии не в самой высокой цене (это перераспр | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-kink | info-kink | 0 | Q∗ (выпуск) | 60 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-kink | info-kink | 1 | P∗ (цена) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-kink | info-kink | 2 | Прибыль π | 1800 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-kink | info-kink | 3 | CS | 1300 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-kink | info-kink | 4 | PS (TR − VC) | 1800 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-kink | info-kink | 5 | VC | 1200 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-kink | info-kink | 6 | Конкурентный выпуск | 120 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-kink | info-kink | 7 | DWL | 900 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-kink | info-kink | 8 | Победил кандидат | MR=MC @ Q = 60 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-kink | info-kink | t | таблица (1) |  | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-kink | info-kink | n0 | пояснение | Оптимум берётся по МАКСИМУМУ прибыли среди кандидатов, а не  | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| mono-kink | #sec-eq | title | заголовок группы | Оптимум монополии: MR=MC | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| mono-kink | #ex-body | p0 | абзац разбора | Потоварный налог на стороне производителя: кривая предложени | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-kink | #ex-body | p1 | абзац разбора | Откуда берётся составной спрос? Когда фирма продаёт двум раз | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-kink | #ex-body | p2 | абзац разбора | Почему предельная выручка разрывается? В точке излома наклон | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-kink | #ex-body | p3 | абзац разбора | Чем это важно? Если предельные издержки попадают в разрыв, о | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-kink | #ex-body | p4 | абзац разбора | Как найти сам излом? По цене, при которой вторая группа толь | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-kink | #ex-body | p5 | абзац разбора | Вывод: Это не модель Суизи с олигополией, а свойство самой с | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-nat | info-mono | 0 | Qm​ (монополия) | 40 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-mono | 1 | Pm​ (цена) | 60 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-mono | 2 | Qc​ (конкуренция) | 80 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-mono | 3 | Pc​ (конкуренция) | 20 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-mono | 4 | DWL (потери) | 800 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-mono | 5 | CS (потребитель) | 800 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-mono | 6 | VC (перем. издержки) | 800 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-mono | 7 | Излишек произв. (TR − VC) | 1600 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-nat | 0 | Постоянные издержки FC | 800 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-nat | 1 | M · монополия: (Q; P) | (40;60) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-nat | 2 | (ATC(Qm​); прибыль) | (40;800) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-nat | 3 | EMC​ · цена P=MC: Q / P | 80/20 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-nat | 4 | ATC на этом Q | 30 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-nat | 5 | Нужна субсидия | 800 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-nat | 6 | EATC​ · цена P=ATC: Q / P | 68,28/31,72 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-nat | 7 | Прибыль | 0 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono-nat | info-nat | n0 | пояснение | Компромисс регулятора: цена по предельным издержкам эффектив | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| mono-nat | #sec-eq | title | заголовок группы | Оптимум монополии: MR=MC | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| mono-nat | #ex-body | p0 | абзац разбора | Что делает монополию естественной? Большие постоянные издерж | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-nat | #ex-body | p1 | абзац разбора | Почему регулирование по P=MC разоряет фирму? При падающих ср | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-nat | #ex-body | p2 | абзац разбора | Чем хорош вариант P=ATC? Он оставляет фирму без убытка и при | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-nat | #ex-body | p3 | абзац разбора | Откуда берутся такие издержки в жизни? Из сетей: рельсы, тру | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono-nat | #ex-body | p4 | абзац разбора | Вывод: Здесь нет решения, которое хорошо сразу по всем мерка | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono | info-tax | n0 | пояснение | Двигайте ставку: налог поднимет MC; новый оптимум: MR = MC + | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| mono | info-mono | 0 | Qm​ (монополия) | 40 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono | info-mono | 1 | Pm​ (цена) | 60 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono | info-mono | 2 | Qc​ (конкуренция) | 80 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono | info-mono | 3 | Pc​ (конкуренция) | 20 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono | info-mono | 4 | DWL (потери) | 800 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono | info-mono | 5 | CS (потребитель) | 800 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono | info-mono | 6 | VC (перем. издержки) | 800 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono | info-mono | 7 | Излишек произв. (TR − VC) | 1600 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| mono | #sec-eq | title | заголовок группы | Оптимум монополии: MR=MC | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| mono | #ex-body | p0 | абзац разбора | Потоварный налог на стороне производителя: кривая предложени | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono | #ex-body | p1 | абзац разбора | Чем монополист отличается от конкурентной фирмы? Он видит пе | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono | #ex-body | p2 | абзац разбора | Почему оптимум там, где MR=MC? Пока последняя единица принос | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono | #ex-body | p3 | абзац разбора | Откуда потери общества? Монополист останавливается раньше, ч | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono | #ex-body | p4 | абзац разбора | Откуда берётся MR ниже спроса? Продавая лишнюю единицу, моно | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| mono | #ex-body | p5 | абзац разбора | Вывод: Вред монополии не в самой высокой цене (это перераспр | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| monoexport | info-d3 | 0 | Внутри: (q₁; P1​) | (25;75) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| monoexport | info-d3 | 1 | Экспорт q₂ (по Pw​) | 25/50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| monoexport | info-d3 | 2 | Σ выпуск | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| monoexport | info-d3 | 3 | MR1​=Pw​=MC | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| monoexport | info-d3 | n0 | пояснение | Мировой рынок для малой фирмы совершенно эластичен: продать  | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| monoexport | #sec-eq | title | заголовок группы | Оптимум монополии: MR=MC | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| monoexport | #ex-body | p0 | абзац разбора | В чём особенность этой задачи? Фирма с рыночной властью дома | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| monoexport | #ex-body | p1 | абзац разбора | Как она делит выпуск? По общему правилу: предельная выручка  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| monoexport | #ex-body | p2 | абзац разбора | Почему нельзя считать рынки по отдельности? Потому что общая | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| monoexport | #ex-body | p3 | абзац разбора | Как решать такую задачу по шагам? Сначала находят общий выпу | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| monoexport | #ex-body | p4 | абзац разбора | Вывод: Внутренняя цена оказывается выше мировой, и это не «н | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| phillips | info-macro | 0 | Ожидаемая инфляция πe | 5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| phillips | info-macro | 1 | Естественный уровень u∗ | 5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| phillips | info-macro | 2 | Наклон β | 0,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| phillips | info-macro | t | таблица (1) |  | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| phillips | info-macro | n0 | пояснение | Краткосрочная кривая проходит через точку (u∗; πe​) с наклон | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| phillips | #ex-body | p0 | абзац разбора | О чём эта кривая? О связи инфляции и безработицы в КОРОТКОМ  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| phillips | #ex-body | p1 | абзац разбора | Почему связь только краткосрочная? Она держится на ошибке в  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| phillips | #ex-body | p2 | абзац разбора | Что такое естественный уровень? Безработица, при которой инф | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| phillips | #ex-body | p3 | абзац разбора | Почему кривая в длинном периоде вертикальна? Потому что люди | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| phillips | #ex-body | p4 | абзац разбора | Вывод: Долгосрочная кривая вертикальна: постоянного размена  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| plants | info-plants | 0 | Совокупный выпуск Q | 30 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| plants | info-plants | 1 | Завод 1: Q1​ | 20 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| plants | info-plants | 2 | Завод 2: Q2​ | 10 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| plants | info-plants | 3 | MC1​=MC2​=MC(Q) | 40 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| plants | info-plants | 4 | TC(Q)=TC1​+TC2​ | 600 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| plants | info-plants | 5 | ∫ MC(q)dq (сверка) | 600 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| plants | info-plants | 6 | «Сумма в лоб» TC1​(Q)+TC2​(Q) | 2700 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| plants | info-plants | n0 | пояснение | Почему сложение ГОРИЗОНТАЛЬНОЕСовокупные издержки это не TC1 | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| plants | #ex-body | p0 | абзац разбора | Откуда берутся все эти кривые? Из одной функции общих издерж | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| plants | #ex-body | p1 | абзац разбора | Почему MC пересекает ATC ровно в её минимуме? Пока последняя | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| plants | #ex-body | p2 | абзац разбора | Что решает фирма по этим кривым? Сколько выпускать: при сове | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| plants | #ex-body | p3 | абзац разбора | Почему средние постоянные издержки нигде не пересекаются с о | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| plants | #ex-body | p4 | абзац разбора | Вывод: Форма кривых не произвольна: она целиком следует из T | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ppf | info-ppf | 0 | Тип КПВ | линейная: постоянные альтернативные издержки | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ppf | info-ppf | 1 | Xmax​ (весь ресурс на X) | 100 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ppf | info-ppf | 2 | Ymax​ (весь ресурс на Y) | 100 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ppf | info-ppf | 3 | Альт. издержки X в середине | 1 Y за ед. X | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ppf | info-ppf | 4 | Альт. издержки Y в середине | 1 X за ед. Y | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ppf | #ex-body | p0 | абзац разбора | Где кончается кривая? Граница возможностей это все наборы, п | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ppf | #ex-body | p1 | абзац разбора | Откуда берутся альтернативные издержки? Это наклон касательн | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ppf | #ex-body | p2 | абзац разбора | Меняются ли издержки вдоль кривой? Нет: кривая прямая, накло | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ppf | #ex-body | p3 | абзац разбора | Что означают точки ВНУТРИ кривой и снаружи? Точка внутри дос | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ppf | #ex-body | p4 | абзац разбора | Что двигает саму кривую? Рост количества ресурсов или улучше | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ppf | #ex-body | p5 | абзац разбора | Вывод. Кривая отвечает сразу на три вопроса: что достижимо,  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ppfsum | info-final | f0 | итоговая функция | Y = \begin{cases} 160 - X, & 0 \le X \le 100 \\ 360 - 3X, & 100 < X \le 120 \end{cases} | на месте | карточка «Итоговая функция» в «Ответе» | compare.mjs: паритет чисел и текстов |
| ppfsum | info-ppfsum | 0 | Складываем кривых | 2 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ppfsum | info-ppfsum | 1 | Xmax​ суммарной | 120 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ppfsum | info-ppfsum | 2 | Ymax​ суммарной | 160 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ppfsum | info-ppfsum | 3 | Точка излома 1 | 100;60 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ppfsum | info-ppfsum | 4 | КПВ 1: постоянны | 1 Y за ед. X | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ppfsum | info-ppfsum | 5 | КПВ 2: постоянны | 3 Y за ед. X | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| ppfsum | #ex-body | p0 | абзац разбора | Кто начинает первым? Порядок специализации задают альтернати | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ppfsum | #ex-body | p1 | абзац разбора | Поэтому кривая начинается с самого пологого участка (КПВ 1,  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ppfsum | #ex-body | p2 | абзац разбора | Излом появляется там, где очередной участник исчерпал свои в | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ppfsum | #ex-body | p3 | абзац разбора | Первый излом стоит ровно там, где КПВ 1 отдал под X весь сво | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ppfsum | #ex-body | p4 | абзац разбора | Концы суммарной кривой это просто суммы концов: Xmax​=120 и  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| ppfsum | #ex-body | p5 | абзац разбора | Саму запись суммарной кривой ищите в «Ключевых значениях», п | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| prod | info-prod | 0 | Перегиб TP (max MP) | L = 10, MP = 300 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| prod | info-prod | 1 | Максимум AP | L = 15, AP = 225 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| prod | info-prod | 2 | MP в этой точке | 225 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| prod | info-prod | 3 | Максимум TP | L = 20, Q = 4 000 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| prod | info-prod | n0 | пояснение | С точки перегиба TP начинается убывающая предельная отдача:  | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| prod | #ex-body | p0 | абзац разбора | Откуда берутся все эти кривые? Из одной функции общих издерж | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| prod | #ex-body | p1 | абзац разбора | Почему MC пересекает ATC ровно в её минимуме? Пока последняя | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| prod | #ex-body | p2 | абзац разбора | Что решает фирма по этим кривым? Сколько выпускать: при сове | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| prod | #ex-body | p3 | абзац разбора | Почему средние постоянные издержки нигде не пересекаются с о | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| prod | #ex-body | p4 | абзац разбора | Вывод: Форма кривых не произвольна: она целиком следует из T | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| quota | sec-eq | 0 | Q (объём торговли) | 40 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| quota | sec-eq | 1 | P (выбранная цена) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| quota | sec-eq | 2 | Коридор возможных цен | 40…60 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| quota | sec-eq | n0 | пояснение | Квота ниже равновесного объёма, поэтому одной цены рынок не  | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| quota | info-areas | 0 | CS (потребитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| quota | info-areas | 1 | PS (производитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| quota | info-areas | 2 | SW=CS+PS | 2500 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| quota | info-areas | n0 | пояснение | до вмешательства государства | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| quota | info-tax | 0 | Коридор цен | 40…60 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| quota | info-tax | 1 | Выбранная цена | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| quota | info-tax | t | таблица (1) |  | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| quota | info-tax | n0 | пояснение | Двигая цену внутри коридора, вы перекладываете выигрыш между | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| quota | #sec-eq | title | заголовок группы | Рынок при квоте | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| quota | #ex-body | p0 | абзац разбора | Квота ограничивает объём напрямую. Если она НИЖЕ равновесног | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| sd | sec-eq | 0 | Q∗ (количество) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sd | sec-eq | 1 | P∗ (цена) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sd | info-areas | 0 | CS (потребитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sd | info-areas | 1 | PS (производитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sd | info-areas | 2 | SW=CS+PS | 2500 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sd | #sec-eq | title | заголовок группы | Равновесие D=S | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| sd | #ex-body | p0 | абзац разбора | Что показывают эти две кривые? Спрос D говорит, сколько поку | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| sd | #ex-body | p1 | абзац разбора | Почему равновесие именно в точке пересечения? Только там нам | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| sd | #ex-body | p2 | абзац разбора | Что означают закрашенные области? Излишек покупателя CS это  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| sd | #ex-body | p3 | абзац разбора | Вывод: Свободное равновесие максимизирует сумму излишков: лю | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| sdsum | info-final | f0 | итоговая функция | P = \begin{cases}100- Q, & \text{если } 0 \le Q < 40\\80-0.5\cdot Q, & \text{если } 40 \le | на месте | карточка «Итоговая функция» в «Ответе» | compare.mjs: паритет чисел и текстов |
| sdsum | info-final | f1 | итоговая функция | P = \begin{cases} Q, & \text{если } 0 \le Q < 20\\0.5\cdot Q+10, & \text{если } Q \ge 20\e | на месте | карточка «Итоговая функция» в «Ответе» | compare.mjs: паритет чисел и текстов |
| sdsum | sec-eq | 0 | Q∗ (количество) | 70 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | sec-eq | 1 | P∗ (цена) | 45 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-areas | 0 | CS (потребитель) | 1625 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-areas | 1 | PS (производитель) | 1325 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-areas | 2 | SW=CS+PS | 2950 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 0 | Равновесная цена P∗ | 45 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 1 | спрос первой группы | 55 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 2 | спрос второй группы | 15 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 3 | вместе Q | 70 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 4 | CS · спрос первой группы | 1512,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 5 | CS · спрос второй группы | 112,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 6 | вместе CS | 1625 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 7 | предложение первой группы | 45 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 8 | предложение второй группы | 25 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 9 | вместе Q | 70 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 10 | PS · предложение первой группы | 1012,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 11 | PS · предложение второй группы | 312,5 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | 12 | вместе PS | 1325 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| sdsum | info-sum | n0 | пояснение | Сумма излишков по группам сошлась с площадью под суммарной к | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| sdsum | #sec-eq | title | заголовок группы | Равновесие D=S | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| sdsum | #ex-body | p0 | абзац разбора | Почему у рыночной кривой участки? Складываем по горизонтали: | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| sdsum | #ex-body | p1 | абзац разбора | Сама запись стоит первой в «Ключевых значениях», блоком «Ито | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| smallopen | sec-eq | 0 | Q∗ (количество) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| smallopen | sec-eq | 1 | P∗ (цена) | 50 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| smallopen | info-areas | 0 | CS (потребитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| smallopen | info-areas | 1 | PS (производитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| smallopen | info-areas | 2 | SW=CS+PS | 2500 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| smallopen | info-open | 0 | Мировая цена Pw​ | 30 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| smallopen | info-open | 1 | Автаркия: (Q∗;P∗) | (50;50) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| smallopen | info-open | 2 | При Pw​: (Qd​; Qs​) | (70;30) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| smallopen | info-open | 3 | Импорт | 40 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| smallopen | info-open | 4 | (CS; PS) при своб. торговле | (2450;450) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| smallopen | info-open | 5 | Выигрыш от торговли | +400 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| smallopen | #sec-eq | title | заголовок группы | Равновесие без торговли (автаркия) | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| smallopen | #ex-body | p0 | абзац разбора | Почему экономика «малая»? Потому что её объёмы не влияют на  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| smallopen | #ex-body | p1 | абзац разбора | Как определить, импортёр страна или экспортёр? Сравнить миро | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| smallopen | #ex-body | p2 | абзац разбора | Что делает тариф? Поднимает внутреннюю цену на величину пошл | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| smallopen | #ex-body | p3 | абзац разбора | Чем квота отличается от тарифа? Тем, кому достаётся прямоуго | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| smallopen | #ex-body | p4 | абзац разбора | Вывод: Тариф и квота одинаково искажают объёмы, но по-разном | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tax-adv | info-final | f0 | итоговая функция | P = 1.2\cdot Q | на месте | карточка «Итоговая функция» в «Ответе» | compare.mjs: паритет чисел и текстов |
| tax-adv | sec-eq | 0 | Q (объём торговли) | 45,45 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax-adv | sec-eq | 1 | Pb​ (платит покупатель) | 54,55 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax-adv | sec-eq | 2 | Ps​ (получает продавец) | 45,45 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax-adv | sec-eq | n0 | пояснение | Цена покупателя и цена продавца разошлись на налог, и одной  | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| tax-adv | info-areas | 0 | CS (потребитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax-adv | info-areas | 1 | PS (производитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax-adv | info-areas | 2 | SW=CS+PS | 2500 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax-adv | info-areas | n0 | пояснение | до вмешательства государства | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| tax-adv | info-tax | 0 | Ставка τ · НДС | 20% | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax-adv | info-tax | 1 | Бремя покупателя | 4,55 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax-adv | info-tax | 2 | Бремя продавца | 4,55 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax-adv | info-tax | t | таблица (1) |  | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax-adv | info-tax | n0 | пояснение | НДС: ставка берётся долей от цены продавца. Кривая после это | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| tax-adv | info-tax | n1 | пояснение | Результат не зависит от того, кто формально платит налог: об | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| tax-adv | #sec-eq | title | заголовок группы | Рынок после налога | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| tax-adv | #ex-body | p0 | абзац разбора | НДС берётся долей от цены ПРОДАВЦА и начисляется сверх неё:  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tax-adv | #ex-body | p1 | абзац разбора | Что делает потоварный налог? Он вставляет клин между ценой,  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tax-adv | #ex-body | p2 | абзац разбора | Кто на самом деле платит налог? Не тот, с кого его берут по  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tax-adv | #ex-body | p3 | абзац разбора | Откуда берутся потери общества? Налог сокращает объём с Q0​  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tax-adv | #ex-body | p4 | абзац разбора | Вывод: Сбор бюджета меньше, чем потеряли покупатель и продав | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tax-adv | #ex-body | p5 | абзац разбора | НДС: ставка это доля, а не сумма. Налог берётся долей τ от ц | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tax-adv | #ex-body | p6 | абзац разбора | Чем это отличается от потоварной формы? У потоварной клин ме | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tax | info-final | f0 | итоговая функция | P = Q+20 | на месте | карточка «Итоговая функция» в «Ответе» | compare.mjs: паритет чисел и текстов |
| tax | sec-eq | 0 | Q (объём торговли) | 40 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax | sec-eq | 1 | Pb​ (платит покупатель) | 60 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax | sec-eq | 2 | Ps​ (получает продавец) | 40 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax | sec-eq | n0 | пояснение | Цена покупателя и цена продавца разошлись на налог, и одной  | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| tax | info-areas | 0 | CS (потребитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax | info-areas | 1 | PS (производитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax | info-areas | 2 | SW=CS+PS | 2500 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax | info-areas | n0 | пояснение | до вмешательства государства | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| tax | info-tax | 0 | Налог t | 20 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax | info-tax | 1 | Бремя покупателя | 10 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax | info-tax | 2 | Бремя продавца | 10 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax | info-tax | t | таблица (1) |  | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tax | info-tax | n0 | пояснение | Результат не зависит от того, кто формально платит налог: об | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| tax | #sec-eq | title | заголовок группы | Рынок после налога | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| tax | #ex-body | p0 | абзац разбора | Потоварный налог на стороне производителя: кривая предложени | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tax | #ex-body | p1 | абзац разбора | Что делает потоварный налог? Он вставляет клин между ценой,  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tax | #ex-body | p2 | абзац разбора | Кто на самом деле платит налог? Не тот, с кого его берут по  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tax | #ex-body | p3 | абзац разбора | Откуда берутся потери общества? Налог сокращает объём с Q0​  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tax | #ex-body | p4 | абзац разбора | Вывод: Сбор бюджета меньше, чем потеряли покупатель и продав | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| taxes | info-final | f0 | итоговая функция | P = Q+20 | на месте | карточка «Итоговая функция» в «Ответе» | compare.mjs: паритет чисел и текстов |
| taxes | sec-eq | 0 | Q (объём торговли) | 40 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| taxes | sec-eq | 1 | Pb​ (платит покупатель) | 60 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| taxes | sec-eq | 2 | Ps​ (получает продавец) | 40 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| taxes | sec-eq | n0 | пояснение | Цена покупателя и цена продавца разошлись на налог, и одной  | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| taxes | info-areas | 0 | CS (потребитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| taxes | info-areas | 1 | PS (производитель) | 1250 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| taxes | info-areas | 2 | SW=CS+PS | 2500 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| taxes | info-areas | n0 | пояснение | до вмешательства государства | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| taxes | info-tax | 0 | Налог t | 20 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| taxes | info-tax | 1 | Бремя покупателя | 10 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| taxes | info-tax | 2 | Бремя продавца | 10 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| taxes | info-tax | t | таблица (1) |  | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| taxes | info-tax | n0 | пояснение | Результат не зависит от того, кто формально платит налог: об | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| taxes | #sec-eq | title | заголовок группы | Рынок после налога | на месте | заголовок группы в «Ответе» | compare.mjs: паритет чисел и текстов |
| taxes | #ex-body | p0 | абзац разбора | Потоварный налог на стороне производителя: кривая предложени | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| taxes | #ex-body | p1 | абзац разбора | Что делает налог на товар? Он вставляет клин между ценой, ко | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| taxes | #ex-body | p2 | абзац разбора | Кто на самом деле платит налог? Не тот, с кого его берут по  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| taxes | #ex-body | p3 | абзац разбора | Откуда берутся потери общества? Налог сокращает объём с Q0​  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| taxes | #ex-body | p4 | абзац разбора | А субсидия? Это тот же механизм с обратным знаком: предложен | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| trade | info-final | f0 | итоговая функция | Y = 200 - 2X,\ 0 \le X \le 100 | на месте | карточка «Итоговая функция» в «Ответе» | compare.mjs: паритет чисел и текстов |
| trade | info-ppft | 0 | Режим | специализация на X | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| trade | info-ppft | 1 | Мировая цена Px​/Py​ | 2 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| trade | info-ppft | 2 | Внутренняя цена X (наклон КПВ) | 1 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| trade | info-ppft | 3 | Производство (Xп​;Yп​) | (100;0) | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| trade | info-ppft | 4 | Предел потребления Xмакс​ | 100 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| trade | info-ppft | 5 | Предел потребления Yмакс​ | 200 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| trade | info-ppft | 6 | Прирост против автаркии | Постройте кривую комплектов | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| trade | #ex-body | p0 | абзац разбора | Стоит ли вообще торговать? Сравниваем две цены. Внутренняя ц | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| trade | #ex-body | p1 | абзац разбора | Где остановиться с выпуском? На самом краю. КПВ прямая, изде | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| trade | #ex-body | p2 | абзац разбора | Из точки производства страна может обменивать один товар на  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| trade | #ex-body | p3 | абзац разбора | Концы линии показывают предел потребления, если всё продать: | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tradeprice | info-tb | 0 | Автарк. цена X стр.1 | 1 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tradeprice | info-tb | 1 | Автарк. цена X стр.2 | 2 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tradeprice | info-tb | 2 | Мировая цена Pw​ | 1,41 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tradeprice | info-tb | 3 | Экспортируют | КПВ 1 → X, КПВ 2 → Y | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tradeprice | info-tb | 4 | Обмен X (макс.) | 70,71 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tradeprice | info-tb | 5 | Обмен Y (макс.) | 100 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tradeprice | info-tb | 6 | Излом КТВ у КПВ 1 | 29,29;100 | на месте | «Ответ»: главные числа или таблица своей группы (§9 п. 1) | compare.mjs: паритет чисел и текстов |
| tradeprice | info-tb | n0 | пояснение | Откуда берётся Pw​Автарктическая цена X это альтернативные и | на месте | тихим текстом под своей группой (§9 п. 3) | compare.mjs: паритет чисел и текстов |
| tradeprice | #ex-body | p0 | абзац разбора | Откуда берётся прямая? Страна КПВ 1 специализируется на X и  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tradeprice | #ex-body | p1 | абзац разбора | Почему она не идёт бесконечно? Взять Y больше, чем партнёр в | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tradeprice | #ex-body | p2 | абзац разбора | Здесь предел сработал: партнёр кончился раньше, чем свой X.  | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |
| tradeprice | #ex-body | p3 | абзац разбора | Рисовать КТВ бесконечной прямой от края до края неверно: это | на месте | «Разбор» | compare.mjs: паритет чисел и текстов |

## 3. Инвентарь (INVENTORY.md)

| Строка | Раздел | Пункт | Судьба | Чем проверено |
|---|---|---|---|---|
| 15 | 1. Окно выбора `#scene-picker` | Оверлей | заменён (г) | по букве закрытого списка |
| 16 | 1. Окно выбора `#scene-picker` | Экран блоков | заменён (г) | по букве закрытого списка |
| 17 | 1. Окно выбора `#scene-picker` | Клик по блоку | заменён (г) | по букве закрытого списка |
| 18 | 1. Окно выбора `#scene-picker` | Карточка модели | заменён (г) | по букве закрытого списка |
| 19 | 1. Окно выбора `#scene-picker` | Повторное открытие | заменён (г) | по букве закрытого списка |
| 20 | 1. Окно выбора `#scene-picker` | Клавиатура | на месте | snapshot.mjs (layer new) + compare.mjs |
| 24 | 2. Док `nav.dock` | «Ко всем моделям» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 25 | 2. Док `nav.dock` | «Скачать график» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 30 | 3. Левая панель `#tools-panel` | Шапка | на месте | snapshot.mjs (layer new) + compare.mjs |
| 31 | 3. Левая панель `#tools-panel` | Стрелка | заменён (в) | по букве закрытого списка |
| 32 | 3. Левая панель `#tools-panel` | «Вернуть исходный вид» | заменён (и) | по букве закрытого списка |
| 36 | 3. Левая панель `#tools-panel` | Три складные карточки | заменён (д) | по букве закрытого списка |
| 37 | 3. Левая панель `#tools-panel` | Подсказки «?» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 48 | 3. Левая панель `#tools-panel` | ✕ | на месте | snapshot.mjs (layer new) + compare.mjs |
| 50 | 3. Левая панель `#tools-panel` | «Добавить кривую» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 60 | 3. Левая панель `#tools-panel` | Кнопка клавиатуры | на месте | snapshot.mjs (layer new) + compare.mjs |
| 65 | 3. Левая панель `#tools-panel` | Конструктор кусочной функции | на месте | snapshot.mjs (layer new) + compare.mjs |
| 75 | 3. Левая панель `#tools-panel` | «Добавить точку» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 78 | 3. Левая панель `#tools-panel` | Строка точки | на месте | snapshot.mjs (layer new) + compare.mjs |
| 79 | 3. Левая панель `#tools-panel` | На холсте | на месте | snapshot.mjs (layer new) + compare.mjs |
| 83 | 3. Левая панель `#tools-panel` | Под кривой | на месте | snapshot.mjs (layer new) + compare.mjs |
| 84 | 3. Левая панель `#tools-panel` | Между точками | на месте | snapshot.mjs (layer new) + compare.mjs |
| 89 | 3. Левая панель `#tools-panel` | «Посчитать площадь» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 90 | 3. Левая панель `#tools-panel` | Таблица | на месте | snapshot.mjs (layer new) + compare.mjs |
| 93 | 3. Левая панель `#tools-panel` | «Убрать всё» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 97 | 4. Правая панель `#params-panel` «Аналитика» | «Сдвиг кривых» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 98 | 4. Правая панель `#params-panel` «Аналитика» | Буквы из формул | на месте | snapshot.mjs (layer new) + compare.mjs |
| 104 | 4. Правая панель `#params-panel` «Аналитика» | Регуляторы моделей | на месте | snapshot.mjs (layer new) + compare.mjs |
| 105 | 4. Правая панель `#params-panel` «Аналитика» | Пустое состояние | убран (л) | по букве закрытого списка |
| 106 | 4. Правая панель `#params-panel` «Аналитика» | «Ключевые значения» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 110 | 4. Правая панель `#params-panel` «Аналитика» | «Объяснение модели» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 114 | 5. Холст `#graph-wrap` / `svg#chart` | Зум | на месте | snapshot.mjs (layer new) + compare.mjs |
| 119 | 5. Холст `#graph-wrap` / `svg#chart` | Панорама | на месте | snapshot.mjs (layer new) + compare.mjs |
| 120 | 5. Холст `#graph-wrap` / `svg#chart` | Возврат масштаба | на месте | snapshot.mjs (layer new) + compare.mjs |
| 121 | 5. Холст `#graph-wrap` / `svg#chart` | Авто-расширение окна | на месте | snapshot.mjs (layer new) + compare.mjs |
| 122 | 5. Холст `#graph-wrap` / `svg#chart` | Щелчок по кривой | на месте | snapshot.mjs (layer new) + compare.mjs |
| 123 | 5. Холст `#graph-wrap` / `svg#chart` | Прокатывание | на месте | snapshot.mjs (layer new) + compare.mjs |
| 124 | 5. Холст `#graph-wrap` / `svg#chart` | Подписи кривых | на месте | snapshot.mjs (layer new) + compare.mjs |
| 125 | 5. Холст `#graph-wrap` / `svg#chart` | Название графика | на месте | snapshot.mjs (layer new) + compare.mjs |
| 126 | 5. Холст `#graph-wrap` / `svg#chart` | Общие перетаскиваемые объекты | на месте | snapshot.mjs (layer new) + compare.mjs |
| 127 | 5. Холст `#graph-wrap` / `svg#chart` | Ручки моделей | на месте | snapshot.mjs (layer new) + compare.mjs |
| 128 | 5. Холст `#graph-wrap` / `svg#chart` | Легенда | на месте | snapshot.mjs (layer new) + compare.mjs |
| 129 | 5. Холст `#graph-wrap` / `svg#chart` | Полоса режима | на месте | snapshot.mjs (layer new) + compare.mjs |
| 130 | 5. Холст `#graph-wrap` / `svg#chart` | Подсказки | на месте | snapshot.mjs (layer new) + compare.mjs |
| 131 | 5. Холст `#graph-wrap` / `svg#chart` | Многопанельные модели | на месте | snapshot.mjs (layer new) + compare.mjs |
| 132 | 5. Холст `#graph-wrap` / `svg#chart` | Первая четверть | на месте | snapshot.mjs (layer new) + compare.mjs |
| 135 | 6. Меню гаечного ключа `#wrench-pop` (кнопка `#btn-wrench`) | «Ось X» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 136 | 6. Меню гаечного ключа `#wrench-pop` (кнопка `#btn-wrench`) | «Ось Y» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 138 | 6. Меню гаечного ключа `#wrench-pop` (кнопка `#btn-wrench`) | «Область значений» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 139 | 6. Меню гаечного ключа `#wrench-pop` (кнопка `#btn-wrench`) | «Излишки» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 140 | 6. Меню гаечного ключа `#wrench-pop` (кнопка `#btn-wrench`) | «Сетка» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 141 | 6. Меню гаечного ключа `#wrench-pop` (кнопка `#btn-wrench`) | «Подписи» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 145 | 7. Экспорт `#export-modal` «Скачать график» | «Заголовок» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 146 | 7. Экспорт `#export-modal` «Скачать график» | «Метка для перекрёстной ссылки» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 147 | 7. Экспорт `#export-modal` «Скачать график» | «Что уйдёт в файл» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 148 | 7. Экспорт `#export-modal` «Скачать график» | «Скачать PNG» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 149 | 7. Экспорт `#export-modal` «Скачать график» | «Скачать .tex» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 150 | 7. Экспорт `#export-modal` «Скачать график» | «Скачать PDF» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 151 | 7. Экспорт `#export-modal` «Скачать график» | «Закрыть» | на месте | snapshot.mjs (layer new) + compare.mjs |
| 152 | 7. Экспорт `#export-modal` «Скачать график» | Печать | на месте | snapshot.mjs (layer new) + compare.mjs |
| 155 | 8. Тема, клавиши, доступность, экраны, касание | Тема | на месте | snapshot.mjs (layer new) + compare.mjs |
| 156 | 8. Тема, клавиши, доступность, экраны, касание | Клавиши | на месте | snapshot.mjs (layer new) + compare.mjs |
| 162 | 8. Тема, клавиши, доступность, экраны, касание | Доступность | на месте | snapshot.mjs (layer new) + compare.mjs |
| 165 | 8. Тема, клавиши, доступность, экраны, касание | Ширина экрана | на месте | snapshot.mjs (layer new) + compare.mjs |
| 166 | 8. Тема, клавиши, доступность, экраны, касание | Касание | на месте | snapshot.mjs (layer new) + compare.mjs |
| 169 | 9. Прочее | Тосты | на месте | snapshot.mjs (layer new) + compare.mjs |
| 170 | 9. Прочее | Память моделей | на месте | snapshot.mjs (layer new) + compare.mjs |
| 171 | 9. Прочее | Виджеты сайта | на месте | snapshot.mjs (layer new) + compare.mjs |
| 424 | Макроэкономика (переключатель macro-seg заперт; формулы живые, числа по change; ручек нет; | adas · AD–AS: | на месте | snapshot.mjs (layer new) + compare.mjs |
| 425 | Макроэкономика (переключатель macro-seg заперт; формулы живые, числа по change; ручек нет; | islm · IS–LM: | на месте | snapshot.mjs (layer new) + compare.mjs |
| 426 | Макроэкономика (переключатель macro-seg заперт; формулы живые, числа по change; ручек нет; | phillips · Кривая Филлипса: | на месте | snapshot.mjs (layer new) + compare.mjs |
| 427 | Макроэкономика (переключатель macro-seg заперт; формулы живые, числа по change; ручек нет; | money · Денежный рынок: | на месте | snapshot.mjs (layer new) + compare.mjs |
| 428 | Макроэкономика (переключатель macro-seg заперт; формулы живые, числа по change; ручек нет; | loanable · Рынок заёмных средств: | на месте | snapshot.mjs (layer new) + compare.mjs |
| 429 | Макроэкономика (переключатель macro-seg заперт; формулы живые, числа по change; ручек нет; | fx · Валютный рынок: | на месте | snapshot.mjs (layer new) + compare.mjs |
| 495 | 2. Сцены, которые ломают скелет | Две панели: | на месте | snapshot.mjs (layer new) + compare.mjs |
| 499 | 2. Сцены, которые ломают скелет | Квадрат: | на месте | snapshot.mjs (layer new) + compare.mjs |
| 500 | 2. Сцены, которые ломают скелет | Полный план | на месте | snapshot.mjs (layer new) + compare.mjs |
| 501 | 2. Сцены, которые ломают скелет | Без формул: | на месте | snapshot.mjs (layer new) + compare.mjs |
| 505 | 2. Сцены, которые ломают скелет | Кривая получена прогоном, а не формулой: | на месте | snapshot.mjs (layer new) + compare.mjs |
| 506 | 2. Сцены, которые ломают скелет | Ответ — диапазон, а не точка: | на месте | snapshot.mjs (layer new) + compare.mjs |
| 507 | 2. Сцены, которые ломают скелет | Гаечный ключ не управляет окнами: | заменён (и) | по букве закрытого списка |

## 4. Сверка (COVERAGE.md, разделы 2–4)

| № | Что | Судьба | Чем проверено |
|---|---|---|---|
| О1 | Esc на окне выбора возвращает в текущую модель | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О2 | Фокус при открытии окна выбора, без кольца при входе мышью | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О3 | Анимации выключаются при «уменьшить движение» | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О4 | «Вернуть исходный вид» сбрасывает точки, вершины, площади, название, имена осей, цвета, ра | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О5 | Закрепка точки, удаление точки и кривой — шаги отмены | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О6 | Девять кнопок «?» и 42 абзаца `.hint` в шаблоне | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О7 | Около 74 пояснений `.hint` рядом с числами в табло, многие меняются вместе с числами | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О8 | Разборы: реестр из 32 ключей с «Вывод:», врезки сцен с «Вывод.», абзацы без жирного вопрос | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О9 | Роли кривой: обычная, D, S, MC, TC, ATC; в монополии TC даёт MC = dTC/dQ, «S как MC», ATC  | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О10 | Суммарные D и S в «Сложении»: строка без поля, но с галочкой, цветом, именем | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О11 | Строка своей точки: цвет, имя на месте, координаты (правятся), «Пунктир к осям», «Координа | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О12 | Вершины площади тянутся; щелчок по вершине удаляет её; двойной щелчок правит координаты | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О13 | Посчитанные площади S₁, S₂: цвет, имя, значение; объяснение, если вершины из разных панеле | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О14 | У каждого регулятора правятся границы и шаг: «min ≤ a ≤ max с шагом s» | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О15 | Значение за границей: полоса переезжает так, чтобы значение стояло посередине, ширина сохр | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О16 | Границы ставки, цены, Pw, МРОТ считаются от модели; «Ось y до» заодно меняет максимумы пол | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О17 | Прокатывание: нажать на кривую и вести, по кривой едет точка с окошком координат | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О18 | Сдвиг окна левой кнопкой с Пробелом или Shift; меню правой кнопки на холсте погашено | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О19 | Одиночный щелчок по подписи кривой зажигает кривую | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О20 | Кружок `#snap-hint` показывает, куда сядет точка или вершина | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О21 | «Показать излишки» в гаечном ключе: одна галочка на CS и PS | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О22 | `?texState=1` включал сборку TeX «от состояния»; снят 08.10 (ADR 0139) | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О23 | Кнопка PDF пишет «Собираю…»; тосты «PNG сохранён», «Файл .tex сохранён», «PDF готов», «PDF | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О24 | В числовых полях ↑ и ↓ заблокированы, колесо снимает фокус, «,» превращается в «.» | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О25 | Вставки шаблона: метка версии, аналитика, Метрика, обратная связь, жалоба на задачу | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О26 | 15 выборов цвета у кривых без карточки: издержки, TP/MP/AP, f и f′, итоговая кривая min/ma | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О27 | Новая строка функции: курсор сразу в поле | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О28 | Если MathLive не загрузился — обычное поле с KaTeX-накладкой | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О29 | Обозначения (MC, Pw…) в текстах обеих панелей набираются формулами | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О30 | Строки интерфейса, которые называют части прежнего экрана по имени или по месту: «нажмите  | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О31 | Число у регулятора в покое показано текстом с запятой (`fmt`, набор KaTeX), щелчок открыва | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О32 | Порог скорости: вход в модель 300 мс, перерисовка 100 мс (решение штаба 13.08) | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О33 | 17 мест `d3.drag` в восьми файлах (клин налога, линии цены и МРОТ, узлы Лоренца, концы бюд | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О34 | Приборы зовут глобальные `pickScene`, `openPicker`, `closePicker`, `loadScene`, `setMode`, | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О35 | «Разбор» есть не у всех моделей: в реестре `SCENE_EXPLAIN` 32 ключа из 44. Шесть математич | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| О36 | Сейчас на любой ширине доступны все органы управления: панели только сужаются, на 820 px п | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| К1 | Площадь под кривой на отрезке: выбор кривой и границы [a; b] | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| К2 | Цвета и числа областей модели; «Убрать всё»; пометки «приближённая» и «обход пересекает са | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| К3 | Сворачивание ползунка буквы | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| К4 | «Метка для перекрёстной ссылки»; «Что уйдёт в файл» | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| К5 | Окно «развернуть» итоговой функции | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| К6 | Название графика тянется по холсту, правится двойным щелчком, у него есть цвет | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| К7 | Печать Ctrl+P: холст 15 см, название, строки чисел, всегда светлая | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель m-optimum | органы: Отрезок, на котором ищутся наибольшее и наименьшее, — это границы окна по x (`70-s | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель m-tangent | органы: Цвета f и f′ (`calc2.html:1796-1799`) · числа: «Разница с касательной» (`70-scenes | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель m-minmax | органы: «Цвет итоговой кривой» (`calc2.html:1875`), цвет каждой fᵢ (`60-overlays.js:241-24 | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель ppf | органы: Поля имён «КПВ» и «КПВ 2» (`calc2.html:1517, 1530`); «Сравнить с другой КПВ» · чис | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель ppfsum | органы: «Единиц X / Y» комплекта (`calc2.html:1579-1581`), имя и цвет каждой строки (`54-s | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель trade | органы: «Единиц X / Y» комплекта (`calc2.html:1611-1612`) · числа: «Режим», «Потребление п | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель tradeprice | органы: — · числа: «Равновесная Pw», «Экспортируют», «Излом КТВ», предупреждение «торговли | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель sdsum | органы: Две суммарные строки D и S: глаз, цвет, имя (О10) · числа: — | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель elast | органы: — · числа: «Точка спроса (Q, P)», «Зона спроса», «Точка предложения», «Зона предло | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель ext | органы: — · числа: Цены в строках «Рынок (D = S)» и «Оптимум» (3281-3283); «Корректирующая | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель prod | органы: Цвета TP, MP, AP (`calc2.html:1226-1230`) · числа: — | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель costs | органы: Цвета семи кривых (1177-1190); предупреждение о несогласованных MC, ATC, AVC (`44- | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель plants | органы: — · числа: «Сумма в лоб» TC₁(Q) + TC₂(Q) (1131) | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель isoquant | органы: Цвет веера (`calc2.html:1256`) · числа: — | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель mono | органы: Роли TC, ATC и «S как MC» (О9) · числа: P_c (`42-scenes-mono.js:170`), «Прибыль (T | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель mono-kink | органы: «Спрос 3 (необязательно)» (`calc2.html:1055-1056`); способ «Кусочный» с полями «Ве | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель labor | органы: — · числа: «Излишек рабочих», «Излишек фирм», «Занятость» при МРОТ (`46-scenes-lab | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель labor-mono | органы: — · числа: Блок МРОТ: «Занятость с МРОТ», «Зарплата», «Безработица» (656-659) | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель labor-union | органы: — · числа: «Желающих работать» (634), L_k и W_k (626-627, 638) | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель labor-bilat | органы: Галочка «Конкурентный ориентир» (`calc2.html:1354`; видимость проверить на экране) | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель smallopen | органы: — · числа: «Автаркия (Q*; P*)», «(CS; PS) при своб. торговле», «Внутренняя цена P₁ | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель consumer | органы: Тип полезности из пяти; подписи a и b меняются по типу, при смене типа ставятся св | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель cons-slutsky | органы: То же: тип из пяти, a и b, k, U(x, y), цвет веера. Заперта только галочка Слуцкого | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель loanable | органы: — · числа: «Частные инвестиции при новой r» (`50-scenes-macro.js:365`) | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель fx | органы: — · числа: «Объём при плавающем», «(Спрос; предложение)» (375, 378) | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| модель ineq | органы: Способ ввода: доли групп, «Доходы (через запятую)» (`calc2.html:1387`), «Функция Л | на месте (по решению строки сверки) | snapshot.mjs (layer new) + compare.mjs |
| Р1 | «роли TC и ATC у своей функции в „Издержках“» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р2 | «сохранить: Ctrl/⌘+Z и Ctrl/⌘+Shift+Z» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р3 | «История у каждой модели своя (как в calc2)» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р4 | «в файл график по-прежнему уходит на белом листе» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р5 | «TeX — нынешний генератор»; PDF «лист A4 с полями»; отдельные «Заголовок» и «Подпись под г | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р6 | Копируется «P = 20 + Q» (минус, запятая), тост «Скопировано: …» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р7 | Проценты «0…100 (акциз 0…90)» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р8 | Постоянные границы: сдвиг −50…50, ставка 0…150, цена 0…100 | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р9 | «Смена инструмента ставит 30 или 70» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р10 | Без первой четверти «окно раздвигается в минус на 12 %» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р11 | x₀ «−5…5»; Δx «0,1…3, шаг 0,05» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р12 | «меньше левого края — подтягивается к краю» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р13 | Ручка «вертикаль квоты» у монополии | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р14 | «рента» у модели «Квоты» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р15 | Стартовые записи islm, money, loanable, fx, πe у phillips | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р16 | «одни числа, без функций: consumer, cons-slutsky, phillips, ineq» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р17 | «своя точка прилипает к кривой в 14 px, к оси и к пересечению» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р18 | Ключевые точки: пересечения, точки с пунктиром к осям, проекции, изломы | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р19 | Итоговая функция «Уравнение касательной» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р20 | «Сбросить» без подтверждения по исключению из 2.8 в DESIGN.md 5.1 | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р21 | «настоящий минус U+2212» у чисел | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р22 | Слои: «шапка сайта 5 … окна 41, тосты 60» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р23 | «Системная палитра цвета → 12 цветов» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р24 | Буквы-исключения «Q/q, P/p, x/X, L/l, Y/y» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р25 | «Подсказка к формуле по роли → сохранить» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |
| Р26 | «в реестре „Вывод:“» | как в коде (спецификация ошибалась) | snapshot.mjs (layer new) + compare.mjs |

**Строк без судьбы: 0.**
