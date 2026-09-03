"""Команда демонстрационных данных: числа обязаны сойтись ровно."""
import json
import pathlib

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from olympiads.models import (
    Olympiad, OlympiadBenefit, OlympiadEvent, OlympiadScore, OlympiadStage,
    OlympiadVariant,
    RegionalCoordinator, UniversityProgram,
)


class SeedTests(TestCase):

    def test_without_yes_nothing_is_written(self):
        out = StringIO()
        call_command('seed_olympiads_demo', stdout=out)
        self.assertIn('ПЛАН', out.getvalue())
        self.assertEqual(Olympiad.objects.count(), 0)

    def test_with_yes_counts_match_exactly(self):
        call_command('seed_olympiads_demo', '--yes', stdout=StringIO())
        self.assertEqual(Olympiad.objects.count(), 21)
        self.assertEqual(
            Olympiad.objects.filter(display_group='main').count(), 16)
        self.assertEqual(
            Olympiad.objects.filter(display_group='related').count(), 5)
        self.assertEqual(UniversityProgram.objects.count(), 7)
        self.assertEqual(OlympiadBenefit.objects.count(), 21)
        self.assertEqual(OlympiadScore.objects.count(), 14)
        self.assertEqual(OlympiadVariant.objects.count(), 12)
        self.assertEqual(RegionalCoordinator.objects.count(), 85)

        vseros = Olympiad.objects.get(slug='vseros')
        self.assertEqual(vseros.stages.count(), 4)
        self.assertEqual(vseros.events.count(), 4)
        # Ни одной конкретной даты у ВсОШ — это и есть правда сезона.
        self.assertEqual(vseros.events.exclude(date_start=None).count(), 0)

    def test_every_olympiad_is_marked_as_placeholder(self):
        call_command('seed_olympiads_demo', '--yes', stdout=StringIO())
        self.assertEqual(
            Olympiad.objects.filter(is_placeholder=False).count(), 0)

    def test_forbidden_slugs_are_not_created(self):
        """solvehub, posh, cpm и ege олимпиадами не являются."""
        call_command('seed_olympiads_demo', '--yes', stdout=StringIO())
        for slug in ('solvehub', 'posh', 'cpm', 'ege'):
            self.assertFalse(Olympiad.objects.filter(slug=slug).exists(), slug)

    def test_score_gap_is_kept(self):
        """2022 год по 9 классу пропущен нарочно — блок обязан показать дыру."""
        call_command('seed_olympiads_demo', '--yes', stdout=StringIO())
        self.assertFalse(
            OlympiadScore.objects.filter(year=2022, grade=9).exists())

    def test_benefits_include_the_none_case(self):
        """Таблица льгот обязана уметь показать «льготы нет»."""
        call_command('seed_olympiads_demo', '--yes', stdout=StringIO())
        self.assertTrue(
            OlympiadBenefit.objects.filter(benefit_type='none').exists())

    def test_wipe_then_seed_is_idempotent(self):
        call_command('seed_olympiads_demo', '--yes', stdout=StringIO())
        call_command('seed_olympiads_demo', '--yes', '--wipe', stdout=StringIO())
        self.assertEqual(Olympiad.objects.count(), 21)
        self.assertEqual(OlympiadEvent.objects.count(), 10)


class SeedInventsNoNumbersTests(TestCase):
    """⚠️ Наполнение примерами НЕ ИМЕЕТ ПРАВА выдумывать числа этапов.

    Длительность и максимум баллов устанавливает предметно-методическая
    комиссия и публикует в требованиях к этапу. Прежде сеялка ставила
    сюда 235 и 240 минут — на экране они выглядели ровно как настоящие и
    прожили две сессии. Настоящая длительность регионального этапа по
    экономике — 180 минут: расхождение почти час, а по этому числу
    школьник ставит себе таймер тренировки.
    """

    def test_seed_writes_no_stage_durations(self):
        call_command('seed_olympiads_demo', yes=True, verbosity=0)
        bad = OlympiadStage.objects.exclude(duration_minutes=None)
        self.assertEqual(
            list(bad.values_list('olympiad__slug', 'code', 'duration_minutes')),
            [], 'сеялка снова выдумывает длительность этапа')

    def test_seed_writes_no_stage_max_score(self):
        call_command('seed_olympiads_demo', yes=True, verbosity=0)
        self.assertEqual(OlympiadStage.objects.exclude(max_score=None).count(), 0)

    def test_seed_writes_no_variant_numbers(self):
        """И у КОМПЛЕКТОВ числа больше не выдумываются — они просто пустые.

        Раньше сеялка ставила «6 заданий, 240 минут, 100 баллов» и «5
        заданий, 235 минут», механически повторённые для всех лет, и
        прикрывалась пометкой «демо». Настоящие числа из шапок файлов
        заданий не совпали НИ С ОДНИМ из них: у тура заключительного
        этапа 4 задания, 48 баллов и 210 минут, у регионального — 18,
        100 и 180. Пометка не делает выдуманное число безвредным: экран
        всё равно показывал его цифрами. [ADR 0067]
        """
        call_command('seed_olympiads_demo', yes=True, verbosity=0)
        self.assertGreater(OlympiadVariant.objects.count(), 0)
        bad = OlympiadVariant.objects.exclude(
            problem_count=None, duration_minutes=None, max_score=None)
        self.assertEqual(
            list(bad.values_list('year', 'problem_count',
                                 'duration_minutes', 'max_score')),
            [], 'сеялка снова выдумывает числа комплекта')

    def test_seed_marks_variants_as_placeholder(self):
        """Заготовка без чисел обязана быть помечена — это её и означает."""
        call_command('seed_olympiads_demo', yes=True, verbosity=0)
        self.assertEqual(
            OlympiadVariant.objects.filter(is_placeholder=False).count(), 0)


