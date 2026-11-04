#!/usr/bin/env python3
"""Сверка формул файла с НАСТОЯЩИМ pgfmath.

Сверка записи с рисунком (texproto.js) считает формулу средствами Math.js.
В файл же уходит её перевод на язык pgfplots, и считать его будет TeX. Этот
прибор закрывает последний зазор: берёт из описей (<состояние>.list.json)
каждую напечатанную формулу с пятью пробными точками «аргумент — значение по
движку», считает формулу самим pgfmath и сравнивает.

    ./venv313/bin/python claude/mockups/calc2_tex_20261007/proto/formulas.py ПАПКА [ПАПКА ...]

Допуск — 0,2 % размаха оси значения: pgfmath держит четыре-пять значащих цифр.
Код возврата 1 при расхождении, 3 — если pdflatex не найден."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


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
    def add(pgf, var, probe, span, where):
        if not pgf or not probe:
            return
        c = cases.setdefault((pgf, var), {'probe': {}, 'span': span or 1, 'where': where})
        for x, y in probe:
            c['probe'][round(x, 9)] = y
        c['span'] = max(c['span'], span or 1)
    for folder in folders:
        for f in sorted(Path(folder).glob('*.list.json')):
            data = json.loads(f.read_text(encoding='utf-8'))
            for p in data.get('panels', []):
                for it in p.get('items', []):
                    if it.get('kind') != 'path':
                        continue
                    r = it.get('rec')
                    if r and r.get('ok'):
                        add(r.get('pgf'), 't' if r.get('axis') == 'y' else 'x', r.get('probe'), r.get('span'), f.name)
                    a = it.get('area')
                    if a and a.get('ok'):
                        for side in ('lo', 'hi'):
                            add(a[side].get('pgf'), 'x', a[side].get('probe'), a.get('span'), f.name)
    return cases


def main():
    folders = sys.argv[1:]
    if not folders:
        print(__doc__)
        return 2
    binary = find_pdflatex()
    if not binary:
        print('pdflatex не найден: формулы сверить нечем')
        return 3
    cases = collect(folders)
    if not cases:
        print('формул в описях нет')
        return 0
    lines = ['\\documentclass{article}', '\\usepackage{pgfplots}', '\\pgfplotsset{compat=1.18}', '\\begin{document}',
             '\\pgfkeys{/pgf/fpu=true,/pgf/fpu/output format=sci}',
             '\\newcommand{\\T}[4]{\\pgfmathdeclarefunction*{#2}{0}{\\pgfmathparse{#3}}\\pgfmathparse{#4}\\typeout{RES #1 => \\pgfmathresult}}']
    index = []
    for (pgf, var), c in cases.items():
        for x, y in sorted(c['probe'].items()):
            lines.append('\\T{%d}{%s}{%s}{%s}' % (len(index), var, repr(float(x)), pgf))
            index.append((pgf, var, x, y, c['span'], c['where']))
    lines.append('\\end{document}')
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / 'f.tex').write_text('\n'.join(lines), encoding='utf-8')
        p = subprocess.run([binary, '-no-shell-escape', '-interaction=nonstopmode', 'f.tex'], cwd=tmp, capture_output=True, text=True, errors='replace', timeout=900)
        log = p.stdout
    got = {int(m.group(1)): m.group(2) for m in re.finditer(r'RES (\d+) => (\S+)', log)}
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
