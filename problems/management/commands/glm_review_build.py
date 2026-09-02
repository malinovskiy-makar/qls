# -*- coding: utf-8 -*-
"""glm_review_build — Фаза 5: `run300_review.html`, 30 задач подряд для
глаз владельца (условие, картинка если есть, все поля обоих вызовов).

Читает готовые `run_parsed.jsonl` (обычно два — основной чек-поинт «первые
300» и донабор с картинками, см. решение владельца 02.09.2026: два честных
прогона вместо подмены выборки, потому что id 1-300 — легаси без единой
картинки, а инвариант «минимум 5 задач с картинкой среди 30 показанных»
столько же реален для честной последовательной выборки). Сама к API не
обращается — только читает файлы и базу (только чтение).

Запуск:
    manage.py glm_review_build \\
        --main reports/enrich_pilot/run_parsed.jsonl --main-count 25 \\
        --supplement reports/enrich_pilot/run_parsed_supplement.jsonl \\
        --supplement-count 5 \\
        --out reports/enrich_pilot/run300_review.html
"""
import base64
import html
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from problems.enrich.text import looks_like_tikz, problem_full_text
from problems.enrich import taxonomy
from problems.models import Problem, ProblemFigure

FIELD_ORDER = [
    ('topic_primary', 'Тема'), ('topics_secondary', 'Доп. темы'),
    ('tags', 'Теги'), ('given', 'Дано'), ('find', 'Найти'),
    ('econ_concepts', 'Понятия'), ('concepts_offlist', 'Вне списка'),
    ('task_nature', 'Характер'), ('features_1', 'Особенности (модель)'),
    ('graphical_solution', 'Графическое решение (после ИЛИ)'),
    ('graphical_solution_source', '  источник'),
    ('topic_confidence', 'Уверенность'),
    ('search_queries', 'Поисковые запросы'), ('plot', 'Сюжет'),
    ('hints', 'Подсказки'), ('text_quality', 'Состояние текста'),
    ('text_quality_note', '  пояснение'), ('problem_type', 'Тип задачи'),
    ('difficulty', 'Сложность'), ('difficulty_note', '  обоснование'),
    ('answer_consistency', 'Согласованность ответа'),
    ('title_candidate', 'Заголовок-кандидат'),
]


def _fmt(value):
    if value is None:
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
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


def pick_entries(parsed_rows, count, exclude_ids=()):
    """Первые `count` НЕ-бракованных строк, в порядке файла (что и есть
    «подряд» для основного прогона), пропуская id из `exclude_ids`
    (донабор не должен дублировать то, что уже показано из основного)."""
    exclude = set(exclude_ids)
    out = []
    for row in parsed_rows:
        if row['problem_id'] in exclude:
            continue
        out.append(row)
        if len(out) >= count:
            break
    return out


def visual_ids(problem_ids):
    """`(tikz_ids, raster_ids)` среди `problem_ids` — растровая картинка
    условия (`import`/`statement`) и настоящий TikZ, по `ProblemFigure`."""
    tikz, raster = set(), set()
    for pid, field, tikz_source, img in ProblemFigure.objects.filter(
            problem_id__in=problem_ids).values_list(
            'problem_id', 'source_field', 'tikz_source', 'image_data'):
        if looks_like_tikz(tikz_source):
            tikz.add(pid)
        elif field in ('import', 'statement') and img:
            raster.add(pid)
    return tikz, raster


