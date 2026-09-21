"""Разбор сданной попытки: змейка цепочкой, арифметика тестов, процентиль, чужой и свой
взгляд на результат, перенос гостевой попытки, «дорешать вне зачёта».

Нумерация `test_NN_…` — сценарии из задания сессии 3; остальные тесты — рядом.
Змейка здесь настоящая: ответ №N+1 начинается со второй буквы ответа №N, иначе
разрыв цепи не с чем сравнивать.
"""
import itertools
import json
from datetime import timedelta
from decimal import Decimal as D

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from vp import review, scoring, views
from vp.loader import chain_letters
from vp.models import VPAnswer, VPAttempt, VPItem
from vp.tests.helpers import make_published

User = get_user_model()

ALPHABET = 'абвгдежзиклмнопрстуфцчшэю'          # 25 букв; «х» и «я» здесь нет — ими «ломаем» цепь
TAIL = 'фъщ'          # хвост слов змейки: бессмыслица, чтобы не совпасть с текстом самого сайта
_codes = itertools.count(1)


def chain_word(number):
    """Эталон задания змейки: вторая буква №N — первая буква №N+1."""
    return ALPHABET[(number - 1) % 25] + ALPHABET[number % 25] + TAIL


def make_review_variant(slug='vp-rv'):
    """Опубликованный вариант со связной змейкой и решениями у части тестов."""
    variant = make_published(slug)
    for item in variant.items.filter(block='snake'):
        item.answer = chain_word(item.number)
        item.chain_first, item.chain_second = chain_letters(item.answer)
        item.save()
    for number in (37, 42, 44):
        item = variant.items.get(number=number)
        item.solution = f'Разбор-{number}: подставьте числа.'
        item.save()
    return variant


def right_answers(variant):
    """Полностью верные ответы на все 44 задания: номер → raw."""
    result = {}
    for item in variant.items.all():
        result[item.number] = (item.answer if item.kind == 'short_text'
                               else item.correct[0] if item.kind == 'single' else list(item.correct))
    return result


def new_code():
    return f'rv-{next(_codes):06d}'


def submit(variant, answers, **fields):
    """Сданная попытка с ответами `answers` (номер → raw); остальные — пустые."""
    now = timezone.now()
    fields.setdefault('session_key', new_code())
    attempt = VPAttempt.objects.create(
        variant=variant, public_code=new_code(), max_score=variant.max_score,
        expires_at=now + timedelta(minutes=30), **fields)
    by_number = {i.number: i for i in variant.items.all()}
    for number, raw in answers.items():
        VPAnswer.objects.create(attempt=attempt, item=by_number[number], raw=raw)
    views._finalize(attempt, auto=False)
    attempt.refresh_from_db()
    return attempt


def owner_client(attempt):
    """Клиент, который «помнит» попытку: код лежит в его сессии, как после старта."""
    client = Client()
    session = client.session
    session['vp_attempts'] = [attempt.public_code]
    session.save()
    return client


def cohort_attempt(variant, score, **fields):
    """Сданная попытка без ответов — только счёт, для тестов процентиля."""
    fields.setdefault('session_key', new_code())
    fields.setdefault('with_timer', True)
    now = timezone.now()
    return VPAttempt.objects.create(
        variant=variant, public_code=new_code(), score=D(score), max_score=D('100'),
        submitted_at=now, expires_at=now, **fields)


def set_started(attempt, moment):
    VPAttempt.objects.filter(pk=attempt.pk).update(started_at=moment)


class ReviewBase(TestCase):
    def setUp(self):
        self.variant = make_review_variant()
        self.item = {i.number: i for i in self.variant.items.all()}
        key = review._cohort_key(self.variant.pk)
        cache.delete(key)
        self.addCleanup(cache.delete, key)


# ------------------------------------------------------ арифметика тестов

