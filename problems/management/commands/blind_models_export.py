# -*- coding: utf-8 -*-
"""blind_models_export — слепое сравнение веток прогона глазами владельца.

Цена — не единственный критерий выбора модели. «Насколько модель понимает
олимпиадную экономику по-русски» бенчмарком не меряется: это смотрит
человек на СВОИХ задачах. Команда собирает страницу, где одна и та же
задача разобрана всеми ветками, а колонки обезличены и перемешаны.

⚠️ СЛЕПОТА — ГЛАВНОЕ СВОЙСТВО, а не оформление. По образцу
`export_blind_sample` и `repair_review_shell`: соответствие «колонка →
ветка» НИКОГДА не попадает ни в HTML, ни в вывод команды — оно уходит в
отдельный `blind_models_key.json`, который открывают уже после разметки.
Порядок колонок свой у каждой задачи, иначе «третья всегда лучшая»
прочиталось бы с одного экрана.

⚠️ ВЕТКИ — ТЕ ЖЕ, ЧТО В ПИЛОТЕ (`pilot_enrich_v2.VARIANTS`), и прогоняются
ТОЙ ЖЕ функцией `run_variant`. Второй копией прогона колонки сравнивали бы
не то, что поедет в бой.

⚠️ ДВЕ ФАЗЫ, как у пилота: без `--apply` не уходит ни одного обращения к
API — печатается состав выборки и смета. `--apply` требует `--max-cost`,
и потолок считается по ФАКТИЧЕСКОМУ usage.

Запуск:
    manage.py blind_models_export
    manage.py blind_models_export --apply --max-cost 1.5
"""
import html
import io
import json
import os
import random
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from problems.enrich import taxonomy
from problems.enrich.shortlist import shortlist_for
from problems.enrich.text import is_english_text, problem_full_text
from problems.management.commands import pilot_enrich_v2 as pilot
from problems.models import Problem

SEED = 20260902
OUT_DIR = 'reports/enrich_pilot'
HTML_NAME = 'blind_models.html'
KEY_NAME = 'blind_models_key.json'
#: ⚠️ Сырые ответы сохраняются ОБЯЗАТЕЛЬНО и сразу. Разбор пилота 01.09
#: провалился ровно потому, что построчные ответы жили одним временным
#: файлом, который не пережил неделю: остались только агрегаты в Notion, а
#: попарное сравнение веток пересчитать стало не из чего. Страница показывает
#: восемь полей из двадцати — по ней такой разбор не восстановить.
ROWS_NAME = 'blind_models_rows.json'

#: Ветки-колонки. Порядок здесь — НЕ порядок на экране (см. слепоту выше).
BRANCHES = ('base', 'terra-low', 'terra-gen', 'luna-luna')
LETTERS = ('A', 'B', 'C', 'D')

#: Состав выборки: смещён к сложному и олимпиадному, а не случаен.
#: Сумма — 25. Цифры взяты из задания сессии, а не подобраны.
QUOTA_HARD = 8       # difficulty 4–5, по-русски
QUOTA_FIGURE = 5     # с чертежом или картинкой, по-русски
QUOTA_ENGLISH = 4    # единственная нерусская часть выборки
QUOTA_PLAIN = 8      # обычные русские расчётные
SAMPLE_SIZE = QUOTA_HARD + QUOTA_FIGURE + QUOTA_ENGLISH + QUOTA_PLAIN


def build_sample(seed=SEED):
    """`(ids, отчёт)` — детерминированная выборка, смещённая к сложному.

    Русскоязычность проверяется кодом (`is_english_text`), потому что поля
    языка у `Problem` нет вовсе. Английские четыре — отдельная страта, и
    только в ней латиница законна.
    """
    rng = random.Random(seed)
    used = set()
    picked = []
    report = []

    def take(label, ids, quota):
        pool = [i for i in ids if i not in used]
        take_n = min(quota, len(pool))
        chosen = sorted(rng.sample(pool, take_n)) if take_n else []
        used.update(chosen)
        picked.extend(chosen)
        report.append('%s: нужно %d, доступно %d, взято %d'
                      % (label, quota, len(pool), take_n))

    russian = set()
    english = set()
    for pid, statement in (Problem.objects.order_by('id')
                           .values_list('id', 'statement')
                           .iterator(chunk_size=500)):
        (english if is_english_text(statement) else russian).add(pid)

    figure_regex = r'\[\[FIGURE:|\\begin\{tikzpicture\}'
    with_figure = set(
        Problem.objects.filter(Q(figures__isnull=False)
                               | Q(statement__iregex=figure_regex)
                               | Q(parts__statement__iregex=figure_regex))
        .distinct().values_list('id', flat=True))
    hard = set(Problem.objects.filter(difficulty__in=(4, 5))
               .values_list('id', flat=True))

    take('сложные 4–5 (рус.)', sorted(hard & russian), QUOTA_HARD)
    take('с чертежом/картинкой (рус.)',
         sorted(with_figure & russian), QUOTA_FIGURE)
    take('англоязычные', sorted(english), QUOTA_ENGLISH)
    take('обычные расчётные (рус.)',
         sorted(russian - with_figure - hard), QUOTA_PLAIN)
    return picked, report


