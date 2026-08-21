# -*- coding: utf-8 -*-
"""Деградация смыслового поиска: выключён — но не сломан.

⚠️ ЗАЧЕМ ЭТОТ ФАЙЛ. Модель эмбеддингов весит 2,12 ГБ и грузится в память
КАЖДОГО рабочего процесса. На боевом сервере четыре воркера и 8 ГБ памяти:
первый же запрос к смысловому поиску съел бы сервер. Это «мина №1», и пока
модель не вынесена в отдельный процесс, поиск выключается флагом.

Главная проверка здесь — НЕ «страница открылась», а то, что модуль
`sentence_transformers` не появился в `sys.modules`. Страница может
открыться и после загрузки двух гигабайт — тогда тест был бы зелёным ровно
в тот момент, когда сервер уже мёртв.
"""
import sys

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from problems.models import Problem, Topic

МОДУЛИ_МОДЕЛИ = ('sentence_transformers', 'torch', 'transformers')


class _База(TestCase):
    """Общая подготовка: пользователь и пара опубликованных задач."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='искатель', password='пароль-для-теста-123')
        cls.topic = Topic.objects.create(name='Спрос и предложение',
                                         slug='spros-predlozhenie')
        cls.нужная = Problem.objects.create(
            title='Эластичность спроса по цене',
            statement='Найдите эластичность спроса при цене 10 рублей.',
            status=Problem.Status.PUBLISHED,
            needs_quality_review=False,
            hidden_pending_review=False,
        )
        cls.нужная.topics.add(cls.topic)
        cls.посторонняя = Problem.objects.create(
            title='Инфляция и безработица',
            statement='Постройте кривую Филлипса по данным таблицы.',
            status=Problem.Status.PUBLISHED,
            needs_quality_review=False,
            hidden_pending_review=False,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _снимок_модулей(self):
        return {имя for имя in МОДУЛИ_МОДЕЛИ if имя in sys.modules}


# ─────────────────────────────────────────────────────────────────────────
# ГЛАВНЫЙ ТЕСТ МИНЫ №1
# ─────────────────────────────────────────────────────────────────────────
@override_settings(SEMANTIC_SEARCH_ENABLED=False)
class ModelIsNotImportedTests(_База):

    def test_модель_не_попадает_в_sys_modules(self):
        """⚠️ САМАЯ ВАЖНАЯ ПРОВЕРКА ФАЙЛА.

        Проверяем именно `sys.modules`, а не код ответа: страница может
        отдать 200 уже ПОСЛЕ того, как в память процесса приехали 2,12 ГБ.
        Тогда зелёный тест означал бы ровно обратное тому, что нужно.
        """
        было = self._снимок_модулей()

        ответ = self.client.get(reverse('catalog:smart_search'),
                                {'q': 'эластичность спроса'})
        self.assertEqual(ответ.status_code, 200)

        стало = self._снимок_модулей()
        новые = стало - было
        self.assertEqual(
            новые, set(),
            'При выключенном смысловом поиске подтянулись модули модели: %s. '
            'Значит проверка флага стоит ПОСЛЕ импорта, а не до, и 2,12 ГБ '
            'уже в памяти воркера — это мина №1.' % sorted(новые))

    def test_модель_не_подтягивается_и_через_гибридный_поиск(self):
        """Вторая дверь к той же модели: подбор домашки ходит через hybrid."""
        from catalog import hybrid

        было = self._снимок_модулей()
        hybrid.search('эластичность спроса', limit=5)
        новые = self._снимок_модулей() - было
        self.assertEqual(новые, set(),
                         'hybrid.dense_search потянул модель: %s' % sorted(новые))

    def test_dense_search_отдаёт_пусто_без_исключения(self):
        from catalog import hybrid

        ids, scores = hybrid.dense_search('эластичность спроса')
        self.assertEqual(ids, [])
        self.assertEqual(scores, {})


# ─────────────────────────────────────────────────────────────────────────
# Деградация страницы: 200, плашка, результаты по словам
# ─────────────────────────────────────────────────────────────────────────
@override_settings(SEMANTIC_SEARCH_ENABLED=False)
class DegradedPageTests(_База):

    def test_страница_отдаёт_200_и_плашку(self):
        ответ = self.client.get(reverse('catalog:smart_search'),
                                {'q': 'эластичность спроса'})
        self.assertEqual(ответ.status_code, 200,
                         'Выключенный поиск обязан деградировать, а не падать')
        тело = ответ.content.decode()
        self.assertIn('Умный поиск временно недоступен', тело)
        self.assertIn('обычный поиск по словам', тело)

    def test_в_плашке_нет_слова_ошибка_и_нет_совета_ставить_пакет(self):
        """Человеку не показывают ни «ошибку», ни `pip install`: он ничего
        не сделал не так, и чинить ему нечего."""
        ответ = self.client.get(reverse('catalog:smart_search'),
                                {'q': 'эластичность спроса'})
        тело = ответ.content.decode()
        self.assertNotIn('pip install', тело)
        self.assertNotIn('Ошибка поиска', тело)

    def test_пустая_страница_без_запроса_тоже_200(self):
        ответ = self.client.get(reverse('catalog:smart_search'))
        self.assertEqual(ответ.status_code, 200)

    def test_лексический_поиск_действительно_находит(self):
        """Плашка без результатов — это не деградация, а отказ с извинением."""
        ответ = self.client.get(reverse('catalog:smart_search'),
                                {'q': 'эластичность'})
        self.assertEqual(ответ.status_code, 200)
        найденные = [r['problem'].pk for r in ответ.context['results']]
        self.assertIn(self.нужная.pk, найденные,
                      'Поиск по словам не нашёл задачу со словом из запроса')
        self.assertNotIn(self.посторонняя.pk, найденные)

    def test_контекст_помечен_как_деградация(self):
        ответ = self.client.get(reverse('catalog:smart_search'), {'q': 'спрос'})
        self.assertTrue(ответ.context['degraded'])

    def test_блок_похожих_задач_работает_без_модели(self):
        """«Похожие» живут кэшем M2M, модель им не нужна вовсе."""
        self.нужная.similar_problems.add(self.посторонняя)
        было = self._снимок_модулей()
        ответ = self.client.get(
            reverse('catalog:problem_detail', args=[self.нужная.pk]))
        self.assertEqual(ответ.status_code, 200)
        похожие = [s['problem'].pk if isinstance(s, dict) else s.pk
                   for s in ответ.context['similar']]
        self.assertIn(self.посторонняя.pk, похожие)
        self.assertEqual(self._снимок_модулей() - было, set())


# ─────────────────────────────────────────────────────────────────────────
# Обратная сторона: при включённом флаге ничего не изменилось
# ─────────────────────────────────────────────────────────────────────────
class EnabledBehaviourUnchangedTests(_База):

    def test_по_умолчанию_флаг_включён(self):
        from django.conf import settings

        self.assertTrue(getattr(settings, 'SEMANTIC_SEARCH_ENABLED', None),
                        'Умолчание обязано быть «включено»: иначе локальная '
                        'разработка и весь существующий набор тестов молча '
                        'сменили бы поведение.')

    @override_settings(SEMANTIC_SEARCH_ENABLED=True)
    def test_при_включённом_флаге_плашки_нет(self):
        from catalog import semantic

        self.assertTrue(semantic.is_enabled())
        ответ = self.client.get(reverse('catalog:smart_search'))
        self.assertEqual(ответ.status_code, 200)
        self.assertNotIn('Умный поиск временно недоступен',
                         ответ.content.decode())
        self.assertFalse(ответ.context['degraded'])

    @override_settings(SEMANTIC_SEARCH_ENABLED=False)
    def test_get_model_возбуждает_понятное_исключение(self):
        from catalog import semantic

        with self.assertRaises(semantic.SemanticSearchDisabled):
            semantic.get_model()
