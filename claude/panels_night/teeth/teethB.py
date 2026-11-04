# Зубастость этапа Б: поломка → прибор → откат (git checkout -- файл).
import subprocess, os, sys, json, time
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
OUT = 'claude/panels_night/teeth/B.txt'
def sub(path, old, new):
    s = open(path, encoding='utf-8').read(); assert old in s, (path, old[:70]); open(path, 'w', encoding='utf-8').write(s.replace(old, new, 1))
def run(cmd):
    e = dict(os.environ, CALC2_BASE_URL='http://127.0.0.1:8099', ENGINES='chromium')
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=e)
    out = r.stdout + r.stderr
    lines = [l for l in out.splitlines() if 'FAIL' in l or 'ИТОГ' in l or '✗' in l or 'ТЕКСТ' in l or 'СТРОКА' in l or 'расхожд' in l]
    return r.returncode, lines
def compare(keys):
    # Опись только этих моделей и сверка с описью ДО этапа Б (A_after.json, та же выборка) и B_allow:
    # то же, что конец этапа, но на одной модели. Выборка пишется в момент запуска (своя на модель).
    k = ' '.join(keys); sub_path = 'claude/panels_night/tmp/A_sub_%s.json' % '_'.join(keys)
    A = json.load(open('claude/panels_night/A_after.json', encoding='utf-8'))
    A['models'] = {x: A['models'][x] for x in keys}
    json.dump(A, open(sub_path, 'w', encoding='utf-8'))
    return ('KEYS="%s" node claude/mockups/calc2_panels_20261014/tools/panels_inventory.mjs claude/panels_night/tmp/teeth_inv.json >/dev/null 2>&1; '
            'node claude/mockups/calc2_panels_20261014/tools/panels_compare.mjs %s claude/panels_night/tmp/teeth_inv.json claude/panels_night/B_allow.json' % (k, sub_path))
P = 'node calc2/tests/redesign/answer_panel_probe.mjs'
CSS, ANS, MKT, WS = 'calc2/static/calc2/calc2.css', 'calc2/static/calc2/94-answer.js', 'calc2/static/calc2/40-scenes-market.js', 'calc2/static/calc2/86-workspace.js'
CASES = [
 ('1 главные значения 16 px', lambda: sub(CSS, '#ans-hero .ans-line { font-size: 20px; }', '#ans-hero .ans-line { font-size: 16px; }'), 'KEYS="taxes mono" ' + P + ' --only В', [CSS]),
 ('2 показать «Δ»', lambda: sub(CSS, '#params-panel .tx-table .tx-delta { display: none; }', ''), 'KEYS="taxes" ' + P + ' --only В', [CSS]),
 ('3 убрать data-word', lambda: sub(ANS, "      if (w) { if (first.dataset.word !== w) first.dataset.word = w; }", "      if (false) { }"), 'KEYS="taxes" ' + P + ' --only В,В2', [ANS]),
 ('4 показать строку Q налога', lambda: sub(ANS, "if (c.tx && c.tx.tr && row.querySelector('.ans-was')) c.tx.tr.classList.add('ans-trdup');", "if (c.tx && c.tx.tr && row.querySelector('.ans-was') && plainText(c.tx.tr.children[0]) !== 'Q') c.tx.tr.classList.add('ans-trdup');"), P + ' --only В2', [ANS]),
 ('5 спрятать строку Q у quota', lambda: sub(ANS, "  const areas = document.getElementById('info-areas');\n  if (!areas) return;", "  if (STATE.sceneKey === 'quota') document.querySelectorAll('#info-tax .tx-table tr').forEach(tr => { if (/^Q/.test(plainText(tr.children[0]))) tr.classList.add('ans-trdup'); });\n  const areas = document.getElementById('info-areas');\n  if (!areas) return;"), compare(['quota']), [ANS]),
 ('6 убрать строку SW', lambda: sub(MKT, "    ['SW', STATE.cs + STATE.ps, STATE.csTax + STATE.psTax + STATE.budget],\n", ''), P + ' --only В2', [MKT]),
 ('7 не копировать заметки в «Разбор»', lambda: sub(WS, "  answerNotesToExplain(from, to);\n}", "}"), compare(['taxes']), [WS]),
 ('8 вернуть подпись «Монополия»', lambda: sub(ANS, "'mono': [['info-mono', 0, null, ['Выпуск монополиста', 'Qm']]", "'mono': [['info-mono', 0]"), P + ' --only В3', [ANS]),
 ('9 склеить ячейки естественной монополии', lambda: sub(ANS, "    ['info-nat', 2, null, null, [['Средние издержки', 'ATC(Qm)', '\\\\mathrm{ATC}(Q_m)'], ['Прибыль', '', '']]]],", "    ['info-nat', 2]],"), P + ' --only В3', [ANS]),
]
only = sys.argv[1:]
with open(OUT, 'a', encoding='utf-8') as f:
    for name, brk, cmd, files in CASES:
        if only and name.split()[0] not in only: continue
        brk(); time.sleep(2)
        code, lines = run(cmd)
        subprocess.run(['git', 'checkout', '--'] + files)
        f.write('### ' + name + ' → код ' + str(code) + '\n' + '\n'.join(l[:400] for l in lines[:8]) + '\n'); f.flush()
    d = subprocess.run(['git', 'diff', '--stat'], capture_output=True, text=True).stdout
    f.write('git diff после отката: ' + (d.strip() or 'пусто') + '\n')
