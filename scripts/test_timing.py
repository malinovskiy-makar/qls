"""ФАЗА 5 сессии 22.08 — ЗАМЕР ВРЕМЕНИ ПРОГОНА.

Сначала измеряем, потом оптимизируем. Прогоняет тесты по одному модулю и
печатает время каждого, отсортированное по убыванию: без этого «прогон идёт
час» не говорит, где именно час.

Запуск: ./venv/bin/python scripts/test_timing.py [--keepdb]
"""
import subprocess, sys, time, pathlib, json, re

KEEPDB = '--keepdb' in sys.argv
root = pathlib.Path(__file__).resolve().parent.parent
mods = []
for app in ('problems', 'catalog', 'student', 'teacher', 'game', 'calc2'):
    d = root / app / 'tests'
    if d.is_dir():
        mods += [f'{app}.tests.{p.stem}' for p in sorted(d.glob('test_*.py'))]
    f = root / app / 'tests.py'
    if f.is_file():
        mods.append(f'{app}.tests')

rows = []
for m in mods:
    cmd = [sys.executable, 'manage.py', 'test', m, '-v', '1']
    if KEEPDB:
        cmd.append('--keepdb')
    t0 = time.time()
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    dt = time.time() - t0
    n = re.search(r'Ran (\d+) test', r.stderr or '')
    rows.append({'module': m, 'seconds': round(dt, 1),
                 'tests': int(n.group(1)) if n else 0,
                 'ok': r.returncode == 0})
    print(f'{dt:7.1f}s  {rows[-1]["tests"]:4d}  {"ok " if r.returncode==0 else "FAIL"}  {m}', flush=True)

rows.sort(key=lambda x: -x['seconds'])
total = sum(x['seconds'] for x in rows)
tests = sum(x['tests'] for x in rows)
out = {'keepdb': KEEPDB, 'total_seconds': round(total, 1), 'tests': tests, 'modules': rows}
dest = root / 'reports' / 'calc2_22aug' / ('timing_keepdb.json' if KEEPDB else 'timing_plain.json')
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'\nИТОГО {total:.0f} с, тестов {tests}, модулей {len(rows)}')
print('Десятка самых долгих:')
for x in rows[:10]:
    print(f'  {x["seconds"]:7.1f}s  {x["tests"]:4d}  {x["module"]}')
