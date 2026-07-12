# -*- coding: utf-8 -*-
"""
preview_vsosh_region — HTML-превью разобранных тестов ВсОШ (региональный этап)
из parsed_<год>.json. Карточки «как увидит пользователь»: тип бейджем, классы,
условие с KaTeX, варианты с выделенным правильным, решение жюри раскрывающимся
блоком, баллы. В шапке — сводка; отдельной секцией — unparsed целиком.

Запуск: ./venv/bin/python manage.py preview_vsosh_region --year 2023
Выход:  reports/vsosh_region/preview_<год>.html (KaTeX с CDN, файл автономный).
"""
import html
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

QTYPE_LABELS = {
    'boolean': ('Верно/Неверно', 'b-bool'),
    'single': ('Один ответ', 'b-single'),
    'multi': ('Все верные', 'b-multi'),
    'numeric': ('Числовой ответ', 'b-numeric'),
}

SECTION_TITLES = {
    1: 'Задание 1 — «Верно/Неверно»',
    2: 'Задание 2 — выберите один',
    3: 'Задание 3 — выберите все верные',
    4: 'Задание 4 — открытый (числовой) ответ',
}

CSS = """
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:#fafaf7;
     color:#232323;margin:0;padding:24px;font-size:15px;line-height:1.55}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:22px;margin:0 0 6px}
.sub{color:#777;margin-bottom:18px;font-size:13px}
.summary{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:22px}
.chip{background:#fff;border:0.5px solid #ddd;border-radius:8px;
      padding:6px 12px;font-size:13px}
.chip b{font-size:15px}
h2.section{font-size:16px;margin:28px 0 4px;border-bottom:0.5px solid #ddd;
           padding-bottom:6px}
.preamble{color:#8a6d1d;background:#FAF3DC;border-radius:8px;padding:8px 12px;
          font-size:12.5px;margin:8px 0 14px}
.card{background:#fff;border:0.5px solid #e2e2dc;border-radius:12px;
      padding:16px 20px;margin-bottom:14px}
.chead{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.qnum{font-weight:600;font-size:15px}
.badge{font-size:12px;padding:3px 10px;border-radius:8px;white-space:nowrap}
.b-bool{background:#E6F1FB;color:#0C447C}
.b-single{background:#EAF3DE;color:#27500A}
.b-multi{background:#F3E8FA;color:#5B2183}
.b-numeric{background:#FAEEDA;color:#854F0B}
.b-grade{background:#F1EFE8;color:#444441}
.b-points{background:#fff;border:0.5px solid #ccc;color:#666}
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
    help = 'Собирает HTML-превью разбора тестов ВсОШ из parsed_<год>.json'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=2023)

    def handle(self, *args, **options):
        year = options['year']
        src = Path('materials/vsosh_region') / str(year) / f'parsed_{year}.json'
        if not src.exists():
            raise CommandError(f'Нет файла {src} — сначала parse_vsosh_region')
        data = json.loads(src.read_text(encoding='utf-8'))
        questions = data['questions']
        unparsed = data['unparsed']

        by_type, by_grade = {}, {}
        for q in questions:
            by_type[q['qtype']] = by_type.get(q['qtype'], 0) + 1
            for g in q['grades']:
                by_grade[g] = by_grade.get(g, 0) + 1

        out = ['<!doctype html>',   # без него KaTeX отказывает (quirks mode)
               '<meta charset="utf-8">',
               f'<title>ВсОШ регион {year} — превью разбора теста</title>',
               KATEX, f'<style>{CSS}</style>', '<div class="wrap">']
        out.append(f'<h1>ВсОШ — региональный этап {year - 1}/{year}. '
                   f'Первый тур (тест)</h1>')
        out.append('<div class="sub">Превью разбора PDF «Правильные ответы и '
                   'комментарии» — как вопросы увидит пользователь. '
                   'Правильные варианты взяты из полужирной разметки жюри, '
                   'ничего не выдумано.</div>')

        chips = [f'<div class="chip">всего уникальных <b>{len(questions)}</b></div>']
        for t, (label, _) in QTYPE_LABELS.items():
            chips.append(f'<div class="chip">{label}: <b>{by_type.get(t, 0)}</b></div>')
        for g in (9, 10, 11):
            chips.append(f'<div class="chip">{g} класс: <b>{by_grade.get(g, 0)}</b></div>')
        nnotes = sum(1 for q in questions if q.get('notes'))
        chips.append(f'<div class="chip">unparsed: <b>{len(unparsed)}</b></div>')
        chips.append(f'<div class="chip">с пометками: <b>{nnotes}</b></div>')
        out.append('<div class="summary">' + ''.join(chips) + '</div>')

        preambles = {}
        for p in data.get('section_preambles', []):
            preambles.setdefault(p['section'], p)

        def q_section(q):
            return q.get('section') or int(q['number'].split('.')[0])

        last_section = None
        for q in sorted(questions,
                        key=lambda q: (q_section(q),
                                       [int(x) for x in q['number'].split('.')],
                                       min(q['grades']))):
            section = q_section(q)
            if section != last_section:
                out.append(f'<h2 class="section">{SECTION_TITLES.get(section, "")}</h2>')
                if section in preambles:
                    out.append(f'<div class="preamble">'
                               f'{esc(preambles[section]["text"])}</div>')
                last_section = section

            label, cls = QTYPE_LABELS[q['qtype']]
            grades = ', '.join(str(g) for g in q['grades'])
            out.append('<div class="card"><div class="chead">')
            out.append(f'<span class="qnum">{q["number"]}</span>')
            out.append(f'<span class="badge {cls}">{label}</span>')
            out.append(f'<span class="badge b-grade">класс: {grades}</span>')
            if q.get('points'):
                out.append(f'<span class="badge b-points">{q["points"]} б.</span>')
            out.append('</div>')
            if q.get('notes'):
                out.append(f'<div class="note">⚠ {esc(q["notes"])}</div>')
            out.append(f'<div class="stmt">{esc(q["statement"])}</div>')

            if q['qtype'] == 'boolean':
                out.append('<ul class="opts">')
                for text, is_ok in (('Верно', q['correct'] is True),
                                    ('Неверно', q['correct'] is False)):
                    out.append(f'<li class="{"ok" if is_ok else ""}">{text}</li>')
                out.append('</ul>')
            elif q['qtype'] in ('single', 'multi'):
                correct = (q['correct'] if isinstance(q['correct'], list)
                           else [q['correct']])
                out.append('<ul class="opts">')
                for i, opt in enumerate(q['options']):
                    ok = ' class="ok"' if i in correct else ''
                    out.append(f'<li{ok}>{i + 1}) {esc(opt)}</li>')
                out.append('</ul>')
            else:  # numeric
                unit = f' {esc(q["unit"])}' if q['unit'] else ''
                out.append(f'<div class="ansbox">Ответ: {esc(q["correct"])}'
                           f'{unit}</div>')

            if q['solution']:
                out.append('<details><summary>Комментарий жюри</summary>'
                           f'<div class="sol">{para(q["solution"])}</div></details>')
            out.append('</div>')

        out.append('<h2 class="section">Unparsed — не разобрано '
                   f'({len(unparsed)})</h2>')
        if not unparsed:
            out.append('<div class="sub">Пусто: все вопросы всех трёх PDF '
                       'разобраны.</div>')
        for u in unparsed:
            out.append('<div class="unparsed">'
                       f'<b>{u["grade"]} класс, №{u["number"]}</b> '
                       f'({u["qtype"]}) — {esc(u["reason"])}'
                       f'<pre>{esc(u["raw"])}</pre></div>')

        out.append('</div>')
        dst = Path('reports/vsosh_region') / f'preview_{year}.html'
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text('\n'.join(out), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(
            f'Превью: {dst} ({len(questions)} карточек, unparsed {len(unparsed)})'))
