"""
Тесты статистики по вопросам Econ Rush (Фаза 1).

Главный тест фазы — `test_pool_rebuild_does_not_reset_stats`: он объясняет,
почему статистика не лежит на GameQuestion. Пул это КЭШ: `build_game_pool`
сносит все несгенерированные строки и создаёт заново с НОВЫМИ id. Счётчики,
привязанные к строке кэша, умерли бы при первой же пересборке.
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from game import config
from game.models import ArchetypeStat, BankQuestionStat, GameQuestion
from game import stats as stats_mod
from problems.models import Problem, ProblemPart

User = get_user_model()


def make_problem(**kw):
    defaults = dict(
        title='Тест', statement='Утверждение про спрос.',
        problem_type='тест: верно/неверно', answer='а',
        status=Problem.Status.PUBLISHED, needs_quality_review=False)
    defaults.update(kw)
    return Problem.objects.create(**defaults)


def make_question(problem=None, part=None, **kw):
    defaults = dict(
        question_type='boolean', question='Верно ли, что спрос падает?',
        options=['Верно', 'Неверно'], correct_index=0, difficulty=3,
        topics=['Спрос и предложение'], lang='ru')
    defaults.update(kw)
    return GameQuestion.objects.create(problem=problem, part=part, **defaults)


class RecordAnswerTests(TestCase):
    """Счётчики: что куда попадает."""

    def setUp(self):
        self.p = make_problem()
        self.gq = make_question(self.p)

    def test_correct_and_wrong_go_to_their_counters(self):
        stats_mod.record_answer(self.gq, 'correct', 1200)
        stats_mod.record_answer(self.gq, 'wrong', 800)
        st = BankQuestionStat.objects.get(problem=self.p, part=None)
        self.assertEqual((st.shown, st.correct, st.wrong, st.skipped),
                         (2, 1, 1, 0))
        self.assertEqual(st.total_ms, 2000)
        self.assertEqual(st.attempts, 2)
        self.assertAlmostEqual(st.p_correct, 0.5)

    def test_skip_does_not_spoil_the_share(self):
        """Пропуск — не ответ: он идёт в свой счётчик и долю верных не портит."""
        stats_mod.record_answer(self.gq, 'correct', 0)
        for _ in range(9):
            stats_mod.record_answer(self.gq, 'skip', 0)
        st = BankQuestionStat.objects.get(problem=self.p)
        self.assertEqual(st.shown, 10)
        self.assertEqual(st.skipped, 9)
        self.assertEqual(st.attempts, 1)
        self.assertEqual(st.p_correct, 1.0)

    def test_part_is_part_of_the_key(self):
        """Вопрос из подпункта — своя строка статистики, не общая с задачей."""
        part = ProblemPart.objects.create(problem=self.p, label='а',
                                          statement='Первый подпункт')
        gq2 = make_question(self.p, part)
        stats_mod.record_answer(self.gq, 'correct')
        stats_mod.record_answer(gq2, 'wrong')
        self.assertEqual(BankQuestionStat.objects.count(), 2)
        self.assertEqual(
            BankQuestionStat.objects.get(problem=self.p, part=None).correct, 1)
        self.assertEqual(
            BankQuestionStat.objects.get(problem=self.p, part=part).wrong, 1)

    def test_generated_question_counts_by_archetype(self):
        """У сгенерированного параметры каждый раз новые — считаем по архетипу."""
        g1 = make_question(None, is_generated=True, generator_key='monopoly')
        g2 = make_question(None, is_generated=True, generator_key='monopoly')
        stats_mod.record_answer(g1, 'correct')
        stats_mod.record_answer(g2, 'wrong')
        self.assertEqual(BankQuestionStat.objects.count(), 0)
        st = ArchetypeStat.objects.get(generator_key='monopoly')
        self.assertEqual((st.shown, st.correct, st.wrong), (2, 1, 1))

    def test_unknown_outcome_is_ignored(self):
        self.assertIsNone(stats_mod.record_answer(self.gq, 'мусор'))
        self.assertEqual(BankQuestionStat.objects.count(), 0)


class ThresholdTests(TestCase):
    """Порог показа: процент на пяти ответах — шум, а не сложность."""

    def setUp(self):
        self.p = make_problem()
        self.gq = make_question(self.p)

    def test_below_threshold_nothing_is_shown(self):
        for _ in range(config.STATS_MIN_ATTEMPTS - 1):
            stats_mod.record_answer(self.gq, 'correct')
        self.assertIsNone(stats_mod.public_stat(stats_mod.get_stat(self.gq)))

    def test_at_threshold_the_percent_appears(self):
        for _ in range(config.STATS_MIN_ATTEMPTS):
            stats_mod.record_answer(self.gq, 'correct')
        pub = stats_mod.public_stat(stats_mod.get_stat(self.gq))
        self.assertEqual(pub['attempts'], config.STATS_MIN_ATTEMPTS)
        self.assertEqual(pub['p_correct'], 1.0)

    def test_skips_do_not_count_towards_the_threshold(self):
        """Порог — по попыткам, а не по показам: сто пропусков процента
        не открывают."""
        for _ in range(100):
            stats_mod.record_answer(self.gq, 'skip')
        self.assertIsNone(stats_mod.public_stat(stats_mod.get_stat(self.gq)))


class EffectiveDifficultyTests(TestCase):
    """effective_difficulty — единственный вход в «сложность» для игры."""

    def setUp(self):
        self.p = make_problem()
        self.gq = make_question(self.p, difficulty=2)

    def test_without_data_the_stored_heuristic_wins(self):
        self.assertEqual(stats_mod.effective_difficulty(self.gq), 2)

    def test_with_data_the_measured_value_wins(self):
        # 20 попыток, из них 4 верных → доля 0,2 → полоса «< 0,30» → 5
        for _ in range(4):
            stats_mod.record_answer(self.gq, 'correct')
        for _ in range(16):
            stats_mod.record_answer(self.gq, 'wrong')
        self.assertEqual(stats_mod.effective_difficulty(self.gq), 5)

    def test_scale_is_read_from_config(self):
        cases = [(1.0, 1), (0.85, 1), (0.84, 2), (0.70, 2), (0.69, 3),
                 (0.50, 3), (0.49, 4), (0.30, 4), (0.29, 5), (0.0, 5)]
        for p, expected in cases:
            self.assertEqual(stats_mod.measured_difficulty(p), expected,
                             'доля %s' % p)


class FirstEncounterTests(TestCase):
    """В статистику идёт только ПЕРВАЯ встреча игрока с вопросом."""

    def setUp(self):
        self.p = make_problem()
        self.gq = make_question(self.p, question_type='single',
                                options=['а', 'б', 'в'], correct_index=0)

    def _start(self):
        return self.client.get(reverse('game:session_start'),
                               {'mode': 'blitz'})

    def _answer(self, qid, choice):
        return self.client.post(
            reverse('game:answer'),
            data=json.dumps({'question_id': qid, 'choice': choice}),
            content_type='application/json')

    def test_only_the_first_encounter_is_counted(self):
        """Второй забег с тем же (единственным) вопросом счётчик не двигает."""
        d = self._start().json()
        self._answer(d['question']['id'], 0)
        st = BankQuestionStat.objects.get(problem=self.p)
        self.assertEqual((st.shown, st.correct), (1, 1))

        # Второй забег: пул из одного вопроса, «виданные» очищаются и он
        # выпадает снова — но это уже НЕ первая встреча.
        d2 = self._start().json()
        self._answer(d2['question']['id'], 1)
        st.refresh_from_db()
        self.assertEqual((st.shown, st.correct, st.wrong), (1, 1, 0))

    def test_two_different_players_both_count(self):
        """Выборка растёт по игрокам: у каждого своя сессия и свой «виданные»."""
        d = self._start().json()
        self._answer(d['question']['id'], 0)
        self.client.logout()
        self.client.cookies.clear()          # другой игрок — чистый браузер
        d2 = self._start().json()
        self._answer(d2['question']['id'], 1)
        st = BankQuestionStat.objects.get(problem=self.p)
        self.assertEqual((st.shown, st.correct, st.wrong), (2, 1, 1))

    def test_answer_payload_carries_the_share_only_above_threshold(self):
        # ниже порога — поля нет вовсе
        d = self._start().json()
        body = self._answer(d['question']['id'], 0).json()
        self.assertNotIn('p_correct', body)

        # добиваем порог «чужими» ответами и играем ещё раз
        for _ in range(config.STATS_MIN_ATTEMPTS):
            stats_mod.record_answer(self.gq, 'correct')
        self.client.cookies.clear()
        d2 = self._start().json()
        body2 = self._answer(d2['question']['id'], 0).json()
        self.assertIn('p_correct', body2)
        self.assertGreaterEqual(body2['attempts'], config.STATS_MIN_ATTEMPTS)

    def test_correct_answer_is_never_in_the_question_payload(self):
        """Анти-чит не должен пострадать от новых полей."""
        d = self._start().json()
        q = d['question']
        for banned in ('correct_index', 'correct_indices', 'correct_value',
                       'p_correct'):
            self.assertNotIn(banned, q)


class PoolRebuildTests(TestCase):
    """★ Ключевой тест фазы: пересборка пула НЕ обнуляет статистику.

    Именно ради этого статистика привязана к Problem/ProblemPart, а не к
    строке GameQuestion. `build_game_pool` удаляет все несгенерированные
    строки кэша и создаёт заново с новыми id — счётчики на них не пережили
    бы ни одной пересборки. Переставьте модель на GameQuestion, и этот тест
    покраснеет.
    """

    def test_stats_survive_build_game_pool(self):
        from django.core.management import call_command
        from io import StringIO

        p = make_problem(statement='Спрос на кофе вырос. Верно ли это?')
        gq = make_question(p)
        for _ in range(5):
            stats_mod.record_answer(gq, 'correct', 1000)
        old_id = gq.id

        call_command('build_game_pool', stdout=StringIO())

        # Строка кэша исчезла (или пересоздана с другим id) — статистика цела.
        self.assertFalse(GameQuestion.objects.filter(id=old_id,
                                                     is_generated=False).exists())
        st = BankQuestionStat.objects.get(problem=p)
        self.assertEqual(st.shown, 5)
        self.assertEqual(st.correct, 5)

    def test_stat_is_found_again_for_the_rebuilt_question(self):
        """Статистика находится по НОВОЙ строке кэша той же задачи."""
        p = make_problem()
        gq = make_question(p)
        for _ in range(config.STATS_MIN_ATTEMPTS):
            stats_mod.record_answer(gq, 'correct')
        gq.delete()                          # имитируем пересборку кэша
        gq2 = make_question(p)
        pub = stats_mod.public_stat(stats_mod.get_stat(gq2))
        self.assertIsNotNone(pub)
        self.assertEqual(pub['attempts'], config.STATS_MIN_ATTEMPTS)


class BulkStatsTests(TestCase):
    def test_bulk_returns_rows_for_both_kinds(self):
        p = make_problem()
        gq = make_question(p)
        gen = make_question(None, is_generated=True, generator_key='monopoly')
        stats_mod.record_answer(gq, 'correct')
        stats_mod.record_answer(gen, 'wrong')
        out = stats_mod.bulk_stats([gq, gen])
        self.assertEqual(out[gq.id].correct, 1)
        self.assertEqual(out[gen.id].wrong, 1)

    def test_problem_summary_sums_parts(self):
        p = make_problem()
        part = ProblemPart.objects.create(problem=p, label='а', statement='…')
        gq1 = make_question(p)
        gq2 = make_question(p, part)
        half = config.STATS_MIN_ATTEMPTS  # по половине порога на каждый вопрос
        for _ in range(half):
            stats_mod.record_answer(gq1, 'correct')
            stats_mod.record_answer(gq2, 'wrong')
        summary = stats_mod.problem_stat_summary(p.pk)
        self.assertEqual(summary['attempts'], 2 * half)
        self.assertEqual(summary['percent'], 50)


class StatsPageTests(TestCase):
    """Служебная страница /game/stats/ — только для персонала."""

    def setUp(self):
        self.p = make_problem()
        self.gq = make_question(self.p)
        self.url = reverse('game:stats')

    def test_anonymous_is_redirected(self):
        r = self.client.get(self.url)
        self.assertIn(r.status_code, (302, 403))

    def test_plain_user_is_not_let_in(self):
        User.objects.create_user(username='u1', password='pw12345')
        self.client.login(username='u1', password='pw12345')
        r = self.client.get(self.url)
        self.assertIn(r.status_code, (302, 403))

    def test_staff_sees_the_table(self):
        User.objects.create_user(username='s1', password='pw12345',
                                 is_staff=True)
        self.client.login(username='s1', password='pw12345')
        for _ in range(config.STATS_MIN_ATTEMPTS):
            stats_mod.record_answer(self.gq, 'correct')
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Статистика игрового пула')
        self.assertContains(r, '100 %')

    def test_archetype_tab_opens(self):
        User.objects.create_user(username='s2', password='pw12345',
                                 is_staff=True)
        self.client.login(username='s2', password='pw12345')
        r = self.client.get(self.url, {'tab': 'arch'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Архетипы генератора')


@override_settings(GAME_GENERATED_ENABLED=False)
class CatalogSurfaceTests(TestCase):
    """Строка «в игре решают верно N %» на странице задачи каталога."""

    def setUp(self):
        self.p = make_problem(problem_type='задача')
        self.gq = make_question(self.p)
        self.url = reverse('catalog:problem_detail', args=[self.p.pk])

    def test_no_stats_no_line(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'В игре решают верно')

    def test_below_threshold_no_line(self):
        for _ in range(config.STATS_MIN_ATTEMPTS - 1):
            stats_mod.record_answer(self.gq, 'correct')
        r = self.client.get(self.url)
        self.assertNotContains(r, 'В игре решают верно')

    def test_above_threshold_the_line_appears(self):
        for _ in range(config.STATS_MIN_ATTEMPTS):
            stats_mod.record_answer(self.gq, 'correct')
        r = self.client.get(self.url)
        self.assertContains(r, 'В игре решают верно')
        self.assertContains(r, '100%')
