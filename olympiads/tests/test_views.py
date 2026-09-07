"""Экраны раздела: главное — они обязаны жить и на пустых данных."""
import re

from django.test import TestCase, override_settings
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


# ⚠️ РАЗДЕЛ ЗАКРЫТ ЗАГЛУШКОЙ «СКОРО» (флаг OLYMPIADS_PUBLIC, 08.09.2026).
# Классы ниже проверяют СОДЕРЖИМОЕ экранов, а не гейт, — поэтому раздел им
# открывают явно. Сам гейт сторожит OlympiadsAreClosedTests.
@override_settings(OLYMPIADS_PUBLIC=True)
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


@override_settings(OLYMPIADS_PUBLIC=True)
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


@override_settings(OLYMPIADS_PUBLIC=True)
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


@override_settings(OLYMPIADS_PUBLIC=True)
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


@override_settings(OLYMPIADS_PUBLIC=True)
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


@override_settings(OLYMPIADS_PUBLIC=True)
class PlaceholderVariantTests(TestCase):
    """Комплект без чисел обязан называть себя вслух.

    ⚠️ ЗАЧЕМ ЭТО СТОРОЖИТЬ И ЧТО ИЗМЕНИЛОСЬ. Сначала пометка значила
    «числа выдуманы наполнением примерами»: стояли 6 заданий, 240 минут и
    100 баллов, повторённые механически для всех лет. Настоящие числа
    пришли из шапок файлов заданий и не совпали ни с одним из них, а
    выдумку убрали из сеялки — теперь пометка значит «чисел НЕТ, файла
    заданий того тура на сайте ЦПМК не выложено». Слово на экране
    поменялось вместе со смыслом: было «демо», стало «чисел нет».
    По числу минут школьник ставит себе таймер тренировки, и молчание
    здесь дороже пустого поля. [ADR 0067]
    """

    def setUp(self):
        self.olympiad = make_olympiad('vseros', kind=Olympiad.Kind.VSOSH,
                                      is_published=True)

    def test_placeholder_variant_says_so_on_screen(self):
        OlympiadVariant.objects.create(
            olympiad=self.olympiad, year=2026, grade=11,
            problem_count=None, duration_minutes=None, max_score=None,
            is_placeholder=True)
        text = visible_text(self.client.get(
            reverse('olympiads:detail', args=['vseros'])))
        self.assertIn('чисел нет', text)

    def test_template_comments_do_not_leak_to_the_page(self):
        """⚠️ `{# #}` в Django ОДНОСТРОЧНЫЙ — многострочный уезжает на экран.

        Ровно так и случилось: пояснение к плашке из двух строк отрисовалось
        школьнику текстом вместе с фигурными скобками. Проверка дешёвая, а
        глазами такое замечается только случайно.
        """
        OlympiadVariant.objects.create(
            olympiad=self.olympiad, year=2026, grade=11, is_placeholder=True)
        text = visible_text(self.client.get(
            reverse('olympiads:detail', args=['vseros'])))
        self.assertNotIn('{#', text)
        self.assertNotIn('{%', text)

    def test_real_variant_shows_no_warning(self):
        """Плашки нет там, где выдумок нет: иначе она перестанет значить."""
        OlympiadVariant.objects.create(
            olympiad=self.olympiad, year=2026, grade=11,
            problem_count=6, duration_minutes=240, max_score=100)
        text = visible_text(self.client.get(
            reverse('olympiads:detail', args=['vseros'])))
        self.assertNotIn('демонстрационные', text)

    def test_placeholder_may_still_have_a_real_original(self):
        """Демонстрационные ЧИСЛА и настоящая ссылка — разные вещи.

        ⚠️ ЭТОТ ТЕСТ ПОМЕНЯЛ СМЫСЛ, И ВОТ ПОЧЕМУ. Сначала он сторожил
        правило «у демонстрационного комплекта оригинала нет»: сеялка
        писала выдуманные адреса вида vos.olimpiada.ru/2026/final/11, и
        гасить их было нужно. Потом нашлись НАСТОЯЩИЕ архивы заданий
        ЦПМК на vso.edsoo.ru — по годам, с разборами. Числа заданий у
        комплекта остаются демонстрационными (к нему привязано 5 задач
        банка, а в настоящем туре 18), но ссылка при этом честная, и
        гасить рабочую кнопку из-за выдуманного числа минут неправильно.
        Выдумку убрали там, где её писали — в сеялке; это сторожит
        SeedWritesNoOriginalUrlTests.
        """
        variant = OlympiadVariant.objects.create(
            olympiad=self.olympiad, year=2026, grade=11,
            original_url='https://vso.edsoo.ru/public.php/dav/files/x/?accept=zip',
            original_source=OlympiadVariant.OriginalSource.OFFICIAL,
            is_placeholder=True)
        self.assertTrue(variant.has_original)

    def test_variant_without_source_offers_no_original(self):
        """Источника нет — кнопка неактивна, даже если адрес в поле есть."""
        variant = OlympiadVariant.objects.create(
            olympiad=self.olympiad, year=2025, grade=11,
            original_url='https://example.test/x',
            original_source=OlympiadVariant.OriginalSource.NONE,
            is_placeholder=True)
        self.assertFalse(variant.has_original)
        html = self.client.get(
            reverse('olympiads:detail', args=['vseros'])).content.decode()
        self.assertNotIn('href="https://example.test/x"', html)


