# -*- coding: utf-8 -*-
"""enrich_full_review_html — Фаза 3 приёмки: `run_full_review.html`, 75
задач на глаза владельцу (условие, картинка если есть, все поля обоих
вызовов, метки мягких нарушений, выброшенные запросы).

Состав, детерминированный зерном:
  - 40 случайных по всему обработанному корпусу (включая брак — честно);
  - 15 с растровой картинкой условия (картинка встроена в страницу);
  - по 1 задаче из 10 САМЫХ ЧАСТЫХ тем (типичное);
  - по 1 задаче из 10 САМЫХ РЕДКИХ тем (края).
Пересечения с уже отобранными не дублируются — на освободившееся место
добирается следующая по порядку зерна задача той же группы.

⚠️ ТОЛЬКО ЧИТАЕТ. К API не обращается, в базу не пишет.

Запуск:
    manage.py enrich_full_review_html
"""
import base64
import html
import json
import random
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from problems.enrich import taxonomy
from problems.enrich.text import problem_full_text
from problems.models import Problem

REPORT_DIR = Path('reports/enrich_pilot')
PARSED_PATH = REPORT_DIR / 'run_parsed.jsonl'
ACCEPT_PATH = REPORT_DIR / 'run_full_accept.json'
OUT_PATH = REPORT_DIR / 'run_full_review.html'

SEED = 20260903
N_RANDOM = 40
N_RASTER = 15
N_TOP_THEMES = 10
N_RARE_THEMES = 10

FIELD_ORDER = [
    ('topic_primary', 'Тема'), ('topics_secondary', 'Доп. темы'),
    ('tags', 'Теги'), ('given', 'Дано'), ('find', 'Найти'),
    ('econ_concepts', 'Понятия'), ('concepts_offlist', 'Вне списка'),
    ('task_nature', 'Характер'), ('features_1', 'Особенности (модель)'),
    ('graphical_solution', 'Графическое решение (после ИЛИ)'),
    ('graphical_solution_source', '  источник'),
    ('topic_confidence', 'Уверенность'),
    ('search_queries', 'Поисковые запросы'),
    ('dropped_queries', '  выброшено (цифра в запросе)'),
    ('plot', 'Сюжет'), ('hints', 'Подсказки'),
    ('text_quality', 'Состояние текста'),
    ('text_quality_note', '  пояснение'), ('problem_type', 'Тип задачи'),
    ('difficulty', 'Сложность'), ('difficulty_note', '  обоснование'),
    ('answer_consistency', 'Согласованность ответа'),
    ('title_candidate', 'Заголовок-кандидат'),
    ('soft_violations', 'Мягкие нарушения'),
]


def _fmt(value):
    if value is None or value == '':
        return '—'
    if isinstance(value, list):
        if not value:
            return '—'
        return ', '.join(_theme_or_tag_label(v) for v in value)
    return str(value)


def _theme_or_tag_label(v):
    v = str(v)
    try:
        if '.' in v:
            return '%s (%s)' % (taxonomy.tag_name_from_id(v), v)
        return '%s (%s)' % (taxonomy.theme_name_from_id(v), v)
    except KeyError:
        return v


