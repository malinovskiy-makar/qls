"""repair_gate — шлюз «не навреди» для починок эксперимента. ТОЛЬКО ЧТЕНИЕ.

Четыре проверки на каждую починенную пару поле-ДО / поле-ПОСЛЕ:

  а) последовательность ЧИСЕЛ И ЗНАКОВ (text_clean.same_numbers_and_signs).
     Любое изменение — красный флаг: чистка не имеет права менять числа.
     LaTeX-запятая «0{,}5» нормализуется внутри самой функции.
  б) ошибки движка KaTeX парами ДО/ПОСЛЕ — стало ли их больше.
  в) фактический ОТРИСОВАННЫЙ текст: не слиплись ли числа. Несуществующая
     команда (\\myarray) не даёт видимой ошибки — движок молча её выбрасывает,
     и соседние числа склеиваются («31»+«8p» → «318p»).
  г) шесть текстовых признаков ухудшения (revert_damage.compare_field).

⚠️ Текстовый предфильтр к ошибкам KaTeX СЛЕП, это замерено на 1 762 полях:
контрольная выборка из 100 полей без единого текстового признака дала три поля
с выросшим числом ошибок. Поэтому рендерим ВСЁ, без предотбора.

Node в этом окружении нет, поэтому пункты (б) и (в) считает настоящий браузер:
команда пишет katex_probe.html, страница рендерит все пары и кладёт результат
в JSON, который скармливается обратно ключом --render.

Запуск:
    venv\\Scripts\\python manage.py repair_gate            # готовит пробник
    venv\\Scripts\\python manage.py repair_gate --render reports/repair_experiment/katex_results.json
"""

import io
import json
import os
import re

from django.core.management.base import BaseCommand

from problems.revert_damage import compare_field, flag_labels
from problems.text_clean import same_numbers_and_signs, number_tokens

OUT_DIR = 'reports/repair_experiment'
FIELDS = ('statement', 'solution', 'answer')

NUM_RE = re.compile(r'\d+(?:[.,]\d+)?')


def whole_record(fields):
    """Вся запись одной строкой: условие + подпункты + решение + ответ.

    ⚠️ Шлюз сверяет ЗАПИСЬ ЦЕЛИКОМ, а не поле с полем. Починка законно
    ПЕРЕНОСИТ содержимое между полями: утёкший ответ уезжает из условия в поле
    ответа, слипшееся условие разбивается на подпункты. При сверке поле-к-полю
    это выглядит как «числа пропали из условия» и «текст усох» — то есть шлюз
    краснел бы ровно на том, ради чего починку и затевали.
    """
    parts = []
    for p in fields.get('parts') or []:
        parts.append((p.get('statement') or '') + ' ' + (p.get('answer') or ''))
    return '\n'.join([
        fields.get('statement') or '',
        '\n'.join(parts),
        fields.get('solution') or '',
        fields.get('answer') or '',
    ])


def record_pair(before, after_fields):
    """Пара «запись ДО → запись ПОСЛЕ» с наложенными правками."""
    after = json.loads(json.dumps(before))
    for k in ('statement', 'solution', 'answer', 'parts'):
        if k in (after_fields or {}):
            after[k] = after_fields[k]
    return whole_record(before), whole_record(after)


def pairs_of(before, after_fields):
    """Пары «поле ДО → поле ПОСЛЕ» по всем правленым полям, включая подпункты."""
    out = []
    for f in FIELDS:
        if f in after_fields:
            out.append((f, before.get(f) or '', after_fields[f] or ''))
    if 'parts' in after_fields:
        old = before.get('parts') or []
        new = after_fields['parts'] or []
        # Подпункты могли быть пересобраны, поэтому сравниваем СКЛЕЙКОЙ всех
        # подпунктов: пооперационное соответствие меток тут не гарантировано.
        old_text = '\n'.join((p.get('statement') or '') + ' ' + (p.get('answer') or '')
                             for p in old)
        new_text = '\n'.join((p.get('statement') or '') + ' ' + (p.get('answer') or '')
                             for p in new)
        out.append(('parts', old_text, new_text))
    return out