@override_settings(OLYMPIADS_PUBLIC=True)
class RegionOrderTests(TestCase):
    """Порядок регионов в списке: сначала sort_order, потом алфавит.

    ⚠️ ЗАЧЕМ ЧИСЛО, А НЕ ПРИЗНАК «НОВЫЙ РЕГИОН». Владелец захотел видеть
    четыре субъекта, которых не было в исходном файле, в конце списка.
    Признак «новый» через год перестанет быть правдой, а число останется
    просто порядком — и его можно будет поменять, не трогая код.
    """

    def setUp(self):
        self.olympiad = make_olympiad('vseros', kind=Olympiad.Kind.VSOSH,
                                      is_published=True)
        for name, order in (('Ямало-Ненецкий автономный округ', 0),
                            ('Алтайский край', 0),
                            ('Херсонская область', 1),
                            ('Донецкая Народная Республика', 1)):
            RegionalCoordinator.objects.create(region_name=name,
                                               sort_order=order)

    def test_sort_order_wins_over_alphabet(self):
        """Сначала группа 0, потом группа 1 — независимо от алфавита.

        ⚠️ ПРОВЕРЯЕМ ГРУППЫ, А НЕ ТОЧНЫЙ ПОРЯДОК ЧЕТЫРЁХ СТРОК. Первая
        версия теста сверяла список целиком и зеленела на SQLite, но
        краснела на PostgreSQL: тестовая база создаётся с локалью
        `en_US.UTF-8`, и порядок кириллицы в ней другой, чем у рабочей
        базы с локалью `C` («Херсонская» встала перед «Донецкой»).
        Сортировка русских строк — свойство СУБД, а не наше правило;
        наше правило здесь одно: sort_order сильнее алфавита.
        """
        rows = list(RegionalCoordinator.objects.all())
        self.assertEqual([r.sort_order for r in rows], [0, 0, 1, 1],
                         'группа с sort_order=1 обязана идти последней')
        self.assertEqual(
            {r.region_name for r in rows[:2]},
            {'Алтайский край', 'Ямало-Ненецкий автономный округ'})
        self.assertEqual(
            {r.region_name for r in rows[2:]},
            {'Донецкая Народная Республика', 'Херсонская область'})

    def test_alphabet_orders_within_one_group(self):
        """Внутри группы — по алфавиту. Пара «А…» и «Я…» одинакова в любой
        локали, поэтому проверку не сносит сортировкой СУБД."""
        names = list(RegionalCoordinator.objects.filter(sort_order=0)
                     .values_list('region_name', flat=True))
        self.assertEqual(names, ['Алтайский край',
                                 'Ямало-Ненецкий автономный округ'])

    def test_screen_shows_regions_in_that_order(self):
        text = visible_text(self.client.get(
            reverse('olympiads:detail', args=['vseros'])))
        last_of_group0 = max(text.index('Алтайский край'),
                             text.index('Ямало-Ненецкий автономный округ'))
        first_of_group1 = min(text.index('Донецкая Народная Республика'),
                              text.index('Херсонская область'))
        self.assertLess(last_of_group0, first_of_group1)


