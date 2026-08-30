# -*- coding: utf-8 -*-
"""Правило старшинства при поиске картинки в зипах Archive 3.

Проверяется главное свойство: команда НЕ приписывает задаче картинку из
чужого проекта, если файлы с этим именем разные (ADR 0037 — приписать
чужой график хуже, чем не приписать никакого).
"""
import io
import json
import os
import shutil
import tempfile
import zipfile

from django.core.management import call_command
from django.test import SimpleTestCase

from problems.management.commands.corpus_archive3_images import zip_name


def make_inner(files):
    """Байты зипа проекта Overleaf с заданными файлами."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def make_outer(path, projects):
    """Внешний зип, внутри которого лежат зипы проектов."""
    with zipfile.ZipFile(path, 'w') as zf:
        for name, files in projects.items():
            zf.writestr(name, make_inner(files))


PNG = b'\x89PNG\r\n\x1a\n' + b'A' * 40
PNG2 = b'\x89PNG\r\n\x1a\n' + b'B' * 40


class Archive3SeniorityTests(SimpleTestCase):
    """Каждый тест строит свой архив и свою выгрузку — состояние не делится."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.archive = os.path.join(self.tmp, 'archive')
        self.raw = os.path.join(self.tmp, 'raw')
        self.reports = os.path.join(self.tmp, 'reports')
        for d in (self.archive, self.raw, self.reports):
            os.makedirs(d)
        os.makedirs(os.path.join(self.raw, 'index'))
        os.makedirs(os.path.join(self.raw, '11'))
        self._inventory([{'slot': '11', 'zip': 'Своя.zip', 'sha256': 'x'},
                         {'slot': '12', 'zip': 'Чужая.zip', 'sha256': 'y'}])
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _inventory(self, entries):
        with open(os.path.join(self.raw, 'index', 'inventory.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(entries, fh, ensure_ascii=False)

    def _unresolved(self, items):
        with open(os.path.join(self.reports, 'unresolved.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(items, fh, ensure_ascii=False)

    def _run(self, apply=False):
        out = io.StringIO()
        args = ['corpus_archive3_images', '--archive', self.archive,
                '--raw', self.raw, '--report-dir', self.reports]
        if apply:
            args.append('--apply')
        call_command(*args, stdout=out)
        with open(os.path.join(self.reports, 'archive3_match.json'),
                  encoding='utf-8') as fh:
            return json.load(fh), out.getvalue()

    # ------------------------------------------------------------------
    def test_same_project_full_path_is_grade_a(self):
        make_outer(os.path.join(self.archive, 'A.zip'),
                   {'Своя.zip': {'00все снимки/04БЕТА/Fin1.png': PNG}})
        self._unresolved([{'id': 1, 'ref': '00все снимки/04БЕТА/Fin1.png',
                           'slot': '11', 'rel': 'a.tex',
                           'why': 'файла нет в архиве'}])
        rows, _ = self._run()
        self.assertEqual(rows[0]['grade'], 'A')

    def test_same_project_basename_only_is_grade_b(self):
        make_outer(os.path.join(self.archive, 'A.zip'),
                   {'Своя.zip': {'другая/папка/Fin1.png': PNG}})
        self._unresolved([{'id': 1, 'ref': '00все снимки/04БЕТА/Fin1.png',
                           'slot': '11', 'rel': 'a.tex',
                           'why': 'файла нет в архиве'}])
        rows, _ = self._run()
        self.assertEqual(rows[0]['grade'], 'B')

    def test_foreign_project_but_identical_bytes_is_grade_c(self):
        """Файл только в чужом проекте, но копии побитово равны — выбор безразличен."""
        make_outer(os.path.join(self.archive, 'A.zip'),
                   {'Чужая.zip': {'x/Fin1.png': PNG},
                    'Третья.zip': {'y/Fin1.png': PNG}})
        self._unresolved([{'id': 1, 'ref': 'Fin1.png', 'slot': '11',
                           'rel': 'a.tex', 'why': 'файла нет в архиве'}])
        rows, _ = self._run()
        self.assertEqual(rows[0]['grade'], 'C')

    def test_foreign_projects_with_different_bytes_is_refused(self):
        """ГЛАВНЫЙ тест: одно имя, разные файлы, чужие проекты — не берём."""
        make_outer(os.path.join(self.archive, 'A.zip'),
                   {'Чужая.zip': {'x/Fin1.png': PNG},
                    'Третья.zip': {'y/Fin1.png': PNG2}})
        self._unresolved([{'id': 1, 'ref': 'Fin1.png', 'slot': '11',
                           'rel': 'a.tex', 'why': 'файла нет в архиве'}])
        rows, _ = self._run()
        self.assertEqual(rows[0]['grade'], 'D')
        self.assertIn('разных файлов', rows[0]['reason'])

    def test_own_project_wins_over_foreign_copy(self):
        """Свой проект старше чужого, даже если у чужого совпал полный путь."""
        make_outer(os.path.join(self.archive, 'A.zip'),
                   {'Своя.zip': {'другая/Fin1.png': PNG},
                    'Чужая.zip': {'00все снимки/04БЕТА/Fin1.png': PNG2}})
        self._unresolved([{'id': 1, 'ref': '00все снимки/04БЕТА/Fin1.png',
                           'slot': '11', 'rel': 'a.tex',
                           'why': 'файла нет в архиве'}])
        rows, _ = self._run()
        self.assertEqual(rows[0]['grade'], 'B')
        self.assertEqual(rows[0]['zip'], 'Своя.zip')

    def test_apply_writes_file_where_includegraphics_looks(self):
        make_outer(os.path.join(self.archive, 'A.zip'),
                   {'Своя.zip': {'00все снимки/04БЕТА/Fin1.png': PNG}})
        self._unresolved([{'id': 1, 'ref': '00все снимки/04БЕТА/Fin1.png',
                           'slot': '11', 'rel': 'a.tex',
                           'why': 'файла нет в архиве'}])
        self._run(apply=True)
        dest = os.path.join(self.raw, '11', '00все снимки', '04БЕТА', 'Fin1.png')
        self.assertTrue(os.path.isfile(dest))
        with open(dest, 'rb') as fh:
            self.assertEqual(fh.read(), PNG)

    def test_path_escaping_the_slot_is_refused(self):
        """`..` в ссылке не должен вывести запись за корень слота."""
        make_outer(os.path.join(self.archive, 'A.zip'),
                   {'Своя.zip': {'evil.png': PNG}})
        self._unresolved([{'id': 1, 'ref': '../../evil.png', 'slot': '11',
                           'rel': 'a.tex', 'why': 'файла нет в архиве'}])
        self._run(apply=True)
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, 'evil.png')))
        self.assertFalse(os.path.isfile(os.path.join(self.raw, 'evil.png')))

    def test_reference_without_extension_is_found(self):
        r"""`\includegraphics{Фото/СК2.4}` — на диске `СК2.4.png`.

        LaTeX подставляет расширение сам; `.4` расширением не является."""
        make_outer(os.path.join(self.archive, 'A.zip'),
                   {'Своя.zip': {'Фото/СК2.4.png': PNG}})
        self._unresolved([{'id': 1, 'ref': 'Фото/СК2.4', 'slot': '11',
                           'rel': 'a.tex', 'why': 'файла нет в архиве'}])
        rows, _ = self._run()
        self.assertEqual(rows[0]['grade'], 'A')

    def test_bare_name_without_dot_is_found(self):
        """У ссылки без папки «хвост пути» и «имя файла» — одно и то же.

        Поэтому вердикт A, а не B: `img/tablic.png` кончается на
        `/tablic.png`. Важно здесь не различение A/B, а то, что файл взят
        ИЗ СВОЕГО проекта."""
        make_outer(os.path.join(self.archive, 'A.zip'),
                   {'Своя.zip': {'img/tablic.png': PNG}})
        self._unresolved([{'id': 1, 'ref': 'tablic', 'slot': '11',
                           'rel': 'a.tex', 'why': 'файла нет в архиве'}])
        rows, _ = self._run()
        self.assertIn(rows[0]['grade'], ('A', 'B'))
        self.assertEqual(rows[0]['zip'], 'Своя.zip')

    def test_bare_name_gets_extension_on_disk(self):
        """Голое имя обязано лечь С расширением: иначе resolve_image его не найдёт."""
        make_outer(os.path.join(self.archive, 'A.zip'),
                   {'Своя.zip': {'img/tablic.png': PNG}})
        self._unresolved([{'id': 1, 'ref': 'tablic', 'slot': '11',
                           'rel': 'a.tex', 'why': 'файла нет в архиве'}])
        self._run(apply=True)
        self.assertTrue(os.path.isfile(
            os.path.join(self.raw, '11', 'tablic.png')))

    def test_dotted_reference_keeps_its_own_name_on_disk(self):
        """У `СК2.4` расширение непустое — resolve_image ищет имя дословно."""
        make_outer(os.path.join(self.archive, 'A.zip'),
                   {'Своя.zip': {'Фото/СК2.4.png': PNG}})
        self._unresolved([{'id': 1, 'ref': 'Фото/СК2.4', 'slot': '11',
                           'rel': 'a.tex', 'why': 'файла нет в архиве'}])
        self._run(apply=True)
        self.assertTrue(os.path.isfile(
            os.path.join(self.raw, '11', 'Фото', 'СК2.4')))

    def test_dry_run_writes_nothing(self):
        make_outer(os.path.join(self.archive, 'A.zip'),
                   {'Своя.zip': {'00все снимки/04БЕТА/Fin1.png': PNG}})
        self._unresolved([{'id': 1, 'ref': '00все снимки/04БЕТА/Fin1.png',
                           'slot': '11', 'rel': 'a.tex',
                           'why': 'файла нет в архиве'}])
        _rows, out = self._run()
        self.assertIn('СУХОЙ ПРОГОН', out)
        self.assertFalse(os.path.isdir(
            os.path.join(self.raw, '11', '00все снимки')))


class ZipNameEncodingTests(SimpleTestCase):
    r"""Починка имени члена зипа.

    Проверяется напрямую, а не через прогон команды: `writestr` сам
    выставляет флаг UTF-8, как только в имени есть не-ASCII, и подделать
    настоящий cp437-зип из Python нечем. А в живых зипах Archive 3 флага
    нет — именно поэтому русские папки (`00все снимки`) без починки
    читаются мусором и не совпадает ни один путь."""

    def test_cp437_name_without_flag_is_repaired(self):
        info = zipfile.ZipInfo('placeholder')
        info.filename = 'снимки/Фин1.png'.encode('utf-8').decode('cp437')
        info.flag_bits = 0
        self.assertEqual(zip_name(info), 'снимки/Фин1.png')

    def test_utf8_flagged_name_is_left_alone(self):
        info = zipfile.ZipInfo('снимки/Фин1.png')
        info.flag_bits = 0x800
        self.assertEqual(zip_name(info), 'снимки/Фин1.png')

    def test_undecodable_name_survives_as_is(self):
        """Имя, которое не читается ни так ни так, не должно ронять индекс."""
        info = zipfile.ZipInfo('Фин1.png')
        info.flag_bits = 0
        self.assertEqual(zip_name(info), 'Фин1.png')
