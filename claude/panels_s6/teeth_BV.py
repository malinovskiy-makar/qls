"""Зубастость этапов Б–В (сессия 6): по одной поломке, прибор, откат (git checkout -- файл).
python3 claude/panels_s6/teeth_BV.py  → claude/panels_s6/teeth/BV.txt"""
import subprocess, time, os, re
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
UI = 'calc2/static/calc2/92-ui-kit.js'
PA = 'calc2/static/calc2/88-params.js'
CP = 'ENGINES=chromium KEYS="%s" node calc2/tests/redesign/cards_probe.mjs --only %s'
CASES = [
 ('1 обернуть поле копией с новым id (adas)', UI, "  const lab = field.querySelector(':scope > label');\n  field.classList.add('fc-card', 'sc-card');",
  "  const lab = field.querySelector(':scope > label');\n  { const cp = inp.cloneNode(true); cp.id = inp.id + '-copy'; inp.replaceWith(cp); }\n  field.classList.add('fc-card', 'sc-card');",
  CP % ('adas', 'Е')),
 ('2 вернуть «…» Слуцкому', UI, "  'cons-px1-row': ['Новая цена товара $x$', 'P_{x_1}', 'consumer'],\n", "",
  CP % ('cons-slutsky', 'Д')),
 ('3 вернуть ползунок r', PA, ".filter(n => !(typeof scAxisLetter === 'function' && scAxisLetter(n)));", ";",
  CP % ('loanable', 'Е')),
 ('4 глаз без действия на карточке AD', UI, "  if (slot) top.appendChild(slot);",
  "  if (o.input === 'ma-ad') { const e = document.createElement('button'); e.type = 'button'; e.className = 'fc-eye fc-ico'; e.textContent = 'o'; top.appendChild(e); }\n  if (slot) top.appendChild(slot);",
  CP % ('adas', 'Е')),
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
open('claude/panels_s6/teeth/BV.txt', 'w').write('\n'.join(out) + '\n')
print(out[-1])
