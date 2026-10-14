"""Зубастость этапа А (сессия 6, А8): по одной поломке, прибор, откат (git checkout -- файл).
python3 claude/panels_s6/teeth_A.py  → claude/panels_s6/teeth/A.txt"""
import subprocess, time, os, re
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
S = 'calc2/static/calc2/'
Q4 = """    '<p><b>Почему предложение денег нарисовано вертикальным?</b> Потому что его задаёт центральный банк, а не ставка: сколько решили выпустить, столько и есть.</p>' +\n"""
CASES = [
 ('1 вернуть 16 px карточкам сцен', S + 'calc2.css',
  "#tools-panel .fc-card > .crow-formula.fc-pre-off > .fc-prefix { display: none; }",
  "#tools-panel .fc-card > .crow-formula.fc-pre-off > .fc-prefix { display: none; }\n#tools-panel .sc-card > .crow-formula math-field { font-size: 16px; }",
  'ENGINES=chromium KEYS="plants costs" node calc2/tests/redesign/cards_probe.mjs --only К'),
 ('2 вернуть пунктир числам', S + 'calc2.css',
  "background: var(--surface-2); border: 1px solid var(--border); border-radius: 6px;\n  text-align: right;",
  "background: transparent; border: none; border-bottom: 1px dashed var(--border); border-radius: 0;\n  text-align: right;",
  'ENGINES=chromium KEYS="isoquant" node calc2/tests/redesign/cards_probe.mjs --only К'),
 ('3 вернуть строке КТВ значение дорожки', S + '88-params.js',
  "return (typeof m === 'number' && isFinite(m) && Math.abs(m - v) <= (+sl.step || 0) / 2 + 1e-9) ? m : v;", "return v;",
  'ENGINES=chromium node calc2/tests/redesign/cards_probe.mjs --only М'),
 ('4 вернуть старый вопрос про AFC', S + '90-explain.js',
  "<p><b>Почему $ATC$ и $AVC$ сближаются, но никогда не пересекаются?</b>", "<p><b>Почему средние постоянные издержки нигде не пересекаются с остальными?</b>",
  'KEYS="costs" node claude/panels_s5/razbor_dump.mjs claude/panels_s6/tmp/teeth4.json >/dev/null && node claude/panels_s5/razbor_check.mjs claude/panels_s6/tmp/teeth4.json'),
 ('5 вернуть «МРОТ W_min»', S + '46-scenes-labor.js',
  "<span>МРОТ $W_{\\\\min}$</span>", "<span>МРОТ W_min</span>",
  'ENGINES=chromium node calc2/tests/redesign/answer_panel_probe.mjs --only Ж'),
 ('6 вернуть второй вопрос «Денежного рынка»', S + '90-explain.js',
  "    'нужно, лишние уходят в активы, и ставка снижается.</p>' +\n", "    'нужно, лишние уходят в активы, и ставка снижается.</p>' +\n" + Q4,
  'KEYS="money" node claude/panels_s5/razbor_dump.mjs claude/panels_s6/tmp/teeth6.json >/dev/null && node claude/panels_s5/razbor_check.mjs claude/panels_s6/tmp/teeth6.json'),
]
out = []
for name, f, old, new, cmd in CASES:
    s = open(f).read()
    assert s.count(old) >= 1, (name, s.count(old))
    open(f, 'w').write(s.replace(old, new))
    time.sleep(1.5)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    subprocess.run(['git', 'checkout', '--', f])
    lines = [l for l in (r.stdout + r.stderr).split('\n') if re.search(r'FAIL|✗|ИТОГ|НЕ ЧИСТ|ЧИСТ', l)]
    red = r.returncode != 0
    out.append('## ' + name + ' — ' + ('КРАСНЫЙ' if red else 'ЗЕЛЁНЫЙ (зубов нет!)') + ' (код ' + str(r.returncode) + ')')
    out += ['    ' + l.strip()[:300] for l in lines[:8]]
    print(out[-len(lines[:8]) - 1], flush=True)
time.sleep(1)
d = subprocess.run(['git', 'diff', '--stat', '--', 'calc2/'], capture_output=True, text=True).stdout
out.append('\ngit diff calc2/ после отката: ' + ('пусто' if not d.strip() else d))
open('claude/panels_s6/teeth/A.txt', 'w').write('\n'.join(out) + '\n')
print('\n'.join(out[-1:]))
