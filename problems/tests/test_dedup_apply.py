# -*- coding: utf-8 -*-
"""Проверки правил дедупа и обратимости команды `dedup_apply`.

Что здесь сторожится:

* рёбра `content_hash` рассыпаются гейтом по подпунктам (старая ложная
  группа из 30 тестовых заданий с общей шапкой);
* косинусное ребро не проходит без числового гейта (пара 51615/51609);
* связные компоненты собирают группы из ТРЁХ и более задач, а не только пары;
* выбор фаворита по каждой ветке правила, включая обе ветки «на глаз»;
* команда без `--apply` не пишет ни строки, а `--revert --apply` возвращает
  базу ровно в прежнее состояние;
* команда не трогает `status`, `duplicate_of`, `hidden_pending_review`.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from problems.dedup import (
    build_groups, choose_best, completeness_score, cosine_edge_passes,
    group_id, hash_edges, is_confident,
)
from problems.management.commands.dedup_apply import protected_digest
from problems.models import DupMark, Problem, ProblemFigure, ProblemPart, Tag, Topic
from problems.tests.factories import make_problem, make_topic


def член(pid, approved=False, parts=0, solution='', figures=0, tags=0,
         topics=0, content_format='plain'):
    """Словарь-задача для правил выбора: ровно те поля, что читает логика."""
    return {'id': pid, 'approved': approved, 'parts': parts,
            'solution': solution, 'figures': figures, 'tags': tags,
            'topics': topics, 'content_format': content_format}


class РёбраПоХешу(TestCase):
    def test_одинаковый_хеш_без_подпунктов_даёт_ребро(self):
        рёбра = hash_edges([(1, 'h', []), (2, 'h', [])])
        self.assertEqual(рёбра, [(1, 2)])

    def test_пустой_хеш_не_считается_совпадением(self):
        # Пустой хеш — это «не считали», а не «одинаковые».
        self.assertEqual(hash_edges([(1, '', []), (2, '', [])]), [])

    def test_ложная_группа_тестовых_заданий_рассыпается(self):
        """Старая ложная группа: общая шапка, разные варианты в подпунктах.

        Ровно этот случай схлопывал `content_hash` в одну группу из 30.
        Гейт по подпунктам обязан развести их поимённо.
        """
        строки = [(i, 'общая_шапка', [('вариант %d' % i, 'ответ %d' % i)])
                  for i in range(1, 31)]
        self.assertEqual(hash_edges(строки), [])

    def test_совпали_и_шапка_и_подпункты_ребро_есть(self):
        строки = [(1, 'h', [('а', '1')]), (2, 'h', [('а', '1')]),
                  (3, 'h', [('б', '2')])]
        self.assertEqual(hash_edges(строки), [(1, 2)])

    def test_метка_подпункта_в_отпечаток_не_входит(self):
        # Метки не уникальны и у источников расставлены по-разному;
        # различать задачи должно содержимое, а не буква пункта.
        строки = [(1, 'h', [('текст', 'ответ')]), (2, 'h', [('текст', 'ответ')])]
        self.assertEqual(hash_edges(строки), [(1, 2)])

    def test_разное_число_подпунктов_не_ребро(self):
        строки = [(1, 'h', [('а', '1')]),
                  (2, 'h', [('а', '1'), ('б', '2')])]
        self.assertEqual(hash_edges(строки), [])


class РёбраПоКосинусу(TestCase):
    ТЕКСТ_A = ('На рынке действуют три группы покупателей и четыре группы '
               'продавцов. Спрос каждой группы задан функцией Q = 100 - 2P. '
               'Найдите равновесие.')
    # Тот же сюжет, ДРУГИЕ параметры — это разные задачи, а не дубль.
    ТЕКСТ_B = ('На рынке действуют две группы покупателей и три группы '
               'продавцов. Спрос каждой группы задан функцией Q = 100 - 2P. '
               'Найдите равновесие.')

    def test_пара_51615_51609_не_проходит_числовой_гейт(self):
        """Регрессия: высокий косинус v1 (0,9885) НЕ должен давать ребро.

        Числа в условиях разные — «четыре» против «трёх» дают разные
        множества чисел, как только они записаны цифрами. В банке эти два
        конкретных условия расходятся ещё и цифрами данных.
        """
        a = self.ТЕКСТ_A + ' Издержки равны 3 и 4.'
        b = self.ТЕКСТ_B + ' Издержки равны 2 и 3.'
        self.assertFalse(cosine_edge_passes(0.9885, a, b))

    def test_низкий_косинус_не_проходит(self):
        self.assertFalse(cosine_edge_passes(0.97, 'Q = 100 - 2P',
                                            'Q = 100 - 2P'))

    def test_совпавший_текст_проходит(self):
        self.assertTrue(cosine_edge_passes(0.99, self.ТЕКСТ_A, self.ТЕКСТ_A))

    def test_текстовый_гейт_отсекает_разные_тексты(self):
        """Единственный сторож здесь — символьная близость.

        Числа у обеих задач ОДНИ И ТЕ ЖЕ (одно число 10), так что числовой
        гейт пару пропускает, косинус высокий. Отказать обязан текстовый
        гейт — тексты про разное. Если убрать его, пара пройдёт.
        """
        общее = 'Цена товара равна 10. '
        a = общее + ('Постройте кривую спроса и определите эластичность '
                     'спроса по цене в точке равновесия рынка. ' * 4)
        b = общее + ('Объясните сравнительные преимущества стран во внешней '
                     'торговле и выигрыш от специализации. ' * 4)
        # Числовой гейт эту пару пропускает — сторожим именно это.
        from problems.dedup_gates import compare_numbers
        self.assertEqual(compare_numbers(a, b), 'совпадают')
        self.assertFalse(cosine_edge_passes(0.99, a, b))


class СвязныеКомпоненты(TestCase):
    def test_группа_из_трёх_собирается_из_двух_рёбер(self):
        группы = build_groups([(1, 2), (2, 3)])
        self.assertEqual(list(группы.values()), [[1, 2, 3]])

    def test_цепочка_склеивает_пять_задач_в_одну_группу(self):
        группы = build_groups([(5, 4), (4, 3), (3, 2), (2, 1)])
        self.assertEqual(list(группы.values()), [[1, 2, 3, 4, 5]])

    def test_две_несвязанные_группы_не_склеиваются(self):
        группы = build_groups([(1, 2), (10, 11)])
        self.assertEqual(sorted(группы.values()), [[1, 2], [10, 11]])

    def test_идентификатор_группы_устойчив_к_порядку(self):
        self.assertEqual(group_id([3, 1, 2]), group_id([1, 2, 3]))

    def test_повторный_прогон_даёт_те_же_идентификаторы(self):
        self.assertEqual(build_groups([(1, 2), (2, 3)]).keys(),
                         build_groups([(3, 2), (2, 1)]).keys())


class БаллПолноты(TestCase):
    def test_пустая_задача_ноль(self):
        self.assertEqual(completeness_score(член(1)), 0)

    def test_все_шесть_признаков(self):
        полная = член(1, parts=2, solution='решение', figures=1, tags=3,
                      topics=1, content_format='markdown')
        self.assertEqual(completeness_score(полная), 6)

    def test_пробельное_решение_баллом_не_считается(self):
        self.assertEqual(completeness_score(член(1, solution='   \n ')), 0)


class ВыборФаворита(TestCase):
    def test_одна_approved_забирает_группу(self):
        правило, лучший = choose_best([
            член(1, approved=True), член(2, parts=3, solution='есть'),
        ])
        self.assertEqual(правило, DupMark.Rule.APPROVED)
        self.assertEqual(лучший, 1)
        self.assertTrue(is_confident(правило))

    def test_approved_без_картинки_при_двойнике_с_картинкой_на_разбор(self):
        правило, лучший = choose_best([
            член(1, approved=True, figures=0), член(2, figures=2),
        ])
        self.assertEqual(правило, DupMark.Rule.APPROVED_PICTURE_REVIEW)
        self.assertIsNone(лучший)
        self.assertFalse(is_confident(правило))

    def test_approved_с_картинкой_правило_картинки_не_включает(self):
        правило, лучший = choose_best([
            член(1, approved=True, figures=1), член(2, figures=3),
        ])
        self.assertEqual(правило, DupMark.Rule.APPROVED)
        self.assertEqual(лучший, 1)

    def test_две_approved_всегда_на_разбор(self):
        правило, лучший = choose_best([
            член(1, approved=True, parts=5, solution='есть', figures=1,
                 tags=2, topics=1, content_format='markdown'),
            член(2, approved=True),
        ])
        self.assertEqual(правило, DupMark.Rule.NEEDS_REVIEW_MULTI_APPROVED)
        self.assertIsNone(лучший)

    def test_две_approved_сильнее_правила_картинки(self):
        правило, _ = choose_best([
            член(1, approved=True, figures=0), член(2, approved=True),
            член(3, figures=4),
        ])
        self.assertEqual(правило, DupMark.Rule.NEEDS_REVIEW_MULTI_APPROVED)

    def test_без_approved_отрыв_в_два_балла_даёт_фаворита(self):
        правило, лучший = choose_best([
            член(1, parts=1, solution='есть'),   # 2
            член(2),                             # 0
        ])
        self.assertEqual(правило, DupMark.Rule.COMPLETENESS_MARGIN)
        self.assertEqual(лучший, 1)

    def test_отрыв_в_один_балл_фаворита_не_даёт(self):
        правило, лучший = choose_best([
            член(1, solution='есть'),  # 1
            член(2),                   # 0
        ])
        self.assertEqual(правило, DupMark.Rule.NEEDS_REVIEW_TIE)
        self.assertIsNone(лучший)

    def test_ничья_на_вершине_фаворита_не_даёт(self):
        правило, лучший = choose_best([
            член(1, parts=1, solution='есть'),
            член(2, parts=1, solution='есть'),
            член(3),
        ])
        self.assertEqual(правило, DupMark.Rule.NEEDS_REVIEW_TIE)
        self.assertIsNone(лучший)

    def test_победителя_по_меньшему_id_не_назначаем(self):
        """Ровно тот дефект, которым был плох `process_duplicates`."""
        правило, лучший = choose_best([член(7), член(9)])
        self.assertIsNone(лучший)
        self.assertEqual(правило, DupMark.Rule.NEEDS_REVIEW_TIE)


class КомандаОбратима(TestCase):
    """Проба ничего не пишет, применение обратимо, Problem не тронут."""

    def setUp(self):
        тема = make_topic('Микроэкономика')
        тег = Tag.objects.create(name='равновесие', slug='ravnovesie')
        # Две задачи с одинаковым условием и одинаковыми подпунктами.
        self.бедная = make_problem(statement='Найдите равновесие: Q = 100 - 2P.',
                                   content_hash='одинаковый')
        self.полная = make_problem(statement='Найдите равновесие: Q = 100 - 2P.',
                                   content_hash='одинаковый',
                                   solution='P = 25, Q = 50.',
                                   content_format='markdown', topic=тема)
        self.полная.tags.add(тег)
        for задача in (self.бедная, self.полная):
            ProblemPart.objects.create(problem=задача, label='а',
                                       statement='пункт', answer='ответ',
                                       order=1)

    def прогон(self, *флаги):
        out = StringIO()
        call_command('dedup_apply', *флаги, stdout=out)
        return out.getvalue()

    def test_без_apply_база_не_тронута(self):
        вывод = self.прогон()
        self.assertIn('СТОП-ГЕЙТ', вывод)
        self.assertEqual(DupMark.objects.count(), 0)

    def test_apply_ставит_пометки_revert_снимает(self):
        до = protected_digest()
        self.прогон('--apply')
        self.assertEqual(DupMark.objects.count(), 2)
        фаворит = DupMark.objects.get(is_best=True)
        self.assertEqual(фаворит.problem_id, self.полная.id)
        self.assertEqual(фаворит.rule, DupMark.Rule.COMPLETENESS_MARGIN)

        self.прогон('--revert', '--apply')
        self.assertEqual(DupMark.objects.count(), 0)
        self.assertEqual(protected_digest(), до)

    def test_revert_без_apply_ничего_не_удаляет(self):
        self.прогон('--apply')
        вывод = self.прогон('--revert')
        self.assertIn('проба', вывод)
        self.assertEqual(DupMark.objects.count(), 2)

    def test_повторный_apply_идемпотентен(self):
        self.прогон('--apply')
        первый = sorted(DupMark.objects.values_list('problem_id', 'group',
                                                    'is_best', 'rule'))
        self.прогон('--apply')
        второй = sorted(DupMark.objects.values_list('problem_id', 'group',
                                                    'is_best', 'rule'))
        self.assertEqual(первый, второй)

    def test_защищённые_поля_не_меняются_при_применении(self):
        до = protected_digest()
        self.прогон('--apply')
        self.assertEqual(protected_digest(), до)
        self.assertEqual(
            list(Problem.objects.order_by('id')
                 .values_list('status', 'duplicate_of_id',
                              'hidden_pending_review')),
            [('published', None, False), ('published', None, False)])

    def test_группа_на_разбор_не_получает_фаворита(self):
        """Две approved в группе — пометки есть, фаворита нет ни у кого."""
        Problem.objects.update(human_review=Problem.HumanReview.APPROVED)
        self.прогон('--apply')
        self.assertEqual(DupMark.objects.count(), 2)
        self.assertEqual(DupMark.objects.filter(is_best=True).count(), 0)
        self.assertEqual(DupMark.objects.first().rule,
                         DupMark.Rule.NEEDS_REVIEW_MULTI_APPROVED)

    def test_правило_картинки_на_живых_объектах(self):
        """approved без фигуры, у двойника фигура — группа уходит на разбор."""
        self.полная.human_review = Problem.HumanReview.APPROVED
        self.полная.save(update_fields=['human_review'])
        ProblemFigure.objects.create(problem=self.бедная,
                                     source_field='statement')
        self.прогон('--apply')
        self.assertEqual(DupMark.objects.filter(is_best=True).count(), 0)
        self.assertEqual(DupMark.objects.first().rule,
                         DupMark.Rule.APPROVED_PICTURE_REVIEW)

    def test_правка_problem_во_время_записи_откатывает_всё(self):
        """Сторож защищённых полей не докладывает, а ОТМЕНЯЕТ запись.

        Подсовываем команде запись в `Problem.status` ВНУТРИ её транзакции —
        так выглядела бы правка, случайно добавленная в будущем. Ожидаем
        ошибку И чистую базу: ни пометок, ни изменённого статуса.

        ⚠️ Граница сторожа: он откатывает то, что сделано внутри транзакции
        записи. Правку, УЖЕ ЗАКРЕПЛЁННУЮ до неё, он заметит и назовёт, но
        отменить не сможет — для этого у команды и нет ни одного пути записи
        в `Problem`.
        """
        from django.core.management.base import CommandError
        from django.db import transaction

        from problems.management.commands import dedup_apply as модуль

        настоящий = модуль.Command._write_marks

        def порченый(сам, решения, отпечаток_до):
            with transaction.atomic():
                Problem.objects.all().update(status=Problem.Status.HIDDEN)
                return настоящий(сам, решения, отпечаток_до)

        модуль.Command._write_marks = порченый
        try:
            with self.assertRaises(CommandError):
                self.прогон('--apply')
        finally:
            модуль.Command._write_marks = настоящий

        self.assertEqual(DupMark.objects.count(), 0)
        self.assertEqual(
            set(Problem.objects.values_list('status', flat=True)),
            {'published'})

    def test_одиночная_задача_в_группы_не_попадает(self):
        make_problem(statement='Одинокая задача.', content_hash='своё')
        self.прогон('--apply')
        self.assertEqual(DupMark.objects.count(), 2)


class ТемыИТегиСчитаются(TestCase):
    """Балл полноты обязан видеть темы и теги через M2M, а не через поле."""

    def test_тема_и_тег_поднимают_балл(self):
        from problems.management.commands.dedup_apply import Command
        тема = Topic.objects.create(name='Макро', slug='makro')
        тег = Tag.objects.create(name='ввп', slug='vvp')
        задача = make_problem(statement='Текст.', content_hash='x')
        задача.topics.add(тема)
        задача.tags.add(тег)
        признаки = Command()._members([задача.id])
        self.assertEqual(признаки[задача.id]['topics'], 1)
        self.assertEqual(признаки[задача.id]['tags'], 1)
        self.assertEqual(completeness_score(признаки[задача.id]), 2)
