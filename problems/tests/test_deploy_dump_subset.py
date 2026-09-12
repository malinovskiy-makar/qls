# -*- coding: utf-8 -*-
u"""Выгрузка подмножества корпуса: `--ids-file` и `--with-dupmark`.

Что здесь сторожится:

* в выгрузку не попадает НИ ОДНА задача вне списка — ни сама, ни через
  подпункт, ссылку на источник, картинку или рубрику;
* модель, для которой в `PROBLEM_PATH` нет пути до задачи, роняет команду,
  а не выгружается целиком молча: иначе на проде получилась бы строка,
  ссылающаяся на задачу, которой там нет;
* `DupMark` едет только целыми группами — половина группы на проде это
  пометка «копия чего-то», чего там нет;
* список с несуществующим id — ошибка, а не тихо уменьшенная выгрузка;
* файлы `DupMark` называются так, что грузятся ПОСЛЕ задач (по алфавиту).
"""
import io
import json
import os
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.management.commands import dump_for_deploy as dfd
from problems.models import DupMark, ProblemFigure, ProblemPart, SourceReference
from problems.tests.factories import link_source, make_problem, make_source


def прочитать(каталог):
    """{модель: [pk, …]} по всем файлам выгрузки."""
    собрано = {}
    for имя in sorted(os.listdir(каталог)):
        if not имя.endswith('.json'):
            continue
        with io.open(os.path.join(каталог, имя), encoding='utf-8') as f:
            for obj in json.load(f):
                собрано.setdefault(obj['model'], []).append(obj['pk'])
    return собрано


class ВыгрузкаПоСписку(TestCase):
    def setUp(self):
        self.источник = make_source()
        self.внутри = make_problem(statement='Едет на прод.')
        self.снаружи = make_problem(statement='Остаётся дома.')
        for задача in (self.внутри, self.снаружи):
            link_source(задача, self.источник)
            ProblemPart.objects.create(problem=задача, order=1, label='а',
                                       statement='подпункт', answer='1')
            ProblemFigure.objects.create(problem=задача, tikz_hash='c' * 64,
                                         tikz_source='x', svg='<svg/>')

    def выгрузить(self, ids, **флаги):
        каталог = tempfile.mkdtemp()
        файл = os.path.join(каталог, 'ids.txt')
        io.open(файл, 'w', encoding='utf-8').write(
            '\n'.join(str(i) for i in ids))
        вывод = os.path.join(каталог, 'out')
        call_command('dump_for_deploy', outdir=вывод, bank_only=True,
                     ids_file=файл, verbosity=0, **флаги)
        return прочитать(вывод)

    def test_едет_только_задача_из_списка(self):
        собрано = self.выгрузить([self.внутри.pk])
        self.assertEqual(собрано['problems.problem'], [self.внутри.pk])

    def test_чужие_подпункты_картинки_и_ссылки_не_едут(self):
        собрано = self.выгрузить([self.внутри.pk])
        чужие_части = ProblemPart.objects.filter(problem=self.снаружи)
        чужие_ссылки = SourceReference.objects.filter(problem=self.снаружи)
        чужие_рисунки = ProblemFigure.objects.filter(problem=self.снаружи)
        for модель, лишние in (('problems.problempart', чужие_части),
                               ('problems.sourcereference', чужие_ссылки),
                               ('problems.problemfigure', чужие_рисунки)):
            уехало = set(собрано.get(модель, []))
            for строка in лишние:
                self.assertNotIn(строка.pk, уехало, модель)

    def test_свои_подпункты_и_картинки_едут(self):
        собрано = self.выгрузить([self.внутри.pk])
        self.assertEqual(len(собрано.get('problems.problempart', [])), 1)
        self.assertEqual(len(собрано.get('problems.problemfigure', [])), 1)

    def test_справочники_едут_целиком(self):
        # Источник один на обе задачи; резать справочники по списку задач
        # незачем — они маленькие и нужны любой задаче.
        собрано = self.выгрузить([self.внутри.pk])
        self.assertIn('problems.source', собрано)

    def test_несуществующий_id_роняет_команду(self):
        with self.assertRaises(CommandError) as случай:
            self.выгрузить([self.внутри.pk, 999999])
        self.assertIn('нет 1 из 2', str(случай.exception))

    def test_модель_без_пути_до_задачи_роняет_команду(self):
        """Молча выгрузить её целиком нельзя — на проде будет ссылка в пустоту."""
        прежний = dict(dfd.PROBLEM_PATH)
        dfd.PROBLEM_PATH.pop('problems.ProblemFigure')
        self.addCleanup(lambda: dfd.PROBLEM_PATH.update(прежний))
        with self.assertRaises(CommandError) as случай:
            self.выгрузить([self.внутри.pk])
        self.assertIn('PROBLEM_PATH', str(случай.exception))


