"""Экраны раздела: главное — они обязаны жить и на пустых данных."""
import re

from django.test import TestCase
from django.urls import reverse

from olympiads.models import (Olympiad, OlympiadVariant,
                              RegionalCoordinator)

from .test_models import make_olympiad


def visible_text(response):
    """Текст страницы БЕЗ стилей и скриптов.

    ⚠️ Без этой чистки проверки ловят комментарии CSS: партиал стилей
    подключён на каждом экране раздела, и слово из комментария выглядит
    как слово с экрана. На этом уже один раз обожглись.
    """
    html = response.content.decode('utf-8')
    html = re.sub(r'<style.*?</style>', ' ', html, flags=re.S)
    html = re.sub(r'<script.*?</script>', ' ', html, flags=re.S)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


class EmptyStateTests(TestCase):

    def test_list_works_with_zero_olympiads(self):
        """Ноль олимпиад в базе — это рабочее состояние, а не поломка."""
        self.assertEqual(Olympiad.objects.count(), 0)
        response = self.client.get(reverse('olympiads:list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Это олимпиады по экономике.', visible_text(response))

    def test_detail_works_with_nothing_filled(self):
        """Ни событий, ни льгот, ни баллов, ни комплектов — все блоки пустые."""
        make_olympiad('bare', is_published=True)
        response = self.client.get(
            reverse('olympiads:detail', args=['bare']))
        self.assertEqual(response.status_code, 200)
        text = visible_text(response)
        self.assertIn('Описание готовится', text)
        self.assertIn('Даты сезона пока не объявлены', text)
        self.assertIn('Данных о льготах пока нет', text)
        self.assertIn('Данные о проходных баллах пока не собраны', text)
        self.assertIn('Задания прошлых лет пока не собраны', text)
        self.assertIn('Задания пока не размечены', text)

    def test_calendar_works_with_zero_events(self):
        response = self.client.get(reverse('olympiads:calendar'))
        self.assertEqual(response.status_code, 200)

    def test_compare_without_slugs_does_not_crash(self):
        response = self.client.get(reverse('olympiads:compare'))
        self.assertEqual(response.status_code, 200)


class RegionsBlockTests(TestCase):
    """Блок регионов — только у ВсОШ: школьный и муниципальный этапы
    назначает субъект, и только у неё это так."""

    def setUp(self):
        make_olympiad('vseros', kind=Olympiad.Kind.VSOSH, is_published=True)
        make_olympiad('mosh', kind=Olympiad.Kind.PERECHEN, is_published=True)
        RegionalCoordinator.objects.create(region_name='Москва')

    def test_regions_block_is_on_vsosh_page(self):
        response = self.client.get(reverse('olympiads:detail', args=['vseros']))
        self.assertContains(response, 'class="ol-regions-list"')
        self.assertIn('Москва', visible_text(response))

    def test_regions_block_is_absent_on_mosh_page(self):
        response = self.client.get(reverse('olympiads:detail', args=['mosh']))
        self.assertNotContains(response, 'class="ol-regions-list"')
        # И в видимом тексте тоже — а не только в разметке.
        self.assertNotIn('Региональные организаторы', visible_text(response))


class RoutingTests(TestCase):

    def test_calendar_is_not_caught_as_a_slug(self):
        """`calendar/` объявлен ДО `<slug>/`, иначе стал бы слагом."""
        make_olympiad('calendar', is_published=True)
        response = self.client.get('/olympiads/calendar/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Календарь олимпиад', visible_text(response))

    def test_compare_is_not_caught_as_a_slug(self):
        make_olympiad('compare', is_published=True)
        response = self.client.get('/olympiads/compare/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Сравнение олимпиад', visible_text(response))

    def test_unknown_slug_is_404(self):
        response = self.client.get('/olympiads/no-such-olympiad/')
        self.assertEqual(response.status_code, 404)


class CompareTests(TestCase):

    def setUp(self):
        for slug in ('a', 'b', 'c', 'd'):
            make_olympiad(slug, is_published=True)

    def test_four_slugs_take_first_three(self):
        """Ссылку могли прислать из чата: усечение лучше ошибки."""
        response = self.client.get(
            reverse('olympiads:compare') + '?slugs=a,b,c,d')
        self.assertEqual(response.status_code, 200)
        text = visible_text(response)
        self.assertIn('Можно сравнить не больше 3', text)
        head = re.search(r'<thead>(.*?)</thead>',
                         response.content.decode(), re.S).group(1)
        self.assertEqual(len(re.findall(r'<th>', head)), 4)

    def test_unknown_slug_is_skipped_not_fatal(self):
        response = self.client.get(
            reverse('olympiads:compare') + '?slugs=a,nope')
        self.assertEqual(response.status_code, 200)


class VariantButtonsTests(TestCase):
    """Кнопки блока комплектов. Заглушку «Скоро» сменила тренировка.

    ⚠️ Прежний тест этого класса сторожил заглушку и был удалён вместе с
    ней — не «поправлен, чтобы позеленел»: экран, который он проверял,
    больше не существует. Сторожим то, что пришло ему на смену.
    """

    def setUp(self):
        self.olympiad = make_olympiad('vseros', kind=Olympiad.Kind.VSOSH,
                                      is_published=True)

    def test_variant_without_linked_problems_offers_no_training(self):
        """Комплект без задач в банке не зовёт решать — и говорит почему."""
        OlympiadVariant.objects.create(
            olympiad=self.olympiad, year=2026, grade=11,
            duration_minutes=240)
        response = self.client.get(
            reverse('olympiads:detail', args=['vseros']))
        text = visible_text(response)
        self.assertIn('Задания ещё не привязаны', text)
        self.assertNotIn('Решать на время', text)

    def test_variant_without_duration_cannot_be_timed(self):
        """Длительность тура неизвестна — «на время» неактивно."""
        variant = OlympiadVariant.objects.create(
            olympiad=self.olympiad, year=2026, grade=11,
            duration_minutes=None, ref_event_id='ev')
        Problem_ = __import__('problems.models', fromlist=['x'])
        problem = Problem_.Problem.objects.create(
            title='з', statement='у', answer='1')
        Problem_.OlympiadRef.objects.create(
            problem=problem, event_id='ev', source_site='solvehub',
            olympiad_slug='vseros', number='1', record_id='r1')
        response = self.client.get(
            reverse('olympiads:detail', args=['vseros']))
        text = visible_text(response)
        self.assertIn('Время тура неизвестно', text)
        self.assertIn('Решать без таймера', text)
        self.assertEqual(variant.duration_minutes, None)


class PlaceholderVariantTests(TestCase):
    """Демонстрационный комплект обязан называть себя вслух.

    ⚠️ ЗАЧЕМ ЭТО СТОРОЖИТЬ. У двенадцати комплектов из наполнения примерами
    числа заданий, минут и баллов выдуманы и повторены механически для всех
    лет, а адреса вроде `vos.olimpiada.ru/2026/final/11` выглядят настоящими,
    но страниц по ним нет. По числу минут школьник ставит себе таймер
    тренировки — молчащая заглушка здесь дороже пустого поля.
    """

    def setUp(self):
        self.olympiad = make_olympiad('vseros', kind=Olympiad.Kind.VSOSH,
                                      is_published=True)

    def test_placeholder_variant_says_so_on_screen(self):
        OlympiadVariant.objects.create(
            olympiad=self.olympiad, year=2026, grade=11,
            problem_count=6, duration_minutes=240, max_score=100,
            is_placeholder=True)
        text = visible_text(self.client.get(
            reverse('olympiads:detail', args=['vseros'])))
        self.assertIn('демо', text)
        self.assertIn('демонстрационные', text)

    def test_real_variant_shows_no_warning(self):
        """Плашки нет там, где выдумок нет: иначе она перестанет значить."""
        OlympiadVariant.objects.create(
            olympiad=self.olympiad, year=2026, grade=11,
            problem_count=6, duration_minutes=240, max_score=100)
        text = visible_text(self.client.get(
            reverse('olympiads:detail', args=['vseros'])))
        self.assertNotIn('демонстрационные', text)

    def test_placeholder_original_link_is_dead_even_with_url(self):
        """Адрес есть, но выдуман — кнопка обязана быть неактивной.

        Проверка стоит в модели, а не в шаблоне: шаблон обойдёт новый экран.
        """
        variant = OlympiadVariant.objects.create(
            olympiad=self.olympiad, year=2026, grade=11,
            original_url='https://vos.olimpiada.ru/2026/final/11',
            original_source=OlympiadVariant.OriginalSource.OFFICIAL,
            is_placeholder=True)
        self.assertFalse(variant.has_original)
        html = self.client.get(
            reverse('olympiads:detail', args=['vseros'])).content.decode()
        self.assertNotIn('href="https://vos.olimpiada.ru/2026/final/11"', html)