@override_settings(OLYMPIADS_PUBLIC=True)
class BenefitWhoGetsTests(TestCase):
    """«Только победителям» обязано быть видно в таблице льгот.

    ⚠️ ЗАЧЕМ. У части олимпиад БВИ положен ТОЛЬКО победителю: у программы
    «Экономика» ФЭН ВШЭ так устроена Московская олимпиада — победителю
    без экзаменов, призёру только сто баллов. Одна запись на пару
    «олимпиада + программа» обязана назвать это различие, иначе призёр
    прочитает «без вступительных испытаний» и не станет готовиться к ЕГЭ.
    """

    def setUp(self):
        from olympiads.models import OlympiadBenefit, UniversityProgram
        self.olympiad = make_olympiad('mosh', is_published=True)
        program = UniversityProgram.objects.create(
            university_name='НИУ ВШЭ', university_short='ФЭН ВШЭ',
            program_name='Экономика', order=1)
        OlympiadBenefit.objects.create(
            olympiad=self.olympiad, program=program, admission_year=2026,
            benefit_type=OlympiadBenefit.BenefitType.BVI,
            confirm_subject='математика', confirm_min_score=75,
            grades_note='11 класс',
            who_gets=OlympiadBenefit.WhoGets.WINNERS)

    def test_only_winners_is_shown(self):
        text = visible_text(self.client.get(
            reverse('olympiads:detail', args=['mosh'])))
        self.assertIn('только победителям', text)
        self.assertIn('математика, не ниже 75', text)

    def test_no_benefit_row_says_nothing_about_who(self):
        """У строки «льготы нет» приписки о победителях быть не должно."""
        from olympiads.models import OlympiadBenefit
        benefit = OlympiadBenefit.objects.get()
        benefit.benefit_type = OlympiadBenefit.BenefitType.NONE
        benefit.save()
        self.assertEqual(benefit.who_label, '')


class OlympiadsAreClosedTests(TestCase):
    """⚠️ РАЗДЕЛ ЗАКРЫТ ЗАГЛУШКОЙ «СКОРО» — гейт, а не содержимое экранов.

    Решение владельца 08.09.2026: раздел собран целиком, но публике его
    показывать рано. Флаг `OLYMPIADS_PUBLIC` по умолчанию выключен, персонал
    ходит внутрь и без него.

    Проверка стоит в КАЖДОЙ вьюхе, а не в middleware: у тренировки семь
    адресов, и один забытый пускал бы внутрь закрытого раздела. Поэтому тут
    проверяются и основные четыре адреса, и тренировочный.
    """

    MAIN = ('/olympiads/', '/olympiads/vseros/',
            '/olympiads/calendar/', '/olympiads/compare/')

    def setUp(self):
        make_olympiad('vseros', is_published=True, kind=Olympiad.Kind.VSOSH)

    def _make_user(self, username, **kwargs):
        from problems.models import User
        return User.objects.create_user(
            username=username, password='olymp-gate-2026', **kwargs)

    def test_guest_sees_the_stub_on_every_main_address(self):
        """Числовой инвариант фазы: «Скоро.» вернулось 4 из 4."""
        seen = 0
        for url in self.MAIN:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            if 'Скоро.' in visible_text(response):
                seen += 1
        self.assertEqual(seen, 4)

    def test_plain_student_sees_the_stub_too(self):
        """Вошедший — не значит «свой»: заглушку снимает только персонал."""
        self.client.force_login(self._make_user('olymp_st', role='student'))
        for url in self.MAIN:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertIn('Скоро.', visible_text(response), url)

    def test_the_stub_promises_nothing(self):
        """Ни формы, ни кнопки, ни поля — обещать на заглушке нечего."""
        html = self.client.get('/olympiads/').content.decode('utf-8')
        body = html.split('<div class="ol-soon">', 1)[1].split('</div>', 1)[0]
        for tag in ('<form', '<button', '<input'):
            self.assertNotIn(tag, body, tag)

    def test_training_addresses_are_closed_as_well(self):
        """Пятый адрес: тренировка. Заглушка стоит ДО поиска комплекта.

        Комплекта с таким номером нет вовсе — и это часть проверки: гейт
        обязан сработать раньше, чем `_variant_or_404`. Иначе закрытый
        раздел отвечал бы 404 и выдавал, какие комплекты существуют.
        """
        response = self.client.get(
            reverse('olympiads:training_intro', args=['vseros', 999]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Скоро.', visible_text(response))

    def test_five_anonymous_addresses_out_of_five(self):
        """Числовой инвариант фазы целиком: 5 из 5."""
        urls = self.MAIN + (
            reverse('olympiads:training_intro', args=['vseros', 999]),)
        closed = [u for u in urls
                  if 'Скоро.' in visible_text(self.client.get(u))]
        self.assertEqual(len(closed), 5, closed)

    def test_staff_walks_straight_in(self):
        """Персонал видит настоящий раздел и без флага."""
        self.client.force_login(
            self._make_user('olymp_ad', role='teacher', is_staff=True))
        text = visible_text(self.client.get('/olympiads/'))
        self.assertNotIn('Скоро.', text)
        self.assertIn('Это олимпиады по экономике.', text)

    @override_settings(OLYMPIADS_PUBLIC=True)
    def test_the_flag_opens_the_section_for_everyone(self):
        """Поднятый флаг — единственное, что нужно для публичного запуска."""
        text = visible_text(self.client.get('/olympiads/'))
        self.assertNotIn('Скоро.', text)
        self.assertIn('Это олимпиады по экономике.', text)
