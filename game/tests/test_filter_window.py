# -*- coding: utf-8 -*-
u"""Окно фильтров тренажёра (фаза 4): теги, звёзды, счётчики, зачётность.

Разбор параметров сторожит `test_filters.py`; здесь — то, что появилось
вместе с окном: фильтр по тегам, множество звёзд вместо отрезка, живые
счётчики и правило «фильтр по сложности делает забег тренировочным».
"""
import io
import json

from django.test import TestCase
from django.urls import reverse

from problems.models import Problem, Tag
from game import config, views
from game.models import GameQuestion

PAGE = 'game/templates/game/game.html'


def make_q(topics=None, group='books', difficulty=3, qtype='single',
           tag_ids=None, **kw):
    p = Problem.objects.create(
        title='Т', statement='Условие про рынок.',
        problem_type='тест: один ответ', answer='а',
        status=Problem.Status.PUBLISHED)
    defaults = dict(
        question_type=qtype, question='Что произойдёт со спросом?',
        options=['вырастет', 'упадёт', 'не изменится'], correct_index=0,
        difficulty=difficulty, topics=topics or ['Спрос и предложение'],
        lang='ru', source_group=group, tag_ids=tag_ids or [])
    defaults.update(kw)
    return GameQuestion.objects.create(problem=p, **defaults)


class TagFilterTests(TestCase):
    u"""Фильтр по тегам: денормализованный список id, без join."""

    def setUp(self):
        self.t_graph = Tag.objects.create(name='график', slug='graph')
        self.t_hard = Tag.objects.create(name='олимпиадная', slug='hard')
        self.with_graph = make_q(tag_ids=[self.t_graph.id])
        self.with_both = make_q(tag_ids=[self.t_graph.id, self.t_hard.id])
        self.plain = make_q(tag_ids=[])

    def _rows(self, **params):
        from django.test import RequestFactory
        req = RequestFactory().get('/game/', params)
        f = views.parse_filter(req)
        return {pk for pk, _d, _t in
                views._candidate_rows({'mode': 'blitz', 'filter': f})}

    def test_tag_filter_narrows_the_pool(self):
        ids = self._rows(tags=[self.t_hard.id])
        self.assertEqual(ids, {self.with_both.id})

    def test_several_tags_mean_any_of_them(self):
        u"""Список тегов — «любой из», а не «все сразу»: пересечение почти
        всегда пусто, и фильтр превращался бы в запрет."""
        ids = self._rows(tags=[self.t_graph.id, self.t_hard.id])
        self.assertEqual(ids, {self.with_graph.id, self.with_both.id})

    def test_no_tag_filter_keeps_everything(self):
        self.assertEqual(len(self._rows()), 3)

    def test_pool_tags_only_lists_tags_that_have_questions(self):
        u"""Тег, по которому ничего не найдётся, обещал бы выбор, которого
        нет."""
        Tag.objects.create(name='ненужный', slug='unused')
        rows = views.pool_tags()
        names = {r['name'] for r in rows}
        self.assertIn('график', names)
        self.assertNotIn('ненужный', names)
        by_name = {r['name']: r['count'] for r in rows}
        self.assertEqual(by_name['график'], 2)
        self.assertEqual(by_name['олимпиадная'], 1)


class StarsFilterTests(TestCase):
    u"""Сложность — любое подмножество из пяти, а не отрезок."""

    def setUp(self):
        self.by_star = {d: make_q(difficulty=d) for d in (1, 2, 3, 4, 5)}

    def _rows(self, **params):
        from django.test import RequestFactory
        req = RequestFactory().get('/game/', params)
        f = views.parse_filter(req)
        return {pk for pk, _d, _t in
                views._candidate_rows({'mode': 'blitz', 'filter': f})}

    def test_gap_subset_is_possible(self):
        u"""То, чего ползунок «от…до» не умел в принципе."""
        self.assertEqual(self._rows(stars=[1, 5]),
                         {self.by_star[1].id, self.by_star[5].id})

    def test_single_star(self):
        self.assertEqual(self._rows(stars=[3]), {self.by_star[3].id})

    def test_empty_means_all(self):
        self.assertEqual(len(self._rows()), 5)


