"""matek_zero_step — разведка и ПРОТОТИП починки структуры МатЭка.

⚠️ ТОЛЬКО ЧИТАЕТ. В базу не пишет ни одной буквы. Применение — отдельной
сессией, после решения владельца.

ЧТО ЧИНИМ. У части задач МатЭка подпункты «г», «д», «е» — это не вопросы, а
РЕШЕНИЯ к пунктам «а», «б», «в»: разбор жюри лежал в `.tex` следом за
условием, и импорт разрезал задачу не там. Ученик видит ответы прямо в
условии.

ПОЧЕМУ ПРЕОБРАЗОВАНИЕ БЕЗОПАСНО. Предлагаемая правка — ПЕРЕНОС, а не
переписывание: текст второй половины уезжает в решение соответствующего
пункта, ни один символ не меняется. Поэтому её можно проверить не на глаз, а
числом.

⚠️ ШЛЮЗ СВЕРЯЕТ ЗАПИСЬ ЦЕЛИКОМ, А НЕ ПОЛЕ С ПОЛЕМ. Правка законно переносит
текст между полями, и полевая сверка покраснела бы ровно на том, ради чего
починку затевали (в прошлой сессии полевой шлюз дал 37 ложных провалов из
64). Поэтому числа и знаки собираются со ВСЕЙ записи — условие, все пункты,
решение, ответ — и сравниваются одним списком.

⚠️ ДЕТЕКТОР НЕ ЗАМЕНЯЕТ ОРИГИНАЛ. Замерено на 14 известных случаях: длина
второй половины относительно первой гуляет от 0.24 до 6.8, а признак «в
тексте есть формула» пропускает гуманитарные разборы. Единственный надёжный
признак — форма меток (подряд, чётное число), и он лишь НЕОБХОДИМЫЙ, а не
достаточный. Настоящая сверка — с авторским `.tex`; сюда она не встроена,
потому что `materials/` на этой машине нет.

    venv\\Scripts\\python manage.py matek_zero_step
    venv\\Scripts\\python manage.py matek_zero_step --limit 30
"""

import io
import os
import re

from django.core.management.base import BaseCommand

from problems.models import Problem, ReviewVerdict
from problems.text_clean import number_tokens

OUT_DIR = os.path.join('reports', 'matek_zero_step')
BUNDLE = 'matek_20260808'
ALPHA = 'абвгдежзиклмн'

# Комментарий, которым владелец прямо назвал этот дефект.
DIRECT_RE = re.compile(r'г\s*д\s*е\s*это\s*решени', re.IGNORECASE)
# Более широкая семья комментариев про решение и ответ.
FAMILY_RE = re.compile(r'(решени|ответ)', re.IGNORECASE)


def parts_of(problem):
    return sorted(problem.parts.all(), key=lambda x: (x.order, x.pk))


def shape_ok(parts):
    """Метки идут подряд с «а» и делятся ровно пополам.

    НЕОБХОДИМЫЙ признак, не достаточный: он лишь говорит, что задачу вообще
    можно разрезать пополам. Что вторая половина — решения, знает только
    оригинал (или человек).
    """
    labels = [(p.label or '').strip().lower() for p in parts]
    n = len(labels)
    return n >= 4 and n % 2 == 0 and labels == list(ALPHA[:n])


def record_tokens(statement, parts_text, solution, answer):
    """Числа и знаки ВСЕЙ записи одним списком (см. докстринг про шлюз)."""
    return number_tokens('\n'.join(
        [statement or ''] + list(parts_text) + [solution or '', answer or '']))


def propose(problem, parts):
    """Что предлагается сделать. Ничего не пишет, только считает.

    Возвращает (план, ДО-токены, ПОСЛЕ-токены) либо None.
    """
    if not shape_ok(parts):
        return None
    half = len(parts) // 2
    questions, answers = parts[:half], parts[half:]

    before = record_tokens(problem.statement,
                           [p.statement or '' for p in parts],
                           problem.solution, problem.answer)

    moves = []
    for q, a in zip(questions, answers):
        moves.append({'question_pk': q.pk, 'question_label': q.label,
                      'solution_pk': a.pk, 'solution_label': a.label,
                      'text': a.statement or ''})

    # ПОСЛЕ: условие и вопросы на месте, тексты второй половины переезжают в
    # решения своих пунктов, сами подпункты-решения исчезают.
    after = record_tokens(problem.statement,
                          [p.statement or '' for p in questions]
                          + [m['text'] for m in moves],
                          problem.solution, problem.answer)
    return {'moves': moves, 'half': half}, before, after


