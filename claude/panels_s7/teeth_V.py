"""Зубастость этапа В (сессия 7): по одной поломке, pts_probe, откат (git checkout -- файлы).
python3 claude/panels_s7/teeth_V.py  → claude/panels_s7/teeth/V.txt"""
import subprocess, time, os, re
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
S = 'calc2/static/calc2/'
P = 'ENGINES=chromium WIDTHS=1440 node calc2/tests/redesign/pts_probe.mjs --only '
CASES = [
 ('1 заморозить ring (обход и число по точкам не пересчитываются) → шаг 2',
  [(S + '60-overlays.js', "  if (r.kind === 'poly' && Array.isArray(r.ids) && r.ids.length) {", "  if (false) {")], P + 'В1'),
 ('2 убрать каскад → шаг 4',
  [(S + '60-overlays.js', "  STATE.areaCalcList = (STATE.areaCalcList || []).filter(r => !(Array.isArray(r.ids) && r.ids.some(x => String(x) === String(id))));\n", "")], P + 'В1,В5'),
 ('3 сделать выбор точек моделью → шаг 11',
  [(S + '60-overlays.js', "    CANVAS.ptsSel = sel;\n", "    CANVAS.ptsSel = sel; STATE.ptsSelModel = sel.slice();\n")], P + 'В1'),
 ('4 поднять версию состояния → шаг 13',
  [(S + '89-model-state.js', "const MODEL_STATE_VERSION = 1;", "const MODEL_STATE_VERSION = 2;")], P + 'В13'),
 ('5 имя площади по длине списка → шаг 10',
  [(S + '60-overlays.js', "  res.label = 'S' + subDigits(k);", "  res.label = 'S' + subDigits(STATE.areaCalcList.length + 1);")], P + 'В1,В5,В3,В10'),
 ('6 заморозить число площади под кривой → шаг 9',
  [(S + '60-overlays.js', "  } else if (r.kind === 'curve' && isFinite(r.a) && isFinite(r.b)) {", "  } else if (false) {")], P + 'В9'),
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
open('claude/panels_s7/teeth/V.txt', 'w').write('\n'.join(out) + '\n')
print(out[-1])