class FilterReallyFiltersTests(TestCase):
    u"""Главная проверка фазы: под фильтром НИ ОДИН выданный вопрос не
    нарушает условие.

    ⚠️ Проверяется 50 настоящих выдач через клиент, а не один вызов
    `_candidate_rows`. Между кандидатами и выдачей стоит эскалация
    сложности по серии, и именно она однажды уже выводила забег за
    пользовательскую рамку.
    """

    def setUp(self):
        self.tag = Tag.objects.create(name='целевой', slug='target')
        self.other_tag = Tag.objects.create(name='чужой', slug='other')
        # Подходящие: тема + звёзды {2,3} + нужный тег.
        for d in (2, 3):
            for _ in range(8):
                make_q(topics=['Эластичность'], difficulty=d,
                       tag_ids=[self.tag.id])
        # Ловушки: нарушают ровно по одному измерению.
        for _ in range(10):
            make_q(topics=['Эластичность'], difficulty=5, tag_ids=[self.tag.id])
            make_q(topics=['Рынок труда'], difficulty=2, tag_ids=[self.tag.id])
            make_q(topics=['Эластичность'], difficulty=2,
                   tag_ids=[self.other_tag.id])

    def test_fifty_served_questions_all_match(self):
        q = ('?mode=blitz&topics=%s&stars=2&stars=3&tags=%d'
             % ('Эластичность', self.tag.id))
        served = []
        for _ in range(50):
            d = self.client.get(reverse('game:session_start') + q).json()
            if not d.get('ok'):
                break
            qid = d['question']['id']
            served.append(qid)
            # Отвечаем верно, чтобы серия росла и включалась эскалация.
            gq = GameQuestion.objects.get(id=qid)
            self.client.post(
                reverse('game:answer'),
                json.dumps({'question_id': qid, 'choice': gq.correct_index}),
                content_type='application/json')
            for _ in range(3):
                nxt = self.client.get(reverse('game:question')).json()
                q_obj = nxt.get('question')
                if not q_obj:
                    break
                served.append(q_obj['id'])
                gq2 = GameQuestion.objects.get(id=q_obj['id'])
                self.client.post(
                    reverse('game:answer'),
                    json.dumps({'question_id': q_obj['id'],
                                'choice': gq2.correct_index}),
                    content_type='application/json')
        self.assertGreaterEqual(len(served), 50, 'выдач набралось мало')
        bad = []
        for gq in GameQuestion.objects.filter(id__in=set(served)):
            if ('Эластичность' not in (gq.topics or [])
                    or gq.difficulty not in (2, 3)
                    or self.tag.id not in (gq.tag_ids or [])):
                bad.append((gq.id, gq.topics, gq.difficulty, gq.tag_ids))
        self.assertEqual(bad, [], 'фильтр пропустил чужие вопросы')


class PoolCountsApiTests(TestCase):
    u"""Живые счётчики окна."""

    def setUp(self):
        for _ in range(12):
            make_q(topics=['Эластичность'], difficulty=2)
        for _ in range(3):
            make_q(topics=['Рынок труда'], difficulty=5)

    def test_counts_match_the_candidates_actually_served(self):
        u"""⚠️ Счётчик обязан считать ТОЙ ЖЕ функцией, что выбирает вопросы.
        Отдельный запрос «сколько подходит» разошёлся бы с выдачей."""
        r = self.client.get(reverse('game:pool_counts'),
                            {'topics': 'Эластичность'})
        d = r.json()
        from django.test import RequestFactory
        f = views.parse_filter(
            RequestFactory().get('/game/', {'topics': 'Эластичность'}))
        real = len(views._candidate_rows({'mode': 'blitz', 'filter': f}))
        self.assertEqual(d['counts']['blitz'], real)
        self.assertEqual(d['counts']['blitz'], 12)

    def test_counts_report_ranked_and_unfiltered(self):
        d = self.client.get(reverse('game:pool_counts')).json()
        self.assertTrue(d['unfiltered'])
        self.assertTrue(d['ranked'])
        d2 = self.client.get(reverse('game:pool_counts'), {'stars': '3'}).json()
        self.assertFalse(d2['unfiltered'])
        self.assertFalse(d2['ranked'])
        d3 = self.client.get(reverse('game:pool_counts'),
                             {'topics': 'Эластичность'}).json()
        self.assertFalse(d3['unfiltered'])
        self.assertTrue(d3['ranked'], 'фильтр темы зачётности не лишает')

    def test_min_playable_is_sent(self):
        d = self.client.get(reverse('game:pool_counts')).json()
        self.assertEqual(d['min_playable'], config.MIN_PLAYABLE)


