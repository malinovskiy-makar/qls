# Зубастость этапа В: поломка → прибор → откат (git checkout -- файл).
import subprocess, os, sys, json, time
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
OUT = 'claude/panels_night/teeth/C.txt'
def sub(path, old, new):
    s = open(path, encoding='utf-8').read(); assert old in s, (path, old[:70]); open(path, 'w', encoding='utf-8').write(s.replace(old, new, 1))
def run(cmd):
    e = dict(os.environ, CALC2_BASE_URL='http://127.0.0.1:8099', ENGINES='chromium')
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=e)
    out = r.stdout + r.stderr
    lines = [l for l in out.splitlines() if 'FAIL' in l or 'ИТОГ' in l or 'НЕ НАЙДЕНО' in l or 'не найден' in l or 'ПРОВЕР' in l]
    return r.returncode, lines
CSS, WS, IN, PAR, TPL = 'calc2/static/calc2/calc2.css', 'calc2/static/calc2/86-workspace.js', 'calc2/static/calc2/82-input.js', 'calc2/static/calc2/88-params.js', 'calc2/templates/calc2/calc2.html'
Q = 'node calc2/tests/redesign/quiet_probe.mjs'
FATES = ('KEYS="quota" node claude/mockups/calc2_panels_20261014/tools/panels_inventory.mjs claude/panels_night/tmp/C_after_quota.json >/dev/null 2>&1; '
         'python3 -c "import json; d=json.load(open(\'claude/panels_night/C_after.json\')); full=d[\'models\']; t=json.load(open(\'claude/panels_night/tmp/C_after_quota.json\')); full[\'quota\']=t[\'models\'][\'quota\']; json.dump(d, open(\'claude/panels_night/tmp/C_after_mix.json\',\'w\'))"; '
         'sed "s#claude/panels_night/C_after.json#claude/panels_night/tmp/C_after_mix.json#" claude/panels_night/fates_C.py > claude/panels_night/tmp/fates_mix.py; python3 claude/panels_night/tmp/fates_mix.py | grep -E "НЕ НАЙДЕНО|не найден"; '
         'KEYS="quota" ' + Q + ' --only А')
CASES = [
 ('1 вернуть показ плашки по наведению', lambda: (sub(WS, 'const HINT_TIP_OFF = true;', 'const HINT_TIP_OFF = false;'), sub(CSS, '#hint-tip { display: none !important; }', '')), 'KEYS="sd taxes" ' + Q + ' --only А', [WS, CSS]),
 ('2 вернуть одну «?»', lambda: sub(CSS, '.hint-btn, .hint-pop, .hint-pop.open, .help-dot,', '.hint-pop, .hint-pop.open, .help-dot,'), 'KEYS="m-graph labor" ' + Q + ' --only А', [CSS]),
 ('3 убрать «Как писать» из клавиатуры', lambda: sub(IN, "  if (!tabs || box.querySelector(':scope > .mkbd-howto') || typeof HOW_TO_ROWS === 'undefined') return;", "  return;"), 'KEYS="sd" ' + Q + ' --only А', [IN]),
 ('4 не скопировать один текст экономики', lambda: sub(WS, "    if (n.closest('.sb-note-src') || n.classList.contains('sb-note-src') || sceneHidden(n)) return;\n    const c = n.cloneNode(true);\n    c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove());\n    if (!norm(c.textContent)) return;\n    items.push", "    if (n.closest('.sb-note-src') || n.classList.contains('sb-note-src') || sceneHidden(n) || n.classList.contains('hint-keep')) return;\n    const c = n.cloneNode(true);\n    c.querySelectorAll('.katex-mathml, annotation').forEach(x => x.remove());\n    if (!norm(c.textContent)) return;\n    items.push"), FATES, [WS]),
 ('5 вернуть подписи 12 px', lambda: sub(CSS, "#pts-panel .mark-on, .fc-menu .fc-mi {\n  font-size: 14px !important; font-weight: 500 !important;", "#pts-panel .mark-on, .fc-menu .fc-mi {\n  font-size: 12px !important; font-weight: 400 !important;"), 'KEYS="taxes mono" ' + Q + ' --only Ш', [CSS]),
 ('6 вернуть #11151d', lambda: sub(CSS, "  --input-bg:    #232019;", "  --input-bg:    #11151d;"), 'KEYS="taxes" ' + Q + ' --only К', [CSS]),
 ('7 вернуть M_C', lambda: sub(PAR, "  if (/^[A-Z]{2,4}$/.test(s)) return '\\\\mathrm{' + s + '}';\n", ""), 'KEYS="taxes" ' + Q + ' --only К', [PAR]),
 ('8 убрать overflow-wrap у названий', lambda: sub(CSS, ".pk-cname, .pk-screen .scard-name, .sw-row > span { -webkit-hyphens: auto; hyphens: auto; overflow-wrap: break-word; }", ".pk-cname, .pk-screen .scard-name, .sw-row > span { -webkit-hyphens: auto; hyphens: auto; }"), 'node calc2/tests/picker_probe.mjs', [CSS]),
]
only = sys.argv[1:]
with open(OUT, 'a', encoding='utf-8') as f:
    for name, brk, cmd, files in CASES:
        if only and name.split()[0] not in only: continue
        brk(); time.sleep(2)
        code, lines = run(cmd)
        subprocess.run(['git', 'checkout', '--'] + files)
        f.write('### ' + name + ' → код ' + str(code) + '\n' + '\n'.join(l[:400] for l in lines[:8]) + '\n'); f.flush()
    d = subprocess.run(['git', 'diff', '--stat'], capture_output=True, text=True).stdout
    f.write('git diff после отката: ' + (d.strip() or 'пусто') + '\n')
