# -*- coding: utf-8 -*-
r"""Фаза 2: достать из зипов «Archive 3» картинки, которых нет в выгрузке 2026.

Что за дыра. `corpus_legacy_figures` разрешает ссылку `\includegraphics`
по распакованной выгрузке `_raw2026` (67 проектов Overleaf). У 465 ссылок
файла там нет вовсе: ссылки ведут в папки вроде `00все снимки/…`, которые
в выгрузку 2026 года не попали.

Где они нашлись. `weconomics-data/Archive 3 - ИЗНАЧАЛЬНАЯ БАЗА` — это НЕ
распакованная папка, а четыре зипа, и внутри `Archive 2.zip` лежат ещё
**61 вложенный зип проектов Overleaf** (плюс один во втором архиве). Это
ДРУГИЕ, более ранние выгрузки тех же проектов: по sha256 со слотами
`_raw2026` не совпадает ни один, а по имени зипа совпадают 56 из 62.
Всего внутри 4 246 растровых картинок против 4 488 в выгрузке 2026 —
наборы разные, и потерянные папки снимков лежат именно в старых.

**Почему нельзя брать файл просто по имени.** Одно и то же имя (`1.jpg`,
`Fin1.png`, `фото кпв.png`) встречается в разных проектах и означает РАЗНЫЕ
картинки: из 418 совпадений 390 неоднозначны по имени. ADR 0037 говорит
прямо — приписать задаче чужой график хуже, чем не приписать никакого.
Поэтому действует правило старшинства:

  * **A** — файл лежит в зипе ТОГО ЖЕ проекта Overleaf, что и задача (имя
    вложенного зипа совпадает с именем зипа слота из `inventory.json`),
    и совпадает хвост пути целиком. Самое надёжное;
  * **B** — тот же проект, но совпало только имя файла;
  * **C** — проект другой, НО все кандидаты с этим именем побитово
    одинаковы (`CRC32` + размер), так что выбор безразличен;
  * **D** — не разрешаем. Лучше оставить дефект, чем показать чужое.

Что делает `--apply`. Не пишет в базу вовсе: кладёт найденный файл в
`_raw2026/<слот>/<путь из ссылки>` — то есть ДОСТРАИВАЕТ выгрузку до того
вида, в котором её ожидает `\includegraphics`. Дальше картинки заводит
`corpus_legacy_figures --apply` своим обычным ходом; логика разрешения
ссылок остаётся в одном месте, а не копируется сюда.

Порядок:

    manage.py corpus_legacy_figures            # родит unresolved.json
    manage.py corpus_archive3_images --apply   # достроит выгрузку
    manage.py corpus_legacy_figures --apply    # заведёт ProblemFigure

По умолчанию — сухой прогон.
"""
import hashlib
import io
import json
import os
import re
import zipfile
from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

RAW = os.path.join('C:', os.sep, 'Users', 'shipu', 'weconomics-data', '_raw2026')
ARCHIVE = os.path.join('C:', os.sep, 'Users', 'shipu', 'weconomics-data',
                       'Archive 3 - ИЗНАЧАЛЬНАЯ БАЗА')
OUT_DIR = os.path.join(settings.BASE_DIR, 'reports', 'corpus_legacy_figures')
IMG_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tif', '.tiff')
#: Тот же потолок, что у corpus_legacy_figures: битый файл не уезжает молча.
MAX_BYTES = 8 * 1024 * 1024
BACKSLASH = chr(92)


def norm(path):
    """Путь из зипа/ссылки к общему виду: прямые слеши, без пустых звеньев."""
    return re.sub(r'/+', '/', (path or '').replace(BACKSLASH, '/')).strip('/')