class Command(BaseCommand):
    help = ('Разведка и прототип починки структуры МатЭка. '
            'Только читает, в базу не пишет.')

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=30,
                            help='сколько задач взять в прототип')

    def handle(self, *args, **opts):
        say = self.stdout.write
        os.makedirs(OUT_DIR, exist_ok=True)

        verdicts = {}
        for rv in ReviewVerdict.objects.filter(bundle=BUNDLE):
            rec = verdicts.setdefault(rv.problem_id,
                                      {'cats': set(), 'comment': ''})
            rec['cats'].add(rv.category)
            if rv.comment:
                rec['comment'] = rv.comment

        defect = {pid for pid, r in verdicts.items() if r['cats'] != {'perfect'}}
        perfect = set(verdicts) - defect

        direct = {pid for pid in defect
                  if DIRECT_RE.search(verdicts[pid]['comment'] or '')}
        family = {pid for pid in defect
                  if FAMILY_RE.search(verdicts[pid]['comment'] or '')}

        say('=== ВЕРДИКТЫ МатЭка ===')
        say('  дефектных                       : {}'.format(len(defect)))
        say('  из них с комментарием про решение/ответ: {}'.format(len(family)))
        say('  из них прямо «г д е это решение»: {}'.format(len(direct)))

        # --- охват: сколько задач вообще имеет разрезаемую форму ---
        def shaped(ids):
            out = set()
            for p in (Problem.objects.filter(id__in=ids)
                      .prefetch_related('parts')):
                if shape_ok(parts_of(p)):
                    out.add(p.id)
            return out

        shaped_defect = shaped(defect)
        shaped_perfect = shaped(perfect)
        say('')
        say('=== ФОРМА «метки подряд, чётное число» ===')
        say('  среди дефектных : {} из {}'.format(len(shaped_defect), len(defect)))
        say('  среди идеальных : {} из {}  <- сверка затронет и их'
            .format(len(shaped_perfect), len(perfect)))
        say('  прямых случаев держат форму: {} из {}'
            .format(len(direct & shaped_defect), len(direct)))

        # --- прототип: предпросмотр переноса, БЕЗ ЗАПИСИ ---
        order = ([pid for pid in sorted(direct)]
                 + [pid for pid in sorted(shaped_defect - direct)])
        chosen = order[:opts['limit']]

        rows, passed, failed = [], 0, 0
        for p in (Problem.objects.filter(id__in=chosen)
                  .prefetch_related('parts')):
            parts = parts_of(p)
            got = propose(p, parts)
            if got is None:
                rows.append({'pid': p.id, 'ok': None,
                             'why': 'форма не подходит — предлагать нечего',
                             'comment': verdicts[p.id]['comment'],
                             'moves': []})
                continue
            plan, before, after = got
            ok = (before == after)
            passed += ok
            failed += (not ok)
            rows.append({'pid': p.id, 'ok': ok,
                         'why': ('числа и знаки записи целиком совпали'
                                 if ok else 'ЧИСЛА РАЗОШЛИСЬ — не применять'),
                         'comment': verdicts[p.id]['comment'],
                         'moves': plan['moves'],
                         'problem': p, 'parts': parts})

        say('')
        say('=== ПРОТОТИП (в базу НЕ пишем) ===')
        say('  задач в прототипе               : {}'.format(len(rows)))
        say('  шлюз «не навреди» пройден       : {}'.format(passed))
        say('  шлюз провален                   : {}'.format(failed))
        say('  формы нет (предлагать нечего)   : {}'
            .format(sum(1 for r in rows if r['ok'] is None)))

        self.write_preview(rows)
        say('')
        say('Предпросмотр: {}'.format(os.path.join(OUT_DIR, 'preview.html')))

        return None

    # ------------------------------------------------------------------
    def write_preview(self, rows):
        def esc(s):
            return (str(s or '').replace('&', '&amp;')
                    .replace('<', '&lt;').replace('>', '&gt;'))

        html = ["""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>МатЭк — прототип переноса решений</title><style>
body{font:15px/1.5 -apple-system,"Segoe UI",sans-serif;margin:0;padding:20px;
     background:#f6f7f9;color:#1b2330}
h1{font-size:20px}
.z-card{background:#fff;border:1px solid #d8dce3;border-radius:8px;
        padding:12px;margin-bottom:14px}
.z-ok{border-left:4px solid #1d7e45}
.z-bad{border-left:4px solid #b00020}
.z-skip{border-left:4px solid #b26b00}
.z-head{font-weight:700;margin-bottom:4px}
.z-cmt{background:#fff7e6;padding:5px 9px;border-radius:6px;font-size:13px;
       margin-bottom:8px}
.z-move{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:8px}
.z-q,.z-s{border:1px solid #e2e6ec;border-radius:6px;padding:7px;
          white-space:pre-wrap;font-size:13px;overflow-wrap:anywhere}
.z-q{background:#f7fbff}.z-s{background:#f7fff9}
.z-lbl{font-size:11px;text-transform:uppercase;letter-spacing:.05em;
       color:#5b6675;margin-bottom:3px}
.z-why{font-size:12px;color:#5b6675}
</style></head><body>
<h1>МатЭк — прототип переноса решений (в базу НЕ писали)</h1>
<p>Слева пункт-вопрос, справа пункт, который на самом деле является его
решением. Предлагаемая правка — перенос текста справа в решение пункта
слева, буква в букву.</p>"""]

        for r in rows:
            cls = ('z-ok' if r['ok'] else 'z-bad') if r['ok'] is not None else 'z-skip'
            html.append('<div class="z-card {}">'.format(cls))
            html.append('<div class="z-head">#{} — {}</div>'.format(
                r['pid'], esc(r['why'])))
            if r['comment']:
                html.append('<div class="z-cmt">Ревьюер: {}</div>'
                            .format(esc(r['comment'])))
            for m in r['moves']:
                q = next((p for p in r['parts'] if p.pk == m['question_pk']), None)
                html.append('<div class="z-move">')
                html.append('<div><div class="z-lbl">пункт {} — вопрос</div>'
                            '<div class="z-q">{}</div></div>'.format(
                                esc(m['question_label']),
                                esc((q.statement if q else '')[:900])))
                html.append('<div><div class="z-lbl">пункт {} — это решение '
                            'к нему</div><div class="z-s">{}</div></div>'.format(
                                esc(m['solution_label']), esc(m['text'][:900])))
                html.append('</div>')
            html.append('</div>')

        html.append('</body></html>')
        with io.open(os.path.join(OUT_DIR, 'preview.html'), 'w',
                     encoding='utf-8') as fh:
            fh.write('\n'.join(html))
