"""Замер tikz-кода по ВСЕМУ банку (только чтение, ничего не чинит).

Карточка Notion 3abb11c92bc1811f8514c33ac8eee827: KaTeX 0.16.9 не поддерживает
tikzpicture вообще — где исходник чертежа лежит в тексте, ученик видит стену
LaTeX-кода вместо графика. Прошлый замер прошёл только по ILE (нашёл 1 задачу);
здесь — по всем источникам и всем видимым полям.

Важное отличие от очереди missing_figure (1 772 задачи, где рисунок потерян
безвозвратно): тут исходник ЦЕЛ, просто не отрисован — не потеря, а
нереализованный актив.

Видимые поля = условие задачи + условия подпунктов у ОПУБЛИКОВАННЫХ и НЕ
зафлагованных задач. Дополнительно (отдельной строкой отчёта) считается охват
за шлюзом качества и в поле solution — прошлый замер их не покрывал и это
было записано оговоркой.

    ./venv/bin/python manage.py tikz_census

Выход: reports/tikz/tikz_census.md, reports/tikz/tikz_ids.txt
"""

import os
import re
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Q

from problems.models import Problem

OUT_DIR = "reports/tikz"
REPORT = os.path.join(OUT_DIR, "tikz_census.md")
IDS = os.path.join(OUT_DIR, "tikz_ids.txt")

# Признаки исходника чертежа в тексте. \draw[ и \foreach — команды tikz,
# \addplot — pgfplots; \begin{tikzpicture} и \begin{axis} — окружения.
TIKZ_MARKERS = (
    ('tikzpicture', re.compile(r'\\begin\{tikzpicture\}')),
    ('axis_env', re.compile(r'\\begin\{axis\}')),
    ('addplot', re.compile(r'\\addplot')),
    ('draw', re.compile(r'\\draw\s*[\[(]')),
    ('foreach', re.compile(r'\\foreach')),
    ('node', re.compile(r'\\node\s*[\[(]')),
)

BEGIN_RE = re.compile(r'\\begin\{(tikzpicture|axis|scope)\}')
END_RE = re.compile(r'\\end\{(tikzpicture|axis|scope)\}')

# Очередь пере-импорта Батча 2: задачи, пропущенные по флагам Sonnet
# missing_figure / truncated (1 772 строки, формат «<id>\tflags:<флаг>»).
MISSING_FIGURE_QUEUE = "reports/batch2/skipped_flagged.txt"

# Контрольные примеры из карточки Notion: замер обязан их найти, иначе он
# ничего не доказывает. #30091 — это и есть «Фаст про излишки» (Фаст —
# персонаж в условии, а не слово из заголовка).
CONTROL_IDS = {4541: 'из карточки', 28800: '«Считай точки»',
               30091: '«Фаст про излишки»'}


def tikz_hits(text):
    """Какие признаки tikz есть в тексте."""
    t = text or ''
    return [name for name, rx in TIKZ_MARKERS if rx.search(t)]


def is_syntactically_whole(text):
    """Груб., но честно: у каждого \\begin{...} есть парный \\end{...}.

    Синтаксическая целость тут значит «чертёж можно попытаться отрисовать»,
    а не «tikz скомпилируется» — компилятора у нас нет и он тут не нужен.
    """
    t = text or ''
    opens = Counter(BEGIN_RE.findall(t))
    closes = Counter(END_RE.findall(t))
    if not opens and not closes:
        # Есть команды (\draw/\addplot), но нет окружения — обрубок.
        return False
    return opens == closes


