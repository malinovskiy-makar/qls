"""Зубастость этапов сессии «рынок труда»: по одной поломке (одна или несколько замен), прибор, откат
(git checkout -- файлы). python3 claude/calc2_labor/teeth.py А|Б|В → claude/calc2_labor/teeth/<этап>.txt"""
import subprocess, time, os, re, sys
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
S = 'calc2/static/calc2/'
L = S + '46-scenes-labor.js'
PROBE = 'ENGINES=chromium WIDTHS=1440 node calc2/tests/redesign/labor_probe.mjs --only '
STAGES = {
 'А': [
  ('1 вернуть цель MRL = S (новый пример даёт 64 / 36)',
   [(L, "const mrl = (l) => marginalRevenue(D, l);", "const mrl = (l) => marginalRevenue(D, l) - evalCurve(S, l);"),
    (L, "const corner = (L0 == null || !(best > Lk * Wk + 1e-9));", "const corner = (L0 == null);")],
   PROBE + 'А'),
  ('2 убрать ограничение «не больше желающих» («Угол» даёт 50 / 50)',
   [(L, "const hiIn = Lk - 1e-6, N = 1000, cands = [];", "const hiIn = modelSpanQ(), N = 1000, cands = [];")],
   PROBE + 'А'),
  ('3 убрать строку «Безработица» профсоюза',
   [(L, "      if (!u.corner && u.unemployment > 1e-6) html += `<div class=\"stat\"><span>Безработица</span><b>${fmt(u.unemployment)}</b></div>`;\n", "")],
   PROBE + 'А'),
  ('4 вернуть точку «MRL = S»',
   [(L, "    // Зарплата профсоюза Wп на кривой спроса (выше конкурентной).",
        "    g.append('circle').attr('cx', px).attr('cy', toPx(u.Lu, evalCurve(STATE.laborS, u.Lu))[1]).attr('r', 3.5).attr('fill', COL.MR);\n    // Зарплата профсоюза Wп на кривой спроса (выше конкурентной).")],
   PROBE + 'А'),
 ],
}
stage = sys.argv[1]
out = []
for name, edits, cmd in STAGES[stage]:
    files = []
    for f, old, new in edits:
        s = open(f, encoding='utf8').read()
        assert s.count(old) == 1, (name, f, s.count(old))
        open(f, 'w', encoding='utf8').write(s.replace(old, new))
        files.append(f)
    time.sleep(1.5)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    subprocess.run(['git', 'checkout', '--'] + sorted(set(files)))
    lines = [l for l in (r.stdout + r.stderr).split('\n') if re.search(r'FAIL|✗|ИТОГ|провал', l)]
    red = r.returncode != 0
    out.append('## ' + name + ' — ' + ('КРАСНЫЙ' if red else 'ЗЕЛЁНЫЙ (зубов нет!)') + ' (код ' + str(r.returncode) + ')')
    out += ['    ' + l.strip()[:300] for l in lines[:8]]
    print('\n'.join(out[-len(lines[:8]) - 1:]), flush=True)
time.sleep(1)
d = subprocess.run(['git', 'diff', '--stat', '--', 'calc2/'], capture_output=True, text=True).stdout
out.append('\ngit diff calc2/ после отката: ' + ('пусто' if not d.strip() else d))
open('claude/calc2_labor/teeth/' + stage + '.txt', 'w', encoding='utf8').write('\n'.join(out) + '\n')
print(out[-1])
