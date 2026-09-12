# -*- coding: utf-8 -*-
"""Проверки инструмента ручной разметки групп копий.

Что здесь сторожится:

* выборка стратифицирована и повторяема по `--seed`;
* страница СЛЕПАЯ: ни правила алгоритма, ни его фаворита, ни `human_review`
  на ней нет — иначе мера «алгоритм против владельца» меряла бы согласие
  человека с подсказкой, а не его собственный выбор;
* картинка приезжает на страницу вшитой (`data:`), иначе на file:// её
  не видно вовсе;
* приёмщик не пускает фаворита из чужой группы и неизвестный вердикт;
* приёмщик без `--apply` не пишет ни строки, `--revert` снимает ровно
  свои группы;
* ни команда разметки, ни приёмщик не трогают `Problem` и `DupMark`.
"""
import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from problems.dedup import REASON_TAGS
from problems.management.commands import dedup_human_review_html as tool
from problems.models import (DupHumanChoice, DupMark, Problem, ProblemFigure,
                             ProblemPart)
from problems.tests.factories import make_problem


def пометить(problem, group, rule, is_best=False):
    return DupMark.objects.create(problem=problem, group=group, rule=rule,
                                  is_best=is_best)


def группа(имя, rule, размер=2, approved_первый=False):
    задачи = []
    for номер in range(размер):
        задача = make_problem(
            statement='Условие версии %d группы %s.' % (номер, имя),
            title='Заголовок %s-%d' % (имя, номер),
            human_review='approved' if (approved_первый and номер == 0) else '')
        пометить(задача, имя, rule, is_best=(номер == 0))
        задачи.append(задача)
    return задачи


class Выборка(TestCase):
    def test_слой_считается_по_правилу_и_размеру(self):
        self.assertEqual(
            tool._stratum_of(DupMark.Rule.APPROVED, 2), 'confident')
        self.assertEqual(
            tool._stratum_of(DupMark.Rule.COMPLETENESS_MARGIN, 2), 'confident')
        self.assertEqual(
            tool._stratum_of(DupMark.Rule.NEEDS_REVIEW_TIE, 2), 'needs_review')
        self.assertEqual(
            tool._stratum_of(DupMark.Rule.APPROVED, 3), 'multi')

    def test_правило_картинки_забирает_группу_себе_даже_из_трёх(self):
        # Специфичное правило важнее общего признака «версий больше двух»:
        # иначе слой картинки не набрался бы вовсе.
        self.assertEqual(
            tool._stratum_of(DupMark.Rule.APPROVED_PICTURE_REVIEW, 4),
            'picture_rule')

    def test_тот_же_seed_даёт_ту_же_выборку(self):
        группы = {'g%02d' % i: {'rule': DupMark.Rule.NEEDS_REVIEW_TIE,
                                'ids': [i, 100 + i]} for i in range(40)}
        первая = tool.sample_groups(группы, 10, 7)
        вторая = tool.sample_groups(группы, 10, 7)
        self.assertEqual(первая, вторая)
        self.assertNotEqual(первая, tool.sample_groups(группы, 10, 8))

    def test_недобор_слоя_переливается_дальше(self):
        """Пустой слой не должен молча уменьшать объём разметки."""
        группы = {'g%02d' % i: {'rule': DupMark.Rule.NEEDS_REVIEW_TIE,
                                'ids': [i, 100 + i]} for i in range(60)}
        # Уверенных, картиночных, ответных и тройных групп нет вовсе —
        # весь объём обязан взяться из единственного непустого слоя.
        self.assertEqual(len(tool.sample_groups(группы, 30, 1)), 30)

    def test_выборка_не_просит_больше_чем_есть(self):
        группы = {'g1': {'rule': DupMark.Rule.NEEDS_REVIEW_TIE, 'ids': [1, 2]}}
        self.assertEqual(tool.sample_groups(группы, 50, 1), ['g1'])


