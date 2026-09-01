# -*- coding: utf-8 -*-
"""Объединённый каталог: то, что легко сломать молча.

Экран `/catalog/` вобрал в себя «Умный поиск» (решение владельца
01.09.2026). Проверки ниже стерегут не вид, а ПОВЕДЕНИЕ — семь мест, где
поломка не покажет себя ни ошибкой, ни пустой страницей:

    1. старый адрес поиска ведёт в каталог и не теряет запрос;
    2. пустой запрос НЕ трогает смысловой поиск (иначе каждый, кто просто
       зашёл посмотреть банк, платит семь секунд загрузки модели);
    3. чисто числовой запрос ведёт на задачу, а не в смысловой поиск;
    4. недоступный смысловой поиск — это 200 и результаты по словам;
    5. фильтр без данных в разметке отсутствует;
    6. каталог и экран домашки показывают ОДИН набор фильтров;
    7. счётчик при запросе называет оба числа.

⚠️ ЦВЕТА И РАЗМЕРЫ ЗДЕСЬ НЕ ПРОВЕРЯЮТСЯ НАРОЧНО. Прошлые сессии дважды
ловили проверки, которые назывались по свойству, а сторожили литерал:
одна из них прошла бы и при сломанном свойстве. Проверяем отношения —
«набор совпадает», «числа два», «группы нет», — а не значения.
"""
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from problems.management.commands.apply_topic_mapping import CANONICAL
from problems.models import Problem
from problems.tests.factories import (
    link_source, make_problem, make_source, make_topic, make_user,
)


class _База(TestCase):
    """Небольшой, но РАЗНООБРАЗНЫЙ корпус.

    Разнообразие тут не украшение: половина проверок про то, показана
    группа фильтра или спрятана, и на одинаковых задачах они были бы
    зелёными при любом поведении.
    """

    @classmethod
    def setUpTestData(cls):
        cls.тема = make_topic(CANONICAL[7])          # «Монополия…»
        cls.источник = make_source('Тестовый сборник')
        # ⚠️ ТЕГ ЗАВОДИТСЯ НАРОЧНО, И БЕЗ НЕГО НАБОР ПРОВЕРОК ТУПОЙ.
        # Первая версия этого файла обходилась без тегов — и проверка
        # «наборы фильтров совпадают» НЕ ПОКРАСНЕЛА, когда фильтр тега
        # убрали из каталога: тегов в базе не было, группа пряталась на
        # обоих экранах, и множества сходились на отсутствии. Поймано
        # подкладыванием дефекта, а не чтением кода.
        from problems.models import Tag
        cls.тег = Tag.objects.create(name='монополия', slug='monopoliya')
        cls.задача = make_problem(
            statement='Монополист максимизирует прибыль при линейном спросе.',
            topic=cls.тема, difficulty=3, solution='Решение есть.',
            solution_needs_review=False)
        link_source(cls.задача, cls.источник)
        cls.задача.tags.add(cls.тег)
        cls.тест = make_problem(
            statement='Эластичность спроса по цене равна единице.',
            difficulty=1, problem_type='тест: один ответ')
        cls.без_темы = make_problem(
            statement='Совокупный спрос и совокупное предложение в модели.')
        # Скрытая задача: она не должна попадать никуда — ни в выдачу, ни в
        # ответ «есть такой номер».
        cls.скрытая = make_problem(statement='Скрытая от каталога задача.',
                                   hidden_pending_review=True)


# ═════════════════════════════════════════════════════════════════════════
# 1. Старый адрес умного поиска
# ═════════════════════════════════════════════════════════════════════════
class OldSearchAddressTests(_База):

    def test_редирект_постоянный_и_ведёт_в_каталог(self):
        ответ = self.client.get(reverse('catalog:smart_search'))
        self.assertEqual(ответ.status_code, 301)
        self.assertEqual(ответ['Location'], reverse('catalog:problem_list'))

    def test_запрос_переносится_вместе_с_человеком(self):
        """Пришедший по своей же старой ссылке обязан увидеть результат.

        Потерять `?q=` здесь — самая тихая из возможных поломок: адрес
        отвечает, страница открывается, просто человек оказывается в
        пустом каталоге вместо своей выдачи.
        """
        ответ = self.client.get(reverse('catalog:smart_search'),
                                {'q': 'монополия'})
        self.assertEqual(ответ.status_code, 301)
        self.assertIn('q=', ответ['Location'])
        self.assertIn(reverse('catalog:problem_list'), ответ['Location'])


