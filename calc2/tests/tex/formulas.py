#!/usr/bin/env python3
"""Сверка формул файла с НАСТОЯЩИМ pgfmath (прибор tex_formulas).

Сверка записи с рисунком считает формулу средствами Math.js. В файл же уходит
её перевод на язык pgfplots, и считать его будет TeX. Прибор закрывает этот
зазор: берёт из журнала аудита (audit.jsonl, поле formulas) каждую напечатанную
формулу с пробными точками «аргумент — значение по движку», считает формулу
самим pgfmath и сравнивает.

    ./venv313/bin/python calc2/tests/tex/formulas.py [ПАПКА ...]

ПАПКА — папка аудита (по умолчанию reports/calc2_tex/audit). Допуск — 0,2 %
размаха оси значения: pgfmath держит четыре-пять значащих цифр. Код возврата 1
при расхождении, 3 — pdflatex не найден."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def find_pdflatex():
    found = shutil.which('pdflatex')
    if found:
        return found
    for guess in ('/Library/TeX/texbin/pdflatex', '/usr/bin/pdflatex'):
        if os.path.isfile(guess):
            return guess
    return None


def collect(folders):
    """Формулы без повторов: (формула, переменная) → пробные точки и размах."""
    cases = {}
    for folder in folders:
        log = Path(folder) / 'audit.jsonl'
        for line in log.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            for f in r.get('formulas') or []:
                if not f.get('pgf') or not f.get('probe'):
                    continue
                c = cases.setdefault((f['pgf'], f['v']), {'probe': {}, 'span': f.get('span') or 1, 'where': r['id']})
                for x, y in f['probe']:
                    c['probe'][round(x, 9)] = y
                c['span'] = max(c['span'], f.get('span') or 1)
    return cases


def main():
    folders = sys.argv[1:] or [str(ROOT / 'reports' / 'calc2_tex' / 'audit')]
    binary = find_pdflatex()
    if not binary:
        print('pdflatex не найден: формулы сверить нечем')
        return 3
    cases = collect(folders)
    if not cases:
        print('формул в журнале нет')
        return 0
    head = ['\\documentclass{article}', '\\usepackage{pgfplots}', '\\pgfplotsset{compat=1.18}', '\\begin{document}',
            '\\pgfkeys{/pgf/fpu=true,/pgf/fpu/output format=sci}',
            # строки журнала TeX переносятся на 79-м знаке: печатаем коротко (RECON.md, раздел 6, п. 30)
            '\\newcommand{\\T}[4]{\\pgfmathdeclarefunction*{#2}{0}{\\pgfmathparse{#3}}\\pgfmathparse{#4}\\typeout{RES #1 => \\pgfmathresult}}']
    index = []
    body = []
    for (pgf, var), c in cases.items():
        for x, y in sorted(c['probe'].items()):
            body.append('\\T{%d}{%s}{%s}{%s}' % (len(index), var, repr(float(x)), pgf))
            index.append((pgf, var, x, y, c['span'], c['where']))
    got = {}
    # пакетами по 4000 пробных точек: один огромный документ TeX считает долго
    for start in range(0, len(body), 4000):
        lines = head + body[start:start + 4000] + ['\\end{document}']
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'f.tex').write_text('\n'.join(lines), encoding='utf-8')
            p = subprocess.run([binary, '-no-shell-escape', '-interaction=nonstopmode', 'f.tex'], cwd=tmp, capture_output=True, text=True, errors='replace', timeout=1800)
            for m in re.finditer(r'RES (\d+) => (\S+)', p.stdout):
                got[int(m.group(1))] = m.group(2)
    bad = []
    for i, (pgf, var, x, y, span, where) in enumerate(index):
        raw = got.get(i)
        try:
            val = float(raw)
        except (TypeError, ValueError):
            bad.append((pgf, var, x, y, raw, where))
            continue
        if abs(val - y) > max(2e-3 * span, 2e-4 * abs(y)):
            bad.append((pgf, var, x, y, val, where))
    print('формул', len(cases), '| пробных точек', len(index), '| расхождений', len(bad))
    seen = set()
    for pgf, var, x, y, val, where in bad:
        if pgf in seen:
            continue
        seen.add(pgf)
        print('   РАСХОЖДЕНИЕ %s: при %s = %s движок даёт %s, pgfmath — %s   [%s]' % (pgf, var, x, y, val, where))
        if len(seen) >= 20:
            break
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