class Command(BaseCommand):
    help = 'Шлюз «не навреди» для починок эксперимента. Только чтение.'

    def add_arguments(self, parser):
        parser.add_argument('--render', default='',
                            help='JSON с результатами рендера из браузера.')

    def say(self, line):
        try:
            self.stdout.write(line)
        except UnicodeEncodeError:
            self.stdout.write(line.encode('ascii', 'replace').decode())

    def handle(self, *args, **options):
        sample = {r['id']: r for r in json.load(
            io.open(f'{OUT_DIR}/sample.json', encoding='utf-8'))}
        repairs = json.load(io.open(f'{OUT_DIR}/repairs.json', encoding='utf-8'))

        render = {}
        if options['render'] and os.path.exists(options['render']):
            for row in json.load(io.open(options['render'], encoding='utf-8')):
                render[row.get('key') or row['k']] = row

        results = []
        for rep in repairs:
            rec = sample.get(rep['id'])
            if rec is None:
                continue
            flags = []
            details = []
            if rep['action'] == 'fixed':
                before, after = record_pair(rec['before'], rep.get('fields') or {})
                key = '%d|%s|record' % (rep['id'], rep['method'])

                # (а) числа и знаки — по всей записи
                if not same_numbers_and_signs(before, after):
                    flags.append('numbers_changed')
                    details.append({
                        'field': 'запись целиком', 'check': 'numbers_changed',
                        'before': number_tokens(before)[:40],
                        'after': number_tokens(after)[:40],
                    })

                # (г) шесть текстовых признаков — по всей записи
                for f in compare_field(before, after):
                    flags.append(f)
                    details.append({'field': 'запись целиком', 'check': f})

                # (б) и (в) — из браузера
                field = 'запись целиком'
                r = render.get(key)
                if r:
                    eb = r.get('err_before', r.get('eb', 0))
                    ea = r.get('err_after', r.get('ea', 0))
                    if ea > eb:
                        flags.append('katex_errors_up')
                        details.append({'field': field,
                                        'check': 'katex_errors_up',
                                        'before': eb, 'after': ea})
                    if 'sn' in r:
                        same_nums, same_digits = r['sn'], r['sd']
                    else:
                        nb = NUM_RE.findall(r['text_before'])
                        na = NUM_RE.findall(r['text_after'])
                        same_nums = nb == na
                        same_digits = (''.join(nb).replace(',', '').replace('.', '')
                                       == ''.join(na).replace(',', '').replace('.', ''))
                    if not same_nums:
                        # ⚠️ Разделяем две разные беды. Если цифры те же, а
                        # разбивка на токены другая — это перегруппировка:
                        # так выглядит собранная таблица, у которой innerText
                        # склеивает ячейки строки. Если различаются сами
                        # цифры — это потеря, и она куда серьёзнее.
                        flag = ('rendered_numbers_regrouped' if same_digits
                                else 'rendered_numbers_changed')
                        flags.append(flag)
                        details.append({'field': field, 'check': flag})
                else:
                    flags.append('not_rendered')

            results.append({
                'id': rep['id'], 'method': rep['method'],
                'action': rep['action'],
                'gate_flags': sorted(set(flags)),
                'gate_passed': not [f for f in set(flags) if f != 'not_rendered'],
                'gate_details': details,
            })

        with io.open(f'{OUT_DIR}/gate.json', 'w', encoding='utf-8') as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1)

        self.write_report(results, bool(render))
        if not render:
            self.write_probe(sample, repairs)

    # ------------------------------------------------------------------

    def write_probe(self, sample, repairs):
        """HTML-пробник: браузер рендерит все пары и отдаёт JSON."""
        items = []
        for rep in repairs:
            rec = sample.get(rep['id'])
            if rec is None or rep['action'] != 'fixed':
                continue
            before, after = record_pair(rec['before'], rep.get('fields') or {})
            items.append({'key': '%d|%s|record' % (rep['id'], rep['method']),
                          'before': before, 'after': after})
        # ⚠️ Пробнику нужен только ДВИЖОК: мы считаем .katex-error и читаем
        # innerText. Шрифты и CSS на это не влияют, а весят втрое больше
        # самого движка — без них страница влезает в окно просмотра.
        js = engine_only()
        chunk = 24
        parts = [items[i:i + chunk] for i in range(0, len(items), chunk)] or [[]]
        for n, part in enumerate(parts, 1):
            page = ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
                    '<title>Пробник рендера %d</title>' % n + js +
                    '</head><body><div id="status">готовлю…</div>'
                    '<div id="stage" style="position:absolute;left:-9999px">'
                    '</div>'
                    '<script>window.PAIRS=' +
                    json.dumps(part, ensure_ascii=False) + ';</script>'
                    '<script>' + PROBE_JS + '</script></body></html>')
            with io.open(f'{OUT_DIR}/katex_probe_{n}.html', 'w',
                         encoding='utf-8') as fh:
                fh.write(page)
        self.say('Пробников записано: %d (всего %d пар полей)'
                 % (len(parts), len(items)))
        self.say('Открой каждый в браузере, забери window.RESULT, склей в '
                 'katex_results.json и перезапусти с --render.')

    def write_report(self, results, rendered):
        total = len(results)
        fixed = [r for r in results if r['action'] == 'fixed']
        failed = [r for r in fixed if not r['gate_passed']]
        counts = {}
        for r in fixed:
            for f in r['gate_flags']:
                if f != 'not_rendered':
                    counts[f] = counts.get(f, 0) + 1
        labels = flag_labels()
        labels.update({
            'numbers_changed': 'изменилась последовательность чисел и знаков',
            'katex_errors_up': 'ошибок KaTeX стало больше',
            'rendered_numbers_changed': 'цифры в ОТРИСОВАННОМ тексте другие '
                                        '(тихая порча: потеря числа)',
            'rendered_numbers_regrouped': 'в отрисованном тексте числа '
                                          'перегруппированы, цифры те же '
                                          '(обычно собранная таблица)',
        })

        L = ['# Шлюз «не навреди» по починкам эксперимента', '',
             f'Починок всего: **{total}**, из них с правкой (action=fixed): '
             f'**{len(fixed)}**.', '',
             f'Не прошли шлюз: **{len(failed)}** из {len(fixed)}.', '']
        if not rendered:
            L.append('⚠️ Рендер ещё не прогонялся: пункты про KaTeX не считаны.')
            L.append('')
        L.append('| Признак | Починок |')
        L.append('|---|---:|')
        for f, n in sorted(counts.items(), key=lambda x: -x[1]):
            L.append(f'| {labels.get(f, f)} | {n} |')
        L.append('')
        if failed:
            L.append('## Кто не прошёл')
            L.append('')
            L.append('| id | способ | признаки |')
            L.append('|---|---|---|')
            for r in failed:
                fl = ', '.join(labels.get(f, f) for f in r['gate_flags']
                               if f != 'not_rendered')
                L.append(f'| #{r["id"]} | {r["method"]} | {fl} |')
            L.append('')
        L.append('⚠️ Ничего не отбраковано намеренно: человек увидит и те '
                 'починки, что шлюз не пропустил — нам надо измерить и сам '
                 'шлюз тоже.')
        L.append('')
        with io.open(f'{OUT_DIR}/gate_report.md', 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(L) + '\n')
        self.say('Починок: %d, с правкой: %d, не прошли шлюз: %d'
                 % (total, len(fixed), len(failed)))