def load_parsed(path):
    with open(path, encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


def pick_sample(rows, seed=SEED):
    """`(entries, groups)` — `groups` — `{problem_id: [метка, ...]}`."""
    rng = random.Random(seed)
    by_id = {r['problem_id']: r for r in rows}
    chosen = []
    chosen_set = set()
    groups = {}

    def add(pid, label):
        if pid in chosen_set:
            groups[pid].append(label)
            return False
        chosen.append(pid)
        chosen_set.add(pid)
        groups[pid] = [label]
        return True

    def fill_from(pool, n, label):
        pool = [p for p in pool if p not in chosen_set]
        rng.shuffle(pool)
        added = 0
        for pid in pool:
            if added >= n:
                break
            if add(pid, label):
                added += 1
        return added

    raster_ids = [r['problem_id'] for r in rows if r.get('has_raster')]
    fill_from(raster_ids, N_RASTER, 'растр')

    topic_counts = Counter(r.get('topic_primary') for r in rows
                           if r.get('topic_primary') and not r.get('defect'))
    ranked = sorted(topic_counts.items(), key=lambda kv: -kv[1])
    top_topics = [t for t, _ in ranked[:N_TOP_THEMES]]
    rare_topics = [t for t, _ in ranked[-N_RARE_THEMES:]]

    by_topic = {}
    for r in rows:
        if r.get('topic_primary'):
            by_topic.setdefault(r['topic_primary'], []).append(r['problem_id'])

    for topic in top_topics:
        fill_from(by_topic.get(topic, []), 1, 'частая_тема:%s' % topic)
    for topic in rare_topics:
        fill_from(by_topic.get(topic, []), 1, 'редкая_тема:%s' % topic)

    all_ids = [r['problem_id'] for r in rows]
    fill_from(all_ids, N_RANDOM, 'случайная')

    # ⚠️ Резерв в 15 растровых — это МИНИМУМ, а не потолок: случайная или
    # тематическая карточка может СЛУЧАЙНО оказаться растровой, и это не
    # повод молчать про её картинку на странице. Метка добавляется задним
    # числом ко всем таким карточкам — подсветка и счётчик честны.
    for pid in chosen:
        if by_id[pid].get('has_raster') and 'растр' not in groups[pid]:
            groups[pid].append('растр')

    entries = [by_id[pid] for pid in chosen]
    return entries, groups


def render_summary(accept):
    p1 = accept['phase1']
    p2 = accept['phase2']
    p4 = accept['phase4_counts']
    lines = [
        'Фаза 1: манифест %d задач, обработано %d, без вызова 2 — %d, '
        'без единого вызова — %d. Расход $%s, ~%.1f ч, ~%.0f задач/мин.' % (
            p1['manifest_total'], p1['both_calls_in_manifest'] + len(p1['call1_only_ids']),
            len(p1['call1_only_ids']), len(p1['missing_entirely_ids']),
            p1['cost_usd'], p1['elapsed_hours_by_mtime'], p1['avg_rate_per_min']),
        'Фаза 2: сошлось %d из %d инвариантов §11. Свип-детектор — 0 '
        'расхождений на %d задачах.' % (
            p2['invariants_passed'], p2['invariants_total'],
            p2['sweep_detector']['checked']),
        'Теги: использовано %d из %d канонических. Заголовки: самый частый '
        'повторяется %d раз.' % (
            p2['tags']['used_count'], p2['tags']['total_canonical'],
            p2['titles']['max_repeat']),
        'problem_type заполнен у %.1f%% задач; совпадение с check_type '
        'SolveHub %.1f%%.' % (
            p2['problem_type']['filled_pct'], p2['problem_type']['check_type_match_pct']),
        'Очереди на ручной разбор: битый текст %d, утраченные визуалы %d, '
        'несходящийся ответ %d, не задача %d. concepts_offlist: %d '
        'уникальных терминов.' % (
            p4['broken_text'], p4['lost_visuals'], p4['answer_mismatch'],
            p4['not_a_problem'], p4['offlist_unique_terms']),
    ]
    return '<br>'.join(html.escape(line) for line in lines)


def render_page(entries, groups, summary_html, seed=SEED):
    problems_by_id = {
        p.id: p for p in
        Problem.objects.filter(id__in=[e['problem_id'] for e in entries])
        .prefetch_related('parts', 'figures')
    }
    parts = ["""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Боевой прогон обогащения — приёмка на 75 задачах (Фаза 3)</title>
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;font-size:14px;margin:24px;
    color:#222;max-width:1100px}
h1{font-size:20px}
.summary{color:#333;font-size:13px;margin-bottom:24px;padding:12px 14px;
    background:#f5f5f0;border:1px solid #ddd;line-height:1.7}
.card{border:1px solid #ccc;margin-bottom:28px;padding:14px}
.card.has-raster{border-left:6px solid #2a7ae2;background:#f3f8ff}
.card h2{margin:0 0 8px;font-size:15px}
.tag{padding:2px 8px;border-radius:3px;font-size:12px;margin-left:6px;
    display:inline-block}
.tag-random{background:#eef;color:#225}
.tag-raster{background:#2a7ae2;color:#fff}
.tag-top{background:#dfe;color:#252}
.tag-rare{background:#fde;color:#a05}
.stmt{white-space:pre-wrap;font-size:13px;background:#fafafa;padding:8px;
    border:1px solid #eee;margin-bottom:10px}
img.figure{max-width:420px;display:block;margin-bottom:10px;border:1px solid #ddd}
table{border-collapse:collapse;width:100%%}
td{border:1px solid #ddd;padding:4px 8px;vertical-align:top;font-size:13px}
td.label{width:220px;color:#555;font-weight:600;background:#fafafa}
.defect{color:#a00;font-weight:bold}
</style></head><body>
<h1>Боевой прогон обогащения GLM-5.3-Flash — приёмка на 75 задачах</h1>
<div class="summary">%s</div>
<p style="color:#666;font-size:13px">Состав: 40 случайных по всему корпусу
+ 15 с растровой картинкой + по 1 из 10 самых частых тем + по 1 из 10
самых редких тем (пересечения не дублируются, зерно %d).</p>
""" % (summary_html, seed)]

    label_class = {
        'растр': 'tag-raster', 'случайная': 'tag-random',
    }

    for entry in entries:
        pid = entry['problem_id']
        problem = problems_by_id.get(pid)
        labels = groups.get(pid, [])
        is_raster = 'растр' in labels
        card_class = 'card' + (' has-raster' if is_raster else '')
        parts.append('<div class="%s">' % card_class)
        badges = ''
        if entry.get('defect'):
            badges += ' <span class="tag defect">БРАК</span>'
        for label in labels:
            if label.startswith('частая_тема:'):
                cls, text = 'tag-top', 'частая тема'
            elif label.startswith('редкая_тема:'):
                cls, text = 'tag-rare', 'редкая тема'
            else:
                cls, text = label_class.get(label, 'tag-random'), label
            badges += ' <span class="tag %s">%s</span>' % (cls, html.escape(text))
        parts.append('<h2>Задача #%d%s</h2>' % (pid, badges))
        if problem:
            text = problem_full_text(problem.statement, problem.parts.all())
            parts.append('<div class="stmt">%s</div>' % html.escape(text[:2500]))
            figure = next(
                (f for f in problem.figures.all()
                 if f.source_field in ('import', 'statement') and f.image_data), None)
            if figure:
                b64 = base64.b64encode(bytes(figure.image_data)).decode('ascii')
                parts.append('<img class="figure" src="data:%s;base64,%s">'
                             % (figure.content_type or 'image/png', b64))
        else:
            parts.append('<div class="stmt">(задача не найдена в базе)</div>')

        parts.append('<table>')
        for key, label in FIELD_ORDER:
            parts.append('<tr><td class="label">%s</td><td>%s</td></tr>'
                         % (html.escape(label), html.escape(_fmt(entry.get(key)))))
        parts.append('</table>')
        parts.append('</div>')

    parts.append('</body></html>')
    return '\n'.join(parts)


class Command(BaseCommand):
    help = 'Фаза 3 приёмки: run_full_review.html на 75 задач (только чтение).'

    def add_arguments(self, parser):
        parser.add_argument('--parsed', type=str, default=str(PARSED_PATH))
        parser.add_argument('--accept', type=str, default=str(ACCEPT_PATH))
        parser.add_argument('--out', type=str, default=str(OUT_PATH))
        parser.add_argument('--seed', type=int, default=SEED)

    def handle(self, *args, **options):
        rows = load_parsed(Path(options['parsed']))
        with open(options['accept'], encoding='utf-8') as fh:
            accept = json.load(fh)

        entries, groups = pick_sample(rows, seed=options['seed'])
        summary_html = render_summary(accept)
        html_text = render_page(entries, groups, summary_html, seed=options['seed'])

        out_path = Path(options['out'])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write(html_text)

        counts = Counter(l for labels in groups.values() for l in labels)
        self.stdout.write('задач в странице: %d' % len(entries))
        self.stdout.write('случайных: %d, растровых: %d, из частых тем: %d, '
                          'из редких тем: %d' % (
                              counts.get('случайная', 0), counts.get('растр', 0),
                              sum(1 for l in counts if l.startswith('частая_тема:')),
                              sum(1 for l in counts if l.startswith('редкая_тема:'))))
        self.stdout.write('страница: %s' % out_path)
