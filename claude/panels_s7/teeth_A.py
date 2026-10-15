"""Зубастость этапа А (сессия 7, А4): по одной поломке (одна или несколько замен), прибор, откат (git checkout -- файлы).
python3 claude/panels_s7/teeth_A.py  → claude/panels_s7/teeth/A.txt"""
import subprocess, time, os, re
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
S = 'calc2/static/calc2/'
CASES = [
 ('1 вернуть \\, в шаблоне «Оптимума при ограничении»',
  [(S + '70-scenes-math.js', "<span>$f(x^*,\\\\, y^*)$</span>", "<span>$f(x^*,\\, y^*)$</span>")],
  'ENGINES=chromium KEYS="m-constraint" node calc2/tests/redesign/answer_panel_probe.mjs --only З'),
 ('2а убрать обёртку запятой на общем входе KaTeX — «Условие»',
  [(S + '82-input.js', ".replace(/(\\d),(?=\\d)/g, '$1{,}');", ";")],
  'ENGINES=chromium KEYS="tradeprice m-tangent ineq" node calc2/tests/redesign/cards_probe.mjs --only И'),
 ('2б убрать обёртку запятой на общем входе KaTeX — «Ответ» и «Разбор»',
  [(S + '82-input.js', ".replace(/(\\d),(?=\\d)/g, '$1{,}');", ";")],
  'ENGINES=chromium KEYS="tradeprice" node calc2/tests/redesign/answer_panel_probe.mjs --only З'),
 ('3 вернуть прежнее правило подписей осей (одна проверка рамок с порогом 1 px, без слияния и разведения вдоль оси)',
  [(S + '30-curves.js', "const TICK_GAP = 4;", "const TICK_GAP = -1;"),
   (S + '30-curves.js', "  yieldTicksToCoords(node);   // второй проход", "  // yieldTicksToCoords(node);   // второй проход"),
   (S + '30-curves.js', "    if (it.only && !dx && !dy) {", "    if (false) {"),
   (S + '20-plane.js', "    if (have.num !== want.num ||", "    if (true || have.num !== want.num ||")],
  'ENGINES=chromium KEYS="labor ext labor-bilat" node calc2/tests/redesign/axis_labels_probe.mjs'),
 ('4 вернуть «50 / 25» у точки A Слуцкого',
  [(S + '48-scenes-consumer.js', "старый выбор ${nb(`(Px=${fmt(b.px)})`)}</span><b>(${fmt(b.x)}; ${fmt(b.y)})</b>",
    "старый выбор ${nb(`(Px=${fmt(b.px)})`)}</span><b>${fmt(b.x)} / ${fmt(b.y)}</b>")],
  'ENGINES=chromium node calc2/tests/redesign/answer_panel_probe.mjs --only И'),
 ('5 вернуть прямой шрифт L (запись Math.js как есть)',
  [(S + '82-input.js', "  return String(tex).replace(/\\\\mathrm", "  return String(tex); String(tex).replace(/\\\\mathrm")],
  'ENGINES=chromium KEYS="labor isoquant" node calc2/tests/redesign/cards_probe.mjs --only Л'),
]
out = []
for name, edits, cmd in CASES:
    files = []
    for f, old, new in edits:
        s = open(f).read()
        assert s.count(old) == 1, (name, f, s.count(old))
        open(f, 'w').write(s.replace(old, new))
        files.append(f)
    time.sleep(1.5)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    subprocess.run(['git', 'checkout', '--'] + sorted(set(files)))
    lines = [l for l in (r.stdout + r.stderr).split('\n') if re.search(r'FAIL|✗|ИТОГ', l)]
    red = r.returncode != 0
    out.append('## ' + name + ' — ' + ('КРАСНЫЙ' if red else 'ЗЕЛЁНЫЙ (зубов нет!)') + ' (код ' + str(r.returncode) + ')')
    out += ['    ' + l.strip()[:300] for l in lines[:8]]
    print('\n'.join(out[-len(lines[:8]) - 1:]), flush=True)
time.sleep(1)
d = subprocess.run(['git', 'diff', '--stat', '--', 'calc2/'], capture_output=True, text=True).stdout
out.append('\ngit diff calc2/ после отката: ' + ('пусто' if not d.strip() else d))
open('claude/panels_s7/teeth/A.txt', 'w').write('\n'.join(out) + '\n')
print(out[-1])
