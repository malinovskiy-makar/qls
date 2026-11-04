"""Зубастость проверок сессии А2 (24–25.10): каждый дефект временно возвращается в код, нужный прибор
обязан покраснеть, потом файл возвращается `git checkout -- <файл>`.

    ./venv313/bin/python claude/calc2_a2/teeth.py        (сервер на 8099 с --noreload: статика читается с диска)

Пишет claude/calc2_a2/teeth.md. Запускать только на ЗАКОММИЧЕННОЙ работе: checkout вернёт файл к коммиту.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = 'calc2/static/calc2/'

# (дефект, файл, было, стало, приборы)
DEFECTS = [
    ('постоянные строки HERO (без HERO_STATE)', JS + '94-answer.js',
     "const live = HERO_STATE[STATE.sceneKey] ? HERO_STATE[STATE.sceneKey]() : null;",
     "const live = null;", ['calc2/tests/answer_interv_probe.mjs']),
    ('«Излишки» без подписи состояния', JS + '94-answer.js',
     "if (STATE.scenario === 'openecon') return 'Излишки при автаркии';",
     "if (false) return 'Излишки при автаркии';", ['calc2/tests/answer_interv_probe.mjs']),
    ('правка спрятанной кривой не включает глаз', JS + '80-ui.js',
     "if (!err && raw && !curve.visible) {", "if (false) {", ['calc2/tests/input_lhs_probe.mjs']),
    ('правка спрятанной MSB / MSC не включает её', JS + '88-params.js',
     "if (!STATE[key + 'On'] && STATE[key + 'Expr'] && STATE[key + 'Expr'] !== prev) {", "if (false) {",
     ['calc2/tests/input_lhs_probe.mjs']),
    ('SW без внешних издержек', JS + '40-scenes-market.js',
     "const extNet = (Q) => (Q > 0) ?", "const extNet = (Q) => (false) ?",
     ['calc2/tests/control_numbers.mjs', 'calc2/tests/answer_interv_probe.mjs']),
    ('пределы ползунка цены — не коридор (прежняя дорожка 0…100 в процентах)', JS + '40-scenes-market.js',
     "  if (sl && q && q.P != null && q.Phi > q.Plo) {", "  if (false) {",
     ['calc2/tests/control_numbers.mjs', 'calc2/tests/input_lhs_probe.mjs']),
    ('середина коридора по умолчанию', JS + '84-picker.js',
     "else if (name === 'quota') { setType('quota'); setQuota(40); setQuotaPos(1); }",
     "else if (name === 'quota') { setType('quota'); setQuota(40); setQuotaPos(0.5); }",
     ['calc2/tests/control_numbers.mjs', 'calc2/tests/answer_interv_probe.mjs']),
    ('Qc монополии первым корнем D = MC', JS + '40-scenes-market.js',
     "      const comp = competitiveOutput(STATE.D, mcAt);",
     "      const comp = (function () { var r = findRoot(function (q) { return evalCurve(STATE.D, q) - mcAt(q); }); return { Q: r, P: r != null ? mcAt(r) : null }; })();",
     ['calc2/tests/control_numbers.mjs']),
    ('составной спрос без границы MC = 0', JS + '42-scenes-mono.js',
     "  const best = monoBestOutput(q => marginalRevenue(segAt(q).D, q), mc, Dk,",
     "  const best = monoBestOutput(q => marginalRevenue(segAt(q).D, q), q => (mc(q) <= 0 ? 1e-12 : mc(q)), Dk,",
     ['calc2/tests/control_numbers.mjs', 'calc2/tests/answer_interv_probe.mjs']),
    ('промежуточная запись остаётся кривой', JS + '80-ui.js',
     "          restoreCurveRecord(curve, fInp._editBase);", "          // restoreCurveRecord(curve, fInp._editBase);",
     ['calc2/tests/input_lhs_probe.mjs']),
]


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def main():
    if run(['git', 'status', '--porcelain', '--', 'calc2/static']).stdout.strip():
        sys.exit('calc2/static с незакоммиченными правками — сначала коммит')
    rows = []
    for name, f, old, new, probes in DEFECTS:
        p = ROOT / f
        src = p.read_text(encoding='utf-8')
        if src.count(old) != 1:
            sys.exit(f'{name}: образец встречается {src.count(old)} раз в {f}')
        p.write_text(src.replace(old, new), encoding='utf-8')
        try:
            for probe in probes:
                r = run(['node', probe])
                out = r.stdout + r.stderr
                fails = len(re.findall(r'^\s*FAIL', out, re.M))
                rows.append((name, probe.split('/')[-1], fails, r.returncode))
                print(f'{name} | {probe} | провалов {fails} | код {r.returncode}', flush=True)
        finally:
            run(['git', 'checkout', '--', f])
        st = run(['git', 'status', '--porcelain', '--', f]).stdout.strip()
        rows[-1] = rows[-1] + ('вернул, чисто' if not st else 'НЕ ЧИСТО: ' + st,)
    lines = ['# Зубастость А2 (24–25.10)', '',
             'Дефект временно возвращён в код, прибор прогнан, файл возвращён `git checkout -- <файл>`.', '',
             '| Дефект | Прибор | Провалов | Код | Возврат |', '|---|---|---|---|---|']
    for r in rows:
        lines.append(f'| {r[0]} | `{r[1]}` | {r[2]} | {r[3]} | {r[4] if len(r) > 4 else "вернул"} |')
    (ROOT / 'claude/calc2_a2/teeth.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