class ExplainItemTests(ReviewBase):
    def test_03_multi_two_right_and_one_extra(self):
        """3 балла, верных 2 из 5: два верных и один неверный → 3,00 − 1,00 = 2,00."""
        item = self.item[37]
        self.assertEqual((item.points, item.correct, item.penalty), (D('3'), [1, 3], True))
        e = scoring.explain_item(item, [1, 3, 2])
        self.assertEqual(e['kind'], 'share')
        self.assertEqual((e['correct_total'], e['correct_hit'], e['wrong_total'], e['wrong_hit']),
                         (2, 2, 3, 1))
        self.assertEqual((e['points'], e['gain'], e['loss'], e['score']),
                         (D('3.00'), D('3.00'), D('1.00'), D('2.00')))
        self.assertFalse(e['clamped'])

    def test_04_penalty_below_zero_is_clamped(self):
        """Отмечены одни неверные: −3,00 поднято до 0,00 — клэмп сработал по-настоящему."""
        e = scoring.explain_item(self.item[37], [2, 4, 5])
        self.assertEqual((e['gain'], e['loss'], e['before_clamp'], e['score']),
                         (D('0.00'), D('3.00'), D('-3.00'), D('0.00')))
        self.assertTrue(e['clamped'])

    def test_04b_all_five_marked_is_exactly_zero_without_clamp(self):
        """Все пять при двух верных: 3,00 − 3,00 = 0,00. Ниже нуля не ушло — клэмпа нет."""
        e = scoring.explain_item(self.item[37], [1, 2, 3, 4, 5])
        self.assertEqual((e['gain'], e['loss'], e['score']), (D('3.00'), D('3.00'), D('0.00')))
        self.assertFalse(e['clamped'])

    def test_binary_and_blank_kinds(self):
        self.assertEqual(scoring.explain_item(self.item[1], chain_word(1)),
                         {'kind': 'binary', 'score': D('2.00'), 'is_correct': True})
        self.assertEqual(scoring.explain_item(self.item[43], 5),
                         {'kind': 'binary', 'score': D('0.00'), 'is_correct': False})
        for number, raw in ((1, None), (1, '  '), (37, []), (43, None)):
            with self.subTest(number=number, raw=raw):
                self.assertEqual(scoring.explain_item(self.item[number], raw),
                                 {'kind': 'blank', 'score': D('0.00'), 'is_correct': None})

    def test_explanation_never_disagrees_with_the_score(self):
        """Разбор и подсчёт берут доли из одной функции: по всем 31 непустым выборам из
        пяти вариантов балл разбора равен баллу подсчёта, а без клэмпа gain − loss = score."""
        item = self.item[36]
        for size in range(1, 6):
            for chosen in itertools.combinations(range(1, 6), size):
                e = scoring.explain_item(item, list(chosen))
                score, _ = scoring.score_item(item, list(chosen))
                self.assertEqual(e['score'], score, chosen)
                if e['clamped']:
                    self.assertEqual(score, D('0.00'), chosen)
                else:
                    self.assertEqual(e['gain'] - e['loss'], score, chosen)


# ------------------------------------------------------------------ змейка