class RankedRulesTests(TestCase):
    u"""Зачётность: фильтр по сложности — тренировочный, остальные нет."""

    def test_difficulty_filter_makes_the_run_unranked(self):
        self.assertTrue(views.is_difficulty_filtered({'stars': [3]}))
        self.assertFalse(views.is_difficulty_filtered({'stars': []}))

    def test_topics_and_tags_do_not_touch_ranked(self):
        u"""Они меняют, ЧТО решаешь, а не КАК ТРУДНО."""
        self.assertFalse(views.is_difficulty_filtered(
            {'topics': ['Эластичность'], 'tags': [1], 'sources': ['vsosh']}))

    def test_unfiltered_needs_every_dimension_empty(self):
        self.assertTrue(views.is_empty_filter({}))
        for key, val in [('topics', ['Эластичность']), ('tags', [1]),
                         ('sources', ['vsosh']), ('stars', [3])]:
            self.assertFalse(views.is_empty_filter({key: val}), key)


class FilterWindowMarkupTests(TestCase):
    u"""Разметка окна и главного экрана."""

    def setUp(self):
        self.src = io.open(PAGE, encoding='utf-8').read()

    def test_topic_chips_are_gone_from_the_start_screen(self):
        u"""Двадцать чипов занимали первый экран целиком и уводили внимание
        с карточек режимов."""
        self.assertNotIn('topic-chips', self.src)
        self.assertNotIn('class="topic-chip', self.src)

    def test_one_button_instead(self):
        self.assertIn('>Добавить фильтры</button>', self.src)
        self.assertIn("'Изменить фильтры'", self.src)
        # При наведении текст чуть жирнее и крупнее — просьба владельца.
        self.assertIn('.filter-open:hover {', self.src)
        self.assertIn('font-weight: 700;', self.src)

    def test_modal_has_every_group(self):
        for marker in ('<h3>Тема</h3>', '<h3>Тег</h3>', '<h3>Сложность</h3>',
                       '>Источник</h3>'):
            self.assertIn(marker, self.src, marker)

    def test_empty_groups_are_not_rendered_at_all(self):
        u"""Серый переключатель, который не нажимается, хуже его отсутствия.
        Появится разметка в базе — группы включатся сами."""
        self.assertIn('{% if feature_options %}', self.src)
        self.assertIn('{% if character_options %}', self.src)
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        # Сверяем ЗАГОЛОВКИ групп, а не слова: слова стоят и в пояснении
        # над окном, которое к разметке групп отношения не имеет.
        self.assertNotIn('<h3>Особенности</h3>', html)
        self.assertNotIn('<h3>Характер задачи</h3>', html)
        self.assertNotIn('f-feature', html)
        self.assertNotIn('f-character', html)

    def test_stars_are_five_toggles_not_a_slider(self):
        self.assertNotIn('diff-slider', self.src)
        self.assertEqual(self.src.count('class="star-btn f-star"'), 5)
        self.assertIn('aria-pressed="false"', self.src)

    def test_tag_search_and_selected_on_top(self):
        self.assertIn('id="tag-search"', self.src)
        self.assertIn('chosen.concat(', self.src)

    def test_tag_group_hides_while_the_pool_has_no_tags(self):
        u"""То же правило, что у «Особенностей»: группа без вариантов не
        рисуется. Пока пул не пересобран, тегов у вопросов нет, и мёртвый
        поиск по пустому списку хуже отсутствия группы."""
        self.assertIn('{% if pool_tags %}', self.src)
        make_q(tag_ids=[])
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        self.assertNotIn('id="tag-search"', html)

    def test_tag_group_appears_once_there_are_tags(self):
        tag = Tag.objects.create(name='график', slug='graph')
        make_q(tag_ids=[tag.id])
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        self.assertIn('id="tag-search"', html)
        self.assertIn('<h3>Тег</h3>', html)

    def test_counter_line_skips_modes_that_are_not_on_screen(self):
        u"""«График 0» при выключенном флаге обещал бы режим, которого на
        экране нет."""
        self.assertIn('return CFG.modes[k] && CFG.pool_counts[k];', self.src)

    def test_live_counters_are_debounced(self):
        self.assertIn("'/game/api/pool_counts/?'", self.src)
        self.assertIn('}, 250);', self.src)

    def test_chips_have_a_cross_and_reset(self):
        self.assertIn("chip.className = 'fchip';", self.src)
        self.assertIn('>Сбросить всё</button>', self.src)
        self.assertIn("'Снять фильтр '", self.src)

    def test_state_lives_in_the_url_and_storage(self):
        self.assertIn('history.replaceState', self.src)
        self.assertIn("localStorage.setItem(FILTER_KEY", self.src)

    def test_mode_card_shows_the_available_count(self):
        self.assertIn("' под фильтром'", self.src)
        self.assertIn("card.classList.add('is-off')", self.src)
        # ⚠️ Сверяем САМО СРАВНЕНИЕ, а не упоминание константы:
        # `CFG.min_playable` встречается ещё в подписи и в обходе клавиш, и
        # проверка на упоминание проспала бы «playable = true».
        self.assertIn('var playable = avail >= (CFG.min_playable || 10);',
                      self.src)

    def test_ranked_note_is_shown_before_the_run(self):
        u"""Игрок обязан знать ДО забега, поедет ли результат на доску."""
        self.assertIn('Тренировочный забег: выбрана сложность', self.src)
        self.assertIn("'Без фильтров: ×'", self.src)
        self.assertIn("'С фильтрами: множителя ×'", self.src)