class Карточки(TestCase):
    def test_группа_без_пары_на_страницу_не_идёт(self):
        задачи = группа('g-одна', DupMark.Rule.NEEDS_REVIEW_TIE)
        задачи[1].delete()
        карточки = tool.build_cards(['g-одна'], tool.collect_groups(),
                                    __import__('random').Random(1))
        self.assertEqual(карточки, [])

    def test_картинка_вшита_в_страницу_как_data(self):
        задачи = группа('g-рис', DupMark.Rule.NEEDS_REVIEW_TIE)
        хеш = 'a' * 64
        задачи[0].statement = 'Смотри график [[FIGURE:%s]] и решай.' % хеш
        задачи[0].save(update_fields=['statement'])
        ProblemFigure.objects.create(problem=задачи[0], tikz_hash=хеш,
                                     tikz_source=r'\draw (0,0);',
                                     svg='<svg xmlns="http://www.w3.org/2000/svg"/>')
        карточки = tool.build_cards(['g-рис'], tool.collect_groups(),
                                    __import__('random').Random(1))
        страница = tool.build_page(карточки, 1)
        self.assertIn('data:image/svg+xml;base64,', страница)
        self.assertNotIn('[[FIGURE:', страница)

    def test_чужой_маркер_не_разрешается(self):
        """Свойство безопасности problems/figures.py сохранено: картинка
        ищется только среди картинок ЭТОЙ задачи."""
        задачи = группа('g-чужой', DupMark.Rule.NEEDS_REVIEW_TIE)
        хеш = 'b' * 64
        ProblemFigure.objects.create(problem=задачи[1], tikz_hash=хеш,
                                     tikz_source='x', svg='<svg/>')
        html = tool.render_field('Текст [[FIGURE:%s]] дальше' % хеш, {})
        self.assertNotIn('<img', html)
        self.assertNotIn('[[FIGURE:', html)

    def test_подпункты_попадают_на_страницу(self):
        задачи = группа('g-часть', DupMark.Rule.NEEDS_REVIEW_TIE)
        ProblemPart.objects.create(problem=задачи[0], order=1, label='а',
                                   statement='Найдите равновесие.',
                                   answer='Q = 5')
        карточки = tool.build_cards(['g-часть'], tool.collect_groups(),
                                    __import__('random').Random(1))
        страница = tool.build_page(карточки, 1)
        self.assertIn('Найдите равновесие', страница)
        self.assertIn('Q = 5', страница)


class СлепаяРазметка(TestCase):
    """Главное свойство инструмента: подсказок алгоритма на странице нет."""

    def setUp(self):
        группа('g-слеп', DupMark.Rule.APPROVED, размер=2, approved_первый=True)
        карточки = tool.build_cards(['g-слеп'], tool.collect_groups(),
                                    __import__('random').Random(3))
        self.страница = tool.build_page(карточки, 3)

    def test_правило_алгоритма_не_показано(self):
        for rule, _label in DupMark.Rule.choices:
            self.assertNotIn(rule, self.страница)

    def test_слово_approved_на_странице_не_встречается(self):
        self.assertNotIn('approved', self.страница)

    def test_фаворит_алгоритма_не_подсвечен(self):
        # `qls-picked` в CSS и в скрипте — это подсветка выбора ЧЕЛОВЕКА,
        # она появляется по клику. В разметке версий её быть не должно.
        self.assertNotIn('is_best', self.страница)
        self.assertNotIn('class="qls-v qls-picked"', self.страница)
        self.assertNotIn('qls-picked"', self.страница.split('</style>')[-1]
                         .split('<script>')[0])

    def test_причины_разметки_берутся_из_единственного_списка(self):
        for _key, label in REASON_TAGS:
            self.assertIn(label, self.страница)


