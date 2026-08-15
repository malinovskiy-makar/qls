"""
Обзор кабинета 13.08.2026, фаза 7 — сводка решений и проверка задачи.

Пункты владельца 41, 43, 45, 46, 47, 48, 51.
"""
import os
import re
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from problems.models import StudentGroup
from problems.tests.factories import make_problem, make_user
from problems.work_review import score_presets

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as handle:
        return handle.read()


# ── Счёт контраста. Держим ЗДЕСЬ, а не «на глаз»: цифра либо есть, либо нет.
def _lum(value):
    value = value.lstrip('#')
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def ratio(one, two):
    first, second = _lum(one), _lum(two)
    top, bottom = max(first, second), min(first, second)
    return (top + 0.05) / (bottom + 0.05)


def over(colour, alpha, below):
    """Полупрозрачный цвет поверх фона → сплошной.

    ⚠️ В тёмной теме подложки заданы через `rgba`, и считать контраст по
    самому `rgba` нельзя: пока он не лёг на поверхность, у него нет яркости.
    """
    top = [int(colour.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
    base = [int(below.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
    return '#%02x%02x%02x' % tuple(
        round(top[i] * alpha + base[i] * (1 - alpha)) for i in range(3))


def _markup_files():
    for folder in ('templates', 'teacher', 'student', 'problems/templates'):
        for base, _dirs, files in os.walk(os.path.join(ROOT, folder)):
            if 'node_modules' in base:
                continue
            for name in files:
                if name.endswith('.html'):
                    path = os.path.join(base, name)
                    with open(path, encoding='utf-8') as handle:
                        yield os.path.relpath(path, ROOT), handle.read()


class Base(TestCase):
    def setUp(self):
        from problems.models import Assignment, AssignmentItem, Submission

        self.now = timezone.now()
        self.tutor = make_user('or_tutor', role='teacher')
        self.student = make_user('or_student', role='student',
                                 first_name='Пётр', last_name='Иванов')
        self.lazy = make_user('or_lazy', role='student',
                              first_name='Илья', last_name='Ленивый')
        self.group = StudentGroup.objects.create(name='Гр', teacher=self.tutor)
        self.group.students.set([self.student, self.lazy])
        self.work = Assignment.objects.create(
            name='Домашка', author=self.tutor, group=self.group,
            deadline=self.now + timedelta(days=1))
        self.work.students.set([self.student, self.lazy])
        # Задача с максимумом 3: на двойке половина совпадает с целым и
        # ничего не проверяет (замечание владельца).
        self.item = AssignmentItem.objects.create(
            assignment=self.work, order=0,
            catalog_problem=make_problem('Условие'), points=Decimal('3'))
        self.sub = Submission.objects.create(
            student=self.student, assignment=self.work,
            problem_item=self.item, status='submitted',
            submitted_at=self.now, submitted_answer='5')
        self.client.force_login(self.tutor)


class AutoCheckHintTests(Base):
    """7.1 — почему у автопроверки знаменатель меньше."""

    def test_hint_stands_next_to_the_number(self):
        html = self.client.get(
            reverse('teacher:group_submissions',
                    args=[self.group.pk, self.work.pk])).content.decode()
        self.assertIn('Результат автопроверки', html)
        page = read('teacher', 'templates', 'teacher', 'groups',
                    'submissions_by_student.html')
        # ⚠️ Режем по РАЗМЕТКЕ: те же слова стоят и в комментарии стилей.
        block = page.split('">Результат автопроверки')[1][:400]
        self.assertIn("_hint.html", block)

    def test_hint_explains_the_denominator(self):
        page = read('teacher', 'templates', 'teacher', 'groups',
                    'submissions_by_student.html')
        self.assertIn('Знаменатель меньше итогового', page)
        self.assertIn('Открытые задачи оценивает преподаватель', page)


class WriteButtonTests(Base):
    """7.2 — «Написать» ведёт в работающий механизм."""

    def _cards(self):
        from teacher.views_groups import student_cards
        return {c['student'].pk: c for c in student_cards(self.work,
                                                          self.group)}

    def test_button_carries_the_student(self):
        card = self._cards()[self.lazy.pk]
        self.assertEqual(card['button']['label'], 'Написать ученику')
        self.assertIn('?write=%d' % self.lazy.pk, card['button']['url'])

    def test_button_points_at_the_assignment_page(self):
        card = self._cards()[self.lazy.pk]
        self.assertTrue(card['button']['url'].startswith(
            reverse('teacher:group_assignment',
                    args=[self.group.pk, self.work.pk])))

    def test_the_target_page_opens(self):
        response = self.client.get(
            reverse('teacher:group_assignment',
                    args=[self.group.pk, self.work.pk])
            + '?write=%d' % self.lazy.pk)
        self.assertEqual(response.status_code, 200)

    def test_the_page_can_actually_address_this_student(self):
        """Механизм настоящий: ученик есть в списке получателей."""
        html = self.client.get(
            reverse('teacher:group_assignment',
                    args=[self.group.pk, self.work.pk])
            + '?write=%d' % self.lazy.pk).content.decode()
        self.assertIn('name="recipient_id"', html)
        self.assertIn('value="%d"' % self.lazy.pk, html)

    def test_script_runs_after_the_form_handler(self):
        """⚠️ Он будит обработчик событием — до объявления будить нечего."""
        page = read('teacher', 'templates', 'teacher', 'groups',
                    'assignment_detail.html')
        self.assertLess(page.index("document.querySelectorAll('.comment-form')"),
                        page.index("get('write')"))

    def test_student_who_submitted_gets_a_different_button(self):
        card = self._cards()[self.student.pk]
        self.assertNotIn('Написать', card['button']['label'])


class PendingColourTests(TestCase):
    """7.3 — «ждёт проверки» больше не янтарный."""

    def test_stripe_uses_its_own_token(self):
        kit = read('templates', '_kit.html')
        line = [l for l in kit.split('\n')
                if l.startswith('.k-mark.k-mark--pending')][0]
        self.assertIn('var(--pending)', line)
        self.assertNotIn('amber', line)

    def test_flag_uses_its_own_token(self):
        kit = read('templates', '_kit.html')
        block = kit.split('.k-flag.k-flag--pending')[1].split('}')[0]
        self.assertIn('var(--pending-tint)', block)
        self.assertIn('var(--pending)', block)
        self.assertNotIn('amber', block)

    def test_amber_is_left_to_partial_only(self):
        kit = read('templates', '_kit.html')
        for line in kit.split('\n'):
            if 'k-mark--' in line and 'border-left-color' in line:
                if 'amber' in line:
                    self.assertIn('partial', line, line)

    def test_token_defined_in_both_themes(self):
        tokens = read('templates', '_tokens.html')
        light, dark = tokens.split('[data-theme="dark"]')
        for part in (light, dark):
            self.assertIn('--pending:', part)
            self.assertIn('--pending-tint:', part)

    def test_contrast_passes_aa(self):
        """Считаем прямо здесь: «проверено на глаз» не проверка."""
        tokens = read('templates', '_tokens.html')
        light = tokens.split('[data-theme="dark"]')[0]
        colour = re.search(r'--pending:\s*(#[0-9a-fA-F]{6})', light).group(1)
        tint = re.search(r'--pending-tint:\s*(#[0-9a-fA-F]{6})',
                         light).group(1)
        self.assertGreaterEqual(round(ratio(colour, tint), 2), 4.5)
        self.assertGreaterEqual(round(ratio(colour, '#ffffff'), 2), 4.5)

    # ── Янтарь: текст на янтарной подложке (ревью 15.08, фаза 4) ─────────
    # ⚠️ Раньше здесь стояла только пометка «ждёт проверки». Пара
    # `--amber` на `--amber-tint` давала 3,95:1 и жила отдельной карточкой в
    # Notion; теперь у текста свой токен, и он проверяется тем же счётом.

    def test_amber_ink_exists_in_both_themes(self):
        tokens = read('templates', '_tokens.html')
        light, dark = tokens.split('[data-theme="dark"]')
        for part in (light, dark):
            self.assertIn('--amber-ink:', part)

    def test_amber_ink_passes_aa_in_light(self):
        tokens = read('templates', '_tokens.html')
        light = tokens.split('[data-theme="dark"]')[0]
        ink = re.search(r'--amber-ink:\s*(#[0-9a-fA-F]{6})', light).group(1)
        tint = re.search(r'--amber-tint:\s*(#[0-9a-fA-F]{6})', light).group(1)
        dense = re.search(r'--amber-border:\s*(#[0-9a-fA-F]{6})',
                          light).group(1)
        surface = re.search(r'--surface:\s*(#[0-9a-fA-F]{6})', light).group(1)
        self.assertGreaterEqual(round(ratio(ink, tint), 2), 4.5)
        self.assertGreaterEqual(round(ratio(ink, dense), 2), 4.5)
        self.assertGreaterEqual(round(ratio(ink, surface), 2), 4.5)

    def test_amber_ink_passes_aa_in_dark(self):
        """⚠️ В тёмной теме подложка ПРОЗРАЧНАЯ — считаем поверх поверхности."""
        tokens = read('templates', '_tokens.html')
        dark = tokens.split('[data-theme="dark"]')[1]
        ink = re.search(r'--amber-ink:\s*(#[0-9a-fA-F]{6})', dark).group(1)
        base = re.search(r'--amber:\s*(#[0-9a-fA-F]{6})', dark).group(1)
        surface = re.search(r'--surface:\s*(#[0-9a-fA-F]{6})', dark).group(1)
        page = re.search(r'--bg:\s*(#[0-9a-fA-F]{6})', dark).group(1)
        for below in (surface, page):
            self.assertGreaterEqual(round(ratio(ink, over(base, .15, below)),
                                          2), 4.5, below)
            self.assertGreaterEqual(round(ratio(ink, over(base, .35, below)),
                                          2), 4.5, below)

    def test_old_pair_really_was_below_aa(self):
        """Проверка «зубастая»: прежняя пара порог НЕ проходит."""
        self.assertLess(round(ratio('#b26b00', '#fff7e8'), 2), 4.5)

    def test_text_on_amber_never_uses_the_signal_colour(self):
        """Сигнал остаётся сигналом, чернила — чернилами."""
        # ⚠️ `(?<![-\w])` обязательна: без неё под правило попадают
        # `border-left-color: var(--amber)` — а это ПОЛОСА, законный сигнал.
        text_colour = re.compile(r'(?<![-\w])color:\s*var\(--amber\)')
        bad = []
        for path, text in _markup_files():
            for line in text.split('\n'):
                if 'amber-tint' in line and text_colour.search(line):
                    bad.append('%s: %s' % (path, line.strip()[:70]))
        self.assertEqual(bad, [], bad)

    def test_stars_keep_the_signal_colour(self):
        """⚠️ Звёзды сложности — САМ СИГНАЛ, их цвет не трогали."""
        page = read('catalog', 'templates', 'catalog', 'problem_list.html')
        stars = [l for l in page.split('\n') if '.card-stars' in l][0]
        self.assertIn('var(--amber)', stars)
        self.assertNotIn('amber-ink', stars)

    def test_pending_is_not_confusable_with_the_grey_empty(self):
        tokens = read('templates', '_tokens.html')
        light = tokens.split('[data-theme="dark"]')[0]
        colour = re.search(r'--pending:\s*(#[0-9a-fA-F]{6})', light).group(1)
        self.assertNotEqual(colour.lower(), '#e2e3e6')


class ScoreBlockTests(Base):
    """7.4, 7.5, 7.6 — блок оценивания."""

    def _html(self):
        return self.client.get(
            reverse('teacher:group_review_submission',
                    args=[self.group.pk, self.sub.pk])).content.decode()

    def test_says_the_score_is_not_set(self):
        html = self._html()
        self.assertIn('балл не поставлен', html)
        self.assertIn('максимум 3', html)

    def test_no_dash_over_the_maximum(self):
        html = self._html()
        head = html.split('class="rv-grade-head"')[1].split('<label')[0]
        self.assertNotIn('>—<', head)

    def test_a_set_score_is_shown_as_a_number(self):
        from problems.models import TeacherFeedback

        TeacherFeedback.objects.create(submission=self.sub,
                                       score=Decimal('1.5'),
                                       reviewed_by=self.tutor)
        html = self._html()
        self.assertNotIn('балл не поставлен', html)
        self.assertIn('1.5', html.split('class="rv-grade-head"')[1][:700])

    def test_eyes_link_is_not_a_button_anymore(self):
        html = self._html()
        actions = html.split('rv-actions')[1].split('</div>')[0]
        self.assertIn('rv-eyes', actions)
        self.assertNotIn('k-btn--quiet', actions)

    def test_eyes_link_still_leads_somewhere(self):
        html = self._html()
        self.assertIn(reverse('teacher:student_work_review',
                              args=[self.group.pk, self.work.pk,
                                    self.student.pk]), html)

    def test_presets_on_a_three_point_task(self):
        self.assertEqual([p['label'] for p in score_presets(3)],
                         ['0', '1,5', '3'])
        self.assertEqual([p['value'] for p in score_presets(3)],
                         ['0', '1.5', '3'])

    def test_comma_typed_by_hand_is_accepted(self):
        from teacher.views import normalize_decimal

        self.assertEqual(normalize_decimal('1,5'), '1.5')
        response = self.client.post(
            reverse('teacher:group_review_submission',
                    args=[self.group.pk, self.sub.pk]),
            {'score': '1,5', 'comment': '', 'go': 'list'})
        self.assertIn(response.status_code, (200, 302))
        self.sub.refresh_from_db()
        self.assertEqual(float(self.sub.feedback.score), 1.5)

    def test_the_field_is_textual_so_the_comma_survives(self):
        page = read('teacher', 'templates', 'teacher', 'review.html')
        # ⚠️ Смотрим САМ ТЕГ: слова `type="number"` есть и в комментарии
        # рядом — там объясняется, почему поле НЕ числовое.
        field = re.search(r'<input\s+[^>]*name="score"[^>]*>', page).group(0)
        self.assertIn('inputmode="decimal"', field)
        self.assertNotIn('type="number"', field)


class StudentViewCaptionTests(Base):
    """7.7 — под крупным баллом больше нет второго объяснения."""

    def _html(self):
        return self.client.get(
            reverse('teacher:student_work_review',
                    args=[self.group.pk, self.work.pk,
                          self.student.pk])).content.decode()

    def test_caption_is_short(self):
        html = self._html()
        # ⚠️ У блока появился признак обновления `data-wr-cap` (ревью
        # 15.08, фаза 6) — ищем по классу, не требуя закрывающей скобки.
        caption = re.search(r'class="wr-cap"[^>]*>(.*?)</div>', html, re.S)
        self.assertIsNotNone(caption)
        text = re.sub(r'\s+', ' ', caption.group(1)).strip()
        self.assertNotIn('всего в работе', text)

    def test_the_plate_still_explains_it(self):
        from problems.models import TeacherFeedback

        # Одна задача проверена, вторая нет — результат предварительный.
        from problems.models import AssignmentItem, Submission
        second = AssignmentItem.objects.create(
            assignment=self.work, order=1,
            catalog_problem=make_problem('Вторая'), points=Decimal('5'))
        Submission.objects.create(student=self.student, assignment=self.work,
                                  problem_item=second, status='submitted',
                                  submitted_at=self.now, submitted_answer='7')
        TeacherFeedback.objects.create(submission=self.sub,
                                       score=Decimal('3'),
                                       reviewed_by=self.tutor)
        html = self._html()
        self.assertIn('предварительный результат', html)
        self.assertIn('по проверенным задачам', html)