class SeedWritesNoOriginalUrlTests(TestCase):
    """⚠️ Наполнение примерами не имеет права выдумывать адрес оригинала.

    Прежде сеялка ставила ссылки вида `vos.olimpiada.ru/2026/final/11` с
    пометкой «официальный источник». Выглядели настоящими, страниц по ним
    не было. Настоящие архивы заданий ВсОШ по экономике лежат на
    vso.edsoo.ru и приходят импортом.
    """

    def test_seed_leaves_original_url_empty(self):
        call_command('seed_olympiads_demo', yes=True, verbosity=0)
        bad = OlympiadVariant.objects.exclude(original_url='')
        self.assertEqual(list(bad.values_list('year', 'original_url')), [],
                         'сеялка снова выдумывает адрес оригинала')

    def test_seed_marks_original_source_as_none(self):
        call_command('seed_olympiads_demo', yes=True, verbosity=0)
        self.assertEqual(
            OlympiadVariant.objects.exclude(original_source='none').count(), 0)


class SeedInventsNoUrlsTests(TestCase):
    """⚠️ Наполнение примерами не имеет права выдумывать адреса.

    Прежде сеялка ставила карточкам official_url вида
    `https://example.org/<слаг>/`, а программам вузов —
    `https://example.org/admission/<номер>/`. На экране это были рабочие
    на вид кнопки «Официальный сайт» и «Смотреть», ведущие в никуда.
    Пустое поле экран переживает, а школьник по такой кнопке уходит.
    """

    def test_no_fabricated_urls_anywhere(self):
        call_command('seed_olympiads_demo', yes=True, verbosity=0)
        bad = []
        for obj in Olympiad.objects.all():
            for field in ('official_url', 'archive_url', 'registration_url'):
                if 'example.' in (getattr(obj, field) or ''):
                    bad.append((obj.slug, field))
        for program in UniversityProgram.objects.all():
            if 'example.' in (program.admission_rules_url or ''):
                bad.append((program.university_short, 'admission_rules_url'))
        self.assertEqual(bad, [], 'сеялка снова выдумывает адреса')


class PlaceholderMeansNumbersAreThereTests(TestCase):
    """⚠️ СНЯТАЯ ПОМЕТКА — ЭТО ОБЕЩАНИЕ, И ОНО ПРОВЕРЯЕМОЕ.

    `is_placeholder=False` означает не «запись хорошая», а ровно одно: все
    три числа комплекта взяты из официального файла заданий. Кнопка
    «Решать на время» смотрит на `duration_minutes` и включается молча —
    комплект с пустой длительностью и снятой пометкой выглядел бы готовым,
    а таймер получил бы пустоту.

    Обратное неверно НАМЕРЕННО: помеченным может быть и комплект с пустыми
    числами — файла заданий того тура на сайте ЦПМК просто нет. Это
    законное состояние, а не брак.

    Проверяем и правило (на объектах), и сам файл данных: правило без файла
    осталось бы зелёным на любой чепухе, которую мы поставляем.
    """

    def _broken(self, variants):
        return [(v.ref_event_id, v.problem_count, v.duration_minutes,
                 v.max_score)
                for v in variants
                if not v.is_placeholder
                and not (v.problem_count and v.duration_minutes
                         and v.max_score)]

    def test_rule_catches_unmarked_variant_without_numbers(self):
        olympiad = Olympiad.objects.create(
            slug='vs', name_full='Тестовая', name_short='ТЕСТ',
            organizer='Никто')
        good = OlympiadVariant(olympiad=olympiad, year=2026, grade=11,
                               problem_count=4, duration_minutes=210,
                               max_score=48, is_placeholder=False,
                               ref_event_id='good')
        bad = OlympiadVariant(olympiad=olympiad, year=2025, grade=11,
                              is_placeholder=False, ref_event_id='bad')
        self.assertEqual(self._broken([good]), [])
        self.assertEqual(self._broken([bad]), [('bad', None, None, None)])

    def test_shipped_variants_file_keeps_the_promise(self):
        """Тот же инвариант — на данных, которые мы реально поставляем."""
        path = pathlib.Path('data/olympiads/out/variants.jsonl')
        rows = [json.loads(line)
                for line in path.read_text(encoding='utf-8').splitlines()
                if line.strip()]
        self.assertGreater(len(rows), 0, 'файл комплектов пуст')
        broken = [r for r in rows if not r.get('is_placeholder')
                  and not (r.get('problem_count') and r.get('duration_minutes')
                           and r.get('max_score'))]
        self.assertEqual(
            broken, [],
            'в variants.jsonl снята пометка, а числа не все: '
            'кнопка «Решать на время» включится на пустой длительности')
        ready = [r for r in rows if not r.get('is_placeholder')]
        self.assertGreater(len(ready), 0,
                           'ни одного готового комплекта — тренировать не на чем')
