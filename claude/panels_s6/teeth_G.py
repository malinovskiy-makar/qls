"""Зубастость этапа Г (сессия 6): две поломки списка Б–В на m-graph и ineq, прибор, откат.
python3 claude/panels_s6/teeth_G.py  → claude/panels_s6/teeth/G.txt"""
import subprocess, time, os, re
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
UI = 'calc2/static/calc2/92-ui-kit.js'
CP = 'ENGINES=chromium KEYS="%s" node calc2/tests/redesign/cards_probe.mjs --only Ж'
CASES = [
 ('1 m-graph: обернуть поле строки копией с новым id', UI, "    row._scG = true;\n",
  "    row._scG = true;\n    { const i = fwrap.querySelector('input[id]'); if (i) { const cp = i.cloneNode(true); cp.id = i.id + '-copy'; i.replaceWith(cp); } }\n",
  CP % 'm-graph'),
 ('2 ineq: глаз без действия на карточке L', UI, "  if (slot) top.appendChild(slot);",
  "  if (o.input === 'ineq-formula') { const e = document.createElement('button'); e.type = 'button'; e.className = 'fc-eye fc-ico'; e.textContent = 'o'; top.appendChild(e); }\n  if (slot) top.appendChild(slot);",
  CP % 'ineq'),
]
out = []
for name, f, old, new, cmd in CASES:
    s = open(f).read()
    assert s.count(old) == 1, (name, s.count(old))
    open(f, 'w').write(s.replace(old, new))
    time.sleep(1.5)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    subprocess.run(['git', 'checkout', '--', f])
    lines = [l for l in (r.stdout + r.stderr).split('\n') if re.search(r'FAIL|ИТОГ', l)]
    red = r.returncode != 0
    out.append('## ' + name + ' — ' + ('КРАСНЫЙ' if red else 'ЗЕЛЁНЫЙ (зубов нет!)') + ' (код ' + str(r.returncode) + ')')
    out += ['    ' + l.strip()[:280] for l in lines[:6]]
    print(out[-min(len(lines), 6) - 1], flush=True)
time.sleep(1)
d = subprocess.run(['git', 'diff', '--stat', '--', 'calc2/'], capture_output=True, text=True).stdout
out.append('\ngit diff calc2/ после отката: ' + ('пусто' if not d.strip() else d))
open('claude/panels_s6/teeth/G.txt', 'w').write('\n'.join(out) + '\n')
print(out[-1])