def theme_label(identifier):
    try:
        return '%s — %s' % (identifier, taxonomy.theme_name_from_id(identifier))
    except (KeyError, TypeError):
        return str(identifier or '—')


def tag_labels(ids):
    out = []
    for identifier in ids or []:
        try:
            out.append('%s (%s)' % (taxonomy.tag_name_from_id(identifier),
                                    identifier))
        except (KeyError, TypeError):
            out.append(str(identifier))
    return out


def column_cells(row):
    """Что показывается в колонке: вызов 1 плюс заголовок и сложность из
    вызова 2. Имя ветки сюда не попадает НИКОГДА."""
    call1 = row.get('call1') or {}
    call2 = row.get('call2') or {}
    return [
        ('Тема', theme_label(call1.get('topic_primary'))),
        ('Уверенность', call1.get('topic_confidence')),
        ('Теги', ', '.join(tag_labels(call1.get('tags')))),
        ('Дано', call1.get('given')),
        ('Найти', call1.get('find')),
        ('Понятия', ', '.join(call1.get('econ_concepts') or [])),
        ('Заголовок', call2.get('title_candidate')),
        ('Сложность', call2.get('difficulty')),
    ]


def _plain(row):
    """Строка `run_variant` без объектов `Reply` — в JSON уходят числа
    usage, а не `repr()` объекта (на этом уже спотыкались в пилоте)."""
    out = {k: v for k, v in row.items() if not k.endswith('_usage')}
    for call in ('call1', 'call2'):
        reply = row.get('%s_usage' % call)
        if reply is None:
            continue
        out['%s_usage' % call] = {
            'input_tokens': reply.input_tokens,
            'output_tokens': reply.output_tokens,
            'cache_read_tokens': reply.cache_read_tokens,
            'reasoning_tokens': reply.reasoning_tokens,
        }
    return out


def esc(value):
    if value is None or value == '':
        return '—'
    return html.escape(str(value))