def pick_entries_visual_first(parsed_rows, count, min_raster):
    """Как `pick_entries`, но СНАЧАЛА резервирует место под визуальный
    пласт (Фаза 3.4 задания сессии 02.09: страница на глаза владельцу
    обязана показать именно то, поняла ли модель рисунок — «первые N по
    файлу» этого не гарантирует, картинки в выборке распределены
    неравномерно). Порядок резервирования: ВЕСЬ TikZ, что нашёлся среди
    строк, затем `min_raster` растровых, затем добор до `count` обычными
    строками в порядке файла. Брак (`defect`) не резервируется отдельно —
    попадает наравне со всеми при доборе."""
    ok_rows = [r for r in parsed_rows if not r.get('defect')]
    by_id = {r['problem_id']: r for r in ok_rows}
    tikz_ids, raster_ids = visual_ids(by_id.keys())

    chosen = []
    chosen_set = set()

    def take(ids_pool, limit=None):
        n = 0
        for r in ok_rows:
            if limit is not None and n >= limit:
                break
            pid = r['problem_id']
            if pid in chosen_set or pid not in ids_pool:
                continue
            chosen.append(r)
            chosen_set.add(pid)
            n += 1

    take(tikz_ids)
    take(raster_ids, limit=min_raster)
    for r in ok_rows:
        if len(chosen) >= count:
            break
        if r['problem_id'] not in chosen_set:
            chosen.append(r)
            chosen_set.add(r['problem_id'])
    return chosen[:count], tikz_ids, raster_ids


