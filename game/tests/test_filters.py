"""
Тесты фильтров стартового экрана и третьей концовки (Фаза 2).

Главные инварианты фазы:
- мульти-фильтр (темы + источники + сложность) действительно сужает выдачу;
- старый одиночный `topic=` продолжает работать (ссылками уже делились);
- фильтр НАСЛЕДУЕТСЯ «сыграть ещё раз» и работой над ошибками — раньше
  выбор игрока молча сбрасывался;
- пустой пул под фильтром не создаёт забег вовсе (Задача 3, 2026-07-27) —
  честный отказ `ok: False`, а не 503 и не забег из нуля вопросов;
- режим с пустым пулом на стартовом экране не рисуется вовсе.
"""
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from game import config, views
from game.figures.base import QUESTION_TYPE as FIGURE_AUDIT
from game.models import GameQuestion
from game import sources as game_sources
from problems.models import Problem


def make_q(topics=None, group='books', difficulty=3, qtype='single', **kw):
    p = Problem.objects.create(
        title='Т', statement='Условие про рынок.',
        problem_type='тест: один ответ', answer='а',
        status=Problem.Status.PUBLISHED)
    defaults = dict(
        question_type=qtype, question='Что произойдёт со спросом?',
        options=['вырастет', 'упадёт', 'не изменится'], correct_index=0,
        difficulty=difficulty, topics=topics or ['Спрос и предложение'],
        lang='ru', source_group=group)
    defaults.update(kw)
    return GameQuestion.objects.create(problem=p, **defaults)


class FilterParsingTests(TestCase):
    """parse_filter: что понимает и что молча отбрасывает."""

    def _f(self, query):
        from django.test import RequestFactory
        from game.views import parse_filter
        return parse_filter(RequestFactory().get('/game/api/session/start/',
                                                 query))

    def test_empty_query_is_the_empty_filter(self):
        from game.views import empty_filter
        self.assertEqual(self._f({}), empty_filter())

    def test_multi_topics_and_sources(self):
        f = self._f({'topics': ['Эластичность', 'Рынок труда'],
                     'sources': ['vsosh', 'ap']})
        self.assertEqual(f['topics'], ['Эластичность', 'Рынок труда'])
        self.assertEqual(f['sources'], ['vsosh', 'ap'])

    def test_legacy_single_topic_still_works(self):
        f = self._f({'topic': 'Эластичность'})
        self.assertEqual(f['topics'], ['Эластичность'])

    def test_difficulty_is_clamped_and_ordered(self):
        f = self._f({'dmin': '9', 'dmax': '-3'})
        # 9→5, −3→1, потом перевёрнутый диапазон разворачивается
        self.assertEqual((f['dmin'], f['dmax']), (1, 5))

    def test_garbage_difficulty_falls_back_to_full_range(self):
        f = self._f({'dmin': 'ой', 'dmax': ''})
        self.assertEqual((f['dmin'], f['dmax']),
                         (config.DIFFICULTY_MIN, config.DIFFICULTY_MAX))


