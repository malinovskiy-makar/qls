# -*- coding: utf-8 -*-
"""
preview_vsosh_municip — HTML-превью разбора муниципального этапа ВсОШ
(все годы одним файлом, навигация по годам сверху). Карточка вопроса:
год, классы, номер, тип бейджем, баллы, условие с KaTeX, варианты с
подсвеченным правильным, ответ (numeric/open), решение жюри раскрывающимся
блоком, пометки парсера и подсказка «файл, страница PDF» для сверки
с оригиналом. Отдельной секцией в конце каждого года — unparsed с причинами.

Запуск: ./venv/bin/python manage.py preview_vsosh_municip [--year N]
Выход:  reports/vsosh_municip/preview.html (KaTeX с CDN, файл автономный).
"""
import html
import json
from pathlib import Path

from django.core.management.base import BaseCommand

YEARS = (2017, 2018, 2019, 2020, 2021, 2022, 2023)

QTYPE_LABELS = {
    'single': ('Один ответ', 'b-single'),
    'numeric': ('Числовой ответ', 'b-numeric'),
    'open': ('Задача (решение жюри)', 'b-open'),
}
SECTION_TITLES = {
    'test': 'Тестовые задания',
    'short': 'Задания с кратким ответом',
    'long': 'Задания с развёрнутым ответом',
}
SECTION_ORDER = {'test': 0, 'short': 1, 'long': 2}

CSS = """
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:#fafaf7;
     color:#232323;margin:0;padding:0 24px 24px;font-size:15px;line-height:1.55}
.wrap{max-width:880px;margin:0 auto}
h1{font-size:22px;margin:18px 0 6px}
.sub{color:#777;margin-bottom:14px;font-size:13px}
.yearnav{position:sticky;top:0;background:#fafaf7ee;backdrop-filter:blur(4px);
         padding:10px 0;display:flex;gap:8px;flex-wrap:wrap;z-index:5;
         border-bottom:0.5px solid #ddd;margin-bottom:10px}
.yearnav a{text-decoration:none;background:#fff;border:0.5px solid #ccc;
           border-radius:8px;padding:6px 14px;color:#232323;font-weight:600}
.yearnav a small{color:#888;font-weight:400}
.summary{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 18px}
.chip{background:#fff;border:0.5px solid #ddd;border-radius:8px;
      padding:6px 12px;font-size:13px}
.chip b{font-size:15px}
h2.year{font-size:20px;margin:34px 0 4px;padding-top:8px;
        border-top:2px solid #BE185D}
h3.section{font-size:15px;margin:22px 0 4px;border-bottom:0.5px solid #ddd;
           padding-bottom:6px;color:#555}
.card{background:#fff;border:0.5px solid #e2e2dc;border-radius:12px;
      padding:16px 20px;margin-bottom:14px}
.chead{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.qnum{font-weight:600;font-size:15px}
.badge{font-size:12px;padding:3px 10px;border-radius:8px;white-space:nowrap}
.b-single{background:#EAF3DE;color:#27500A}
.b-numeric{background:#FAEEDA;color:#854F0B}
.b-open{background:#E6F1FB;color:#0C447C}
.b-grade{background:#F1EFE8;color:#444441}
.b-points{background:#fff;border:0.5px solid #ccc;color:#666}
.src{margin-left:auto;color:#999;font-size:11.5px}
.note{background:#FCEBEB;color:#791F1F;border-radius:8px;padding:8px 12px;
      font-size:12.5px;margin:8px 0}
.stmt{margin:6px 0 12px}
.opts{list-style:none;margin:0 0 10px;padding:0}
.opts li{padding:7px 12px;border:0.5px solid #e5e5df;border-radius:8px;
         margin-bottom:6px}
.opts li.ok{background:#EAF6E4;border-color:#9CCB84;font-weight:500}
.opts li.ok::after{content:' ✓';color:#1d7e45;font-weight:700}
.ansbox{display:inline-block;background:#EAF6E4;border:0.5px solid #9CCB84;
        border-radius:8px;padding:6px 14px;font-weight:600;margin-bottom:10px}
details{margin-top:8px}
summary{cursor:pointer;color:#0C447C;font-size:13.5px;user-select:none}
.sol{background:#f6f6f2;border-radius:8px;padding:10px 14px;margin-top:8px;
     font-size:14px}
.unparsed{background:#FCEBEB;border:0.5px solid #E5A5A5;border-radius:12px;
          padding:14px 18px;margin-bottom:12px}
.unparsed pre{white-space:pre-wrap;font-size:12px;background:#fff;
              border-radius:8px;padding:10px;overflow-x:auto}
.katex{font-size:1.04em}
"""

