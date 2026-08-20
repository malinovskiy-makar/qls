"""Сборка архива передачи Макару. ТОЛЬКО ЧИТАЕТ базу и файлы.

На выходе один zip: три выгрузки источников, файл идей, manifest.json со
сводкой и папка materials/ с вердиктами ревью, починками волны 1 и планом
нулевого шага МатЭка.

⚠️ Архив собирается СРЕДСТВАМИ PYTHON (zipfile, ZIP_DEFLATED), а не внешней
утилитой: имена внутри архива обязаны быть в UTF-8, а windows-утилиты пишут
их в кодировке консоли, и кириллическое имя файла у получателя разъезжается.

⚠️ Числа в manifest берутся ИЗ САМИХ ФАЙЛОВ (json.load), а не пересчитываются
запросом в базу. Иначе сводка описывала бы не то, что лежит в архиве.

    venv\\Scripts\\python scripts/build_handover_zip.py
"""

import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ZIP = os.path.join(ROOT, 'qls_handover_20260820.zip')
EXPORT_DIR = os.path.join(ROOT, 'reports', 'handover_20260820')

SOURCE_FILES = ['ile.json', 'aa.json', 'matek.json']

# Имя в архиве -> путь на диске.
MATERIALS = {
    'materials/verdicts_ile_20260721.json':
        'reports/review_bundles/ile_20260721/verdicts_ile_20260721_202607272155.json',
    'materials/verdicts_aa_20260728.json':
        'reports/review_bundles/verdicts_aa_20260728.json',
    'materials/verdicts_matek_20260808.json':
        'reports/review_bundles/verdicts_matek_20260808.json',
    'materials/aa_repairs.json':
        'reports/repair_wave1/aa_repairs.json',
    'materials/repair_wave1_gate.json':
        'reports/repair_wave1/gate.json',
    'materials/repair_wave1_gate_report.md':
        'reports/repair_wave1/gate_report.md',
    'materials/repair_wave1_FORMAT.md':
        'reports/repair_wave1/FORMAT.md',
    'materials/matek_zero_step_plan.md':
        'reports/matek_zero_step/plan.md',
}

NOT_INCLUDED = [
    'починки волны 1 по АА (87 правок) — в базу не записаны, '
    'лежат в materials/aa_repairs.json',
    'нулевой шаг МатЭка — в базу не записан, только план в materials/',
]


def md5_of(path):
    h = hashlib.md5()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from problems.models import Problem

    db_path = os.path.join(ROOT, 'db.sqlite3')

    files_meta = []
    totals = {'problems': 0, 'approved': 0, 'defect': 0, 'not_reviewed': 0}
    for name in SOURCE_FILES:
        path = os.path.join(EXPORT_DIR, name)
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        counts = data['counts']
        files_meta.append({
            'name': name,
            'bytes': os.path.getsize(path),
            'md5': md5_of(path),
            'problems': counts['total'],
            'approved': counts['approved'],
            'defect': counts['defect'],
            'not_reviewed': counts['not_reviewed'],
        })
        for key, cnt_key in (('problems', 'total'), ('approved', 'approved'),
                             ('defect', 'defect'),
                             ('not_reviewed', 'not_reviewed')):
            totals[key] += counts[cnt_key]

    manifest = {
        'format': 'qls-handover-v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'db_md5': md5_of(db_path),
        'db_problems_total': Problem.objects.count(),
        'files': files_meta,
        'totals': totals,
        'not_included': NOT_INCLUDED,
    }

    manifest_path = os.path.join(EXPORT_DIR, 'manifest.json')
    with open(manifest_path, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    ideas_path = os.path.join(ROOT, 'ПЕРЕДАЧА_ИДЕИ.md')

    with zipfile.ZipFile(OUT_ZIP, 'w', zipfile.ZIP_DEFLATED,
                         compresslevel=9) as zf:
        zf.write(ideas_path, 'ПЕРЕДАЧА_ИДЕИ.md')
        zf.write(manifest_path, 'manifest.json')
        for name in SOURCE_FILES:
            zf.write(os.path.join(EXPORT_DIR, name), name)
        for arcname, rel in MATERIALS.items():
            src = os.path.join(ROOT, rel)
            if not os.path.exists(src):
                raise SystemExit(f'Нет файла для архива: {rel}')
            zf.write(src, arcname)

    print('Архив:', OUT_ZIP)
    print('Размер:', f'{os.path.getsize(OUT_ZIP):,}'.replace(',', ' '), 'байт',
          f'({os.path.getsize(OUT_ZIP) / 1024 / 1024:.1f} МБ)')
    print('MD5:', md5_of(OUT_ZIP))
    print('MD5 базы:', manifest['db_md5'])
    print('Задач в базе:', manifest['db_problems_total'])
    print('Итого в архиве:', totals)
    with zipfile.ZipFile(OUT_ZIP) as zf:
        print('Файлов внутри:', len(zf.namelist()))
        for n in zf.namelist():
            print('   ', n)


if __name__ == '__main__':
    main()
