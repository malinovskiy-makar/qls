"""Зубастость этапа Д (сессия 6): по одной поломке, прибор, откат (git checkout -- файл).
python3 claude/panels_s6/teeth_D.py  → claude/panels_s6/teeth/D.txt"""
import subprocess, time, os, re
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
UI, PA, CSS = 'calc2/static/calc2/92-ui-kit.js', 'calc2/static/calc2/88-params.js', 'calc2/static/calc2/calc2.css'
CP = 'ENGINES=chromium KEYS="%s" node calc2/tests/redesign/cards_probe.mjs --only З'
CASES = [
 ('1 вернуть цвет кривой дорожке сдвига', PA, "       на одном экране дорожки пяти цветов. Кривую называет карточка, под которой ползунок стоит. */",
  "       на одном экране дорожки пяти цветов. Кривую называет карточка, под которой ползунок стоит. */\n    sl.style.accentColor = c.color;", CP % 'mono'),
 ('2 вернуть «-50» с дефисом', PA, "function boundText(v) { return String(fmt(v)).replace(/-/g, '−'); }", "function boundText(v) { return String(fmt(v)); }", CP % 'sd'),
 ('3 показать тумблер стороны налога', UI, "['mc-max', 'm-constraint'], ['tsb-seller', 'd3'],", "['mc-max', 'm-constraint'],", CP % 'taxes'),
 ('4 показать полосу из одной кнопки', CSS, '#tools-panel #sec-tax .seg[data-n="1"] { display: none; }', '', CP % 'quota'),
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
    out += ['    ' + l.strip()[:300] for l in lines[:6]]
    print(out[-min(len(lines), 6) - 1], flush=True)
time.sleep(1)
d = subprocess.run(['git', 'diff', '--stat', '--', 'calc2/'], capture_output=True, text=True).stdout
out.append('\ngit diff calc2/ после отката: ' + ('пусто' if not d.strip() else d))
open('claude/panels_s6/teeth/D.txt', 'w').write('\n'.join(out) + '\n')
print(out[-1])
