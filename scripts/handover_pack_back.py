"""Упаковка отчётов для передачи обратно Макару + итоговый манифест.

ТОЛЬКО ЧТЕНИЕ проекта: читает reports/, пишет ТОЛЬКО в папку отправки
за пределами репозитория. Базу не открывает вовсе.
"""
import hashlib
import io
import json
import sys
import zipfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEND = Path('C:/Users/COLORFUL/qls_send_20260820')
SEND.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8')

FOLDERS = [
    ('repair_wave1_20260820.zip', ROOT / 'reports' / 'repair_wave1',
     'Оболочка разбора волны 1 (reviewer.html) + 87 починок АА, шлюз, партии'),
    ('matek_zero_step_20260820.zip', ROOT / 'reports' / 'matek_zero_step',
     'Нулевой шаг МатЭка: план и превью прототипа на 30 задачах'),
    ('publication_check_20260820.zip', ROOT / 'reports' / 'publication_check',
     'Проверка одобренных на дыры: 8 признаков, списки id, очередь рендера'),
]


def md5_of(path):
    h = hashlib.md5(usedforsecurity=False)
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def human(n):
    if n >= 1048576:
        return '{:.2f} МБ'.format(n / 1048576)
    return '{:.1f} КБ'.format(n / 1024)


rows = []

# --- архивы отчётов ---------------------------------------------------------
for zip_name, folder, note in FOLDERS:
    if not folder.exists():
        print('нет папки, пропускаю:', folder)
        continue
    target = SEND / zip_name
    files = sorted(p for p in folder.rglob('*') if p.is_file())
    # Порядок и даты фиксированные — иначе MD5 архива не воспроизводится
    # и сверкой пользоваться нельзя (тот же довод, что в verify_handover).
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in files:
            info = zipfile.ZipInfo(str(p.relative_to(folder.parent)).replace('\\', '/'),
                                   date_time=(2026, 8, 20, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            z.writestr(info, p.read_bytes())
    rows.append(OrderedDict([
        ('file', zip_name), ('bytes', target.stat().st_size),
        ('md5', md5_of(target)), ('inner_files', len(files)), ('note', note),
    ]))
    print('{:<34} {:>10}  {} файлов'.format(zip_name, human(target.stat().st_size), len(files)))

# --- паспорт кладём и россыпью, чтобы читался без распаковки -----------------
passport = ROOT / 'reports' / 'handover_back_20260820'
for name in ('STATE.md', 'state.json', 'diff_vs_baseline.json'):
    src = passport / name
    if not src.exists():
        continue
    dst = SEND / name
    dst.write_bytes(src.read_bytes())
    rows.append(OrderedDict([
        ('file', name), ('bytes', dst.stat().st_size), ('md5', md5_of(dst)),
        ('inner_files', None),
        ('note', 'Паспорт состояния базы — эталон для сверки реконструкции'),
    ]))
    print('{:<34} {:>10}'.format(name, human(dst.stat().st_size)))

# --- bundle уже лежит, только измеряем --------------------------------------
bundle = SEND / 'qls_anich_20260820.bundle'
if bundle.exists():
    rows.insert(0, OrderedDict([
        ('file', bundle.name), ('bytes', bundle.stat().st_size),
        ('md5', md5_of(bundle)), ('inner_files', None),
        ('note', 'Код и ВСЯ история git, все ветки. Разворачивать: git clone <файл> qls'),
    ]))
    print('{:<34} {:>10}'.format(bundle.name, human(bundle.stat().st_size)))

# --- манифест ---------------------------------------------------------------
man = OrderedDict([
    ('format', 'qls-handover-back-v1'),
    ('generated_at', datetime.now().isoformat(timespec='seconds')),
    ('from', 'машина Анича, Windows, C:\\qls'),
    ('to', 'Макар, Mac'),
    ('files', rows),
])
with io.open(SEND / 'manifest.json', 'w', encoding='utf-8') as fh:
    json.dump(man, fh, ensure_ascii=False, indent=2)

L = []
L.append('# Что отправляется Макару — 2026-08-20')
L.append('')
L.append('Собрано на машине Анича (Windows, `C:\\qls`). База в этой сессии **не менялась**:')
L.append('MD5 `db.sqlite3` в начале и в конце совпал.')
L.append('')
L.append('| Файл | Размер | MD5 | Что это |')
L.append('|---|---|---|---|')
for r in rows:
    L.append('| `{}` | {} | `{}` | {} |'.format(
        r['file'], human(r['bytes']), r['md5'], r['note']))
L.append('')
L.append('## Как разворачивать')
L.append('')
L.append('```bash')
L.append('# код и вся история, все ветки')
L.append('git clone qls_anich_20260820.bundle qls-anich')
L.append('cd qls-anich && git log --oneline -5')
L.append('# рабочая ветка называется feat/human-review-gate')
L.append('```')
L.append('')
L.append('⚠️ **Перед слиянием сверить номера миграций.** Наших три: `0040_human_review_gate`,')
L.append('`0041_review_fixed_wrong`, `0042_review_quotes`. Если на `main` завелись свои')
L.append('`0040+` — перенумеровывать надо наши, см. раздел 11–12 в `STATE.md`.')
L.append('')
L.append('⚠️ **Архив `qls_handover_20260820.zip` сюда НЕ вложен** — он уже у Макара,')
L.append('а пересобирается `scripts/build_handover_zip.py` за секунду. В историю git')
L.append('он тоже не взят: двоичный файл на 6,5 МБ остался бы там навсегда.')
L.append('')
io.open(SEND / 'MANIFEST.md', 'w', encoding='utf-8').write('\n'.join(L) + '\n')

print()
print('манифест:', SEND / 'MANIFEST.md')
print('всего файлов к отправке:', len(rows) + 2)