class FilterNarrowsServingTests(TestCase):
    """Фильтр реально сужает выдачу."""

    def setUp(self):
        self.elastic = make_q(topics=['Эластичность'], group='vsosh',
                              difficulty=2)
        self.labour = make_q(topics=['Рынок труда'], group='books',
                             difficulty=5)

    def _start(self, **params):
        params.setdefault('mode', 'blitz')
        return self.client.get(reverse('game:session_start'), params).json()

    def test_topic_filter(self):
        d = self._start(topics=['Эластичность'])
        self.assertEqual(d['question']['id'], self.elastic.id)

    def test_source_filter(self):
        d = self._start(sources=['books'])
        self.assertEqual(d['question']['id'], self.labour.id)

    def test_difficulty_filter(self):
        d = self._start(dmin=4, dmax=5)
        self.assertEqual(d['question']['id'], self.labour.id)

    def test_two_topics_widen_the_choice(self):
        d = self._start(topics=['Эластичность', 'Рынок труда'])
        self.assertIn(d['question']['id'], {self.elastic.id, self.labour.id})

    def test_impossible_combination_does_not_start_a_run(self):
        """Тема из одного вопроса + источник из другого = пусто.

        Это не 503 и не забег из нуля вопросов, который сам себя тут же
        хоронит: сервер честно отказывается начинать (Задача 3), сессия не
        создаётся вовсе — session_finish на неё отвечает «забег не начат»."""
        d = self._start(topics=['Эластичность'], sources=['books'])
        self.assertFalse(d['ok'])
        self.assertEqual(d['reason'], 'pool_empty')
        self.assertNotIn('question', d)

        r = self.client.post(reverse('game:session_finish'),
                             json.dumps({'reason': 'done'}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_measured_difficulty_is_used_by_the_filter(self):
        """Фильтр сложности опирается на ту же величину, что и вся игра:
        измеренную, когда она есть."""
        from game import stats as stats_mod
        # хранимая сложность у labour = 5, но игроки решают его почти всегда
        for _ in range(config.STATS_MIN_ATTEMPTS):
            stats_mod.record_answer(self.labour, 'correct')
        d = self._start(dmin=1, dmax=1)
        self.assertEqual(d['question']['id'], self.labour.id)


class FilterInheritanceTests(TestCase):
    """Фильтр переживает «сыграть ещё раз» и работу над ошибками."""

    def setUp(self):
        self.elastic = [make_q(topics=['Эластичность']) for _ in range(3)]
        self.other = [make_q(topics=['Рынок труда']) for _ in range(3)]

    def _start(self, **params):
        params.setdefault('mode', 'blitz')
        return self.client.get(reverse('game:session_start'), params).json()

    def test_filter_is_returned_and_kept_in_state(self):
        d = self._start(topics=['Эластичность'])
        self.assertEqual(d['filter']['topics'], ['Эластичность'])
        # «Сыграть ещё раз» на клиенте шлёт тот же фильтр — проверяем, что
        # сервер отдаёт из него ровно те же вопросы
        ids = set()
        for _ in range(4):
            d = self._start(topics=['Эластичность'])
            ids.add(d['question']['id'])
        self.assertTrue(ids <= {q.id for q in self.elastic})

    def test_mistakes_run_inherits_the_filter(self):
        """Работа над ошибками не имеет права молча вернуть весь пул."""
        d = self._start(topics=['Эластичность'])
        qid = d['question']['id']
        self.client.post(reverse('game:answer'),
                         json.dumps({'question_id': qid, 'choice': 1}),
                         content_type='application/json')
        self.client.post(reverse('game:session_finish'),
                         json.dumps({'reason': 'time'}),
                         content_type='application/json')
        r = self.client.get(reverse('game:session_start_mistakes')).json()
        self.assertTrue(r['ok'])
        state = self.client.session['econ_rush']
        queue = [r['question']['id']] + list(state['queue'])
        self.assertTrue(set(queue) <= {q.id for q in self.elastic},
                        'в целевой забег попали вопросы вне фильтра')


class EmptyModeIsHiddenTests(TestCase):
    """Режим без единого вопроса на стартовом экране не рисуется."""

    def test_pool_counts_are_zero_for_empty_modes(self):
        make_q(qtype='single')
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        cfg = json.loads(
            html.split('var CFG = ', 1)[1].split(';\n', 1)[0])
        self.assertEqual(cfg['pool_counts']['blitz'], 1)
        self.assertEqual(cfg['pool_counts']['bullet'], 0)

    def test_client_skips_modes_with_an_empty_pool(self):
        """Отрисовка карточек читает pool_counts и пропускает нули —
        проверяем сам код клиента, чтобы правило не разъехалось."""
        import os
        from django.conf import settings
        path = os.path.join(settings.BASE_DIR, 'game', 'templates', 'game',
                            'game.html')
        with open(path, encoding='utf-8') as f:
            src = f.read()
        self.assertIn('if (!m || !CFG.pool_counts[key]) return;', src)


class SourceMapTests(TestCase):
    """Словарь «источник → группа олимпиад» построен по реальной таблице."""

    def test_every_group_key_is_known(self):
        for name, key in game_sources.SOURCE_GROUPS.items():
            self.assertIn(key, game_sources.GROUP_KEYS, name)

    def test_unknown_source_falls_into_other(self):
        self.assertEqual(game_sources.group_of('Совсем новый источник'),
                         'other')
        self.assertEqual(game_sources.group_of(None), 'other')

    def test_real_sources_are_all_mapped(self):
        """Каждый источник из базы обязан быть в словаре — иначе он молча
        уедет в «Прочее», и фильтр начнёт врать."""
        from problems.models import Source
        unmapped = [s.name for s in Source.objects.all()
                    if s.name not in game_sources.SOURCE_GROUPS]
        self.assertEqual(unmapped, [])

    def test_build_pool_writes_the_group(self):
        from io import StringIO
        from django.core.management import call_command
        from problems.models import Source, SourceReference
        p = Problem.objects.create(
            title='Т', statement='Спрос на кофе вырос. Верно ли это?',
            problem_type='тест: верно/неверно', answer='а',
            status=Problem.Status.PUBLISHED)
        from problems.models import ProblemPart
        ProblemPart.objects.create(problem=p, label='а', statement='Верно')
        ProblemPart.objects.create(problem=p, label='б', statement='Неверно')
        src = Source.objects.create(name='ВсОШ — региональный этап')
        SourceReference.objects.create(problem=p, source=src, year=2024)
        call_command('build_game_pool', stdout=StringIO())
        gq = GameQuestion.objects.get(problem=p)
        self.assertEqual(gq.source_id, src.id)
        self.assertEqual(gq.source_group, 'vsosh')


class TopicGroupsTests(TestCase):
    """Группировка тем в три колонки покрывает все 21 каноническую."""

    def test_all_canonical_topics_are_grouped_exactly_once(self):
        from problems.management.commands.apply_topic_mapping import CANONICAL
        grouped = []
        for _key, _title, names in config.TOPIC_GROUPS:
            grouped.extend(names)
        self.assertEqual(sorted(grouped), sorted(CANONICAL))
        self.assertEqual(len(grouped), len(set(grouped)))

    def test_page_renders_every_topic_as_a_checkbox(self):
        make_q()
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        from problems.management.commands.apply_topic_mapping import CANONICAL
        for name in CANONICAL:
            self.assertIn('value="%s"' % name, html, name)

    def test_page_shows_all_source_groups_even_empty_ones(self):
        """Пустые группы не гасим: фильтр обещает выбор, а не отчёт о
        сегодняшнем состоянии банка (указание Макара)."""
        make_q(group='books')
        html = self.client.get(reverse('game:page')).content.decode('utf-8')
        for key, title in game_sources.GROUPS:
            self.assertIn('value="%s"' % key, html, key)
            self.assertIn(title, html, title)


def make_typed_q(qtype, topics):
    """Один вопрос заданного типа с заданными темами — минимум, нужный
    _candidate_rows (сам ответ в этих тестах не проверяется)."""
    kw = dict(question_type=qtype, problem=None, question='Вопрос.',
             options=['а', 'б'], difficulty=3, topics=topics, lang='ru',
             is_generated=True)
    if qtype == 'numeric':
        kw['options'] = []
        kw['correct_value'] = '5'
    elif qtype == 'multi':
        kw['correct_indices'] = [0]
    else:
        kw['correct_index'] = 0
    return GameQuestion.objects.create(**kw)


@override_settings(GAME_FIGURE_ENABLED=True)
class EmptyFilterNeverStartsARunTests(TestCase):
    """Задача 3 (2026-07-27), общее правило для ВСЕХ режимов: если под
    выбранным фильтром не нашлось ни одного вопроса, забег не начинается.

    У каждого режима здесь вопросы ЕСТЬ (просто не под запрошенной темой) —
    поэтому причина именно `pool_empty`, а не `mode_unavailable`
    (недостижимость самого режима проверяет FlagOffTests в
    test_figure_audit.py)."""

    def setUp(self):
        for qtype in ('boolean', 'single', 'multi', 'numeric', FIGURE_AUDIT):
            make_typed_q(qtype, topics=['Спрос и предложение'])

    def test_every_mode_refuses_to_start_under_an_impossible_topic(self):
        for mode in config.MODES:
            with self.subTest(mode=mode):
                r = self.client.get(reverse('game:session_start'),
                                    {'mode': mode,
                                     'topics': 'Инфляция и безработица'})
                self.assertEqual(r.status_code, 200)
                d = r.json()
                self.assertFalse(d['ok'], mode)
                self.assertEqual(d['reason'], 'pool_empty', mode)
                self.assertNotIn('question', d)
                self.assertIsNone(self.client.session.get(views.SESSION_KEY))
