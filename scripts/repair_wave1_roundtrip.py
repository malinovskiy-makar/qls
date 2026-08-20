# -*- coding: utf-8 -*-
"""Круговая проверка формата оценок починки: выгрузка -> импорт -> сверка.

⚠️ РАБОТАЕТ ПО КОПИИ БАЗЫ. Импорт вердиктов — это запись, а боевую базу за
эту волну трогать нельзя вовсе. Копия — `db_check.sqlite3`, та же, что у
браузерных сценариев (config/settings_check.py); после прогона её можно
просто удалить.

Что проверяется:
  1. исход и цитаты дошли из файла в базу без потерь;
  2. счётчик одобренных вырос РОВНО на число исходов «починил, идеально»
     (правило SUPERSEDES: разбор починки отменяет прежний вердикт «брак»);
  3. повторный импорт того же файла ничего не дублирует.

Запуск:
    venv\\Scripts\\python.exe -X utf8 scripts\\repair_wave1_roundtrip.py <файл.json>
"""
import io
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

SRC_DB = os.path.join(ROOT, 'db.sqlite3')
CHECK_DB = os.path.join(ROOT, 'db_check.sqlite3')
PY = os.path.join(ROOT, 'venv', 'Scripts', 'python.exe')
SETTINGS = 'config.settings_check'


def run(*args):
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    r = subprocess.run([PY, 'manage.py'] + list(args) +
                       ['--settings=' + SETTINGS],
                       capture_output=True, text=True, encoding='utf-8', env=env)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise SystemExit('команда упала: %s' % ' '.join(args))
    return r.stdout


def counts():
    """Числа из копии базы — отдельным процессом, чтобы настройки не смешались."""
    code = (
        "import json;from collections import Counter;"
        "from problems.models import Problem, ReviewVerdict;"
        "print(json.dumps({"
        "'approved': Problem.objects.filter(human_review='approved').count(),"
        "'defect': Problem.objects.filter(human_review='defect').count(),"
        "'verdicts': ReviewVerdict.objects.count(),"
        "'repair_rows': ReviewVerdict.objects.filter(bundle='repair_aa_20260728').count(),"
        "}))")
    out = run('shell', '-c', code)
    return json.loads(out.strip().splitlines()[-1])


def main():
    if len(sys.argv) < 2:
        raise SystemExit('нужен путь к файлу оценок')
    path = sys.argv[1]
    doc = json.load(io.open(path, encoding='utf-8'))
    verdicts = doc['verdicts']
    perfect = [v for v in verdicts if v.get('outcome') == 'fixed_perfect']
    quoted = {v['problem_id']: v['quotes'] for v in verdicts if v.get('quotes')}

    print('=== ФАЙЛ ===')
    print('формат:', doc['format'], '| пакет:', doc['bundle_id'])
    print('вердиктов:', len(verdicts), '| «идеально»:', len(perfect),
          '| с цитатами:', len(quoted))

    print('\n=== КОПИЯ БАЗЫ ===')
    shutil.copy2(SRC_DB, CHECK_DB)
    print('снял копию ->', os.path.basename(CHECK_DB))
    run('human_review_mark', '--apply')          # опорное состояние копии
    before = counts()
    print('до импорта:', before)

    print('\n=== ИМПОРТ ===')
    print(run('import_review_verdicts', path).strip())
    run('human_review_mark', '--apply')
    after = counts()
    print('после импорта:', after)

    print('\n=== СВЕРКА ===')
    ok = True
    grew = after['approved'] - before['approved']
    want = len(perfect)
    ok &= (grew == want)
    print(('OK  ' if grew == want else 'ПЛОХО ') +
          'одобренных стало больше на %d, «идеально» в файле %d' % (grew, want))

    # исходы и цитаты в базе
    code = (
        "import json;from problems.models import ReviewVerdict;"
        "rows={};"
        "[rows.setdefault(v.problem_id, {'cats': [], 'quotes': v.quotes})"
        "['cats'].append(v.category) "
        "for v in ReviewVerdict.objects.filter(bundle='repair_aa_20260728')];"
        "print(json.dumps({str(k): {'cats': sorted(x['cats']), "
        "'quotes': x['quotes']} for k, x in rows.items()}, ensure_ascii=False))")
    in_db = json.loads(run('shell', '-c', code).strip().splitlines()[-1])

    from problems.repair_outcomes import categories_for  # noqa: E402
    bad = []
    for v in verdicts:
        want_cats = sorted(categories_for(v.get('outcome'),
                                          v.get('origin_categories') or []))
        got = in_db.get(str(v['problem_id']))
        got_cats = got['cats'] if got else []
        if want_cats != got_cats:
            bad.append((v['problem_id'], want_cats, got_cats))
    ok &= not bad
    print(('OK  ' if not bad else 'ПЛОХО ') +
          'исходы дошли категориями: расхождений %d' % len(bad))
    for row in bad[:5]:
        print('    #%s ждали %s, в базе %s' % row)

    lost = []
    for pid, quotes in quoted.items():
        got = (in_db.get(str(pid)) or {}).get('quotes') or []
        if got != quotes:
            lost.append(pid)
    ok &= not lost
    print(('OK  ' if not lost else 'ПЛОХО ') +
          'цитаты дошли дословно: задач с цитатами %d, расхождений %d'
          % (len(quoted), len(lost)))

    print('\n=== ПОВТОРНЫЙ ИМПОРТ ===')
    run('import_review_verdicts', path)
    again = counts()
    same = again == after
    ok &= same
    print(('OK  ' if same else 'ПЛОХО ') + 'числа не изменились: %s' % (again,))

    print('\n=== БОЕВАЯ БАЗА ===')
    print('не трогалась: вся работа шла по', os.path.basename(CHECK_DB))
    print('\nИТОГ:', 'всё сошлось' if ok else 'ЕСТЬ РАСХОЖДЕНИЯ')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