class ВыгрузкаПометокКопий(TestCase):
    def setUp(self):
        self.а = make_problem(statement='Версия А.')
        self.б = make_problem(statement='Версия Б.')
        self.в = make_problem(statement='Версия В, чужая группа.')
        self.г = make_problem(statement='Версия Г, чужая группа.')
        for задача in (self.а, self.б):
            DupMark.objects.create(problem=задача, group='целая',
                                   rule=DupMark.Rule.APPROVED,
                                   is_best=(задача is self.а))
        for задача in (self.в, self.г):
            DupMark.objects.create(problem=задача, group='половинка',
                                   rule=DupMark.Rule.APPROVED,
                                   is_best=(задача is self.в))

    def выгрузить(self, ids):
        каталог = tempfile.mkdtemp()
        файл = os.path.join(каталог, 'ids.txt')
        io.open(файл, 'w', encoding='utf-8').write('\n'.join(str(i) for i in ids))
        вывод = os.path.join(каталог, 'out')
        call_command('dump_for_deploy', outdir=вывод, bank_only=True,
                     ids_file=файл, with_dupmark=True, verbosity=0)
        return вывод, прочитать(вывод)

    def test_целая_группа_едет(self):
        _, собрано = self.выгрузить([self.а.pk, self.б.pk])
        self.assertEqual(len(собрано.get('problems.dupmark', [])), 2)

    def test_половина_группы_не_едет_вовсе(self):
        # self.в внутри, self.г снаружи — группа «половинка» остаётся дома
        # целиком, иначе на проде висел бы внешний ключ в пустоту.
        _, собрано = self.выгрузить([self.а.pk, self.б.pk, self.в.pk])
        уехало = set(собрано.get('problems.dupmark', []))
        чужие = set(DupMark.objects.filter(group='половинка')
                    .values_list('pk', flat=True))
        self.assertFalse(уехало & чужие)
        self.assertEqual(len(уехало), 2)

    def test_файл_пометок_грузится_после_задач(self):
        каталог, _ = self.выгрузить([self.а.pk, self.б.pk])
        файлы = sorted(f for f in os.listdir(каталог) if f.endswith('.json'))
        пометки = [f for f in файлы if 'dupmark' in f]
        задачи = [f for f in файлы if f.startswith('20_problem')]
        self.assertTrue(пометки and задачи)
        self.assertGreater(min(пометки), max(задачи))

    def test_без_списка_задач_флаг_запрещён(self):
        каталог = tempfile.mkdtemp()
        with self.assertRaises(CommandError) as случай:
            call_command('dump_for_deploy', outdir=каталог, bank_only=True,
                         with_dupmark=True, verbosity=0)
        self.assertIn('--ids-file', str(случай.exception))


class ПолнаяВыгрузкаНеИзменилась(TestCase):
    """Без новых флагов команда обязана вести себя ровно как прежде."""

    def test_без_ids_file_едут_все_задачи(self):
        make_problem(statement='Первая.')
        make_problem(statement='Вторая.')
        каталог = tempfile.mkdtemp()
        call_command('dump_for_deploy', outdir=каталог, bank_only=True,
                     verbosity=0)
        собрано = прочитать(каталог)
        self.assertEqual(len(собрано['problems.problem']), 2)
        self.assertNotIn('problems.dupmark', собрано)


class ОбластьВидимостиГрупп(TestCase):
    """Группа копий может стоять одной ногой в уже залитой задаче.

    Заливка только ДОБАВЛЯЕТ (`bulk_create(ignore_conflicts=True)`), поэтому
    задачи, которые уже на проде, во второй раз не выгружаются — иначе их
    подпункты и картинки приехали бы вторыми экземплярами с новыми номерами.
    Но пометки их групп на проде нужны, и область видимости задаётся отдельно.
    """

    def setUp(self):
        self.уже_на_проде = make_problem(statement='Лежит на проде.')
        self.новая = make_problem(statement='Едет впервые.')
        for задача in (self.уже_на_проде, self.новая):
            DupMark.objects.create(problem=задача, group='смешанная',
                                   rule=DupMark.Rule.APPROVED,
                                   is_best=(задача is self.новая))

    def выгрузить(self, ids, scope):
        каталог = tempfile.mkdtemp()
        путь_ids = os.path.join(каталог, 'ids.txt')
        путь_scope = os.path.join(каталог, 'scope.txt')
        io.open(путь_ids, 'w', encoding='utf-8').write('\n'.join(map(str, ids)))
        io.open(путь_scope, 'w', encoding='utf-8').write('\n'.join(map(str, scope)))
        вывод = os.path.join(каталог, 'out')
        call_command('dump_for_deploy', outdir=вывод, bank_only=True,
                     ids_file=путь_ids, with_dupmark=True,
                     dupmark_scope_file=путь_scope, verbosity=0)
        return прочитать(вывод)

    def test_пометки_едут_а_чужая_задача_нет(self):
        собрано = self.выгрузить(
            [self.новая.pk], [self.новая.pk, self.уже_на_проде.pk])
        self.assertEqual(собрано['problems.problem'], [self.новая.pk])
        self.assertEqual(len(собрано['problems.dupmark']), 2)

    def test_без_области_видимости_группа_не_проходит(self):
        собрано = self.выгрузить([self.новая.pk], [self.новая.pk])
        self.assertNotIn('problems.dupmark', собрано)

    def test_область_видимости_обязана_включать_список_выгрузки(self):
        with self.assertRaises(CommandError) as случай:
            self.выгрузить([self.новая.pk], [self.уже_на_проде.pk])
        self.assertIn('обязан включать весь', str(случай.exception))