class PoolGateTests(TestCase):
    u"""Шлюз пула: что попадает в игру, а что нет (фаза 8.2).

    ⚠️ Правило пула игры — «опубликовано и без брака», а НЕ правило каталога
    «только проверенное человеком». Требуй пул `hidden_pending_review=False`,
    и источники, которых ещё не смотрели глазами, не попали бы в игру
    никогда: у одного только Сборника АА таких 562 задачи.
    """

    def test_defect_marked_by_a_human_never_enters_the_pool(self):
        u"""Брак, найденный человеком, сильнее любого автодетектора."""
        import io
        src = io.open('game/management/commands/build_game_pool.py',
                      encoding='utf-8').read()
        self.assertIn(".exclude(human_review='defect')", src)

    def test_pool_does_not_require_the_catalogue_gate(self):
        import io
        src = io.open('game/management/commands/build_game_pool.py',
                      encoding='utf-8').read()
        self.assertNotIn('hidden_pending_review=False', src)

    def test_dry_run_writes_nothing(self):
        u"""Сухой прогон обязан быть безвредным: им смотрят на пересборку
        ДО того, как решают её делать."""
        from io import StringIO
        from django.core.management import call_command
        before = list(GameQuestion.objects.values_list('id', flat=True))
        out = StringIO()
        call_command('build_game_pool', '--dry-run', stdout=out)
        after = list(GameQuestion.objects.values_list('id', flat=True))
        self.assertEqual(before, after, 'сухой прогон тронул базу')
        self.assertIn('СУХОЙ ПРОГОН', out.getvalue())
