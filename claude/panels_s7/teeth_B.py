"""Зубастость этапа Б (сессия 7): по одной поломке, прибор pts_probe, откат (git checkout -- файлы).
python3 claude/panels_s7/teeth_B.py  → claude/panels_s7/teeth/B.txt"""
import subprocess, time, os, re
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
S = 'calc2/static/calc2/'
T = 'calc2/templates/calc2/calc2.html'
P = 'ENGINES=chromium WIDTHS=1440 node calc2/tests/redesign/pts_probe.mjs --only '
CASES = [
 ('1 вернуть «← Условие» в шапку',
  [(T, '        <h2 class="pts-title">Точки и площади</h2>\n', '        <button class="col-quiet pts-back" id="pts-back" type="button">← Условие</button>\n        <h2 class="pts-title">Точки и площади</h2>\n')],
  P + 'Б1'),
 ('2 вернуть имена «Точка N»',
  [(S + '60-overlays.js', 'text: nextMarkName(),', "text: 'Точка ' + markCounter,")],
  P + 'Б4'),
 ('3 меню внутри строки (гибнет при пересборке списка)',
  [(S + '60-overlays.js', "  _markMenu.dataset.mark = String(id);\n  fillMarkMenu();", "  _markMenu.dataset.mark = String(id);\n  anchor.parentNode.appendChild(_markMenu);\n  fillMarkMenu();")],
  P + 'Б3'),
 ('4 Esc при открытом меню выходит из режима',
  [(S + '92-ui-kit.js', "  e.preventDefault(); e.stopPropagation();\n  closePop();\n}", "  closePop();\n}")],
  P + 'Б3'),
]
out = []
for name, edits, cmd in CASES:
    files = []
    for f, old, new in edits:
        s = open(f).read()
        assert s.count(old) == 1, (name, f, s.count(old))
        open(f, 'w').write(s.replace(old, new))
        files.append(f)
    time.sleep(2)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    subprocess.run(['git', 'checkout', '--'] + sorted(set(files)))
    lines = [l for l in (r.stdout + r.stderr).split('\n') if re.search(r'FAIL|ИТОГ|Error', l)]
    red = r.returncode != 0
    out.append('## ' + name + ' — ' + ('КРАСНЫЙ' if red else 'ЗЕЛЁНЫЙ (зубов нет!)') + ' (код ' + str(r.returncode) + ')')
    out += ['    ' + l.strip()[:300] for l in lines[:8]]
    print('\n'.join(out[-len(lines[:8]) - 1:]), flush=True)
time.sleep(1)
d = subprocess.run(['git', 'diff', '--stat', '--', 'calc2/'], capture_output=True, text=True).stdout
out.append('\ngit diff calc2/ после отката: ' + ('пусто' if not d.strip() else d))
open('claude/panels_s7/teeth/B.txt', 'w').write('\n'.join(out) + '\n')
print(out[-1])
