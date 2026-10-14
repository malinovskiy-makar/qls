# Зубастость этапа А: поломка → прибор → откат (git checkout -- файл).
import subprocess, os, sys
os.chdir(os.path.expanduser('~/Downloads/qls_platform'))
OUT = 'claude/panels_night/teeth/A.txt'
def sub(path, old, new):
    s = open(path, encoding='utf-8').read(); assert old in s, (path, old[:60]); open(path, 'w', encoding='utf-8').write(s.replace(old, new, 1))
def run(cmd, env=None):
    e = dict(os.environ, CALC2_BASE_URL='http://127.0.0.1:8099', ENGINES='chromium', **(env or {}))
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=e)
    out = r.stdout + r.stderr
    lines = [l for l in out.splitlines() if 'FAIL' in l or 'ИТОГ' in l or '✗' in l or 'НАРУШЕН' in l or 'ПРОВАЛ' in l]
    return r.returncode, lines
CASES = [
 ('1 вернуть «по умолчанию открыт»', lambda: sub('calc2/static/calc2/93-shell.js', "setAnswerHidden(!(typeof storeGet === 'function' && storeGet(ANS_HIDDEN_KEY) === '0'), true);", "setAnswerHidden(typeof storeGet === 'function' && storeGet(ANS_HIDDEN_KEY) === '1', true);"),
   'node calc2/tests/redesign/answer_panel_probe.mjs --only А', ['calc2/static/calc2/93-shell.js']),
 ('2 стрелку внутрь .side-inner (в шапку)', lambda: (sub('calc2/templates/calc2/calc2.html', '    <button type="button" class="ans-hide" id="ans-hide" aria-label="Спрятать «Ответ»" aria-expanded="true"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 5.5L16 12l-6.5 6.5"/></svg></button>\n', ''), sub('calc2/templates/calc2/calc2.html', '<h2>Ответ</h2>', '<h2>Ответ</h2><button type="button" class="ans-hide" id="ans-hide" aria-label="Спрятать «Ответ»" aria-expanded="true">›</button>')),
   'node calc2/tests/redesign/answer_panel_probe.mjs --only А', ['calc2/templates/calc2/calc2.html']),
 ('3 убрать пересборку при открытии', lambda: (sub('calc2/static/calc2/94-answer.js', "function answerReflow() {\n  _answerSig = '';", "function answerReflow() {\n  return;\n  _answerSig = '';"), sub('calc2/static/calc2/94-answer.js', "  if (retypesetSeenRows()) _answerSig = '';", "")),
   'node calc2/tests/redesign/answer_panel_probe.mjs --only А2', ['calc2/static/calc2/94-answer.js']),
 ('4 убрать запас 24 px у .cv-bar', lambda: sub('calc2/static/calc2/calc2.css', '  .cv-bar { padding-right: 32px; }', ''),
   'node calc2/tests/redesign/answer_panel_probe.mjs --only А', ['calc2/static/calc2/calc2.css']),
 ('5 сворачивать «Разбор» display у узла с id', lambda: (sub('calc2/static/calc2/94-answer.js', "      document.body.classList.toggle('ex-shown', on);", "      document.body.classList.toggle('ex-shown', on);\n      document.getElementById('ex-fold').style.display = on ? '' : 'none';"), sub('calc2/static/calc2/94-answer.js', "    document.body.classList.remove('ex-shown');", "    document.body.classList.remove('ex-shown');\n    const f = document.getElementById('ex-fold'); if (f) f.style.display = 'none';"), sub('calc2/static/calc2/calc2.css', "  body:not(.ex-shown) #ex-fold { display: none; }", "")),
   'node calc2/tests/redesign/answer_panel_probe.mjs --only Б', ['calc2/static/calc2/94-answer.js', 'calc2/static/calc2/calc2.css']),
 ('6 раскрыть «Разбор» по умолчанию', lambda: sub('calc2/static/calc2/94-answer.js', "    document.body.classList.remove('ex-shown');", "    document.body.classList.add('ex-shown');"),
   'node calc2/tests/redesign/answer_panel_probe.mjs --only Б', ['calc2/static/calc2/94-answer.js']),
 ('7 вернуть display: block жирному', lambda: sub('calc2/static/calc2/calc2.css', "  display: inline; margin: 0; font-size: inherit; text-transform: none; letter-spacing: 0;\n}", "  display: block; margin: 0; font-size: inherit; text-transform: none; letter-spacing: 0;\n}"),
   'node calc2/tests/redesign/answer_panel_probe.mjs --only Б', ['calc2/static/calc2/calc2.css']),
 ('8 в answer_probe убрать открытие колонки', lambda: sub('calc2/tests/redesign/answer_probe.mjs', "keepAnswerOpen(browser);", ""),
   'node calc2/tests/redesign/answer_probe.mjs', ['calc2/tests/redesign/answer_probe.mjs']),
]
only = sys.argv[1:] 
with open(OUT, 'a', encoding='utf-8') as f:
    for name, brk, cmd, files in CASES:
        if only and name.split()[0] not in only: continue
        brk()
        import time; time.sleep(2)
        code, lines = run(cmd)
        subprocess.run(['git', 'checkout', '--'] + files)
        f.write('### ' + name + ' → код ' + str(code) + '\n' + '\n'.join(l[:400] for l in lines[:8]) + '\n'); f.flush()
    d = subprocess.run(['git', 'diff', '--stat'], capture_output=True, text=True).stdout
    f.write('git diff после отката: ' + (d.strip() or 'пусто') + '\n')
