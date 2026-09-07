# -*- coding: utf-8 -*-
"""Страница приёмки контрольной точки: старые и новые поля РЯДОМ.

Фаза 4.3 задания сессии 03.09.2026. Владелец смотрит глазами, а не верит
процентам, поэтому таблица «было / стало» из `run300_v2_compare.md` без этой
страницы неполна: проценты говорят, что тегов стало больше, но не говорят,
СТАЛИ ЛИ ОНИ ПРАВИЛЬНЕЕ.

Отличие от `glm_review_build`: тот показывает ОДНУ версию разбора, здесь —
две колонки, старую и новую, и расхождения подсвечены. Общего кода у них
немного (`FIELD_ORDER`, `_fmt`, `visual_ids` берутся оттуда напрямую), а
вёрстка разная по сути: там карточка-список, здесь карточка-сравнение.

Команда только ЧИТАЕТ: два журнала и базу (текст задачи и картинку). В базу
не пишет ничего.
"""
import base64
import html
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from problems.enrich.text import problem_full_text
from problems.management.commands.glm_review_build import (
    FIELD_ORDER, _fmt, _theme_or_tag_label, visual_ids)
from problems.models import Problem

# Поля вызова 2 в режиме `--call1-only` переносятся из старого журнала
# без изменений — сравнивать их бессмысленно, они совпадают по построению.
# Показываем их ОДНОЙ колонкой на всю ширину, чтобы владелец видел разбор
# целиком, но не искал расхождений там, где их не может быть.
CALL2_FIELDS = frozenset({
    'search_queries', 'plot', 'hints', 'text_quality', 'text_quality_note',
    'problem_type', 'difficulty', 'difficulty_note', 'answer_consistency',
    'title_candidate',
})


# Главная тема — скаляр, и общий  печатает её голым числом: он
# разворачивает в название только СПИСКИ (доп. темы, теги). На странице
# сравнения тема — ключевое поле, и «7» против «12» ничего не говорит
# глазу. Правка местная: общий форматтер обслуживает и другую страницу,
# трогать его ради этой незачем.
_ID_FIELDS = frozenset({'topic_primary'})


def fmt_field(key, value):
    if key in _ID_FIELDS and value not in (None, ''):
        return _theme_or_tag_label(value)
    return _fmt(value)