def engine_only():
    """Только движок KaTeX, без CSS и шрифтов.

    Пробнику нужно лишь посчитать `.katex-error` и прочитать innerText —
    оформление на это не влияет, а вес страницы решает: со шрифтами она
    не открывается в окне просмотра.
    """
    base = 'reports/review_bundles/ile_20260721/assets/vendor/katex'
    try:
        js = io.open(os.path.join(base, 'katex.min.js'), encoding='utf-8').read()
        ar = io.open(os.path.join(base, 'contrib', 'auto-render.min.js'),
                     encoding='utf-8').read()
    except OSError:
        return ''
    return '<script>' + js + '</script><script>' + ar + '</script>'


def katex_head():
    """KaTeX из пакета ревью — вшиваем, чтобы пробник работал с file://."""
    import base64
    base = 'reports/review_bundles/ile_20260721/assets/vendor/katex'
    try:
        css = io.open(os.path.join(base, 'katex.min.css'), encoding='utf-8').read()
        js = io.open(os.path.join(base, 'katex.min.js'), encoding='utf-8').read()
        ar = io.open(os.path.join(base, 'contrib', 'auto-render.min.js'),
                     encoding='utf-8').read()
    except OSError:
        return ''
    fonts = os.path.join(base, 'fonts')

    def sub(m):
        p = os.path.join(fonts, m.group(1))
        if not os.path.exists(p):
            return m.group(0)
        b64 = base64.b64encode(open(p, 'rb').read()).decode('ascii')
        return 'url(data:font/woff2;base64,' + b64 + ')'

    css = re.sub(r'url\(fonts/([A-Za-z0-9_\-]+\.woff2)\)', sub, css)
    css = re.sub(r",\s*url\(fonts/[^)]+\)\s*format\(['\"](?:woff|truetype)['\"]\)",
                 '', css)
    return ('<style>' + css + '</style><script>' + js + '</script>'
            '<script>' + ar + '</script>')


PROBE_JS = r"""
(function(){
  var stage=document.getElementById('stage');
  var out=[];
  function render(text){
    var d=document.createElement('div');
    d.textContent=text;
    stage.appendChild(d);
    var errs=0;
    try{
      renderMathInElement(d,{delimiters:[{left:'$$',right:'$$',display:true},
        {left:'$',right:'$',display:false}],throwOnError:false,
        errorColor:'#cc0000'});
    }catch(e){}
    errs=d.querySelectorAll('.katex-error').length;
    var txt=d.innerText;
    stage.removeChild(d);
    return {errs:errs,txt:txt};
  }
  window.PAIRS.forEach(function(p){
    var b=render(p.before), a=render(p.after);
    out.push({key:p.key,err_before:b.errs,err_after:a.errs,
              text_before:b.txt,text_after:a.txt});
  });
  window.RESULT=out;
  document.getElementById('status').textContent =
    'готово, пар: '+out.length+'  (window.RESULT)';
})();
"""
