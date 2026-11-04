# Зубастость этапа Г: поломка → прибор → откат (git checkout -- файл).
import subprocess, os, sys, json, time
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
OUT = 'claude/panels_night/teeth/D.txt'
def sub(path, old, new):
    s = open(path, encoding='utf-8').read(); assert old in s, (path, old[:70]); open(path, 'w', encoding='utf-8').write(s.replace(old, new, 1))
def run(cmd):
    e = dict(os.environ, CALC2_BASE_URL='http://127.0.0.1:8099', ENGINES='chromium')
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=e)
    out = r.stdout + r.stderr
    lines = [l for l in out.splitlines() if 'FAIL' in l or 'ИТОГ' in l or 'ОРГАН' in l or 'расхожд' in l]
    return r.returncode, lines
U, S = 'calc2/static/calc2/92-ui-kit.js', 'calc2/static/calc2/91-session.js'
V = 'node calc2/tests/redesign/view_probe.mjs'
def compare(keys):
    k = ' '.join(keys); sub_path = 'claude/panels_night/tmp/C_sub_%s.json' % '_'.join(keys)
    A = json.load(open('claude/panels_night/C_after.json', encoding='utf-8'))
    A['models'] = {x: A['models'][x] for x in keys}
    json.dump(A, open(sub_path, 'w', encoding='utf-8'))
    return ('KEYS="%s" node claude/mockups/calc2_panels_20261014/tools/panels_inventory.mjs claude/panels_night/tmp/teeth_inv.json >/dev/null 2>&1; '
            'node claude/mockups/calc2_panels_20261014/tools/panels_compare.mjs %s claude/panels_night/tmp/teeth_inv.json claude/panels_night/D_allow.json; ' % (k, sub_path))
CASES = [
 ('1 перенести галочку копией с новым id', lambda: sub(U, "  VG_MOVE.forEach(([id, kind, covers]) => {\n    const nodes = vgNodeOf(id);",
   "  VG_MOVE.forEach(([id, kind, covers]) => {\n    let nodes = vgNodeOf(id);\n    if (id === 'chk-ghost' && nodes) { const cp = nodes[0].cloneNode(true); cp.querySelector('input').id = 'chk-ghost-copy'; nodes[0].remove(); nodes = [cp]; vgList('more').appendChild(cp); }"),
   lambda: compare(['taxes']) + 'KEYS="taxes" ' + V + ' --only А', [U]),
 ('2 показать строку в чужой модели', lambda: sub(U, "    const on = vgHomeShown(r.home) && self;", "    const on = r.id === 'chk-ghost' || (vgHomeShown(r.home) && self);"), lambda: 'KEYS="sd ppf" ' + V + ' --only А', [U]),
 ('3 не убирать спрятанную закраску из .tex', lambda: sub(U, "    if (hid.has(k)) this.remove();", "    if (hid.has(k)) this.setAttribute('opacity', 0);"), lambda: 'KEYS="taxes" ' + V + ' --only Б', [U]),
 ('4 «Вид по умолчанию» не сбрасывает areaHidden', lambda: sub(S, "  'areaHidden', 'areaColor',", "  'areaColor',"), lambda: V + ' --only В', [S]),
 ('5 старая ссылка с showCS: false не прячет', lambda: sub(U, "function syncOnChart() {", "function syncOnChart() {\n  STATE.showCS = true;"), lambda: V + ' --only В', [U]),
 ('6 «Излишек фирм» в labor не прячет', lambda: sub(U, "    if (hid.has(k)) this.remove();", "    if (hid.has(k) && k !== 'Излишек фирм') this.remove();"), lambda: 'KEYS="labor" ' + V + ' --only Б', [U]),
]
only = sys.argv[1:]
with open(OUT, 'a', encoding='utf-8') as f:
    for name, brk, cmdf, files in CASES:
        if only and name.split()[0] not in only: continue
        cmd = cmdf()
        brk(); time.sleep(2)
        code, lines = run(cmd)
        subprocess.run(['git', 'checkout', '--'] + files)
        f.write('### ' + name + ' → код ' + str(code) + '\n' + '\n'.join(l[:400] for l in lines[:8]) + '\n'); f.flush()
    d = subprocess.run(['git', 'diff', '--stat'], capture_output=True, text=True).stdout
    f.write('git diff после отката: ' + (d.strip() or 'пусто') + '\n')
