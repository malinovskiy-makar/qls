#!/usr/bin/env python3
"""Корпус подписей холста (прибор tex_labels).

Все РАЗНЫЕ тексты подписей по набору состояний (подписи, числа делений, имена
осей, строки легенды — поле labels журнала аудита) переводятся так же, как в
файле, и собираются ОДНИМ документом настоящим pdflatex: если хоть одна
подпись роняет сборку, корпус не соберётся.

    ./venv313/bin/python calc2/tests/tex/labels.py [ПАПКА ...]

ПАПКА — папка аудита (по умолчанию reports/calc2_tex/audit). Пишет в первую
ПАПКУ labels/corpus.tex, corpus.pdf, страницы corpus-N.png и corpus.txt
(номер → исходная разметка → перевод) для сверки с таблицей SPEC.md, раздел 7.
Код возврата 1, если корпус не собрался; 3 — pdflatex не найден."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from compile import find_pdflatex  # noqa: E402

HEAD = r"""\documentclass[10pt,a4paper]{article}
\usepackage[T2A]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[english,russian]{babel}
\usepackage{amsmath}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usepackage{geometry}
\geometry{margin=1.5cm}
\begin{document}
\pagestyle{empty}
"""


def main():
    folders = sys.argv[1:] or [str(ROOT / 'reports' / 'calc2_tex' / 'audit')]
    binary = find_pdflatex()
    if not binary:
        print('pdflatex не найден: корпус собрать нечем')
        return 3
    seen = {}
    for folder in folders:
        for line in (Path(folder) / 'audit.jsonl').read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            for lab in r.get('labels') or []:
                if lab.get('tex') and lab['tex'] not in seen:
                    seen[lab['tex']] = (lab.get('raw') or '', r['id'])
    items = list(seen.items())
    out = Path(folders[0]) / 'labels'
    out.mkdir(parents=True, exist_ok=True)
    body = []
    per = 40
    for k in range(0, len(items), per):
        body.append(r'\noindent\begin{tikzpicture}')
        for j, (tex, _) in enumerate(items[k:k + per]):
            n = k + j + 1
            body.append(r'\node[anchor=base east, font=\tiny] at (0,%.2f) {%d};' % (-j * 0.6, n))
            body.append(r'\node[anchor=base west, inner sep=0pt, font=\fontsize{9}{10.3}\selectfont] at (0.2,%.2f) {%s};' % (-j * 0.6, tex))
        body.append(r'\end{tikzpicture}\newpage')
    (out / 'corpus.tex').write_text(HEAD + '\n'.join(body) + '\n\\end{document}\n', encoding='utf-8')
    (out / 'corpus.txt').write_text('\n'.join('%d\t%s\t%s\t%s' % (i + 1, raw, tex, sid) for i, (tex, (raw, sid)) in enumerate(items)) + '\n', encoding='utf-8')
    p = subprocess.run([binary, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', 'corpus.tex'], cwd=out,
                       capture_output=True, text=True, errors='replace', timeout=900)
    ok = p.returncode == 0 and (out / 'corpus.pdf').exists()
    if ok and shutil.which('pdftoppm'):
        subprocess.run(['pdftoppm', '-r', '110', '-png', str(out / 'corpus.pdf'), str(out / 'corpus')], capture_output=True)
    print('разных подписей', len(items), '| корпус', 'собрался' if ok else 'НЕ СОБРАЛСЯ', '→', out)
    if not ok:
        log = (out / 'corpus.log').read_text(errors='replace') if (out / 'corpus.log').exists() else p.stdout
        i = log.find('\n!')
        print(log[i:i + 800] if i >= 0 else log[-800:])
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
