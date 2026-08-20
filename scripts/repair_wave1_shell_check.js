/**
 * Проверка оболочки разбора починок — прожимает клавиши как ревьюер.
 *
 * ⚠️ NODE НА ЭТОЙ МАШИНЕ НЕТ (нет ни package.json, ни node_modules, ни самого
 * node), поэтому запустить это Playwright-ом, как остальные scripts/*.js,
 * нельзя. Файл написан так, чтобы работать ПРЯМО В СТРАНИЦЕ: открыть
 * reviewer.html и вставить содержимое в консоль браузера (или выполнить через
 * встроенный браузер сессии). Когда node появится, обёртка Playwright сведётся
 * к page.evaluate(этого текста).
 *
 * Пакет крупнее ~0,5 МБ встроенный браузер по file:// не открывает (он
 * разворачивает файл в data:-URL), поэтому для проверки он отдаётся по http:
 * конфигурация `wave1-bundle` в .claude/launch.json поднимает http.server над
 * КОРНЕМ проекта, и страница лежит на
 * http://localhost:8402/reports/repair_wave1/reviewer.html — оттуда же
 * fetch-ом берётся и этот файл. Владельцу сервер не нужен: он открывает
 * reviewer.html двойным щелчком, и file:// в его браузере работает.
 *
 * Что проверяется: клавиши исходов и стрелки, повторное нажатие снимает
 * оценку, цитата с настоящего выделения несёт сторону/поле/вид, состояние
 * переживает перезагрузку, выгрузка собирается в правильном формате.
 *
 * Возвращает объект {ok, checks: [...]}: каждая строка «что проверяли» и
 * «сошлось ли».
 */
(function () {
  var checks = [];
  function ok(name, cond, detail) {
    checks.push({ name: name, ok: !!cond, detail: detail === undefined ? '' : String(detail) });
  }
  function key(k) {
    document.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true }));
  }
  function code(c) {
    document.dispatchEvent(new KeyboardEvent('keydown', { code: c, bubbles: true }));
  }

  if (typeof QLS_SHELL === 'undefined') {
    return { ok: false, checks: [{ name: 'оболочка загрузилась', ok: false }] };
  }
  QLS_SHELL.reset();

  var total = document.querySelectorAll('.qls-screen').length;
  ok('экранов больше нуля', total > 0, total);

  /* --- кнопки строятся из словаря, категорий дефекта среди них нет --- */
  var keys = [].map.call(document.querySelectorAll('.qls-out'),
                         function (b) { return b.dataset.key; });
  ok('пять кнопок исхода', keys.length === 5, keys.join(','));
  ok('категорий дефекта среди кнопок нет',
     keys.indexOf('broken_formula') === -1 && keys.indexOf('perfect') === -1);

  /* --- клавиши --- */
  var p0 = QLS_SHELL.pid();
  key('1');
  ok('клавиша 1 листает дальше', QLS_SHELL.pid() !== p0);
  key('ArrowLeft');
  ok('стрелка влево возвращает', QLS_SHELL.pid() === p0);
  var doc = QLS_SHELL.buildDoc('проверка');
  var first = doc.verdicts.filter(function (v) { return String(v.problem_id) === String(p0); })[0];
  ok('исход записан', first && first.outcome === 'fixed_perfect',
     first && first.outcome);
  key('1');                       /* повтор того же исхода снимает оценку */
  doc = QLS_SHELL.buildDoc('проверка');
  first = doc.verdicts.filter(function (v) { return String(v.problem_id) === String(p0); })[0];
  ok('повторное нажатие снимает оценку', !first || !first.outcome);
  key('4');
  ok('после снятия ставится другой исход',
     QLS_SHELL.buildDoc('x').verdicts[0].outcome === 'broke');
  key('ArrowLeft');

  /* --- цитата с настоящего выделения --- */
  var cur = document.querySelector('.qls-screen.qls-cur');
  var zone = cur.querySelector('.qls-field[data-side="after"] .qls-render');
  var r = document.createRange();
  r.selectNodeContents(zone);
  var sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(r);
  var oldPrompt = window.prompt;
  window.prompt = function () { return 'проверка цитаты'; };
  code('KeyC');                   /* по коду клавиши, а не по букве */
  window.prompt = oldPrompt;
  doc = QLS_SHELL.buildDoc('проверка');
  var q = (doc.verdicts.filter(function (v) { return v.quotes.length; })[0] || {}).quotes;
  ok('цитата привязалась', q && q.length === 1);
  if (q && q.length) {
    ok('у цитаты есть версия', q[0].side === 'after', q[0].side);
    ok('у цитаты есть поле', !!q[0].field, q[0].field);
    ok('у цитаты есть вид', q[0].view === 'rendered', q[0].view);
    ok('у цитаты есть заметка', q[0].note === 'проверка цитаты');
    /* Скрытая копия MathML тащит за собой распорки нулевой ширины и
       повтор формулы; приватный сентинел доллара наружу выходить не
       должен вовсе. Ловим все три. */
    ok('в цитате нет приватного сентинела доллара',
       q[0].text.indexOf('\ue000') === -1);
    ok('в цитате нет распорок нулевой ширины',
       !/[\u200B\u200C\uFEFF]/.test(q[0].text));
    ok('в цитате нет удвоенного куска',
       !/(.{20,})\1/.test(q[0].text));
  }
  ok('цитата видна на экране',
     cur.querySelectorAll('.qls-quote').length === 1);

  /* --- формат выгрузки --- */
  ok('формат выгрузки объявлен',
     doc.format === 'qls-repair-verdicts-v1', doc.format);
  ok('пакет назван', doc.bundle_id === 'repair_aa_20260728', doc.bundle_id);
  ok('в записи едут категории первого прохода',
     Array.isArray(doc.verdicts[0].origin_categories));

  /* --- переключатель исходника --- */
  var before = cur.querySelectorAll('.qls-raw[hidden]').length;
  document.getElementById('qls-toggle').click();
  var after = cur.querySelectorAll('.qls-raw[hidden]').length;
  ok('кнопка показывает исходник', before > 0 && after === 0, before + '->' + after);
  document.getElementById('qls-toggle').click();
  ok('кнопка возвращает отрендеренный вид',
     cur.querySelectorAll('.qls-raw[hidden]').length === before);

  return {
    ok: checks.every(function (c) { return c.ok; }),
    checks: checks
  };
})();
