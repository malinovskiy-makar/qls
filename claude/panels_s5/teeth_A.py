"""Зубастость этапа А (сессия 5): по одной поломке, прибор, откат (git checkout -- файл).
python3 claude/panels_s5/teeth_A.py  → claude/panels_s5/teeth/A.txt"""
import subprocess, time, os, re
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
S = 'calc2/static/calc2/'
CASES = [
 ('1 вернуть второй шаг истории (кнопки-раскрывашки снова в форме)', S + '89-model-state.js',
  "!FORM_SKIP_IDS.has(el.id) && !isDisclosureBtn(el) &&", "!FORM_SKIP_IDS.has(el.id) &&",
  'ENGINES=chromium KEYS="taxes" node calc2/tests/redesign/view_probe.mjs --only Г'),
 ('2 «до / после» всегда на строке заголовка', S + 'calc2.css',
  "#params-panel #info-tax[data-head].tx-lift .tx-table { margin-top: -30px; }", "#params-panel #info-tax[data-head] .tx-table { margin-top: -30px; }",
  'ENGINES=chromium KEYS="quota taxes" node calc2/tests/redesign/answer_panel_probe.mjs --only Д'),
 ('3 показать пустой заголовок в costs', S + '92-ui-kit.js',
  "function hideEmptyGroupTitles() {\n", "function hideEmptyGroupTitles() {\n  return;\n",
  'ENGINES=chromium KEYS="costs" node calc2/tests/redesign/quiet_probe.mjs --only З'),
 ('4 вернуть «MC , предельные затраты»', 'calc2/templates/calc2/calc2.html',
  '<span class="show-name">Предельные затраты</span><span class="show-not">MC</span>', 'MC, предельные затраты',
  'ENGINES=chromium KEYS="costs" node calc2/tests/redesign/view_probe.mjs --only В'),
 ('5 вернуть в «Разбор» labor «Линию можно тянуть мышью.»', 'calc2/templates/calc2/calc2.html',
  "предельные издержки труда горизонтальными (= $W_{\\min}$) до встречи с предложением.</div>",
  "предельные издержки труда горизонтальными (= $W_{\\min}$) до встречи с предложением. Линию можно тянуть мышью.</div>",
  'KEYS="labor" node claude/panels_s5/razbor_dump.mjs claude/panels_s5/tmp/teeth5.json >/dev/null && node claude/panels_s5/razbor_check.mjs claude/panels_s5/tmp/teeth5.json'),
 ('6 вернуть минус у «Расходов бюджета»', S + '40-scenes-market.js',
  "const budShown = isSub ? Math.abs(STATE.budget) : STATE.budget;", "const budShown = STATE.budget;",
  'ENGINES=chromium node calc2/tests/redesign/answer_panel_probe.mjs --only Е'),
]
out = []
for name, f, old, new, cmd in CASES:
    s = open(f).read()
    assert s.count(old) == 1, (name, s.count(old))
    open(f, 'w').write(s.replace(old, new))
    time.sleep(1.5)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    subprocess.run(['git', 'checkout', '--', f])
    lines = [l for l in (r.stdout + r.stderr).split('\n') if re.search(r'FAIL|✗|ИТОГ|НЕ ЧИСТ|ЧИСТ', l)]
    red = r.returncode != 0
    out.append('## ' + name + ' — ' + ('КРАСНЫЙ' if red else 'ЗЕЛЁНЫЙ (зубов нет!)') + ' (код ' + str(r.returncode) + ')')
    out += ['    ' + l.strip()[:300] for l in lines[:8]]
    print(out[-len(lines[:8]) - 1])
time.sleep(1)
d = subprocess.run(['git', 'diff', '--stat', '--', 'calc2/'], capture_output=True, text=True).stdout
out.append('\ngit diff calc2/ после отката: ' + ('пусто' if not d.strip() else d))
open('claude/panels_s5/teeth/A.txt', 'w').write('\n'.join(out) + '\n')
print('\n'.join(out[-1:]))
