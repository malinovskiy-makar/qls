"""Зубастость А1 (24.10): по одному возвращает дефект, гоняет прибор, откатывает файл.

    ./venv313/bin/python claude/calc2_a1/teeth.py [номер …]

Каждая строка: файл, что заменить, на что, прибор и строка его вывода, которая обязана
покраснеть. После прибора файл возвращается `git checkout -- <файл>`, и `git status`
обязан показать, что он чист. Итог — таблица в claude/calc2_a1/teeth.md.
"""
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
JS = 'calc2/static/calc2/'
CN = 'calc2/tests/control_numbers.mjs'
LHS = 'calc2/tests/input_lhs_probe.mjs'

TEETH = [
    ('первый корень MR = MC вместо помощника', JS + '40-scenes-market.js',
     'const best = monoBestOutput(q => marginalRevenue(STATE.D, q), mcAt, STATE.D);',
     'const _r = findRoot(q => marginalRevenue(STATE.D, q) - mcAt(q)); const best = { Q: (_r == null ? 0 : _r), alts: [], profit: 0 };',
     CN, r'FAIL D: Q = 120 − P, MC = 160-4\*Q: выпуск'),
    ('без границы «MC падает до нуля»', JS + '42-scenes-mono.js',
     "if (pv > 0 && v <= 0) return { hi: (v === 0) ? q : bisect(mcFn, pq, q), cap: 'mc' };",
     '',
     CN, r'FAIL D: Q = 120 − P, MC = 160-4\*Q: выпуск'),
    ('без вывода безразличия', JS + '42-scenes-mono.js',
     'return { Q, profit: profitAt(Q), alts: ties.slice(1), cap, Qhi: hi, cands };',
     'return { Q, profit: profitAt(Q), alts: [], cap, Qhi: hi, cands };',
     CN, r'FAIL D: Q = 120 − P, MC = 160-4\*Q: безразличие названо словами'),
    ("lhs: 'P' и старая подстановка для Q(P)", JS + '40-scenes-market.js',
     "const sAfter = (STATE.S && STATE.S.srcForm === 'QP')",
     'const sAfter = false',
     CN, r'FAIL Qd = 180 − P, Qs = 3P − 60, налог 24 на продавца: запись'),
    ('без splitCurveLhs (левая часть не разбирается)', JS + '80-ui.js',
     "  if (parts.length === 1) return { rhs: raw, lhs: '', form: null };",
     "  if (parts.length >= 1) return { rhs: raw, lhs: '', form: null };",
     LHS, r'FAIL «Q=100-2P»: Q\* = 100/3'),
    ('makeCurve на голом compileFormula', JS + '42-scenes-mono.js',
     "  const b = buildAnyCurve((expr || '').trim());\n  if (b.error) return { error: b.error };\n  if (b.form === 'QP') {",
     "  const b = Object.assign({ form: 'PQ', rhs: (expr || '').trim() }, compileFormula((expr || '').trim()));\n  if (b.error) return { error: b.error };\n  b.linear = detectLinear(b.compiled);\n  if (b.form === 'QP') {",
     LHS, r'FAIL Дискриминация 3-й степени: оба спроса Q\(P\)'),
    ('английская ошибка Math.js', JS + '10-math-core.js',
     "  const m = String(msg == null ? '' : msg);\n  let r =",
     "  const m = String(msg == null ? '' : msg);\n  return m;\n  let r =",
     LHS, r'FAIL Undefined symbol X'),
    ('приставка без обновления', JS + '80-ui.js',
     "          if (typeof row._syncPrefix === 'function') row._syncPrefix();\n",
     '',
     LHS, r'FAIL правка «100 − Q» → «100 − 2P»: приставка'),
    ('мост MathLive стирает ошибку на Enter', JS + '82-input.js',
     "      if (inp.value !== text) {\n        if (typeof fieldProblem === 'function') fieldProblem(inp, '');",
     "      if (typeof fieldProblem === 'function') fieldProblem(inp, '');\n      if (inp.value !== text) {",
     LHS, r'FAIL «P=100-2P»: ошибка под полем видна после Enter'),
    ('«Лаффер» на голом compileFormula', JS + '50-scenes-macro.js',
     '    const D = buildAnyCurve(P.d), S = buildAnyCurve(P.s);',
     '    const D = compileFormula(P.d), S = compileFormula(P.s); if (D.compiled) D.linear = detectLinear(D.compiled); if (S.compiled) S.linear = detectLinear(S.compiled);',
     LHS, r'FAIL Лаффер, D: Q = 120 − P'),
]


def sh(cmd):
    return subprocess.run(cmd, cwd=ROOT, shell=True, capture_output=True, text=True)


def main():
    pick = {int(a) for a in sys.argv[1:]} or set(range(1, len(TEETH) + 1))
    rows = []
    for i, (what, path, old, new, probe, red) in enumerate(TEETH, 1):
        if i not in pick:
            continue
        f = ROOT / path
        src = f.read_text(encoding='utf-8')
        assert src.count(old) == 1, f'{i}: образец не найден ровно один раз в {path}'
        f.write_text(src.replace(old, new), encoding='utf-8')
        try:
            out = sh(f'node {probe}')
            log = out.stdout + out.stderr
            hit = re.search(red, log) is not None
            fails = len(re.findall(r'^\s*FAIL', log, re.M))
        finally:
            sh(f'git checkout -- {path}')
        clean = sh(f'git status --porcelain -- {path}').stdout.strip() == ''
        rows.append((i, what, probe.split('/')[-1], fails, hit, clean))
        print(f'{i}. {what}: {"КРАСНЫЙ" if hit else "НЕ ПОКРАСНЕЛ"} ({fails} FAIL), откат {"чистый" if clean else "НЕ ЧИСТЫЙ"}', flush=True)
    md = ['| # | Дефект | Прибор | Покраснело | Строка-признак | Откат |', '|---|---|---|---|---|---|']
    for i, what, probe, fails, hit, clean in rows:
        md.append(f'| {i} | {what} | `{probe}` | {fails} FAIL | {"да" if hit else "НЕТ"} | {"git status чист" if clean else "НЕ ЧИСТ"} |')
    (ROOT / 'claude/calc2_a1/teeth.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print('\n'.join(md))


if __name__ == '__main__':
    main()