def zip_name(info):
    r"""Имя члена зипа с починкой кодировки.

    Zip без флага UTF-8 хранит имя в cp437, и русские папки (`00все
    снимки`) читаются мусором. Без починки не совпадёт ни один путь."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode('cp437').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


class Command(BaseCommand):
    help = ('Достать из зипов Archive 3 картинки, которых нет в выгрузке 2026, '
            'и доложить их в _raw2026. Без --apply — сухой прогон.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='записать файлы в _raw2026 (иначе сухой прогон)')
        parser.add_argument('--archive', default=ARCHIVE)
        parser.add_argument('--raw', default=RAW)
        parser.add_argument('--unresolved', default='',
                            help='путь к unresolved.json (по умолчанию из --report-dir)')
        parser.add_argument('--report-dir', default=OUT_DIR)

    def handle(self, *args, **options):
        raw = options['raw']
        archive = options['archive']
        report_dir = options['report_dir']
        unresolved_path = (options['unresolved']
                           or os.path.join(report_dir, 'unresolved.json'))

        if not os.path.isdir(archive):
            raise CommandError('нет папки архивов: %s' % archive)
        if not os.path.isfile(unresolved_path):
            raise CommandError(
                'нет %s — сначала прогоните corpus_legacy_figures' % unresolved_path)

        inventory_path = os.path.join(raw, 'index', 'inventory.json')
        if not os.path.isfile(inventory_path):
            raise CommandError('нет индекса выгрузки: %s' % inventory_path)
        with open(inventory_path, encoding='utf-8') as fh:
            inventory = {e['slot']: e for e in json.load(fh)}

        with open(unresolved_path, encoding='utf-8') as fh:
            unresolved = json.load(fh)
        missing = [x for x in unresolved if x.get('why') == 'файла нет в архиве']

        images = self._index(archive)
        by_zip, by_base = defaultdict(list), defaultdict(list)
        for im in images:
            by_zip[im['zipbase']].append(im)
            by_base[os.path.basename(im['npath'])].append(im)

        rows, stats = [], defaultdict(int)
        for item in missing:
            row = self._grade(item, inventory, by_zip, by_base)
            stats[row['grade']] += 1
            rows.append(row)

        stats['ссылок разобрано'] = len(missing)
        stats['картинок в зипах Archive 3'] = len(images)
        good = [r for r in rows if r['grade'] in ('A', 'B', 'C')]
        stats['разрешено ссылок'] = len(good)
        stats['разрешено задач'] = len({r['id'] for r in good})
        stats['НЕ разрешено ссылок'] = len(rows) - len(good)
        stats['НЕ разрешено задач'] = len({r['id'] for r in rows
                                           if r['grade'].startswith('D')})

        os.makedirs(report_dir, exist_ok=True)
        with open(os.path.join(report_dir, 'archive3_match.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)

        written = 0
        if options['apply']:
            written = self._extract(archive, raw, good, stats)

        self._print(stats, options['apply'], written, report_dir)

    # ------------------------------------------------------------------
    def _index(self, archive):
        """Все растровые картинки вложенных зипов: путь, CRC, размер."""
        images = []
        for name in sorted(os.listdir(archive)):
            if not name.lower().endswith('.zip'):
                continue
            with zipfile.ZipFile(os.path.join(archive, name)) as outer:
                for info in outer.infolist():
                    inner_name = zip_name(info)
                    if info.is_dir() or inner_name.startswith('__MACOSX'):
                        continue
                    if not inner_name.lower().endswith('.zip'):
                        continue
                    try:
                        inner = zipfile.ZipFile(io.BytesIO(outer.read(info)))
                    except (zipfile.BadZipFile, RuntimeError):
                        continue
                    with inner:
                        for member in inner.infolist():
                            mname = zip_name(member)
                            if member.is_dir() or mname.startswith('__MACOSX'):
                                continue
                            if not mname.lower().endswith(IMG_EXT):
                                continue
                            images.append({
                                'outer': name,
                                'zip': inner_name,
                                'zipbase': os.path.basename(norm(inner_name)).lower(),
                                'path': mname,
                                'npath': norm(mname).lower(),
                                'crc': member.CRC,
                                'size': member.file_size,
                            })
        return images

    def _grade(self, item, inventory, by_zip, by_base):
        """Вердикт по одной ссылке — см. правило старшинства в докстринге."""
        base_row = {'id': item['id'], 'ref': item['ref'],
                    'slot': item.get('slot'), 'rel': item.get('rel')}
        ref = norm(item['ref'])
        if not ref:
            return dict(base_row, grade='D', reason='пустая ссылка')

        variants = self._variants(ref.lower())
        slot = item.get('slot')
        entry = inventory.get(slot)
        own = os.path.basename(norm(entry['zip'])).lower() if entry else None

        if own and own in by_zip:
            hit, how = self._pick(by_zip[own], variants)
            if hit:
                return dict(base_row, grade='A' if how == 'path' else 'B',
                            **self._chosen(hit[0]))

        pool = []
        seen = set()
        for low in variants:
            for cand in by_base.get(os.path.basename(low), ()):
                key = (cand['zip'], cand['npath'])
                if key not in seen:
                    seen.add(key)
                    pool.append(cand)
        hit, _how = self._pick(pool, variants)
        if hit:
            if len({(h['crc'], h['size']) for h in hit}) == 1:
                return dict(base_row, grade='C', **self._chosen(hit[0]))
            return dict(base_row, grade='D',
                        reason='%d разных файлов с этим именем в чужих проектах'
                               % len(hit))
        return dict(base_row, grade='D', reason='нет ни в одном зипе Archive 3')

    @staticmethod
    def _variants(low):
        r"""Написания ссылки, которые LaTeX считает одной и той же картинкой.

        `\includegraphics{Фото/СК2.4}` подставляет расширение сам, и на
        диске лежит `СК2.4.png`. Без этого ссылка без расширения не
        совпадёт ни с чем: `os.path.splitext` честно считает `.4`
        расширением, и поиск по имени идёт по `ск2.4`. Ровно тот же
        перебор делает `raw_units.resolve_image` — здесь он повторён,
        чтобы два места судили ссылку одинаково.

        Живой замер: так возвращаются ссылки вида `Фото/СК2.4`, `tablic`,
        `SK1`, `3` — 12 задач Archive 3."""
        out = [low]
        if os.path.splitext(low)[1] not in IMG_EXT:
            out += [low + ext for ext in IMG_EXT]
        return out

    @staticmethod
    def _pick(candidates, variants):
        """Сначала полный хвост пути, потом имя файла — по всем написаниям."""
        for low in variants:
            exact = [c for c in candidates
                     if c['npath'] == low or c['npath'].endswith('/' + low)]
            if exact:
                return exact, 'path'
        for low in variants:
            base = os.path.basename(low)
            named = [c for c in candidates
                     if os.path.basename(c['npath']) == base]
            if named:
                return named, 'base'
        return [], None

    @staticmethod
    def _chosen(image):
        return {'outer': image['outer'], 'zip': image['zip'],
                'member': image['path'], 'crc': image['crc'],
                'size': image['size']}

    def _extract(self, archive, raw, rows, stats):
        r"""Положить найденные файлы в `_raw2026/<слот>/<ссылка>`.

        Именно по пути ССЫЛКИ, а не по пути внутри зипа: `resolve_image`
        ищет относительно корня проекта, и файл обязан лечь туда, куда
        смотрит `\includegraphics`."""
        wanted = defaultdict(list)
        for row in rows:
            wanted[(row['outer'], row['zip'])].append(row)

        written = 0
        for (outer_name, inner_name), items in sorted(wanted.items()):
            with zipfile.ZipFile(os.path.join(archive, outer_name)) as outer:
                target = next((i for i in outer.infolist()
                               if zip_name(i) == inner_name), None)
                if target is None:
                    continue
                with zipfile.ZipFile(io.BytesIO(outer.read(target))) as inner:
                    members = {zip_name(i): i for i in inner.infolist()}
                    for row in items:
                        info = members.get(row['member'])
                        if info is None:
                            stats['пропущено: член зипа исчез'] += 1
                            continue
                        if info.file_size > MAX_BYTES:
                            stats['пропущено: больше потолка'] += 1
                            continue
                        dest = self._destination(raw, row)
                        if dest is None:
                            stats['пропущено: путь вне слота'] += 1
                            continue
                        if os.path.isfile(dest):
                            stats['уже лежал'] += 1
                            continue
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with open(dest, 'wb') as fh:
                            fh.write(inner.read(info))
                        written += 1
        stats['файлов доложено в _raw2026'] = written
        return written

    @staticmethod
    def _destination(raw, row):
        r"""Куда лечь файлу. None — если путь вылезает за корень слота.

        Имя берётся из ССЫЛКИ, а не из зипа: `resolve_image` ищет ровно
        то, что написано в `\includegraphics`.

        ⚠️ Исключение — ссылка вовсе без точки (`tablic`, `SK1`). Там
        `resolve_image` пробует `tablic.png`, `tablic.jpg`, … и голое имя
        НЕ проверяет вовсе (`names` перезаписывается, а не дополняется).
        Файл без расширения такая ссылка не нашла бы, поэтому расширение
        берётся у найденного члена зипа."""
        ref = norm(row['ref'])
        if not os.path.splitext(ref)[1]:
            ref += os.path.splitext(norm(row['member']))[1]
        root = os.path.realpath(os.path.join(raw, row['slot']))
        dest = os.path.realpath(os.path.join(root, ref.replace('/', os.sep)))
        if os.path.commonpath([root, dest]) != root:
            return None
        return dest

    def _print(self, stats, applied, written, report_dir):
        for key in ('ссылок разобрано', 'картинок в зипах Archive 3',
                    'A', 'B', 'C', 'D',
                    'разрешено ссылок', 'разрешено задач',
                    'НЕ разрешено ссылок', 'НЕ разрешено задач',
                    'уже лежал', 'пропущено: больше потолка',
                    'пропущено: член зипа исчез', 'пропущено: путь вне слота'):
            if key in stats:
                self.stdout.write('%-34s %6d' % (key, stats[key]))
        self.stdout.write('')
        if applied:
            self.stdout.write('ЗАПИСАНО файлов в _raw2026: %d' % written)
            self.stdout.write('Дальше: corpus_legacy_figures --apply')
        else:
            self.stdout.write('СУХОЙ ПРОГОН — на диск не записано ничего.')
        self.stdout.write('разбор: %s'
                          % os.path.join(report_dir, 'archive3_match.json'))
