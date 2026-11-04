"""Зубастость карточек (сессия 5): по одной поломке компонента, прибор, откат.
python3 claude/panels_s5/teeth_B.py <имя файла отчёта> "<ключи>"  → claude/panels_s5/teeth/<имя>.txt"""
import subprocess, time, os, re, sys
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
NAME, KEYS = sys.argv[1], sys.argv[2]
F = 'calc2/static/calc2/92-ui-kit.js'
CARDS = 'ENGINES=chromium KEYS="%s" node calc2/tests/redesign/cards_probe.mjs' % KEYS
CASES = [
 ('1 обернуть поле копией с новым id', F, "  const lab = field.querySelector(':scope > label');\n  field.classList.add('fc-card', 'sc-card');",
  "  const lab = field.querySelector(':scope > label');\n  { const cp = inp.cloneNode(true); cp.id = inp.id + '-copy'; inp.replaceWith(cp); }\n  field.classList.add('fc-card', 'sc-card');",
  CARDS),
 ('2 глаз без действия', F, "  if (slot) top.appendChild(slot);",
  "  { const e = document.createElement('button'); e.type = 'button'; e.className = 'fc-eye fc-ico'; e.textContent = 'o'; top.appendChild(e); }\n  if (slot) top.appendChild(slot);", CARDS),
 ('3 убрать обозначение', F, "  if (c.sym._tex !== sym) { c.sym._tex = sym; katexInto(c.sym, sym); }", "  c.sym.textContent = '';", CARDS),
 ('4 клонировать поле без обработчиков (тот же id)', F, "  const lab = field.querySelector(':scope > label');\n  field.classList.add('fc-card', 'sc-card');",
  "  const lab = field.querySelector(':scope > label');\n  { const cp = inp.cloneNode(true); inp.replaceWith(cp); }\n  field.classList.add('fc-card', 'sc-card');", CARDS),
 ('5 обрезать имя многоточием', 'calc2/static/calc2/calc2.css',
  "#tools-panel .fc-card .fc-name { white-space: normal; overflow: visible; text-overflow: clip; overflow-wrap: anywhere; }",
  "#tools-panel .fc-card .fc-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }", CARDS),
]
out = []
for name, f, old, new, cmd in CASES:
    s = open(f).read()
    assert s.count(old) == 1, (name, s.count(old))
    open(f, 'w').write(s.replace(old, new))
    time.sleep(1.5)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    subprocess.run(['git', 'checkout', '--', f])
    txt = r.stdout + r.stderr
    lines = [l for l in txt.split('\n') if re.search(r'FAIL|ИТОГ|сверка|ОРГАН', l)]
    red = bool(re.search(r'FAIL|ОРГАН', txt))
    out.append('## ' + name + ' — ' + ('КРАСНЫЙ' if red else 'ЗЕЛЁНЫЙ (зубов нет!)'))
    out += ['    ' + l.strip()[:260] for l in lines[:6]]
    print(out[-min(len(lines), 6) - 1])
time.sleep(1)
d = subprocess.run(['git', 'diff', '--stat', '--', 'calc2/'], capture_output=True, text=True).stdout
out.append('\ngit diff calc2/ после отката: ' + ('пусто' if not d.strip() else d))
open('claude/panels_s5/teeth/%s.txt' % NAME, 'w').write('\n'.join(out) + '\n')
print(out[-1])
