"""repair_wave1_gate — шлюз «не навреди» по починкам волны 1. ТОЛЬКО ЧТЕНИЕ.

Четыре проверки на каждую починку:

  а) последовательность ЧИСЕЛ И ЗНАКОВ (text_clean.same_numbers_and_signs).
     LaTeX-запятая «0{,}5» нормализуется внутри самой функции.
  б) ошибки движка KaTeX парами ДО/ПОСЛЕ — стало ли их больше. Считаются ДВА
     режима поломки: узел `.katex-error` и НЕИЗВЕСТНАЯ КОМАНДА внутри
     разобравшейся формулы, которая узла ошибки не создаёт вовсе
     (см. scripts/katex_damage.js).
  в) фактический ОТРИСОВАННЫЙ текст: не слиплись ли числа. Именно неизвестная
     команда (\\myarray) и склеивает соседние числа молча.
  г) шесть текстовых признаков ухудшения (revert_damage.compare_field).

⚠️ СВЕРЯЕТСЯ ЗАПИСЬ ЦЕЛИКОМ, А НЕ ПОЛЕ С ПОЛЕМ — переиспользуется
`repair_gate.record_pair`. Правка законно ПЕРЕНОСИТ текст между полями
(утёкший ответ уезжает в поле ответа, слипшееся условие разбивается на
подпункты), и полевая сверка краснела бы ровно на том, ради чего починку
затевали: в прошлый раз она дала 37 ложных провалов из 64.

⚠️ ТЕКСТОВЫЙ ПРЕДФИЛЬТР К ОШИБКАМ KaTeX СЛЕП — замерено на 1 762 полях.
Рендерим ВСЁ, без предотбора.

⚠️ ОТЛИЧИЕ ОТ ПРОБНИКА ЭКСПЕРИМЕНТА (repair_gate), два, оба существенные:
  1. Здесь работает БОЕВОЙ конвейер долларов (defect_review_export.PIPELINE_JS,
     он же в оболочке разбора), а не урезанный «$$ и $». Мерить надо ровно то,
     что увидит человек на экране разбора.
  2. Отрисованный текст читается с КЛОНА, из которого удалены `.katex-mathml`
     и `annotation`: KaTeX печатает каждую формулу трижды (вёрстка, MathML,
     исходный TeX в annotation), и `innerText` без этой чистки показывает
     числа формулы по три раза. Ловушка записана в CLAUDE.md.

Node в этом окружении нет, поэтому (б) и (в) считает настоящий браузер:
команда пишет katex_probe_*.html, страница считает всё сама и кладёт готовый
компактный результат в `window.RESULT_JSON`.

Запуск:
    venv\\Scripts\\python manage.py repair_wave1_gate            # готовит пробники
    venv\\Scripts\\python manage.py repair_wave1_gate --render reports/repair_wave1/katex_results.json
"""

import io
import json
import os
import re

from django.core.management.base import BaseCommand

from problems.revert_damage import compare_field, flag_labels
from problems.text_clean import same_numbers_and_signs, number_tokens
from problems.management.commands.repair_gate import record_pair, engine_only
from problems.management.commands.defect_review_export import PIPELINE_JS

OUT_DIR = os.path.join('reports', 'repair_wave1')
NUM_RE = re.compile(r'\d+(?:[.,]\d+)?')

LABELS = dict(flag_labels())
LABELS.update({
    'numbers_changed': 'изменилась последовательность чисел и знаков',
    'katex_errors_up': 'ошибок KaTeX стало больше',
    'katex_red_macro_up': 'появилась неизвестная команда в формуле '
                          '(.katex-error её НЕ создаёт)',
    'rendered_numbers_changed': 'цифры в ОТРИСОВАННОМ тексте другие '
                                '(тихая порча: потеря числа)',
    # ⚠️ Признак двусмысленный ПО ПРИРОДЕ, и подменять эту двусмысленность
    # успокаивающим словом нельзя. Ровно так выглядит и починка склейки
    # («$100 … $800» перестало быть формулой, и «7800» распалось на «7» и
    # «800»), и сама склейка («31» + «8p» → «318p», ловушка #27420). Цифры в
    # обоих случаях те же — различить может только человек глазами.
    'rendered_numbers_regrouped': 'числа в отрисованном тексте иначе разбиты, '
                                  'цифры те же (так выглядит и починка склейки, '
                                  'и новая склейка — смотреть глазами)',
    'not_rendered': 'рендер не прогонялся',
})


def load(name):
    return json.load(io.open(os.path.join(OUT_DIR, name), encoding='utf-8'))


