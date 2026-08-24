"""Проверка архива передачи. ТОЛЬКО ЧИТАЕТ.

Семь проверок из задания сессии: повторяемость выгрузки, сходимость чисел,
целостность распакованного архива, три задачи глазами, длины условий против
базы и неизменность самой базы.

⚠️ Повторяемость сверяется БЕЗ поля generated_at: оно меняется на каждом
прогоне по устройству, и сравнивать байты вместе с ним бессмысленно.

    venv\\Scripts\\python scripts/verify_handover.py
"""

import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
EXPORT_DIR = os.path.join(ROOT, 'reports', 'handover_20260820')
OUT_ZIP = os.path.join(ROOT, 'qls_handover_20260820.zip')
NAMES = ['ile.json', 'aa.json', 'matek.json']

ok_all = True


def say(ok, text):
    global ok_all
    if not ok:
        ok_all = False
    print(('  OK   ' if ok else '  ПРОВАЛ ') + text)


def md5_bytes(b):
    return hashlib.md5(b, usedforsecurity=False).hexdigest()


def md5_file(path):
    h = hashlib.md5(usedforsecurity=False)
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def normalized_md5(path):
    """MD5 файла с вырезанной строкой generated_at."""
    with open(path, 'rb') as fh:
        raw = fh.read()
    raw = re.sub(rb'"generated_at": "[^"]*"', b'"generated_at": "X"', raw)
    return md5_bytes(raw)


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from problems.models import Problem

    db_path = os.path.join(ROOT, 'db.sqlite3')

    print('=== 0. СНИМОК БАЗЫ ДО ПРОВЕРОК ===')
    db_md5_before = md5_file(db_path)
    n_before = Problem.objects.count()
    hr_before = Problem.objects.exclude(human_review='').count()
    print(f'  db.sqlite3 MD5 = {db_md5_before}')
    print(f'  Problem.objects.count() = {n_before}')
    print(f'  с непустым human_review = {hr_before}')

    print()
    print('=== 2. ПОВТОРНАЯ ВЫГРУЗКА ДАЁТ ТЕ ЖЕ ФАЙЛЫ ===')
    # ⚠️ Повтор пишется в ОТДЕЛЬНУЮ папку (--out), а не поверх боевой выгрузки:
    # у нового прогона другой generated_at, и запись поверх расходила бы файлы
    # на диске с теми, что уже лежат в архиве. Первая версия проверки так и
    # сделала — и «провалила» сама себя.
    before = {n: normalized_md5(os.path.join(EXPORT_DIR, n)) for n in NAMES}
    again = tempfile.mkdtemp(prefix='qls_handover_repeat_')
    try:
        subprocess.run(
            [sys.executable, 'manage.py', 'export_sources_json', '--out', again],
            cwd=ROOT, check=True, capture_output=True,
            env={**os.environ, 'PYTHONUTF8': '1'},
        )
        for n in NAMES:
            after = normalized_md5(os.path.join(again, n))
            say(before[n] == after,
                f'{n}: MD5 без generated_at {before[n][:12]}… '
                f'{"совпал" if before[n] == after else "РАЗОШЁЛСЯ → " + after[:12]}')
    finally:
        shutil.rmtree(again, ignore_errors=True)

    print()
    print('=== 3. ЧИСЛА СХОДЯТСЯ С БАЗОЙ ===')
    data = {}
    for n in NAMES:
        with open(os.path.join(EXPORT_DIR, n), encoding='utf-8') as fh:
            data[n] = json.load(fh)

    total_json = sum(d['counts']['total'] for d in data.values())
    reviewed_json = sum(
        1 for d in data.values() for p in d['problems'] if p['review']['reviewed'])
    approved_json = sum(d['counts']['approved'] for d in data.values())
    defect_json = sum(d['counts']['defect'] for d in data.values())

    src_ids = [d['source']['id'] for d in data.values()]
    total_db = (Problem.objects
                .filter(source_references__source_id__in=src_ids)
                .distinct().count())
    say(total_json == total_db,
        f'задач в трёх файлах {total_json} == задач трёх источников в базе {total_db}')
    say(reviewed_json == 6626,
        f'задач с непустым human_review в архиве {reviewed_json} (ожидалось 6626)')
    say(approved_json == 5090, f'approved {approved_json} (ожидалось 5090)')
    say(defect_json == 1536, f'defect {defect_json} (ожидалось 1536)')

    # Каждая задача файла действительно принадлежит своему источнику.
    for n, d in data.items():
        sid = d['source']['id']
        bad = [p['id'] for p in d['problems']
               if sid not in {r['source_id'] for r in p['source_refs']}]
        say(not bad, f'{n}: все задачи ссылаются на источник {sid} '
                     f'(чужих {len(bad)})')

    print()
    print('=== 4. РАСПАКОВКА АРХИВА ===')
    tmp = tempfile.mkdtemp(prefix='qls_handover_check_')
    try:
        with zipfile.ZipFile(OUT_ZIP) as zf:
            bad = zf.testzip()
            say(bad is None, f'CRC всех записей в порядке (testzip → {bad})')
            zf.extractall(tmp)
            names = zf.namelist()
        expected = ['ПЕРЕДАЧА_ИДЕИ.md', 'manifest.json'] + NAMES + [
            'materials/verdicts_ile_20260721.json',
            'materials/verdicts_aa_20260728.json',
            'materials/verdicts_matek_20260808.json',
            'materials/aa_repairs.json',
            'materials/repair_wave1_gate.json',
            'materials/repair_wave1_gate_report.md',
            'materials/repair_wave1_FORMAT.md',
            'materials/matek_zero_step_plan.md',
        ]
        say(sorted(names) == sorted(expected),
            f'состав архива: {len(names)} файлов, ожидалось {len(expected)}')
        for name in expected:
            say(os.path.exists(os.path.join(tmp, name)),
                f'распакован: {name}')

        ideas = os.path.join(tmp, 'ПЕРЕДАЧА_ИДЕИ.md')
        text = open(ideas, encoding='utf-8').read()
        say(len(text) > 10000 and 'Передача базы задач' in text,
            f'ПЕРЕДАЧА_ИДЕИ.md читается в utf-8: {len(text)} символов, '
            f'первая строка {text.splitlines()[0][:50]!r}')
        say(md5_file(ideas) == md5_file(os.path.join(ROOT, 'ПЕРЕДАЧА_ИДЕИ.md')),
            'ПЕРЕДАЧА_ИДЕИ.md в архиве побайтно равен исходному')

        for name in expected:
            if not name.endswith('.json'):
                continue
            try:
                with open(os.path.join(tmp, name), encoding='utf-8') as fh:
                    json.load(fh)
                say(True, f'json.load без ошибок: {name}')
            except Exception as exc:                       # noqa: BLE001
                say(False, f'json.load СЛОМАЛСЯ на {name}: {exc}')

        # Выгрузки в архиве == выгрузки на диске.
        for n in NAMES:
            say(md5_file(os.path.join(tmp, n))
                == md5_file(os.path.join(EXPORT_DIR, n)),
                f'{n} в архиве побайтно равен файлу на диске')

        print()
        print('=== 5. ТРИ ЗАДАЧИ ЦЕЛИКОМ ===')
        show_samples(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print('=== 6. ДЛИНА statement: БАЗА ПРОТИВ JSON (50 случайных) ===')
    by_id = {p['id']: p for d in data.values() for p in d['problems']}
    rnd = random.Random(20260820)
    sample = rnd.sample(sorted(by_id), 50)
    bad = []
    for pid in sample:
        p = Problem.objects.only('id', 'statement', 'answer', 'solution').get(id=pid)
        j = by_id[pid]
        if (p.statement != j['statement'] or p.answer != j['answer']
                or p.solution != j['solution']):
            bad.append(pid)
    say(not bad, f'50 задач: statement/answer/solution совпадают дословно '
                 f'(расхождений {len(bad)}{": " + str(bad) if bad else ""})')

    lens_db = {pid: len(Problem.objects.values_list("statement", flat=True).get(id=pid))
               for pid in sample[:5]}
    print('  пример длин (id: символов):',
          {pid: (lens_db[pid], len(by_id[pid]['statement'])) for pid in sample[:5]})

    # Отдельно — вся выгрузка на кириллицу и доллары: суммарные длины.
    say(all(len(p['statement']) > 0 or p['parts']
            for d in data.values() for p in d['problems']),
        'у каждой задачи есть условие или подпункты')

    print()
    print('=== 7. БАЗА НЕ ИЗМЕНИЛАСЬ ===')
    db_md5_after = md5_file(db_path)
    n_after = Problem.objects.count()
    hr_after = Problem.objects.exclude(human_review='').count()
    say(db_md5_before == db_md5_after,
        f'MD5 db.sqlite3: до {db_md5_before} / после {db_md5_after}')
    say(n_before == n_after, f'Problem.objects.count(): {n_before} → {n_after}')
    say(hr_before == hr_after,
        f'с непустым human_review: {hr_before} → {hr_after}')

    print()
    print('ИТОГ:', 'ВСЁ ЗЕЛЕНО' if ok_all else 'ЕСТЬ ПРОВАЛЫ')
    return 0 if ok_all else 1


def show_samples(tmp):
    """Три задачи из распакованных файлов — распечатать целиком."""
    def load(name):
        with open(os.path.join(tmp, name), encoding='utf-8') as fh:
            return json.load(fh)

    ile, aa, matek = load('ile.json'), load('aa.json'), load('matek.json')

    pick = []
    pick.append(('ILE, approved', next(
        p for p in ile['problems']
        if p['review']['human_review'] == 'approved' and p['parts'])))
    pick.append(('АА, defect с комментарием', next(
        p for p in aa['problems']
        if p['review']['human_review'] == 'defect'
        and any(v['comment'].strip() for v in p['review']['verdicts']))))
    pick.append(('МатЭк, defect merged_structure', next(
        p for p in matek['problems']
        if p['review']['human_review'] == 'defect'
        and any(v['category_key'] == 'merged_structure'
                for v in p['review']['verdicts']))))

    for label, p in pick:
        print()
        print('-' * 70)
        print(f'[{label}]  #{p["id"]}  {p["title"]!r}')
        print(f'  human_review = {p["review"]["human_review"]!r}, '
              f'reviewed = {p["review"]["reviewed"]}, '
              f'пакеты = {p["review"]["bundles"]}')
        for v in p['review']['verdicts']:
            print(f'  вердикт: {v["category_key"]} / {v["category_label"]} '
                  f'/ kind={v["kind"]} / ревьюер={v["reviewer"]!r}')
            if v['comment']:
                print(f'     комментарий: {v["comment"]!r}')
            if v['quotes']:
                print(f'     цитат: {len(v["quotes"])}')
        print(f'  visibility = {p["visibility"]}')
        print(f'  темы = {p["topics"]}')
        print(f'  канон = {p["topics_canonical"]}, теги = {p["tags"]}')
        print(f'  source_refs = {p["source_refs"]}')
        print(f'  вложения = {p["attachments"]}, тип = {p["problem_type"]!r}, '
              f'сложность = {p["difficulty"]}/{p["difficulty_native"]!r}')
        print(f'  УСЛОВИЕ ({len(p["statement"])} символов):')
        print('    ' + p['statement'].replace('\n', '\n    '))
        print(f'  ОТВЕТ ({len(p["answer"])}): {p["answer"]!r}')
        print(f'  РЕШЕНИЕ ({len(p["solution"])}): '
              f'{p["solution"][:600]!r}{"…" if len(p["solution"]) > 600 else ""}')
        print(f'  ПОДПУНКТОВ: {p["parts_count"]}')
        for part in p['parts']:
            print(f'    [order={part["order"]}] «{part["label"]}» '
                  f'баллы={part["points"]}')
            print(f'      условие: {part["statement"]!r}')
            print(f'      ответ:   {part["answer"]!r}')


if __name__ == '__main__':
    sys.exit(main())