class ChainReviewTests(ReviewBase):
    def wrong_fourth(self):
        answers = right_answers(self.variant)
        # Первая буква верная, вторая — «х»: ни один эталон на «х» не начинается.
        answers[4] = chain_word(4)[0] + 'х' + TAIL
        return submit(self.variant, answers)

    def test_01_one_wrong_answer_breaks_exactly_one_link(self):
        rows = {r['number']: r for r in review.chain_review(self.wrong_fourth())}
        self.assertTrue(rows[4]['broke_chain'])
        self.assertFalse(rows[3]['broke_chain'])
        self.assertFalse(rows[5]['broke_chain'])
        self.assertEqual([n for n, r in rows.items() if r['broke_chain']], [4])
        self.assertIs(rows[4]['is_correct'], False)
        self.assertEqual(rows[4]['right'], chain_word(4))
        self.assertEqual((rows[4]['my_letter'], rows[4]['link_letter']), ('х', chain_word(5)[0]))

    def test_02_unanswered_does_not_break_the_chain(self):
        answers = right_answers(self.variant)
        del answers[6]
        rows = {r['number']: r for r in review.chain_review(submit(self.variant, answers))}
        self.assertTrue(rows[6]['blank'])
        self.assertFalse(rows[6]['broke_chain'])
        self.assertEqual(rows[6]['right'], '')                      # эталона у пустого нет
        self.assertEqual(rows[6]['statement'], self.item[6].statement)
        self.assertFalse(any(r['broke_chain'] for r in rows.values()))

    def test_rows_are_ordered_and_the_last_has_no_link(self):
        rows = review.chain_review(submit(self.variant, right_answers(self.variant)))
        self.assertEqual([r['number'] for r in rows], list(range(1, 31)))
        self.assertEqual(rows[-1]['link_letter'], '')
        self.assertEqual(rows[0]['link_letter'], chain_word(2)[0])
        self.assertTrue(all(r['is_correct'] for r in rows))

    def test_letters_ignore_case_yo_and_padding(self):
        """«Ё» = «е», регистр и пробелы не мешают: вторая буква та же, разрыва нет."""
        item = self.item[2]
        item.answer = 'аё' + TAIL
        item.chain_first, item.chain_second = chain_letters(item.answer)
        item.save()
        nxt = self.item[3]
        nxt.chain_first = 'е'
        nxt.save()
        answers = right_answers(self.variant)
        answers[2] = '  АЁ' + TAIL.upper() + ' '
        rows = {r['number']: r for r in review.chain_review(submit(self.variant, answers))}
        self.assertFalse(rows[2]['broke_chain'])
        self.assertEqual(rows[2]['my_letter'], 'е')

    def test_one_letter_answer_has_no_second_letter_and_breaks(self):
        answers = right_answers(self.variant)
        answers[8] = 'а'
        rows = {r['number']: r for r in review.chain_review(submit(self.variant, answers))}
        self.assertTrue(rows[8]['broke_chain'])
        self.assertEqual(rows[8]['my_letter'], '')

    def test_05_row_scores_add_up_to_the_attempt_score(self):
        answers = right_answers(self.variant)
        answers[4] = chain_word(4)[0] + 'х' + TAIL          # неверный в змейке
        del answers[9]                                        # пустой в змейке
        answers[33] = 1                                       # неверный «один верный»
        answers[37] = [1, 3, 2]                               # долевой со штрафом → 2,00
        answers[38] = [2, 4, 5]                               # клэмп → 0,00
        del answers[40]                                       # пустой тест
        attempt = submit(self.variant, answers)
        rows = review.chain_review(attempt) + review.tests_review(attempt)
        self.assertEqual(len(rows), 44)
        self.assertEqual(sum(r['score'] for r in rows), attempt.score)
        self.assertEqual(attempt.score, D('100') - D('2') - D('2') - D('2') - D('3') - D('1') - D('3'))


class TestsReviewTests(ReviewBase):
    def test_answered_rows_carry_marks_and_explanation(self):
        attempt = submit(self.variant, {**right_answers(self.variant), 37: [1, 3, 2]})
        row = next(r for r in review.tests_review(attempt) if r['number'] == 37)
        self.assertEqual((row['chosen'], row['correct'], row['tone']), ([1, 2, 3], [1, 3], 'mid'))
        flags = {o['n']: (o['chosen'], o['right']) for o in row['options']}
        self.assertEqual(flags[2], (True, False))
        self.assertEqual(flags[3], (True, True))
        self.assertEqual(row['explain']['score'], D('2.00'))
        self.assertIn('Разбор-37', row['solution'])

    def test_unanswered_rows_hold_no_answer_at_all(self):
        answers = right_answers(self.variant)
        del answers[37], answers[44]
        attempt = submit(self.variant, answers)
        rows = {r['number']: r for r in review.tests_review(attempt)}
        for number in (37, 44):
            row = rows[number]
            self.assertTrue(row['blank'])
            self.assertEqual(row['tone'], 'blank')
            self.assertEqual((row['correct'], row['solution']), ([], ''))
            self.assertIsNone(row['explain'])
            self.assertFalse(any(o['right'] or o['chosen'] for o in row['options']))


