# -*- coding: utf-8 -*-
"""`quality_gate --sources`: точечный прогон не трогает чужие источники.

Опасность здесь несимметрична. `--apply` СНАЧАЛА снимает флаг со всех
задач и только потом ставит заново по свежему аудиту. Значит «точечный»
прогон без ограничения области не просто не поможет — он МОЛЧА РАСКРОЕТ
брак во всех остальных источниках. Поэтому большая часть тестов ниже —
про то, что осталось нетронутым.
"""
import io
import os
import shutil
import tempfile
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from problems.models import Problem
from problems.tests.factories import link_source, make_problem, make_source


class GateScopeTests(TestCase):

    def setUp(self):
        self.our = make_source('Наш источник')
        self.other = make_source('Чужой источник')
        # чужая задача, заранее помеченная браком
        self.foreign_flagged = make_problem('Чужая бракованная.', flagged=True)
        link_source(self.foreign_flagged, self.other)
        # чужая чистая задача
        self.foreign_clean = make_problem('Чужая чистая задача про спрос.')
        link_source(self.foreign_clean, self.other)
        # наша задача, заранее помеченная браком
        self.our_flagged = make_problem('Наша бракованная.', flagged=True)
        link_source(self.our_flagged, self.our)

    def run_gate(self, **kwargs):
        out = io.StringIO()
        call_command('quality_gate', stdout=out, **kwargs)
        return out.getvalue()

    def flags(self):
        return dict(Problem.objects.values_list('id', 'needs_quality_review'))

    # ------------------------------------------------------------------
    def test_scoped_apply_does_not_clear_foreign_flag(self):
        """ГЛАВНЫЙ тест: чужой флаг брака переживает точечный прогон."""
        self.run_gate(apply=True, sources=str(self.our.id))
        self.foreign_flagged.refresh_from_db()
        self.assertTrue(self.foreign_flagged.needs_quality_review)

    def test_scoped_apply_does_not_flag_foreign_clean(self):
        self.run_gate(apply=True, sources=str(self.our.id))
        self.foreign_clean.refresh_from_db()
        self.assertFalse(self.foreign_clean.needs_quality_review)

    def test_scoped_apply_recomputes_inside_the_scope(self):
        """Внутри области флаг пересчитывается: чистая задача раскрывается."""
        self.run_gate(apply=True, sources=str(self.our.id))
        self.our_flagged.refresh_from_db()
        self.assertFalse(self.our_flagged.needs_quality_review)

    def test_unscoped_apply_still_touches_everything(self):
        """Поведение без --sources не изменилось — иначе это была бы регрессия."""
        self.run_gate(apply=True)
        self.foreign_flagged.refresh_from_db()
        self.assertFalse(self.foreign_flagged.needs_quality_review)

    def test_scoped_revert_leaves_foreign_flags_alone(self):
        self.run_gate(revert=True, sources=str(self.our.id))
        self.foreign_flagged.refresh_from_db()
        self.our_flagged.refresh_from_db()
        self.assertTrue(self.foreign_flagged.needs_quality_review)
        self.assertFalse(self.our_flagged.needs_quality_review)

    def test_nothing_outside_scope_changes_at_all(self):
        """Побитовая сверка снимка флагов вне области — до и после."""
        before = self.flags()
        scope = {self.our_flagged.id}
        self.run_gate(apply=True, sources=str(self.our.id))
        after = self.flags()
        outside_before = {k: v for k, v in before.items() if k not in scope}
        outside_after = {k: v for k, v in after.items() if k not in scope}
        self.assertEqual(outside_before, outside_after)

    def test_several_sources_can_be_given(self):
        out = self.run_gate(apply=True,
                            sources='%d,%d' % (self.our.id, self.other.id))
        self.assertIn('Область ограничена', out)

    def test_unknown_source_is_refused(self):
        with self.assertRaises(CommandError) as ctx:
            self.run_gate(apply=True, sources='999999')
        self.assertIn('нет таких источников', str(ctx.exception))

    def test_garbage_argument_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_gate(apply=True, sources='четырнадцать')

    def test_false_positive_list_keeps_a_card_visible(self):
        """Карточку из списка ложных срабатываний шлюз не флагует.

        Живой случай: `unpaired_dollar` на суммах в долларах (#26724,
        #29691). Человек посмотрел — это деньги, а не обрывок формулы.

        ⚠️ REPORT_DIR подменяется на временную папку. Без подмены прогон
        набора писал бы тестовые id в БОЕВОЙ список ложных срабатываний —
        ровно та беда, что уже случалась с журналами отката."""
        from problems.management.commands import quality_gate as qg
        # Источнику нужны чистые задачи: у шлюза есть предохранитель «больше
        # 5 % кандидатов — источник пропускаем целиком», и на двух задачах
        # он сработал бы раньше проверяемого правила.
        for i in range(30):
            link_source(make_problem('Чистая задача про спрос номер %d.' % i),
                        self.our)
        bad = make_problem('Цена $2 в виде трансфертов, закрывающего доллара нет.')
        link_source(bad, self.our)
        self.run_gate(apply=True, sources=str(self.our.id))
        bad.refresh_from_db()
        self.assertTrue(bad.needs_quality_review, 'детектор обязан её ловить')

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with open(os.path.join(tmp, 'gate_false_positive_ids.txt'), 'w',
                  encoding='utf-8') as fh:
            fh.write('# тест\n%d\tденьги, а не формула\n' % bad.id)
        with mock.patch.object(qg, 'REPORT_DIR', tmp):
            self.run_gate(apply=True, sources=str(self.our.id))
        bad.refresh_from_db()
        self.assertFalse(bad.needs_quality_review,
                         'из списка ложных срабатываний флаг ставиться не должен')

    def test_empty_sources_means_no_limit(self):
        """Пустая строка — это «без ограничения», а не «ни одной задачи»."""
        out = self.run_gate(apply=True, sources='')
        self.assertNotIn('Область ограничена', out)