# ═════════════════════════════════════════════════════════════════════════
# 2. Пустой запрос не трогает смысловой поиск
# ═════════════════════════════════════════════════════════════════════════
class EmptyQueryCostsNothingTests(_База):
    """⚠️ САМАЯ ВАЖНАЯ ПРОВЕРКА ФАЙЛА.

    Модель грузится лениво и первый раз занимает около семи секунд. Пока
    поиск жил отдельной страницей, это была плата за вход ИМЕННО НА НЕЁ.
    Теперь каталог — главный вход, и стоит один раз вызвать поиск при
    пустом запросе, как эти секунды достанутся каждому, кто просто зашёл
    посмотреть банк. Сломать это можно одной строкой, и ни один экран
    не покажет, что что-то не так, — он просто будет медленным.
    """

    def test_без_запроса_поиск_не_вызывается_вовсе(self):
        with mock.patch('catalog.semantic.search') as смысловой, \
                mock.patch('catalog.hybrid.lexical_search') as словами:
            ответ = self.client.get(reverse('catalog:problem_list'))
        self.assertEqual(ответ.status_code, 200)
        self.assertFalse(смысловой.called,
                         'Пустой запрос пошёл в смысловой поиск: каждый, кто '
                         'просто открыл каталог, платит загрузку модели.')
        self.assertFalse(словами.called)

    def test_с_фильтром_но_без_запроса_поиск_тоже_не_вызывается(self):
        """Фильтр — это не запрос. Выбор темы не повод будить модель."""
        with mock.patch('catalog.semantic.search') as смысловой:
            ответ = self.client.get(reverse('catalog:problem_list'),
                                    {'topic': str(self.тема.pk)})
        self.assertEqual(ответ.status_code, 200)
        self.assertFalse(смысловой.called)

    def test_с_запросом_поиск_всё_таки_вызывается(self):
        """Обратная сторона: иначе проверка выше зеленела бы на сломанном."""
        with mock.patch('catalog.semantic.search', return_value=[]) as поиск:
            self.client.get(reverse('catalog:problem_list'),
                            {'q': 'монополия'})
        self.assertTrue(поиск.called)


# ═════════════════════════════════════════════════════════════════════════
# 3. Числовой запрос — это номер задачи
# ═════════════════════════════════════════════════════════════════════════
class NumericQueryTests(_База):

    def test_число_ведёт_прямо_на_задачу(self):
        ответ = self.client.get(reverse('catalog:problem_list'),
                                {'q': str(self.задача.pk)})
        self.assertEqual(ответ.status_code, 302)
        self.assertEqual(ответ['Location'],
                         reverse('catalog:problem_detail',
                                 args=[self.задача.pk]))

    def test_число_не_идёт_в_смысловой_поиск(self):
        """У числа нет смысла, который можно с чем-то сравнить."""
        with mock.patch('catalog.semantic.search') as поиск:
            self.client.get(reverse('catalog:problem_list'),
                            {'q': str(self.задача.pk)})
        self.assertFalse(поиск.called)

    def test_несуществующий_номер_объясняется_словами(self):
        ответ = self.client.get(reverse('catalog:problem_list'),
                                {'q': '99999999'})
        self.assertEqual(ответ.status_code, 200)
        self.assertEqual(ответ.context['missing_id'], '99999999')
        self.assertIn('99999999', ответ.content.decode())

    def test_скрытая_задача_не_подтверждается_номером(self):
        """⚠️ Ответ «есть такой номер» не должен быть оглавлением скрытого."""
        ответ = self.client.get(reverse('catalog:problem_list'),
                                {'q': str(self.скрытая.pk)})
        self.assertEqual(ответ.status_code, 200)
        self.assertEqual(ответ.context['missing_id'], str(self.скрытая.pk))


# ═════════════════════════════════════════════════════════════════════════
# 4. Недоступный смысловой поиск — деградация, а не отказ
# ═════════════════════════════════════════════════════════════════════════
@override_settings(SEMANTIC_SEARCH_ENABLED=False)
class DegradationTests(_База):

    def test_страница_отвечает_200_и_находит_словами(self):
        ответ = self.client.get(reverse('catalog:problem_list'),
                                {'q': 'монополист'})
        self.assertEqual(ответ.status_code, 200)
        self.assertTrue(ответ.context['degraded'])
        найдено = [c['problem'].pk for c in ответ.context['cards']]
        self.assertIn(self.задача.pk, найдено,
                      'Деградация не нашла ничего — это отказ, а не '
                      'деградация.')

    def test_на_экране_нет_нашей_кухни(self):
        ответ = self.client.get(reverse('catalog:problem_list'),
                                {'q': 'монополист'})
        тело = ответ.content.decode()
        self.assertNotIn('Ошибка поиска', тело)
        self.assertNotIn('pip install', тело)
        self.assertNotIn('эмбеддинг', тело.lower())