# ------------------------------------------------------------- процентиль

class PercentileTests(ReviewBase):
    def cohort(self, lower, higher, mine=50):
        """Моя попытка + `lower` чужих ниже неё + `higher` выше; все — разные люди."""
        me = cohort_attempt(self.variant, mine)
        for i in range(lower):
            cohort_attempt(self.variant, 10 + i)
        for i in range(higher):
            cohort_attempt(self.variant, 60 + i)
        return me

    def test_06_share_of_people_strictly_below(self):
        me = self.cohort(lower=15, higher=9)                  # всего 25 человек
        self.assertEqual(review.percentile(me), 60)

    def test_strictly_less_ties_do_not_count(self):
        me = self.cohort(lower=10, higher=9)
        for _ in range(5):
            cohort_attempt(self.variant, 50)                  # ровно мой балл: «ниже» не считается
        self.assertEqual(review.percentile(me), 10 * 100 // 25)

    def test_07_none_when_fewer_than_twenty_people(self):
        me = self.cohort(lower=10, higher=8)                  # 19 человек
        self.assertIsNone(review.percentile(me))
        self.assertIsNone(review.comparison(me))
        cohort_attempt(self.variant, 70)                      # 20-й — граница включена
        cache.delete(review._cohort_key(self.variant.pk))
        self.assertEqual(review.percentile(me), 50)

    def test_08_one_person_counts_once_and_by_the_earliest_attempt(self):
        base = timezone.now() - timedelta(days=3)
        for i in range(1, 20):                                # 19 гостей: 1…19
            cohort_attempt(self.variant, i)
        user = User.objects.create_user('vp_diligent', password='p12345')
        trio = [cohort_attempt(self.variant, score, user=user, session_key='')
                for score in (50, 5, 6)]                      # самая ранняя — 50, две другие ниже
        for offset, attempt in enumerate(trio):
            set_started(attempt, base + timedelta(hours=offset))
        me = cohort_attempt(self.variant, 30)
        # Люди: 19 гостей + усердный + я = 21. Ниже 30: 19 гостей (его самая ранняя, 50, — не ниже).
        self.assertEqual(review.percentile(me), 19 * 100 // 21)
        self.assertEqual(len(cache.get(review._cohort_key(self.variant.pk))), 21)

    def test_guest_key_is_the_person_and_keyless_attempts_are_separate(self):
        base = timezone.now() - timedelta(days=1)
        first = cohort_attempt(self.variant, 90, session_key='same-browser')
        again = cohort_attempt(self.variant, 1, session_key='same-browser')
        set_started(first, base)
        set_started(again, base + timedelta(hours=1))
        for i in range(2):
            cohort_attempt(self.variant, 20 + i, session_key='')      # без ключа: каждый — сам по себе
        self.assertEqual(review._load_cohort(self.variant), [D('20'), D('21'), D('90')])

    def test_only_full_timed_submitted_attempts_form_the_cohort(self):
        me = self.cohort(lower=15, higher=9)
        cohort_attempt(self.variant, 5, with_timer=False)     # без таймера
        cohort_attempt(self.variant, 5, mode='block')         # один блок
        VPAttempt.objects.create(variant=self.variant, public_code=new_code(),
                                 session_key=new_code(), score=D('5'))  # не сдана
        self.assertEqual(review.percentile(me), 60)

    def test_attempt_without_timer_or_block_gets_no_percentile(self):
        self.cohort(lower=15, higher=9)
        self.assertIsNone(review.percentile(cohort_attempt(self.variant, 50, with_timer=False)))
        self.assertIsNone(review.percentile(cohort_attempt(self.variant, 50, mode='block')))

    def test_the_cohort_is_cached_for_five_minutes(self):
        me = self.cohort(lower=15, higher=9)
        self.assertEqual(review.percentile(me), 60)
        cohort_attempt(self.variant, 55)                      # новый человек — кэш его ещё не знает
        self.assertEqual(review.percentile(me), 60)
        self.assertEqual(review.COHORT_TTL, 300)
        self.assertEqual(len(cache.get('vp:pct:%d' % self.variant.pk)), 25)
        cache.delete('vp:pct:%d' % self.variant.pk)
        self.assertEqual(review.percentile(me), 15 * 100 // 26)

    def test_comparison_gives_median_and_size(self):
        me = self.cohort(lower=15, higher=9)
        info = review.comparison(me)
        self.assertEqual((info['percent'], info['count']), (60, 25))
        self.assertEqual(info['median'], D('22'))            # 13-й из 25: 15 ниже меня заняли места 1–15


# --------------------------------------------------- свой и чужой результат

class ResultViewTests(ReviewBase):
    def setUp(self):
        super().setUp()
        answers = right_answers(self.variant)
        answers[4] = chain_word(4)[0] + 'х' + TAIL
        answers[37] = [1, 3, 2]
        answers[38] = [2, 4, 5]
        del answers[9], answers[44]
        self.attempt = submit(self.variant, answers)
        self.url = reverse('vp:result', args=[self.attempt.public_code])
        self.owner = owner_client(self.attempt)

    def html(self, client):
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_owner_sees_the_full_review(self):
        html = self.html(self.owner)
        self.assertIn('Змейка целиком', html)
        self.assertIn('здесь цепь порвалась: следующий ответ должен был начинаться на «%s»'
                      % chain_word(5)[0], html)
        self.assertIn('у вас вторая буква «х»', html)
        self.assertIn(chain_word(4), html)                                # эталон показан
        self.assertIn('3 × 2/2 − 3 × 1/3 = 3,00 − 1,00 = 2,00', html)
        self.assertIn('3 × 0/2 − 3 × 3/3 = 0,00 − 3,00 = −3,00 → 0,00', html)   # клэмп
        self.assertIn('Разбор-37', html)
        self.assertIn('Поделиться результатом', html)
        self.assertEqual(html.count('Дорешать вне зачёта</button>'), 2)   # №9 и №44 пустые
        self.assertIn('На балл не влияет, он уже записан.', html)

    def test_blank_items_keep_their_answers_out_of_the_page(self):
        html = self.html(self.owner)
        self.assertNotIn('Разбор-44', html)                               # решение пустого №44
        self.assertNotIn(chain_word(9), html)                             # эталон пустого №9

    def test_09_stranger_sees_the_score_but_not_a_single_answer(self):
        theirs = self.html(Client())
        self.assertRegex(theirs, r'<b>%s</b><span>из 100</span>' % self.attempt.score.normalize())
        self.assertIn('Участник', theirs)
        for number, item in self.item.items():
            if item.kind == 'short_text':
                self.assertNotIn(item.answer, theirs, f'эталон №{number} утёк')
        for marker in ('Разбор-37', 'Разбор-42', 'Разбор-44', 'эталон', 'Змейка целиком',
                       'Откуда взялись баллы', 'вариант 3', 'class="vp-tag', 'class="vp-topt', 'class="vp-crow', 'class="vp-clink',
                       'id="vp-chain"', 'id="vp-tests"', 'data-practice',
                       'Дорешать', 'result.js', 'ваш выбор', 'цепь порвалась'):
            self.assertNotIn(marker, theirs, marker)
        self.assertIn('Пройти этот же вариант', theirs)
        self.assertIn(reverse('vp:intro', args=[self.variant.slug]), theirs)
        self.assertNotIn('Поделиться', theirs)
        # Положительный контроль: у владельца всё это на месте, тест не «зелёный впустую».
        mine = self.html(self.owner)
        for marker in ('Разбор-37', 'эталон', chain_word(4), 'class="vp-tag vp-tag--right"',
                       'class="vp-crow', 'class="vp-clink', 'id="vp-chain"'):
            self.assertIn(marker, mine, marker)

    def test_stranger_gets_no_review_rows_in_the_context(self):
        response = Client().get(self.url)
        for key in ('chain', 'tests', 'practice_url'):
            self.assertNotIn(key, response.context, key)
        self.assertFalse(response.context['is_owner'])

    def test_signed_in_author_is_not_named_at_all(self):
        """Всем посторонним — «Участник», вошёл автор или нет: логин школьника публичным не бывает."""
        user = User.objects.create_user('vp_nick', password='p12345',
                                        first_name='Пётр', last_name='Тайный')
        attempt = submit(self.variant, {}, user=user, session_key='')
        stranger = Client()
        stranger.force_login(User.objects.create_user('vp_looker', password='p12345'))
        for client in (Client(), stranger):
            html = client.get(reverse('vp:result', args=[attempt.public_code])).content.decode()
            for private in ('vp_nick', 'Пётр', 'Тайный'):
                self.assertNotIn(private, html, private)
            self.assertIn('Участник', html)

    def test_signed_in_non_owner_gets_the_reduced_view_of_any_attempt(self):
        """Вошедший — не значит владелец: чужая попытка, гостевая или с хозяином, — как у чужого."""
        other = Client()
        other.force_login(User.objects.create_user('vp_bystander', password='p12345'))
        owned = submit(self.variant, right_answers(self.variant),
                       user=User.objects.create_user('vp_host', password='p12345'), session_key='')
        for attempt in (self.attempt, owned):
            html = other.get(reverse('vp:result', args=[attempt.public_code])).content.decode()
            for marker in ('Змейка целиком', 'эталон', 'id="vp-chain"', 'data-practice', chain_word(4)):
                self.assertNotIn(marker, html, marker)
        self.assertEqual(other.post(reverse('vp:practice', args=[owned.public_code]),
                                    json.dumps({'item': 1, 'raw': 'x'}),
                                    content_type='application/json').status_code, 404)

    def test_share_note_says_the_link_shows_the_score_without_name_and_answers(self):
        """Подпись у «Поделиться» одна для гостя и для вошедшего: имени в ссылке нет ни у кого."""
        user = User.objects.create_user('vp_shared', password='p12345')
        attempt = submit(self.variant, {}, user=user, session_key='')
        signed_in = Client()
        signed_in.force_login(user)
        for html in (self.html(self.owner),
                     signed_in.get(reverse('vp:result', args=[attempt.public_code])).content.decode()):
            self.assertIn('показывает балл без имени и без ваших ответов', html)
            self.assertNotIn('логин', html)

    def test_no_comparison_block_below_twenty_people(self):
        for i in range(10):
            cohort_attempt(self.variant, 10 + i)
        for client in (self.owner, Client()):
            self.assertNotIn('прошедших этот вариант', self.html(client))

    def test_comparison_block_with_scale_median_and_size(self):
        for i in range(24):
            cohort_attempt(self.variant, 10 + i)              # все ниже моих 100−…; я — 25-я
        html = self.html(self.owner)
        percent = review.percentile(self.attempt)
        self.assertGreater(percent, 0)
        self.assertIn('Выше, чем у %d%% прошедших этот вариант' % percent, html)
        self.assertIn('vp-cmp-you', html)
        self.assertIn('медиана', html)
        self.assertIn('По первым попыткам 25 человек', html)
        self.assertIn('Выше, чем у', self.html(Client()))     # чужому — та же полоса, без «вы»
        self.assertNotIn('>вы<', self.html(Client()))

    def test_guest_owner_is_offered_to_keep_progress_and_a_signed_in_owner_is_not(self):
        self.assertIn('Сохранить прогресс', self.html(self.owner))
        user = User.objects.create_user('vp_signed', password='p12345')
        attempt = submit(self.variant, {}, user=user, session_key='')
        client = Client()
        client.force_login(user)
        url = reverse('vp:result', args=[attempt.public_code])
        html = client.get(url).content.decode()
        self.assertIn('Змейка целиком', html)                 # он владелец — разбор его
        self.assertNotIn('Сохранить прогресс', html)

    def test_unpublished_variant_offers_no_repeat_link_to_strangers(self):
        self.variant.is_published = False
        self.variant.save()
        self.assertNotIn('Пройти этот же вариант', self.html(Client()))


# -------------------------------------------------------- перенос на аккаунт

class AdoptGuestAttemptsTests(TestCase):
    def setUp(self):
        self.variant = make_published('vp-adopt')

    def start(self, client):
        response = client.post(reverse('vp:start', args=[self.variant.slug]), {'with_timer': '1'})
        self.assertEqual(response.status_code, 302)
        return VPAttempt.objects.order_by('-id').first()

    def test_10_guest_attempt_moves_to_the_account_on_login(self):
        guest = Client()
        attempt = self.start(guest)
        old_key = attempt.session_key
        self.assertIsNone(attempt.user_id)
        user = User.objects.create_user('vp_mover', password='p12345')
        guest.force_login(user)
        attempt.refresh_from_db()
        self.assertEqual(attempt.user_id, user.pk)
        # Ключ сессии при входе новый — потому переносим по кодам из сессии, а не по ключу.
        self.assertNotEqual(guest.session.session_key, old_key)
        self.assertEqual(guest.get(reverse('vp:take', args=[attempt.public_code])).status_code, 200)
        self.assertEqual(Client().get(reverse('vp:take', args=[attempt.public_code])).status_code, 404)

    def test_move_works_on_the_first_login_after_registration(self):
        guest = Client()
        attempt = self.start(guest)
        password = 'Zx9-kQ7-vB2-mLp-41'
        response = guest.post(reverse('register'), {
            'username': 'vp_fresh', 'password1': password, 'password2': password,
            'role': 'student', 'consent': 'on'})
        self.assertEqual(response.status_code, 302, response.content[:400])
        attempt.refresh_from_db()
        self.assertEqual(attempt.user.username, 'vp_fresh')

    def test_only_this_browsers_attempts_move(self):
        mine, other = Client(), Client()
        mine_attempt, other_attempt = self.start(mine), self.start(other)
        mine.force_login(User.objects.create_user('vp_only_mine', password='p12345'))
        mine_attempt.refresh_from_db()
        other_attempt.refresh_from_db()
        self.assertIsNotNone(mine_attempt.user_id)
        self.assertIsNone(other_attempt.user_id)

    def test_an_attempt_that_already_has_an_owner_is_not_reassigned(self):
        first = User.objects.create_user('vp_first', password='p12345')
        second = User.objects.create_user('vp_second', password='p12345')
        client = Client()
        client.force_login(first)
        attempt = self.start(client)
        self.assertEqual(attempt.user_id, first.pk)
        client.force_login(second)
        attempt.refresh_from_db()
        self.assertEqual(attempt.user_id, first.pk)

    def test_login_with_no_vp_attempts_is_untouched(self):
        Client().force_login(User.objects.create_user('vp_none', password='p12345'))
        self.assertEqual(VPAttempt.objects.count(), 0)


# ------------------------------------------------------ дорешать вне зачёта

class PracticeCheckTests(ReviewBase):
    def setUp(self):
        super().setUp()
        answers = right_answers(self.variant)
        del answers[27], answers[33], answers[40]             # пустые: змейка, «один верный», выбор
        self.attempt = submit(self.variant, answers)
        self.owner = owner_client(self.attempt)
        self.url = reverse('vp:practice', args=[self.attempt.public_code])

    def ask(self, item, raw, client=None, url=None):
        return (client or self.owner).post(
            url or self.url, json.dumps({'item': item, 'raw': raw}), content_type='application/json')

    def snapshot(self):
        return (list(VPAnswer.objects.order_by('pk').values_list('pk', 'raw', 'score', 'is_correct', 'updated_at')),
                VPAttempt.objects.values_list('score', 'submitted_at', 'is_auto_submitted').get(pk=self.attempt.pk))

    def test_11_checks_on_the_fly_and_writes_nothing(self):
        before, count = self.snapshot(), VPAnswer.objects.count()
        cases = [(27, chain_word(27), True, chain_word(27)),
                 (27, 'совсем не то', False, chain_word(27)),
                 (33, 3, True, '3. вариант 3'),
                 (33, 1, False, '3. вариант 3'),
                 (40, [1, 3], True, '1. вариант 1; 3. вариант 3'),
                 (40, [1], False, '1. вариант 1; 3. вариант 3')]
        for item, raw, is_correct, right in cases:
            with self.subTest(item=item, raw=raw):
                response = self.ask(item, raw)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json(), {'is_correct': is_correct, 'right': right})
                self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(VPAnswer.objects.count(), count)
        self.assertEqual(self.snapshot(), before)
        # Пустые задания остались пустыми, балл — прежним.
        self.assertIsNone(VPAnswer.objects.get(attempt=self.attempt, item__number=27).raw)
        self.assertEqual(self.attempt.score, D('100') - D('2') - D('2') - D('3'))

    def test_12_unsubmitted_attempt_is_404(self):
        now = timezone.now()
        fresh = VPAttempt.objects.create(
            variant=self.variant, public_code=new_code(), session_key=new_code(),
            expires_at=now + timedelta(minutes=30))
        client = owner_client(fresh)
        url = reverse('vp:practice', args=[fresh.public_code])
        self.assertEqual(self.ask(1, 'что-то', client=client, url=url).status_code, 404)
        self.assertEqual(VPAnswer.objects.filter(attempt=fresh).count(), 0)

    def test_expired_but_unsubmitted_attempt_is_still_404_and_is_not_closed(self):
        """Просроченную несданную эта ручка не сдаёт за человека: она ничего не пишет."""
        old = VPAttempt.objects.create(
            variant=self.variant, public_code=new_code(), session_key=new_code(),
            expires_at=timezone.now() - timedelta(hours=2))
        client = owner_client(old)
        self.assertEqual(self.ask(1, 'x', client=client,
                                  url=reverse('vp:practice', args=[old.public_code])).status_code, 404)
        old.refresh_from_db()
        self.assertIsNone(old.submitted_at)

    def test_stranger_and_signed_in_other_user_get_404(self):
        for client in (Client(), Client()):
            self.assertEqual(self.ask(27, chain_word(27), client=client).status_code, 404)
        other = Client()
        other.force_login(User.objects.create_user('vp_stranger', password='p12345'))
        self.assertEqual(self.ask(27, chain_word(27), client=other).status_code, 404)

    def test_bad_requests_are_400_and_write_nothing(self):
        before = self.snapshot()
        self.assertEqual(self.ask(99, 'x').status_code, 400)          # нет такого задания
        self.assertEqual(self.ask('27', 'x').status_code, 400)        # номер — не число
        self.assertEqual(self.ask(27, '   ').status_code, 400)        # пустой ответ
        self.assertEqual(self.ask(33, 9).status_code, 400)            # чужой номер варианта
        self.assertEqual(self.ask(27, 'я' * 300).status_code, 400)    # слишком длинный
        self.assertEqual(self.owner.post(self.url, 'не json', content_type='application/json').status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_get_is_not_allowed_and_csrf_is_enforced(self):
        self.assertEqual(self.owner.get(self.url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        session = strict.session
        session['vp_attempts'] = [self.attempt.public_code]
        session.save()
        response = strict.post(self.url, json.dumps({'item': 27, 'raw': 'x'}), content_type='application/json')
        self.assertEqual(response.status_code, 403)