class Command(BaseCommand):
    help = 'Сколько задач банка содержат tikz-код в видимых полях (замер).'

    def handle(self, *args, **opts):
        visible = Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                         needs_quality_review=False)
        self.stdout.write('Видимых задач: {}'.format(visible.count()))

        found = {}     # pid -> dict
        by_source = defaultdict(set)
        marker_counter = Counter()

        qs = (visible.prefetch_related('parts', 'source_references__source')
              .only('id', 'title', 'statement'))
        # Сначала грубо сузим выборку по базе, чтобы не тащить 19 тысяч задач.
        rough = Q(statement__contains='\\draw') | Q(statement__contains='tikz') | \
                Q(statement__contains='\\addplot') | Q(statement__contains='\\foreach') | \
                Q(parts__statement__contains='\\draw') | Q(parts__statement__contains='tikz') | \
                Q(parts__statement__contains='\\addplot') | Q(parts__statement__contains='\\foreach')
        qs = qs.filter(rough).distinct()

        for p in qs:
            texts = [('statement', p.statement or '')]
            for part in p.parts.all():
                texts.append(('part:{}'.format(part.label or part.pk),
                              part.statement or ''))
            hits, whole, fields = set(), True, []
            for field, text in texts:
                h = tikz_hits(text)
                if not h:
                    continue
                hits.update(h)
                fields.append(field)
                if not is_syntactically_whole(text):
                    whole = False
            if not hits:
                continue
            ref = next(iter(p.source_references.all()), None)
            src = ref.source.name if ref and ref.source else '(без источника)'
            found[p.id] = {'title': p.title or '', 'source': src,
                           'hits': sorted(hits), 'whole': whole, 'fields': fields}
            by_source[src].add(p.id)
            for h in hits:
                marker_counter[h] += 1

        whole_n = sum(1 for v in found.values() if v['whole'])
        self.stdout.write(self.style.SUCCESS(
            'Задач с tikz в видимых полях: {} (синтаксически целых: {})'
            .format(len(found), whole_n)))

        overlap = self._missing_figure_overlap(set(found))
        wider = self._wider_coverage()
        self._write(found, by_source, marker_counter, whole_n, overlap, wider)
        self.stdout.write('Отчёт → {}'.format(REPORT))

        for pid, v in sorted(found.items()):
            self.stdout.write('  #{} [{}] {} — {}{}'.format(
                pid, v['source'][:28], v['title'][:38], ', '.join(v['hits']),
                '' if v['whole'] else '  ⚠ обрубок'))

    def _missing_figure_overlap(self, pids):
        """Пересечение с очередью пере-импорта «потерян рисунок / обрублено»."""
        if not os.path.exists(MISSING_FIGURE_QUEUE):
            return None
        queue, only_figure = set(), set()
        with open(MISSING_FIGURE_QUEUE, encoding='utf-8') as f:
            for line in f:
                parts = line.split()
                if not parts or not parts[0].isdigit():
                    continue
                pid = int(parts[0])
                queue.add(pid)
                if 'missing_figure' in line:
                    only_figure.add(pid)
        return {'queue_size': len(queue), 'figure_only': len(only_figure),
                'overlap': sorted(pids & queue),
                'overlap_figure': sorted(pids & only_figure)}

    def _wider_coverage(self):
        """Охват за пределами видимых условий — то, чего не было в прошлом замере."""
        rough_sol = (Q(solution__contains='\\draw') | Q(solution__contains='tikz') |
                     Q(solution__contains='\\addplot') | Q(solution__contains='\\foreach'))
        in_solution = set(Problem.objects.filter(rough_sol).values_list('id', flat=True))
        sol_real = set()
        for p in Problem.objects.filter(id__in=in_solution).only('id', 'solution'):
            if tikz_hits(p.solution):
                sol_real.add(p.id)

        rough_st = (Q(statement__contains='\\draw') | Q(statement__contains='tikz') |
                    Q(statement__contains='\\addplot') | Q(statement__contains='\\foreach'))
        hidden = Problem.objects.filter(rough_st).exclude(
            status=Problem.Status.PUBLISHED, needs_quality_review=False)
        hidden_real = {p.id for p in hidden.only('id', 'statement')
                       if tikz_hits(p.statement)}
        return {'solution': sorted(sol_real), 'hidden': sorted(hidden_real)}

    def _write(self, found, by_source, markers, whole_n, overlap, wider):
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(IDS, 'w', encoding='utf-8') as f:
            for pid in sorted(found):
                f.write('{}\n'.format(pid))

        L = []
        L.append('# tikz-код в банке — замер по всем источникам (Задача 4)\n')
        L.append('Карточка Notion 3abb11c92bc1811f8514c33ac8eee827. KaTeX 0.16.9 '
                 'tikzpicture не поддерживает — где исходник чертежа лежит в '
                 'тексте, ученик видит стену LaTeX-кода. Только замер.\n')
        L.append('Прошлый замер шёл ТОЛЬКО по ILE и нашёл 1 задачу. Здесь — '
                 'все источники, все видимые поля (условие + подпункты).\n')

        L.append('## Итог\n')
        L.append('| | Задач |')
        L.append('|---|---:|')
        L.append('| **Задач с tikz в видимых полях** | **{}** |'.format(len(found)))
        L.append('| из них синтаксически целых (все `\\begin` закрыты) | {} |'.format(whole_n))
        L.append('| из них обрубков | {} |'.format(len(found) - whole_n))
        L.append('')
        if found:
            L.append('Доля целых: **{:.0f}%**.'
                     .format(100.0 * whole_n / len(found)))
        L.append('')

        L.append('## По источникам\n')
        L.append('| Источник | Задач |')
        L.append('|---|---:|')
        for src, pids in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
            L.append('| {} | {} |'.format(src, len(pids)))
        L.append('')

        L.append('## По признакам\n')
        L.append('| Признак | Задач |')
        L.append('|---|---:|')
        for name, n in markers.most_common():
            L.append('| `{}` | {} |'.format(name, n))
        L.append('')

        L.append('## Пересечение с очередью missing_figure\n')
        if overlap is None:
            L.append('Не посчитано: файла очереди `{}` нет.'.format(MISSING_FIGURE_QUEUE))
        else:
            L.append('Очередь пере-импорта (`{}`): {} задач, из них с флагом '
                     '`missing_figure` — {}.'
                     .format(MISSING_FIGURE_QUEUE, overlap['queue_size'],
                             overlap['figure_only']))
            L.append('')
            L.append('Пересечение с tikz: **{}** (по флагу `missing_figure` — {}){}'
                     .format(len(overlap['overlap']), len(overlap['overlap_figure']),
                             ('  — ' + ', '.join('#{}'.format(i) for i in overlap['overlap']))
                             if overlap['overlap'] else '.'))
            L.append('')
            L.append('Пустое или малое пересечение — ожидаемо и это ХОРОШАЯ '
                     'новость: очередь missing_figure про потерянные рисунки, '
                     'а tikz — про целые, но не отрисованные. Разные классы.')
        L.append('')

        L.append('## Охват, которого не было в прошлом замере\n')
        L.append('Прошлый замер честно оговаривал, что не смотрит поле '
                 '`solution` и задачи за шлюзом качества. Смотрим:\n')
        L.append('| Где | Задач |')
        L.append('|---|---:|')
        L.append('| tikz в поле `solution` (любой статус) | {} |'.format(len(wider['solution'])))
        L.append('| tikz в условии у задач ВНЕ видимой выдачи | {} |'.format(len(wider['hidden'])))
        L.append('')
        if wider['hidden']:
            L.append('Скрытые: {}'.format(
                ', '.join('#{}'.format(i) for i in wider['hidden'][:40])))
            L.append('')
        if wider['solution']:
            L.append('В решениях: {}'.format(
                ', '.join('#{}'.format(i) for i in wider['solution'][:40])))
            L.append('')

        L.append('## Контрольные примеры\n')
        L.append('| id | Что это | Найден | Где |')
        L.append('|---|---|---|---|')
        for pid, what in sorted(CONTROL_IDS.items()):
            if pid in found:
                where = 'видимые поля'
            elif pid in wider['hidden']:
                where = 'за шлюзом качества (`needs_quality_review`)'
            elif pid in wider['solution']:
                where = 'поле `solution`'
            else:
                where = '—'
            L.append('| #{} | {} | {} | {} |'.format(
                pid, what, '**да**' if where != '—' else '**НЕТ**', where))
        L.append('')

        L.append('## Полный список (видимые поля)\n')
        L.append('| id | Источник | Признаки | Цел? | Заголовок |')
        L.append('|---|---|---|---|---|')
        for pid, v in sorted(found.items()):
            L.append('| #{} | {} | {} | {} | {} |'.format(
                pid, v['source'], ', '.join(v['hits']),
                'да' if v['whole'] else '**обрубок**',
                v['title'][:60].replace('|', '\\|')))
        L.append('')
        L.append('Список id — `{}`.'.format(IDS))

        with open(REPORT, 'w', encoding='utf-8') as f:
            f.write('\n'.join(L) + '\n')
