"""Схема под пакет олимпиад 30.10 (миграция 0008, ADR 0169).

Каждый тест сторожит правило, на котором держится идемпотентный импорт
или показ комплектов. Ограничения проверяются на настоящей базе: тестовая
база строится миграциями, поэтому правило, забытое в файле миграции,
здесь краснеет, даже если в `Meta` модели оно есть.
"""
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse

from olympiads.models import (
    Olympiad, OlympiadVariant, OlympiadVariantFile, OlympiadVariantGrade,
    OlympiadVariantItem,
)
from problems.models import Problem

from .test_models import make_olympiad


def make_kit(olympiad, kit_key=None, **kwargs):
    return OlympiadVariant.objects.create(
        olympiad=olympiad, year=kwargs.pop('year', 2024), kit_key=kit_key,
        **kwargs)


class KitKeyTests(TestCase):
    """`kit_key` — ключ идемпотентности комплекта."""

    def setUp(self):
        self.olympiad = make_olympiad('mosh')

    def test_same_kit_key_twice_is_rejected(self):
        """Второй комплект с тем же ключом — дубль, база его не пускает."""
        make_kit(self.olympiad, 'mosh-2024-final-9-v1')
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_kit(self.olympiad, 'mosh-2024-final-9-v1')

    def test_many_kits_without_key_are_allowed(self):
        """Прежние комплекты (не из пакета) живут без ключа — и их много."""
        make_kit(self.olympiad)
        make_kit(self.olympiad)
        self.assertEqual(
            OlympiadVariant.objects.filter(kit_key__isnull=True).count(), 2)

    def test_kit_without_year_is_allowed(self):
        """Комплект без сезона в пакете есть — выдумывать ему год нельзя."""
        kit = make_kit(self.olympiad, 'vseros-regional-unknown-ru-all-all',
                       year=None)
        kit.refresh_from_db()
        self.assertIsNone(kit.year)

    def test_new_kit_is_shown_by_default(self):
        """Прежние комплекты показывались — новое поле этого не меняет."""
        kit = make_kit(self.olympiad)
        kit.refresh_from_db()
        self.assertEqual(kit.visibility, OlympiadVariant.Visibility.PUBLISHED)


class GradeRowsTests(TestCase):
    """Развёрнутые классы: «10-11» — две строки, 10 и 11."""

    def setUp(self):
        self.kit = make_kit(make_olympiad('vp'), 'vp-2024-final-10-11-v1',
                            grade_raw='10-11')

    def test_range_lands_in_both_grades(self):
        OlympiadVariantGrade.objects.create(variant=self.kit, grade=10)
        OlympiadVariantGrade.objects.create(variant=self.kit, grade=11)
        self.assertEqual(
            list(OlympiadVariant.objects.filter(grades__grade=11)), [self.kit])
        self.assertEqual(
            list(OlympiadVariant.objects.filter(grades__grade=10)), [self.kit])

    def test_same_grade_twice_is_rejected(self):
        OlympiadVariantGrade.objects.create(variant=self.kit, grade=10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OlympiadVariantGrade.objects.create(variant=self.kit, grade=10)

    def test_grade_outside_school_is_rejected(self):
        """Класса 12 нет: опечатка в пакете не должна стать фильтром."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            OlympiadVariantGrade.objects.create(variant=self.kit, grade=12)


class KitFileTests(TestCase):

    def setUp(self):
        self.kit = make_kit(make_olympiad('vseros'), 'vseros-final-2024-25-ru-9-1')

    def test_same_file_twice_in_one_kit_is_rejected(self):
        """Повторный импорт не перекладывает тот же файл второй строкой."""
        OlympiadVariantFile.objects.create(variant=self.kit, kind='условия',
                                           sha256='a' * 64)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OlympiadVariantFile.objects.create(variant=self.kit,
                                               kind='условия', sha256='a' * 64)

    def test_shared_pdf_lives_in_two_kits(self):
        """Один PDF на несколько комплектов — у каждого своя строка."""
        other = make_kit(self.kit.olympiad, 'vseros-final-2024-25-ru-9-2')
        OlympiadVariantFile.objects.create(variant=self.kit, kind='условия',
                                           sha256='b' * 64)
        OlympiadVariantFile.objects.create(variant=other, kind='условия',
                                           sha256='b' * 64)
        self.assertEqual(OlympiadVariantFile.objects.count(), 2)


class ItemTests(TestCase):
    """Позиция комплекта: ключ задания пакета → задача банка."""

    def setUp(self):
        self.kit = make_kit(make_olympiad('mosh'), 'mosh-2022-qualifying-9-v1')
        self.problem = Problem.objects.create(title='з', statement='условие')

    def item(self, ref_key, **kwargs):
        return OlympiadVariantItem.objects.create(
            variant=self.kit, ref_key=ref_key, problem=self.problem, **kwargs)

    def test_same_ref_key_twice_is_rejected(self):
        """`ref_key` — ключ идемпотентности: дубль задания база не пускает."""
        self.item('mosh-2022-qualifying-9-v1:5:1')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.item('mosh-2022-qualifying-9-v1:5:1')

    def test_one_problem_carries_several_keys_of_one_kit(self):
        """Ради этого ключ и не в `OlympiadRef`: варианты 5:1 и 5:2 одного
        комплекта с одним текстом — одна задача банка и ДВЕ позиции."""
        self.item('mosh-2022-qualifying-9-v1:5:1', order=1)
        self.item('mosh-2022-qualifying-9-v1:5:2', order=2)
        self.assertEqual(self.problem.olympiad_items.count(), 2)

    def test_problem_in_a_kit_is_not_deleted_silently(self):
        """Задача, стоящая в комплекте, молча не удаляется."""
        self.item('mosh-2022-qualifying-9-v1:7:1')
        with self.assertRaises(ProtectedError):
            self.problem.delete()

    def test_new_item_is_clean_until_said_otherwise(self):
        item = self.item('mosh-2022-qualifying-9-v1:8:1')
        item.refresh_from_db()
        self.assertEqual(item.quality, OlympiadVariantItem.Quality.CLEAN)
        self.assertEqual(item.quality_reasons, [])
        self.assertFalse(item.absent_in_last_import)


@override_settings(OLYMPIADS_PUBLIC=True)
class KitWithoutYearPageTests(TestCase):

    def test_olympiad_page_lives_with_a_kit_without_year(self):
        """Годы комплектов сортируются для фильтра — пустой год не роняет
        страницу олимпиады."""
        olympiad = make_olympiad('vseros', kind=Olympiad.Kind.VSOSH,
                                 is_published=True)
        make_kit(olympiad, 'vseros-2024', year=2024)
        make_kit(olympiad, 'vseros-regional-unknown-ru-all-all', year=None)
        response = self.client.get(reverse('olympiads:detail', args=['vseros']))
        self.assertEqual(response.status_code, 200)