# ═════════════════════════════════════════════════════════════════════════
# 5. Фильтр без данных в разметке отсутствует
# ═════════════════════════════════════════════════════════════════════════
class EmptyFilterIsHiddenTests(_База):

    def _группы(self, ответ):
        import re
        return set(re.findall(r'data-fl="([a-z_]+)"',
                              ответ.content.decode()))

    def test_неразмеченное_поле_не_показывается(self):
        """«Характер задачи» и «особенности» в базе не размечены вовсе.

        Серый переключатель, который не нажимается, хуже его отсутствия:
        он обещает отбор, которого нет.
        """
        группы = self._группы(self.client.get(reverse('catalog:problem_list')))
        self.assertNotIn('character', группы)
        self.assertNotIn('feature', группы)

    def test_а_размеченное_показывается(self):
        """Обратная сторона: иначе проверка выше зеленела бы на пустом экране."""
        группы = self._группы(self.client.get(reverse('catalog:problem_list')))
        self.assertIn('topic', группы)
        self.assertIn('source', группы)

    def test_фильтр_исчезает_вместе_с_данными(self):
        """Убрали источники у всех задач — группа «Источник» ушла.

        Это ОБЩЕЕ правило компонента, а не заглушка на два поля: как
        только разметка появится, группа включится сама.
        """
        from problems.models import SourceReference

        SourceReference.objects.all().delete()
        группы = self._группы(self.client.get(reverse('catalog:problem_list')))
        self.assertNotIn('source', группы)
        # Тема осталась — исчез именно тот фильтр, у которого не стало данных.
        self.assertIn('topic', группы)


# ═════════════════════════════════════════════════════════════════════════
# 6. Каталог и домашка показывают ОДИН набор фильтров
# ═════════════════════════════════════════════════════════════════════════
class SameFilterSetTests(_База):
    """⚠️ МАШИННАЯ ЗАЩИТА РЕШЕНИЯ ПРО ОБЩИЙ КОМПОНЕНТ.

    Прежде наборы уже разошлись: в каталоге был фильтр «Источник», на
    экране домашки его не было, и заметил это не тест, а человек. Эта
    проверка краснеет, если фильтр добавили в один экран и забыли про
    другой, — независимо от того, как он выглядит.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.репетитор = make_user('репетитор', role='teacher')

    def _группы(self, url, **params):
        import re

        ответ = self.client.get(url, params)
        self.assertEqual(ответ.status_code, 200)
        return set(re.findall(r'data-fl="([a-z_]+)"',
                              ответ.content.decode()))

    def test_наборы_совпадают(self):
        каталог = self._группы(reverse('catalog:problem_list'))
        self.client.force_login(self.репетитор)
        домашка = self._группы(reverse('teacher:work_pick'))
        self.assertEqual(каталог, домашка,
                         'Наборы фильтров разошлись: %s только в каталоге, '
                         '%s только на домашке.'
                         % (sorted(каталог - домашка) or '—',
                            sorted(домашка - каталог) or '—'))

    def test_набор_не_пустой(self):
        """Иначе сравнение выше сошлось бы на двух пустых множествах."""
        self.assertTrue(self._группы(reverse('catalog:problem_list')))


# ═════════════════════════════════════════════════════════════════════════
# 7. Счётчик называет оба числа
# ═════════════════════════════════════════════════════════════════════════
class CounterTests(_База):

    def test_при_запросе_чисел_два(self):
        """«Похожих задач: 18 · из 294 по теме „Монополия“».

        У смыслового поиска нет числа «сколько всего подходит» — есть
        «сколько прошло порог». Второе число говорит, из чего выбирали.
        """
        with mock.patch('catalog.semantic.search',
                        return_value=[{'problem': self.задача, 'score': 0.9}]):
            ответ = self.client.get(reverse('catalog:problem_list'),
                                    {'q': 'монополия',
                                     'topic': str(self.тема.pk)})
        self.assertEqual(ответ.status_code, 200)
        self.assertTrue(ответ.context['searched'])
        # Оба числа есть в контексте и различаются по смыслу: первое —
        # сколько похоже, второе — сколько подходит под фильтры.
        self.assertEqual(ответ.context['total'], 1)
        self.assertEqual(
            ответ.context['filtered_total'],
            Problem.objects.filter(
                topics=self.тема, status=Problem.Status.PUBLISHED,
                needs_quality_review=False,
                hidden_pending_review=False).distinct().count())
        тело = ответ.content.decode()
        self.assertIn('Похожих задач', тело)
        # Подпись второго числа называет ПРИЧИНУ сужения, а не просто число.
        self.assertIn(self.тема.name, тело)

    def test_без_запроса_число_одно(self):
        ответ = self.client.get(reverse('catalog:problem_list'))
        self.assertFalse(ответ.context['searched'])
        self.assertNotIn('Похожих задач', ответ.content.decode())
