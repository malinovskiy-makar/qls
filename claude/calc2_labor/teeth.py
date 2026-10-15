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
 'Б': [
  ('1 вернуть S = L на старте',
   [(S + '52-modes.js', "addCurve('10 + 0.5*L');", "addCurve('L');")],
   PROBE + 'Б'),
  ('2 МРОТ включён на старте «Двусторонней монополии»',
   [(S + '84-picker.js', "setMode('labor'); setLaborMinOn(false); setLaborStruct('bilateral');", "setMode('labor'); setLaborStruct('bilateral');")],
   PROBE + 'Б'),
  ('3 снова спрятать галочку МРОТ в «Двусторонней монополии»',
   [(L, "  if (lb) lb.style.display = (mode === 'union') ? 'none' : '';",
        "  if (lb) { lb.style.display = (mode === 'union') ? 'none' : ''; const lc = lb.querySelector(':scope > label.chk'); if (lc) lc.style.display = (mode === 'bilateral') ? 'none' : ''; }")],
   PROBE + 'Б'),
  ('4 превью не пересобраны (previews.json кода до сессии)',
   [(S + 'previews.json', None, 'git:bfb74cc3')],
   'node calc2/tests/tex/ci_quick.mjs'),
  ('5 паритет без «за галочкой» (органы МРОТ labor-bilat не ищутся за #chk-labmin)',
   [('calc2/tests/redesign/parity_quick.mjs', "const BEHIND_CHECKBOX = { 'labor-bilat': 'chk-labmin' };", "const BEHIND_CHECKBOX = {};")],
   'node calc2/tests/redesign/parity_quick.mjs'),
  # Подпись, просто поставленная на числа оси, наложения не даёт: общее разведение (spreadLabels) сдвигает число вниз.
  # Зуб — подпись, прибитая (data-no-spread) поверх деления «60»: прибор обязан её увидеть.
  ('6 подпись «MRL = 0» прибита поверх деления 60 оси L (axis_labels_probe её видит)',
   [(L, "const t = haloText(g, p0 + 7, oy - 7, 'MRL = 0', 'start', 'auto');\n      if (t) t.attr('fill', COL.MR).attr('class', 'labor-mrl0');",
        "const t = haloText(g, sx(60), oy + 8, 'MRL = 0', 'middle', 'hanging');\n      if (t) t.attr('fill', COL.MR).attr('class', 'labor-mrl0').attr('data-no-spread', '1');")],
   'ENGINES=chromium KEYS="labor-union" node calc2/tests/redesign/axis_labels_probe.mjs'),
 ],
 'В': [
  ('1 нижняя граница без МРОТ (связывающий МРОТ не поднимает низ)',
   [(L, "  const bind = !!(mm && mm.binding);", "  const bind = false;")],
   PROBE + 'В'),
  ('2 нет «исхода одного» (верх ниже низа)',
   [(L, "  if (W >= b.Wu - 1e-9) {\n    const Ld = qtyAt(D, W), Ls = qtyAt(S, W);", "  if (false) {\n    const Ld = qtyAt(D, W), Ls = qtyAt(S, W);")],
   PROBE + 'В'),
  ('3 МРОТ в двусторонней по-старому, как в конкуренции',
   [(L, "    STATE.laborMin = (STATE.laborStruct === 'monopsony' || STATE.laborStruct === 'bilateral')", "    STATE.laborMin = (STATE.laborStruct === 'monopsony')")],
   PROBE + 'В'),
  ('4 поднять версию состояния',
   [(S + '89-model-state.js', "const MODEL_STATE_VERSION = 1;", "const MODEL_STATE_VERSION = 2;")],
   PROBE + 'В'),
 ],
}
stage = sys.argv[1]
only = sys.argv[2:]   # номера зубов (первое слово названия); без них — все
out = []
for name, edits, cmd in STAGES[stage]:
    if only and name.split()[0] not in only:
        continue
    files = []
    for f, old, new in edits:
        if old is None:   # весь файл — из коммита (new = 'git:<коммит>')
            body = subprocess.run(['git', 'show', new[4:] + ':' + f], capture_output=True, text=True).stdout
            open(f, 'w', encoding='utf8').write(body)
            files.append(f)
            continue
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
open('claude/calc2_labor/teeth/' + stage + ('_' + '_'.join(only) if only else '') + '.txt', 'w', encoding='utf8').write('\n'.join(out) + '\n')
print(out[-1])