class Command(BaseCommand):
    help = 'Шлюз «не навреди» по починкам волны 1. Только чтение.'

    def add_arguments(self, parser):
        parser.add_argument('--render', default='',
                            help='JSON с результатами рендера из браузера.')
        parser.add_argument('--chunk', type=int, default=40,
                            help='Пар на один пробник.')

    def say(self, line):
        try:
            self.stdout.write(line)
        except UnicodeEncodeError:
            self.stdout.write(line.encode('ascii', 'replace').decode())

    def handle(self, *args, **opts):
        sample = {r['id']: r for r in load('sample.json')}
        repairs = load('aa_repairs.json')['repairs']

        render = {}
        if opts['render'] and os.path.exists(opts['render']):
            for row in json.load(io.open(opts['render'], encoding='utf-8')):
                render[row['k']] = row

        results = []
        for rep in repairs:
            rec = sample.get(rep['id'])
            if rec is None:
                continue
            flags, details = [], []
            if rep['action'] == 'fixed':
                before, after = record_pair(rec['before'], rep.get('fields') or {})
                key = '%d|%s' % (rep['id'], rep['method'])

                if not same_numbers_and_signs(before, after):
                    flags.append('numbers_changed')
                    details.append({'check': 'numbers_changed',
                                    'before': number_tokens(before)[:40],
                                    'after': number_tokens(after)[:40]})

                for f in compare_field(before, after):
                    flags.append(f)
                    details.append({'check': f})

                r = render.get(key)
                if r is None:
                    flags.append('not_rendered')
                else:
                    if r['ea'] > r['eb']:
                        flags.append('katex_errors_up')
                        details.append({'check': 'katex_errors_up',
                                        'before': r['eb'], 'after': r['ea']})
                    if r['ra'] > r['rb']:
                        flags.append('katex_red_macro_up')
                        details.append({'check': 'katex_red_macro_up',
                                        'before': r['rb'], 'after': r['ra']})
                    if not r['sn']:
                        # ⚠️ Две разные беды. Цифры те же, а разбивка на токены
                        # другая — перегруппировка (так выглядит собранный
                        # список, у которого innerText склеивает строки).
                        # Различаются сами цифры — это потеря, она серьёзнее.
                        flag = ('rendered_numbers_regrouped' if r['sd']
                                else 'rendered_numbers_changed')
                        flags.append(flag)
                        details.append({'check': flag,
                                        'before': r.get('nb', [])[:30],
                                        'after': r.get('na', [])[:30]})

            uniq = sorted(set(flags))
            results.append({
                'id': rep['id'], 'method': rep['method'],
                'action': rep['action'],
                'gate_flags': uniq,
                'gate_labels': [LABELS.get(f, f) for f in uniq],
                'gate_passed': not [f for f in uniq if f != 'not_rendered'],
                'gate_rendered': rep['action'] != 'fixed'
                                 or 'not_rendered' not in uniq,
                'gate_details': details,
            })

        with io.open(os.path.join(OUT_DIR, 'gate.json'), 'w',
                     encoding='utf-8') as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1)

        self.write_report(results, bool(render))
        if not render:
            self.write_probe(sample, repairs, opts['chunk'])

    # ------------------------------------------------------------------
    def write_probe(self, sample, repairs, chunk):
        items = []
        for rep in repairs:
            rec = sample.get(rep['id'])
            if rec is None or rep['action'] != 'fixed':
                continue
            before, after = record_pair(rec['before'], rep.get('fields') or {})
            items.append({'k': '%d|%s' % (rep['id'], rep['method']),
                          'before': before, 'after': after})
        # ⚠️ Пробнику нужен только ДВИЖОК: считаем узлы и читаем текст, а
        # шрифты и CSS на это не влияют и весят втрое больше самого движка.
        # Цвет ошибки задаётся сентинелом прямо в вызове, поэтому
        # getComputedStyle работает и без katex.min.css.
        engine = engine_only()
        parts = [items[i:i + chunk] for i in range(0, len(items), chunk)] or [[]]
        for n, part in enumerate(parts, 1):
            page = ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
                    '<title>Пробник рендера %d</title>' % n + engine +
                    '</head><body><div id="status">готовлю…</div>'
                    '<div id="stage" style="position:absolute;left:-9999px">'
                    '</div><script>window.PAIRS='
                    + json.dumps(part, ensure_ascii=False) + ';</script>'
                    '<script>' + PIPELINE_JS + '</script>'
                    '<script>' + PROBE_JS + '</script></body></html>')
            with io.open(os.path.join(OUT_DIR, 'katex_probe_%d.html' % n), 'w',
                         encoding='utf-8') as fh:
                fh.write(page)
        self.say('')
        self.say('Пробников записано: %d (всего %d записей).'
                 % (len(parts), len(items)))
        self.say('Открой каждый в браузере, забери window.RESULT_JSON, склей '
                 'в один список и перезапусти с --render.')

    def write_report(self, results, rendered):
        fixed = [r for r in results if r['action'] == 'fixed']
        failed = [r for r in fixed if not r['gate_passed']]
        counts = {}
        for r in fixed:
            for f in r['gate_flags']:
                counts[f] = counts.get(f, 0) + 1

        L = ['# Шлюз «не навреди» по починкам волны 1 (Сборник АА)', '',
             'Починок всего: **%d**, из них с правкой (action=fixed): **%d**.'
             % (len(results), len(fixed)), '',
             'Не прошли шлюз: **%d** из %d.' % (len(failed), len(fixed)), '']
        if not rendered:
            L += ['⚠️ Рендер ещё не прогонялся: пункты (б) и (в) не считаны.', '']
        L += ['| Признак | Починок |', '|---|---:|']
        for f, n in sorted(counts.items(), key=lambda x: -x[1]):
            L.append('| %s | %d |' % (LABELS.get(f, f), n))
        L.append('')
        if failed:
            L += ['## Кто не прошёл', '', '| id | признаки |', '|---|---|']
            for r in failed:
                L.append('| #%d | %s |' % (r['id'], ', '.join(
                    LABELS.get(f, f) for f in r['gate_flags']
                    if f != 'not_rendered')))
            L.append('')
        L += ['⚠️ Ничего не отбраковано намеренно: на экране разбора видна '
              'пометка шлюза, и оценка человека заодно измеряет сам шлюз.', '']
        with io.open(os.path.join(OUT_DIR, 'gate_report.md'), 'w',
                     encoding='utf-8') as fh:
            fh.write('\n'.join(L) + '\n')

        self.say('=== ШЛЮЗ ===')
        self.say('починок: %d, с правкой: %d, не прошли: %d'
                 % (len(results), len(fixed), len(failed)))
        for f, n in sorted(counts.items(), key=lambda x: -x[1]):
            self.say('  %-42s %d' % (LABELS.get(f, f)[:42], n))