class Приёмщик(TestCase):
    def setUp(self):
        self.задачи = группа('g-приём', DupMark.Rule.NEEDS_REVIEW_TIE)
        self.чужая = make_problem(statement='Совсем другая задача.')

    def файл(self, rows):
        handle = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False,
                                             encoding='utf-8')
        json.dump({'seed': '1', 'rows': rows}, handle, ensure_ascii=False)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def запустить(self, rows, **флаги):
        out = StringIO()
        call_command('import_dup_human_choices', self.файл(rows),
                     stdout=out, **флаги)
        return out.getvalue()

    def test_без_apply_не_пишет_ни_строки(self):
        вывод = self.запустить([{'group': 'g-приём', 'verdict': 'chosen',
                                 'chosen_problem_id': self.задачи[0].pk,
                                 'reason_tags': [], 'note': ''}])
        self.assertEqual(DupHumanChoice.objects.count(), 0)
        self.assertIn('план', вывод.lower())

    def test_apply_записывает_выбор(self):
        self.запустить([{'group': 'g-приём', 'verdict': 'chosen',
                         'chosen_problem_id': self.задачи[1].pk,
                         'reason_tags': ['has_answer'], 'note': 'ответ живой'}],
                       apply=True)
        строка = DupHumanChoice.objects.get(group='g-приём')
        self.assertEqual(строка.chosen_problem_id, self.задачи[1].pk)
        self.assertEqual(строка.reason_tags, 'has_answer')
        self.assertEqual(строка.note, 'ответ живой')

    def test_фаворит_из_чужой_группы_отклонён(self):
        вывод = self.запустить([{'group': 'g-приём', 'verdict': 'chosen',
                                 'chosen_problem_id': self.чужая.pk,
                                 'reason_tags': [], 'note': ''}],
                               apply=True)
        self.assertEqual(DupHumanChoice.objects.count(), 0)
        self.assertIn('не входит в эту группу', вывод)

    def test_неизвестный_вердикт_отклонён(self):
        вывод = self.запустить([{'group': 'g-приём', 'verdict': 'наверное',
                                 'chosen_problem_id': None,
                                 'reason_tags': [], 'note': ''}], apply=True)
        self.assertEqual(DupHumanChoice.objects.count(), 0)
        self.assertIn('неизвестный вердикт', вывод)

    def test_причина_вне_списка_отброшена_а_строка_сохранена(self):
        self.запустить([{'group': 'g-приём', 'verdict': 'cannot_decide',
                         'chosen_problem_id': None,
                         'reason_tags': ['has_answer', 'выдумка'], 'note': ''}],
                       apply=True)
        строка = DupHumanChoice.objects.get(group='g-приём')
        self.assertEqual(строка.reason_tags, 'has_answer')
        self.assertIsNone(строка.chosen_problem_id)

    def test_не_дубли_сохраняются_без_фаворита(self):
        self.запустить([{'group': 'g-приём', 'verdict': 'not_duplicates',
                         'chosen_problem_id': self.задачи[0].pk,
                         'reason_tags': [], 'note': ''}], apply=True)
        строка = DupHumanChoice.objects.get(group='g-приём')
        self.assertIsNone(строка.chosen_problem_id)

    def test_повторная_разметка_перезаписывает_прежнюю(self):
        строки = [{'group': 'g-приём', 'verdict': 'chosen',
                   'chosen_problem_id': self.задачи[0].pk,
                   'reason_tags': [], 'note': ''}]
        self.запустить(строки, apply=True)
        строки[0]['chosen_problem_id'] = self.задачи[1].pk
        self.запустить(строки, apply=True)
        self.assertEqual(DupHumanChoice.objects.count(), 1)
        self.assertEqual(DupHumanChoice.objects.get().chosen_problem_id,
                         self.задачи[1].pk)

    def test_revert_снимает_только_свои_группы(self):
        группа('g-чужая', DupMark.Rule.NEEDS_REVIEW_TIE)
        DupHumanChoice.objects.create(group='g-чужая', verdict='cannot_decide',
                                      labeled_at='2026-09-12T00:00:00Z')
        self.запустить([{'group': 'g-приём', 'verdict': 'cannot_decide',
                         'chosen_problem_id': None,
                         'reason_tags': [], 'note': ''}], apply=True)
        self.assertEqual(DupHumanChoice.objects.count(), 2)
        self.запустить([{'group': 'g-приём', 'verdict': 'cannot_decide',
                         'chosen_problem_id': None,
                         'reason_tags': [], 'note': ''}], revert=True)
        self.assertEqual(
            list(DupHumanChoice.objects.values_list('group', flat=True)),
            ['g-чужая'])


class НичегоНеТрогаем(TestCase):
    """Разметка человека живёт РЯДОМ с алгоритмической, а не поверх неё."""

    def test_ни_problem_ни_dupmark_не_изменились(self):
        задачи = группа('g-цел', DupMark.Rule.APPROVED, approved_первый=True)
        снимок_задач = list(Problem.objects.order_by('pk')
                            .values('pk', 'status', 'human_review',
                                    'hidden_pending_review', 'duplicate_of'))
        снимок_меток = list(DupMark.objects.order_by('pk')
                            .values('problem_id', 'group', 'is_best', 'rule'))

        handle = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False,
                                             encoding='utf-8')
        json.dump({'rows': [{'group': 'g-цел', 'verdict': 'chosen',
                             'chosen_problem_id': задачи[1].pk,
                             'reason_tags': [], 'note': ''}]}, handle)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        call_command('import_dup_human_choices', handle.name, apply=True,
                     stdout=StringIO())

        with tempfile.TemporaryDirectory() as каталог:
            call_command('dedup_human_review_html', count=5, seed=1,
                         output=os.path.join(каталог, 'p.html'),
                         stdout=StringIO())

        self.assertEqual(снимок_задач,
                         list(Problem.objects.order_by('pk')
                              .values('pk', 'status', 'human_review',
                                      'hidden_pending_review', 'duplicate_of')))
        self.assertEqual(снимок_меток,
                         list(DupMark.objects.order_by('pk')
                              .values('problem_id', 'group', 'is_best', 'rule')))