PAGE_HEAD = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Слепое сравнение моделей — %(n)d задач</title>
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;font-size:14px;margin:24px;color:#222}
table{border-collapse:collapse;width:100%%;margin-bottom:30px}
td,th{border:1px solid #ccc;padding:8px;vertical-align:top;text-align:left}
th{background:#f0f0f0}
.stmt{white-space:pre-wrap;font-size:13px;color:#333;background:#fafafa}
.field{margin-bottom:6px}
.field b{color:#555}
h2{margin-top:36px;font-size:16px}
.howto{background:#fff6d5;border:1px solid #e2cf7a;padding:12px;font-size:15px}
</style></head><body>
<h1>Слепое сравнение: как разные ветки прогона разобрали одни и те же задачи</h1>
<p class="howto">По каждой задаче отметь лучшую и худшую колонку.</p>
<p style="color:#777;font-size:12px">Задач: %(n)d, колонок: %(cols)d.
Колонки обезличены и перемешаны СВОИМ порядком у каждой задачи —
«колонка A» на разных задачах это разные ветки. Соответствие лежит
отдельным файлом и до конца разметки не открывается. База не менялась.</p>
"""


def build_html(problems_by_id, per_problem, order):
    parts = [PAGE_HEAD % {'n': len(order), 'cols': len(LETTERS)}]
    for pid in order:
        columns = per_problem[pid]
        problem = problems_by_id[pid]
        parts.append('<h2>Задача #%d</h2>' % pid)
        parts.append('<table><tr><th style="width:26%%">Условие</th>')
        for letter, _ in columns:
            parts.append('<th>Колонка %s</th>' % letter)
        parts.append('</tr><tr>')
        text = problem_full_text(problem.statement, problem.parts.all())
        parts.append('<td class="stmt">%s</td>' % esc(text[:1400]))
        for _, row in columns:
            cells = ''.join(
                '<div class="field"><b>%s:</b> %s</div>' % (name, esc(value))
                for name, value in column_cells(row))
            parts.append('<td>%s</td>' % cells)
        parts.append('</tr></table>')
    parts.append('</body></html>')
    return '\n'.join(parts)


class Command(BaseCommand):
    help = ('Слепое сравнение веток прогона на смещённой выборке. '
            'Без --apply денег не тратит.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--max-cost', type=float, default=None)
        parser.add_argument('--seed', type=int, default=SEED)

    def handle(self, *args, **options):
        if options['apply'] and options['max_cost'] is None:
            raise CommandError('--apply требует --max-cost — прогона без '
                               'потолка расхода не бывает.')

        sample_ids, report = build_sample(options['seed'])
        self.stdout.write('=== ВЫБОРКА (сид %d) ===' % options['seed'])
        for line in report:
            self.stdout.write('  ' + line)
        self.stdout.write('Итого задач: %d' % len(sample_ids))

        by_id = {p.id: p for p in Problem.objects.filter(id__in=sample_ids)
                 .prefetch_related('parts', 'figures')}
        problems = [by_id[i] for i in sample_ids if i in by_id]
        shortlists = {p.id: shortlist_for(
            problem_full_text(p.statement, p.parts.all())) for p in problems}

        self.stdout.write('')
        self.stdout.write('=== СМЕТА (оценка, не счёт) ===')
        total = Decimal('0')
        for key in BRANCHES:
            branch_cost, _ = pilot.estimate_variant_cost(
                problems, pilot.VARIANTS[key], shortlists)
            total += branch_cost
            self.stdout.write('  %-11s ~$%.4f' % (key, branch_cost))
        self.stdout.write('ИТОГО по %d веткам: ~$%.4f' % (len(BRANCHES), total))

        if not options['apply']:
            self.stdout.write('')
            self.stdout.write('ФАЗА ПОКАЗА: API не вызывался, денег не '
                              'потрачено.')
            return

        complete_fn = pilot.make_openai_complete_fn()
        per_branch = {}
        spent = Decimal('0')
        cap = options['max_cost'] / len(BRANCHES)
        for key in BRANCHES:
            self.stdout.write('')
            self.stdout.write('=== ВЕТКА %s ===' % key)
            rows, branch_spent, stopped = pilot.run_variant(
                problems, pilot.VARIANTS[key], complete_fn, shortlists,
                max_cost=cap,
                on_progress=lambda pid, s: self.stdout.write(
                    '  #%d готово, $%.4f' % (pid, s)))
            spent += branch_spent
            per_branch[key] = {r['problem_id']: r for r in rows}
            self.stdout.write('  обработано %d, потрачено $%.4f%s'
                              % (len(rows), branch_spent,
                                 ' (упёрлась в потолок)' if stopped else ''))

        # Задачи, разобранные ВСЕМИ ветками: неполная строка сравнима не с
        # чем — колонка с прочерком читалась бы как «модель промолчала».
        complete_ids = [pid for pid in sample_ids
                        if all(pid in per_branch[k] for k in BRANCHES)]

        rng = random.Random(options['seed'])
        per_problem = {}
        key_map = {}
        for pid in complete_ids:
            order = list(BRANCHES)
            rng.shuffle(order)
            per_problem[pid] = [(LETTERS[i], per_branch[branch][pid])
                                for i, branch in enumerate(order)]
            key_map[str(pid)] = dict(zip(LETTERS, order))

        os.makedirs(OUT_DIR, exist_ok=True)
        html_path = os.path.join(OUT_DIR, HTML_NAME)
        with io.open(html_path, 'w', encoding='utf-8') as fh:
            fh.write(build_html(by_id, per_problem, complete_ids))
        key_path = os.path.join(OUT_DIR, KEY_NAME)
        with io.open(key_path, 'w', encoding='utf-8') as fh:
            json.dump({'seed': options['seed'], 'branches': list(BRANCHES),
                       'columns': key_map}, fh, ensure_ascii=False, indent=2)

        rows_path = os.path.join(OUT_DIR, ROWS_NAME)
        with io.open(rows_path, 'w', encoding='utf-8') as fh:
            json.dump({'seed': options['seed'],
                       'spent': float(spent),
                       'rows': {branch: {str(pid): _plain(row)
                                         for pid, row in per_pid.items()}
                                for branch, per_pid in per_branch.items()}},
                      fh, ensure_ascii=False, indent=2)

        self.stdout.write('')
        self.stdout.write('Страница: %s (задач %d из %d)'
                          % (html_path, len(complete_ids), len(sample_ids)))
        self.stdout.write('Ключ соответствия: %s — владельцу НЕ показывать '
                          'до конца разметки.' % key_path)
        self.stdout.write('Сырые ответы: %s' % rows_path)
        self.stdout.write('Потрачено по факту usage: $%.4f' % spent)
