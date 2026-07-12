# -*- coding: utf-8 -*-
"""
scan_vsosh_artifacts — поиск систематических артефактов разбора во всех
parsed_<год>.json (диагностика перед фиксом парсера).

Классы паттернов:
- literal_comma:   литеральный «{,}» ВНЕ математики (виден пользователю);
- double_eq:       «==» внутри $...$;
- glyph_slash:     «/» на месте буквы (слэш, зажатый между кириллицей/буквами);
- lost_subscript:  переменная + min/max без индекса ($w$ min и т.п.) или
                   одинокая кириллическая буква после формулы (L ж);
- glued_fraction:  склеенные числовые цепочки (−5,51,1 / 2,421,1^{2}) —
                   числитель слипся со знаменателем без \\frac и /;
- linearized_note: вопросы с плашкой «математика линеаризована …».

Запуск: ./venv/bin/python manage.py scan_vsosh_artifacts
"""
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand

MATH_SEG_RE = re.compile(r'(?<!\\)\$((?:\\.|[^$\\])*)\$')

PATTERNS = {
    # {,} вне математики: вырезаем математические сегменты и ищем остаток
    'literal_comma': None,   # спец-обработка
    'double_eq': None,       # спец-обработка (внутри математики)
    'glyph_slash': re.compile(r'[а-яёА-ЯЁ]/[-а-яёА-ЯЁ]|[а-яёА-ЯЁ]-/|/-[а-яёА-ЯЁ]'),
    'lost_subscript': re.compile(
        r'\$[^$]*[A-Za-zшыжз]\$\s*(?:min|max|ж|ш)(?![а-яё])|'
        r'[A-Za-z]\s+(?:min|max)(?![a-z])'),
    'glued_fraction': re.compile(
        r'\d[,.]\d+\d[,.]\d|'            # 5,51,1 — две десятичных слиплись
        r'−\d+[,.]?\d*\d+[,.]\d'),       # −5,51,1
}


def math_parts(text):
    return MATH_SEG_RE.findall(text or '')


def outside_math(text):
    return MATH_SEG_RE.sub(' ', text or '')


class Command(BaseCommand):
    help = 'Ищет систематические артефакты разбора в parsed_<год>.json'

    def handle(self, *args, **options):
        rows = []   # (pattern, year, number, field, snippet)
        for path in sorted(Path('materials/vsosh_region').glob('*/parsed_*.json')):
            year = path.parent.name
            data = json.loads(path.read_text(encoding='utf-8'))
            for q in data['questions']:
                fields = [('statement', q.get('statement', '')),
                          ('solution', q.get('solution', ''))]
                fields += [(f'option{i+1}', o)
                           for i, o in enumerate(q.get('options') or [])]
                if q.get('qtype') == 'numeric':
                    fields.append(('answer', str(q.get('correct', ''))))
                for fname, text in fields:
                    if not text:
                        continue
                    out = outside_math(text)
                    if '{,}' in out:
                        i = out.find('{,}')
                        rows.append(('literal_comma', year, q['number'], fname,
                                     out[max(0, i-30):i+35]))
                    for seg in math_parts(text):
                        if '==' in seg.replace(' ', ''):
                            # '= =' и '==' одинаково подозрительны
                            pass
                        if re.search(r'=\s*=', seg):
                            i = re.search(r'=\s*=', seg).start()
                            rows.append(('double_eq', year, q['number'], fname,
                                         seg[max(0, i-30):i+35]))
                    for pname in ('glyph_slash', 'lost_subscript',
                                  'glued_fraction'):
                        for m in PATTERNS[pname].finditer(text):
                            rows.append((pname, year, q['number'], fname,
                                         text[max(0, m.start()-35):m.end()+35]))
                if q.get('notes'):
                    rows.append(('linearized_note', year, q['number'], 'notes',
                                 q['notes'][:70]))

        from collections import Counter
        counts = Counter(r[0] for r in rows)
        self.stdout.write('=== Сводка ===')
        for p, n in counts.most_common():
            years = sorted(set(r[1] for r in rows if r[0] == p))
            self.stdout.write(f'{p}: {n} вхождений, годы: {", ".join(years)}')
        self.stdout.write('')
        self.stdout.write('=== Детали ===')
        for p, year, num, fname, snip in rows:
            snip = snip.replace('\n', ' | ')
            self.stdout.write(f'[{p}] {year} №{num} {fname}: …{snip}…')