def render_page(entries, main_count, supplement_count, note_html=None,
                tikz_ids=(), raster_ids=()):
    """`tikz_ids`/`raster_ids` (Фаза 3.4 задания сессии 02.09, третья
    пересъёмка) — подсвечивают карточки цветом, чтобы задачи с картинкой
    было видно сразу, не читая таблицу полей."""
    tikz_ids, raster_ids = set(tikz_ids), set(raster_ids)
    problems_by_id = {
        p.id: p for p in
        Problem.objects.filter(id__in=[e['problem_id'] for e in entries])
        .prefetch_related('parts', 'figures')
    }
    parts = ["""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Боевой прогон GLM-5.3-Flash — контрольная точка 300 (Фаза 5)</title>
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;font-size:14px;margin:24px;
    color:#222;max-width:1100px}
h1{font-size:20px}
.note{color:#666;font-size:13px;margin-bottom:24px;padding:10px;
    background:#f5f5f0;border:1px solid #ddd}
.card{border:1px solid #ccc;margin-bottom:28px;padding:14px}
.card.has-raster{border-left:6px solid #2a7ae2;background:#f3f8ff}
.card.has-tikz{border-left:6px solid #a02aa0;background:#faf3ff}
.card h2{margin:0 0 8px;font-size:15px}
.tag-main{background:#eef;color:#225;padding:2px 8px;border-radius:3px;
    font-size:12px;margin-left:8px}
.tag-supp{background:#efe;color:#252;padding:2px 8px;border-radius:3px;
    font-size:12px;margin-left:8px}
.tag-raster{background:#2a7ae2;color:#fff;padding:2px 8px;border-radius:3px;
    font-size:12px;margin-left:8px}
.tag-tikz{background:#a02aa0;color:#fff;padding:2px 8px;border-radius:3px;
    font-size:12px;margin-left:8px}
.stmt{white-space:pre-wrap;font-size:13px;background:#fafafa;padding:8px;
    border:1px solid #eee;margin-bottom:10px}
img.figure{max-width:420px;display:block;margin-bottom:10px;border:1px solid #ddd}
table{border-collapse:collapse;width:100%%}
td{border:1px solid #ddd;padding:4px 8px;vertical-align:top;font-size:13px}
td.label{width:220px;color:#555;font-weight:600;background:#fafafa}
.defect{color:#a00;font-weight:bold}
</style></head><body>
<h1>Боевой прогон GLM-5.3-Flash — контрольная точка (Фаза 5)</h1>
<p class="note">
%s
</p>
""" % (note_html or (
        '%d задач подряд из основного чек-поинта «первые 300 по id» (легаси, без '
        'картинок — <b>это честно, а не сокрытие</b>) + %d задач из отдельного '
        'донабора специально с растровой картинкой (решение владельца 02.09.2026: '
        'два честных прогона вместо подмены выборки одной стратифицированной). '
        'Донабор помечен зелёным тегом и НЕ входит в официальные метрики чек-поинта '
        'на 300 — только сюда, для визуальной проверки.'
        % (main_count, supplement_count)))]

    for entry in entries:
        problem = problems_by_id.get(entry['problem_id'])
        is_supplement = entry.get('_supplement', False)
        is_raster = entry['problem_id'] in raster_ids
        is_tikz = entry['problem_id'] in tikz_ids
        card_class = 'card' + (' has-tikz' if is_tikz else ' has-raster' if is_raster else '')
        parts.append('<div class="%s">' % card_class)
        badges = ''
        if entry.get('defect'):
            badges += ' <span class="defect">БРАК</span>'
        if is_tikz:
            badges += ' <span class="tag-tikz">TikZ</span>'
        if is_raster:
            badges += ' <span class="tag-raster">растровая картинка</span>'
        badges += (' <span class="tag-supp">донабор — картинка</span>' if is_supplement
                   else ' <span class="tag-main">основной чек-поинт</span>')
        parts.append('<h2>Задача #%d%s</h2>' % (entry['problem_id'], badges))
        if problem:
            text = problem_full_text(problem.statement, problem.parts.all())
            parts.append('<div class="stmt">%s</div>' % html.escape(text[:2000]))
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
    help = 'Фаза 5: собрать run300_review.html из готовых run_parsed.jsonl (только чтение).'

    def add_arguments(self, parser):
        parser.add_argument('--main', type=str, required=True)
        parser.add_argument('--main-count', type=int, default=25)
        parser.add_argument('--supplement', type=str, default=None)
        parser.add_argument('--supplement-count', type=int, default=5)
        parser.add_argument('--out', type=str, required=True)
        parser.add_argument(
            '--prioritize-visual', action='store_true',
            help='Резервирует место под ВЕСЬ найденный TikZ и '
                 '--min-raster растровых картинок ПЕРЕД добором «первые N '
                 'по файлу» (Фаза 3.4 задания сессии 02.09, третья '
                 'пересъёмка) — вместо старой логики main+supplement.')
        parser.add_argument('--min-raster', type=int, default=12)
        parser.add_argument('--note', type=str, default=None,
                            help='Свой текст заметки вместо стандартного main+supplement.')

    def handle(self, *args, **options):
        main_rows = load_parsed(options['main'])
        if not main_rows:
            raise CommandError('%s пуст или не найден.' % options['main'])

        tikz_ids, raster_ids = set(), set()
        if options['prioritize_visual']:
            main_entries, tikz_ids, raster_ids = pick_entries_visual_first(
                main_rows, options['main_count'], options['min_raster'])
        else:
            main_entries = pick_entries(main_rows, options['main_count'])

        supplement_entries = []
        if options['supplement']:
            supplement_rows = load_parsed(options['supplement'])
            supplement_entries = pick_entries(
                supplement_rows, options['supplement_count'],
                exclude_ids=[e['problem_id'] for e in main_entries])
            for e in supplement_entries:
                e['_supplement'] = True

        entries = main_entries + supplement_entries
        with_images = sum(1 for e in entries if e['problem_id'] in raster_ids) \
            if options['prioritize_visual'] else sum(
            1 for e in entries
            if Problem.objects.filter(
                id=e['problem_id'],
                figures__source_field__in=('import', 'statement')).exists())
        with_tikz = sum(1 for e in entries if e['problem_id'] in tikz_ids)

        html_text = render_page(entries, len(main_entries), len(supplement_entries),
                                note_html=options['note'],
                                tikz_ids=tikz_ids, raster_ids=raster_ids)
        out_path = Path(options['out'])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write(html_text)

        self.stdout.write('задач в странице: %d (основных %d, донабор %d)'
                          % (len(entries), len(main_entries), len(supplement_entries)))
        self.stdout.write('из них с картинкой: %d (инвариант Фазы 5: >= 5)' % with_images)
        self.stdout.write('из них с TikZ: %d' % with_tikz)
        self.stdout.write('страница: %s' % out_path)