KATEX = """
<link rel="stylesheet"
 href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer
 src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script defer
 src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"
 onload="renderMathInElement(document.body,{delimiters:[
   {left:'$$',right:'$$',display:true},
   {left:'$',right:'$',display:false}],throwOnError:false});"></script>
"""


def esc(s):
    return html.escape(s, quote=False)


def para(s):
    parts = [p.strip() for p in s.split('\n\n') if p.strip()]
    return ''.join(f'<p>{esc(p)}</p>' for p in parts)


class Command(BaseCommand):
    help = 'HTML-превью разбора муниципального этапа ВсОШ (все годы)'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int,
                            help='только один год (по умолчанию все)')

    def handle(self, *args, **options):
        years = [options['year']] if options['year'] else list(YEARS)
        data_by_year = {}
        for year in years:
            src = Path(f'materials/vsosh_municip/{year}/parsed.json')
            if src.exists():
                data_by_year[year] = json.loads(src.read_text(encoding='utf-8'))

        out = ['<!doctype html>', '<meta charset="utf-8">',
               '<title>ВсОШ муниципальный (Москва) — превью разбора</title>',
               KATEX, f'<style>{CSS}</style>', '<div class="wrap">']
        out.append('<h1>ВсОШ — муниципальный этап (Москва), 2017–2023. '
                   'Превью разбора</h1>')
        out.append('<div class="sub">Как вопросы увидит пользователь. '
                   'Правильные ответы взяты из разметки жюри (полужирный '
                   'вариант / таблица ответов / радиокнопка) — ничего не '
                   'выдумано. У каждой карточки справа — файл и страница '
                   'PDF для сверки с оригиналом.</div>')

        nav = ['<div class="yearnav">']
        for year, data in data_by_year.items():
            nav.append(f'<a href="#y{year}">{year} '
                       f'<small>({len(data["questions"])})</small></a>')
        nav.append('</div>')
        out.append(''.join(nav))

        total_q = sum(len(d['questions']) for d in data_by_year.values())
        total_u = sum(len(d['unparsed']) for d in data_by_year.values())
        by_type = {}
        for d in data_by_year.values():
            for q in d['questions']:
                by_type[q['qtype']] = by_type.get(q['qtype'], 0) + 1
        chips = [f'<div class="chip">всего вопросов <b>{total_q}</b></div>']
        for t, (label, _) in QTYPE_LABELS.items():
            chips.append(f'<div class="chip">{label}: '
                         f'<b>{by_type.get(t, 0)}</b></div>')
        chips.append(f'<div class="chip">не разобрано: <b>{total_u}</b></div>')
        out.append('<div class="summary">' + ''.join(chips) + '</div>')

        for year, data in data_by_year.items():
            self.render_year(out, year, data)

        out.append('</div>')
        dst = Path('reports/vsosh_municip/preview.html')
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text('\n'.join(out), encoding='utf-8')
        size_mb = dst.stat().st_size / 1e6
        self.stdout.write(self.style.SUCCESS(
            f'Превью: {dst} ({total_q} карточек, unparsed {total_u}, '
            f'{size_mb:.1f} МБ)'))

    def render_year(self, out, year, data):
        questions = data['questions']
        unparsed = data['unparsed']
        out.append(f'<h2 class="year" id="y{year}">{year - 1}/{year} '
                   f'учебный год</h2>')
        by_type, notes_n = {}, 0
        for q in questions:
            by_type[q['qtype']] = by_type.get(q['qtype'], 0) + 1
            if q.get('notes'):
                notes_n += 1
        chips = [f'<div class="chip">вопросов <b>{len(questions)}</b></div>']
        for t, (label, _) in QTYPE_LABELS.items():
            if by_type.get(t):
                chips.append(f'<div class="chip">{label}: '
                             f'<b>{by_type[t]}</b></div>')
        chips.append(f'<div class="chip">с пометками: <b>{notes_n}</b></div>')
        chips.append(f'<div class="chip">не разобрано: '
                     f'<b>{len(unparsed)}</b></div>')
        out.append('<div class="summary">' + ''.join(chips) + '</div>')

        def sort_key(q):
            try:
                num = int(q['number'])
            except ValueError:
                num = 99
            return (SECTION_ORDER.get(q['section'], 9), num,
                    q['grade_group'])

        last_section = None
        for q in sorted(questions, key=sort_key):
            if q['section'] != last_section:
                out.append(f'<h3 class="section">'
                           f'{SECTION_TITLES.get(q["section"], "")}</h3>')
                last_section = q['section']
            self.render_card(out, q)

        if unparsed:
            out.append(f'<h3 class="section">Не разобрано — {len(unparsed)} '
                       '(причина + сырой текст)</h3>')
        for u in unparsed:
            src = f'{u.get("src_file", "?")}' + (
                f', стр. {u["src_page"]}' if u.get('src_page') else '')
            out.append('<div class="unparsed">'
                       f'<b>{u["grade_group"]} класс, №{u["number"]}</b> '
                       f'({u["qtype"]}) — {esc(u["reason"])}<br>'
                       f'<small>{esc(src)}</small>'
                       f'<pre>{esc(u.get("raw") or "")}</pre></div>')

    def render_card(self, out, q):
        label, cls = QTYPE_LABELS[q['qtype']]
        grades = ', '.join(str(g) for g in q['grades'])
        numbers = '; '.join(f'{g} кл. — №{n}'
                            for g, n in sorted(q['numbers'].items()))
        out.append('<div class="card"><div class="chead">')
        out.append(f'<span class="qnum">№{q["number"]}</span>')
        out.append(f'<span class="badge {cls}">{label}</span>')
        out.append(f'<span class="badge b-grade" title="{esc(numbers)}">'
                   f'класс: {grades}</span>')
        if q.get('points'):
            out.append(f'<span class="badge b-points">{q["points"]} б.</span>')
        src = q.get('src_file', '')
        page = f', стр. {q["src_page"]}' if q.get('src_page') else ''
        out.append(f'<span class="src">{esc(src)}{page}</span>')
        out.append('</div>')
        if q.get('notes'):
            out.append(f'<div class="note">⚠ {esc(q["notes"])}</div>')
        out.append(f'<div class="stmt">{para(q["statement"])}</div>')

        if q['qtype'] == 'single':
            out.append('<ul class="opts">')
            for i, opt in enumerate(q['options']):
                ok = ' class="ok"' if i == q['correct'] else ''
                out.append(f'<li{ok}>{i + 1}) {esc(opt)}</li>')
            out.append('</ul>')
        elif q['qtype'] == 'numeric':
            unit = f' {esc(q["unit"])}' if q.get('unit') else ''
            out.append(f'<div class="ansbox">Ответ: {esc(q["correct"])}'
                       f'{unit}</div>')
        elif q.get('answer_text'):
            out.append(f'<div class="ansbox">Ответ: '
                       f'{esc(q["answer_text"])}</div>')

        if q.get('solution'):
            out.append('<details><summary>Решение / комментарий жюри'
                       '</summary>'
                       f'<div class="sol">{para(q["solution"])}</div>'
                       '</details>')
        out.append('</div>')