def load(path, only_ids=None):
    path = Path(path)
    if not path.exists():
        raise CommandError('Нет файла: %s' % path)
    rows = {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if only_ids is None or row['problem_id'] in only_ids:
                rows[row['problem_id']] = row
    return rows


def pick(old, new, count, min_raster):
    """Задачи для страницы: сначала растровые, затем добор по порядку id.

    Растровые резервируются первыми по той же причине, что и в
    `glm_review_build`: картинки в выборке распределены неравномерно, и
    «первые N по файлу» не гарантируют ни одной.
    """
    common = sorted(set(old) & set(new))
    _tikz, raster = visual_ids(common)
    chosen, seen = [], set()
    for pid in common:
        if len(chosen) >= min_raster:
            break
        if pid in raster:
            chosen.append(pid)
            seen.add(pid)
    for pid in common:
        if len(chosen) >= count:
            break
        if pid not in seen:
            chosen.append(pid)
            seen.add(pid)
    return chosen, raster


HEAD = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Контрольная точка 300 — было и стало</title>
<style>
/* Фон задаётся ЯВНО: без него страница берёт фон браузера, и в тёмной
   теме тёмный текст ложится на тёмное — читать нечего. Страница
   намеренно светлая: это лист для вычитки глазами, а не интерфейс. */
html{background:#fff}
body{font-family:-apple-system,Segoe UI,sans-serif;font-size:14px;margin:24px;
     color:#222;max-width:1400px;background:#fff}
h1{font-size:20px;margin-bottom:4px}
.note{color:#555;font-size:13px;margin-bottom:24px;padding:10px 12px;
      background:#f5f5f0;border:1px solid #ddd}
.card{border:1px solid #ccc;margin-bottom:30px;padding:14px}
.card.has-raster{border-left:6px solid #2a7ae2;background:#f7fbff}
.card h2{margin:0 0 8px;font-size:15px}
.badge{padding:2px 8px;border-radius:3px;font-size:12px;margin-left:8px}
.b-raster{background:#2a7ae2;color:#fff}
.b-defect{background:#a00;color:#fff}
.b-fix{background:#8a6d00;color:#fff}
.stmt{white-space:pre-wrap;font-size:13px;background:#fafafa;padding:8px;
      border:1px solid #eee;margin-bottom:10px;max-height:260px;overflow:auto}
img.figure{max-width:420px;display:block;margin-bottom:10px;
           border:1px solid #ddd}
table{border-collapse:collapse;width:100%}
td,th{border:1px solid #ddd;padding:4px 8px;vertical-align:top;font-size:13px}
th{background:#f0f0ec;text-align:left;font-size:12px}
td.label{width:190px;color:#555;font-weight:600;background:#fafafa}
tr.changed td.old{background:#fff2f2}
tr.changed td.new{background:#f0fff0}
tr.changed td.label{background:#fff8e0}
td.both{background:#fcfcfc;color:#444}
.legend span{margin-right:16px}
.sw{display:inline-block;width:12px;height:12px;vertical-align:middle;
    border:1px solid #bbb;margin-right:4px}
</style></head><body>
<h1>Контрольная точка 300 — было и стало</h1>
<p class="note">
%(note)s
</p>
<p class="legend">
<span><i class="sw" style="background:#fff2f2"></i>было</span>
<span><i class="sw" style="background:#f0fff0"></i>стало</span>
<span><i class="sw" style="background:#fcfcfc"></i>поле вызова 2 —
перенесено из старого журнала без изменений</span>
<span><i class="sw" style="background:#f7fbff"></i>задача с растровой
картинкой</span>
</p>
"""


def render(chosen, old, new, raster_ids, note):
    problems = {p.id: p for p in Problem.objects.filter(id__in=chosen)
                .prefetch_related('parts', 'figures')}
    # HEAD несёт CSS с '100%' — подстановка через replace, а не
    # через оператор %: иначе процент в стилях читается как формат.
    out = [HEAD.replace('%(note)s', note)]
    for pid in chosen:
        o, n = old[pid], new[pid]
        problem = problems.get(pid)
        is_raster = pid in raster_ids
        out.append('<div class="card%s">'
                   % (' has-raster' if is_raster else ''))
        badges = ''
        if n.get('defect'):
            badges += ' <span class="badge b-defect">БРАК (новый разбор)</span>'
        if is_raster:
            badges += ' <span class="badge b-raster">растровая картинка</span>'
        if problem is not None and problem.content_status != 'ok':
            badges += (' <span class="badge b-fix">%s</span>'
                       % html.escape(problem.content_status))
        out.append('<h2>Задача #%d%s</h2>' % (pid, badges))
        if problem is not None:
            text = problem_full_text(problem.statement, problem.parts.all())
            out.append('<div class="stmt">%s</div>'
                       % html.escape(text[:2500]))
            figure = next((f for f in problem.figures.all()
                           if f.source_field in ('import', 'statement')
                           and f.image_data), None)
            if figure is not None:
                b64 = base64.b64encode(
                    bytes(figure.image_data)).decode('ascii')
                out.append('<img class="figure" src="data:%s;base64,%s">'
                           % (figure.content_type or 'image/png', b64))
        else:
            out.append('<div class="stmt">(задача удалена из базы)</div>')

        out.append('<table><tr><th>Поле</th><th>Было (боевой прогон)</th>'
                   '<th>Стало (новая версия промпта)</th></tr>')
        for key, label in FIELD_ORDER:
            was, now = fmt_field(key, o.get(key)), fmt_field(key, n.get(key))
            if key in CALL2_FIELDS:
                out.append('<tr><td class="label">%s</td>'
                           '<td class="both" colspan="2">%s</td></tr>'
                           % (html.escape(label), html.escape(now)))
                continue
            cls = ' class="changed"' if was != now else ''
            out.append('<tr%s><td class="label">%s</td>'
                       '<td class="old">%s</td><td class="new">%s</td></tr>'
                       % (cls, html.escape(label), html.escape(was),
                          html.escape(now)))
        out.append('</table></div>')
    out.append('</body></html>')
    return '\n'.join(out)


class Command(BaseCommand):
    help = ('Страница приёмки: старые и новые поля контрольной точки рядом, '
            'расхождения подсвечены. Только чтение.')

    def add_arguments(self, parser):
        parser.add_argument('--old', type=str,
                            default='reports/enrich_pilot/run_parsed.jsonl')
        parser.add_argument(
            '--new', type=str,
            default='reports/enrich_pilot/run300_v2_parsed.jsonl')
        parser.add_argument(
            '--sample', type=str,
            default='reports/enrich_pilot/run300_sample_ids.json')
        parser.add_argument(
            '--out', type=str,
            default='reports/enrich_pilot/run300_v2_review.html')
        parser.add_argument('--count', type=int, default=40)
        parser.add_argument('--min-raster', type=int, default=10)

    def handle(self, *args, **options):
        with open(options['sample'], encoding='utf-8') as fh:
            sample = set(json.load(fh)['ids'])
        old = load(options['old'], only_ids=sample)
        new = load(options['new'], only_ids=sample)
        self.stdout.write('старый журнал: %d строк выборки, новый: %d'
                          % (len(old), len(new)))
        chosen, raster = pick(old, new, options['count'],
                              options['min_raster'])
        with_raster = sum(1 for pid in chosen if pid in raster)
        changed_fields = 0
        for pid in chosen:
            for key, _label in FIELD_ORDER:
                if key in CALL2_FIELDS:
                    continue
                if (fmt_field(key, old[pid].get(key))
                        != fmt_field(key, new[pid].get(key))):
                    changed_fields += 1
        note = (
            'Задач на странице: <b>%d</b>, из них с растровой картинкой: '
            '<b>%d</b>. Слева — разбор боевого прогона, справа — новая версия '
            'промпта в режиме <code>--call1-only</code>. Поля вызова 2 '
            '(заголовок, сложность, тип задачи, подсказки, сюжет) в этот '
            'перегон не переделывались и перенесены из старого журнала без '
            'изменений — они показаны одной колонкой на всю ширину. '
            'Расхождений в полях вызова 1 на этой странице: <b>%d</b>.'
            % (len(chosen), with_raster, changed_fields))
        out_path = Path(options['out'])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render(chosen, old, new, raster, note),
                            encoding='utf-8')
        self.stdout.write('задач в странице: %d, из них с картинкой: %d '
                          '(требование: >= %d)'
                          % (len(chosen), with_raster, options['min_raster']))
        self.stdout.write('расхождений в полях вызова 1: %d' % changed_fields)
        self.stdout.write('страница: %s' % out_path)
        if with_raster < options['min_raster']:
            raise CommandError(
                'На странице %d задач с картинкой при требовании %d — '
                'страница собрана, но инвариант не сошёлся.'
                % (with_raster, options['min_raster']))
