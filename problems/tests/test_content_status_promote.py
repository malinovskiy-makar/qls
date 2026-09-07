# -*- coding: utf-8 -*-
"""`content_status_promote` — размыкание круга по данным (решение 07.09.2026).

Правило «чистка сильнее прогона, повышений не бывает» остаётся в силе для
РУЧНОЙ чистки, но не для метки, которую поставил сам слабый прогон. Иначе
круг не размыкается никогда: задачу пометил слабый прогон → из-за пометки её
не пустили в сильный → она навсегда вне каталога.

Главный инвариант файла — «ни одна задача ВНЕ манифеста не сменила
`content_status`». Проверка глазами здесь бесполезна: задач 41 307.
"""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.management.commands.content_status_promote import status_for
from problems.models import Problem


class StatusForTests(TestCase):

    def test_не_задача_в_любом_из_двух_полей_даёт_junk(self):
        self.assertEqual(status_for('не_задача', 'единственный_выбор'), 'junk')
        self.assertEqual(status_for('чистая', 'не_задача'), 'junk')

    def test_серьёзные_дефекты_дают_needs_fix(self):
        self.assertEqual(status_for('серьёзные_дефекты', 'верно_неверно'),
                         'needs_fix')

    def test_всё_остальное_даёт_ok(self):
        for tq in ('чистая', 'мелкие_дефекты', '', None):
            self.assertEqual(status_for(tq, 'верно_неверно'), 'ok')

    def test_правило_ПОВЫШАЕТ_в_отличие_от_layout(self):
        """`layout.content_status_for` никогда не понижает планку —
        `content_cleanup` сильнее модели. Здесь повышение и есть смысл
        команды, поэтому правило своё, а не то с флагом."""
        from problems.enrich import layout
        self.assertEqual(layout.content_status_for('needs_fix', 'чистая',
                                                   'верно_неверно'),
                         'needs_fix')
        self.assertEqual(status_for('чистая', 'верно_неверно'), 'ok')


class PromoteCommandTests(TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.снимок = self.tmp / 'backup.json'
        # в манифесте
        self.поднимется = Problem.objects.create(
            statement='Хорошая задача про рынок.', content_status='needs_fix',
            text_quality='чистая', problem_type='верно_неверно',
            status=Problem.Status.PUBLISHED)
        self.поднимется_черновик = Problem.objects.create(
            statement='Черновик.', content_status='needs_fix',
            text_quality='мелкие_дефекты', problem_type='верно_неверно',
            status=Problem.Status.DRAFT)
        self.останется = Problem.objects.create(
            statement='Битая задача.', content_status='needs_fix',
            text_quality='серьёзные_дефекты', problem_type='верно_неверно')
        self.уедет_в_junk = Problem.objects.create(
            statement='Не задача.', content_status='needs_fix',
            text_quality='не_задача', problem_type='не_задача')
        # ВНЕ манифеста — те же признаки, что у поднимающихся
        self.чужая = Problem.objects.create(
            statement='Чужая задача, тоже годная.', content_status='needs_fix',
            text_quality='чистая', problem_type='верно_неверно',
            status=Problem.Status.PUBLISHED)

        self.манифест = self.tmp / 'manifest.txt'
        self.манифест.write_text(
            '# манифест допрогона\n%s\n'
            % '\n'.join(str(p.id) for p in (
                self.поднимется, self.поднимется_черновик, self.останется,
                self.уедет_в_junk)),
            encoding='utf-8')

    def _run(self, **kwargs):
        buf = StringIO()
        call_command('content_status_promote', manifest=str(self.манифест),
                     snapshot=str(self.снимок), stdout=buf, **kwargs)
        for p in (self.поднимется, self.поднимется_черновик, self.останется,
                  self.уедет_в_junk, self.чужая):
            if Problem.objects.filter(pk=p.pk).exists():
                p.refresh_from_db()
        return buf.getvalue()

    def test_по_умолчанию_ничего_не_меняет(self):
        вывод = self._run()
        self.assertIn('Это план', вывод)
        self.assertEqual(self.поднимется.content_status, 'needs_fix')

    def test_план_называет_прирост_каталога_отдельной_строкой(self):
        вывод = self._run()
        self.assertIn('поднялось needs_fix → ok: 2, из них published: 1', вывод)

    def test_apply_повышает_понижает_и_оставляет(self):
        self._run(apply=True)
        self.assertEqual(self.поднимется.content_status, 'ok')
        self.assertEqual(self.поднимется_черновик.content_status, 'ok')
        self.assertEqual(self.останется.content_status, 'needs_fix')
        self.assertEqual(self.уедет_в_junk.content_status, 'junk')

    def test_задача_вне_манифеста_не_тронута(self):
        """Главный инвариант. У «чужой» ровно те же признаки, что у
        поднимающейся, — если команда смотрит на признаки, а не на манифест,
        тест это поймает."""
        self._run(apply=True)
        self.assertEqual(self.чужая.content_status, 'needs_fix')

    def test_revert_возвращает_как_было(self):
        self._run(apply=True)
        self.assertEqual(self.поднимется.content_status, 'ok')
        self._run(revert=True)
        self.assertEqual(self.поднимется.content_status, 'needs_fix')
        self.assertEqual(self.уедет_в_junk.content_status, 'needs_fix')

    def test_снимок_содержит_только_изменённые(self):
        self._run(apply=True)
        данные = json.loads(self.снимок.read_text(encoding='utf-8'))
        self.assertEqual(sorted(int(k) for k in данные['before']),
                         sorted([self.поднимется.id,
                                 self.поднимется_черновик.id,
                                 self.уедет_в_junk.id]))

    def test_revert_без_снимка_это_ошибка(self):
        with self.assertRaises(CommandError):
            self._run(revert=True)

    def test_повторный_apply_идемпотентен(self):
        self._run(apply=True)
        вывод = self._run(apply=True)
        self.assertIn('Менять нечего', вывод)

    def test_исчезнувшие_из_банка_задачи_названы_а_не_проглочены(self):
        pid = self.уедет_в_junk.id
        Problem.objects.filter(pk=pid).delete()
        вывод = self._run()
        self.assertIn('В банке нет 1 задач', вывод)
        self.assertIn(str(pid), вывод)