# Сентинел цвета ошибки — как в scripts/katex_damage.js. Автор задачи такой
# оттенок не напишет, поэтому всё, что им покрашено, гарантированно работа
# KaTeX, а не человека.
PROBE_JS = r"""
(function () {
  var SENT = '#010203', SENT_RGB = 'rgb(1, 2, 3)';
  var stage = document.getElementById('stage');
  var NUM = /\d+(?:[.,]\d+)?/g;

  /* Самые внешние узлы служебного цвета, мимо скрытой копии MathML.
     Правила и причины — scripts/katex_damage.js. */
  function countColored(root) {
    var hits = 0, all = root.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (el.closest && el.closest('.katex-mathml')) continue;
      if (getComputedStyle(el).color !== SENT_RGB) continue;
      var p = el.parentElement;
      if (p && p !== root && getComputedStyle(p).color === SENT_RGB) continue;
      hits++;
    }
    return hits;
  }

  /* Видимый текст: с клона, из которого выброшены скрытая копия MathML и
     annotation с исходным TeX. Без этого числа формулы считаются трижды. */
  function visibleText(box) {
    var clone = box.cloneNode(true);
    var junk = clone.querySelectorAll('.katex-mathml, annotation');
    for (var i = 0; i < junk.length; i++) junk[i].remove();
    document.body.appendChild(clone);
    var t = clone.innerText;
    clone.remove();
    return t;
  }

  function measure(text) {
    var d = document.createElement('div');
    d.className = 'qls-render';
    d.style.whiteSpace = 'pre-line';
    d.textContent = text;
    stage.appendChild(d);
    maskEscapedDollars(d);
    try {
      renderMathInElement(d, {
        delimiters: QLS_DELIMS, throwOnError: false, errorColor: SENT
      });
    } catch (e) {}
    fixCurrencyDollars(d);
    var errors = d.querySelectorAll('.katex-error').length;
    var colored = countColored(d);
    var txt = visibleText(d);
    stage.removeChild(d);
    return {
      err: errors,
      red: Math.max(0, colored - errors),
      nums: txt.match(NUM) || []
    };
  }

  var out = [];
  window.PAIRS.forEach(function (p) {
    var b = measure(p.before), a = measure(p.after);
    var digits = function (list) {
      return list.join('').split(',').join('').split('.').join('');
    };
    out.push({
      k: p.k, eb: b.err, ea: a.err, rb: b.red, ra: a.red,
      sn: b.nums.join('|') === a.nums.join('|'),
      sd: digits(b.nums) === digits(a.nums),
      nb: b.nums.slice(0, 30), na: a.nums.slice(0, 30)
    });
  });
  window.RESULT = out;
  window.RESULT_JSON = JSON.stringify(out);
  document.getElementById('status').textContent =
    'готово, записей: ' + out.length + '  (window.RESULT_JSON)';
})();
"""
