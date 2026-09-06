"""Этап 4 редизайна: страница задачи — каркас, облачка, условие, решение и
ответ, похожие, карточка чата вёрсткой (мокап `problem_page_mockup.html`)."""
from django.test import TestCase
from django.urls import reverse

from problems.models import ProblemPart, Tag
from problems.models_platform import SavedProblem
from problems.tests.factories import (
    link_source, make_problem, make_source, make_topic, make_user,
)

CUT_TITLE = 'Известно, что монополист получает максимальную выр'
CUT_STATEMENT = ('Известно, что монополист получает максимальную выручку в точке '
                 '$P=20$, $Q=40$. Найдите функцию спроса.')


def _url(problem):
    return reverse('catalog:problem_detail', args=[problem.pk])


class ProblemPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mon = make_topic('Монополия и ценовая дискриминация')
        cls.tag = Tag.objects.create(name='обратная индукция', slug='backward')
        cls.src = make_source('МатЭк')
        cls.p_named = make_problem('На школьной ярмарке спрос $Q_d = 120 - P$.',
                                   title='Вмешательство — 5', topic=cls.mon,
                                   difficulty=4, solution='1800')
        ProblemPart.objects.create(problem=cls.p_named, label='а', statement='Какие ставки?', order=1)
        ProblemPart.objects.create(problem=cls.p_named, label='б', statement='Сборы?', order=2)
        cls.p_named.tags.add(cls.tag)
        link_source(cls.p_named, cls.src)
        cls.p_cut = make_problem(CUT_STATEMENT, title=CUT_TITLE, topic=cls.mon,
                                 solution='Полное решение задачи длиннее тридцати знаков.',
                                 answer='42')
        cls.p_bare = make_problem('Задача без всего.')
        cls.p_test = make_problem('Выберите верное утверждение.', title='Тест про монополию',
                                  topic=cls.mon, problem_type='тест: один ответ', answer='б')
        for label, text in (('а', 'Первое'), ('б', 'Второе'), ('в', 'Третье')):
            ProblemPart.objects.create(problem=cls.p_test, label=label, statement=text,
                                       answer='', order=ord(label))
        cls.p_review = make_problem('С непроверенным решением.', title='Спорное решение',
                                    solution='Длинное решение, которое ещё не проверено человеком.',
                                    solution_needs_review=True, answer='7')

    def test_every_shape_renders(self):
        for problem in (self.p_named, self.p_cut, self.p_bare, self.p_test, self.p_review):
            self.assertEqual(self.client.get(_url(problem)).status_code, 200, problem.pk)

    def test_named_title_is_shown_and_cut_title_is_hidden(self):
        html = self.client.get(_url(self.p_named)).content.decode()
        self.assertIn('<h1 class="pd-title">Вмешательство — 5</h1>', html)
        self.assertIn('<title>Вмешательство — 5 · Экономика</title>', html)
        html = self.client.get(_url(self.p_cut)).content.decode()
        self.assertNotIn('class="pd-title"', html)
        self.assertIn('<h1 class="sr-only">Задача: Монополия и ценовая дискриминация</h1>', html)
        self.assertIn('<title>Задача: Монополия и ценовая дискриминация · Экономика</title>', html)
        html = self.client.get(_url(self.p_bare)).content.decode()
        self.assertIn('<h1 class="sr-only">Задача</h1>', html)

    def test_number_appears_nowhere_but_the_address(self):
        html = self.client.get(_url(self.p_named)).content.decode()
        body = html.split('<main')[1]
        self.assertNotIn('№', body)
        self.assertNotIn('Задача #', html)

    def test_page_uses_its_own_wide_column(self):
        self.assertIn('<main class="pd-wrap">', self.client.get(_url(self.p_named)).content.decode())
        self.assertIn('<main class="page-wrap">', self.client.get('/catalog/').content.decode())

    def test_clouds_link_to_the_catalog_with_that_filter(self):
        html = self.client.get(_url(self.p_named)).content.decode()
        self.assertIn('class="pp pp--topic" href="/catalog/?topic=%d" style="--gc: var(--map-g-micro)">'
                      'Монополия и ценовая дискриминация</a>' % self.mon.pk, html)
        self.assertIn('class="pp pp--tag" href="/catalog/?tag=%d" style="--gc: var(--map-g-micro)">'
                      'обратная индукция</a>' % self.tag.pk, html)
        self.assertIn('class="pp pp--diff" href="/catalog/?difficulty=4"><span class="st">★★★★☆</span> сложность 4</a>', html)
        self.assertIn('class="pp pp--kind" href="/catalog/?type=open">Развёрнутая задача</a>', html)
        self.assertIn('class="pp-sep"', html)
        self.assertIn('class="pp pp--src" href="/catalog/?source=%d">МатЭк</a>' % self.src.pk, html)
        test_html = self.client.get(_url(self.p_test)).content.decode()
        self.assertIn('href="/catalog/?type=test&amp;test_type=%D1%82%D0%B5%D1%81%D1%82%3A+%D0%BE%D0%B4%D0%B8%D0%BD+%D0%BE%D1%82%D0%B2%D0%B5%D1%82">Тест · один верный</a>', test_html)

    def test_empty_properties_render_nothing(self):
        html = self.client.get(_url(self.p_cut)).content.decode()
        # Проверяем РАЗМЕТКУ (класс на элементе), а не текст страницы: правила
        # `.pp--tag` лежат в CSS и есть всегда.
        for absent in ('class="pp pp--tag"', 'class="pp pp--diff"', 'class="pp pp--src"', 'class="pp-sep"'):
            self.assertNotIn(absent, html)
        self.assertIn('class="pp pp--topic"', html)

    def test_answer_and_solution_are_separate(self):
        html = self.client.get(_url(self.p_named)).content.decode()
        self.assertIn('Ответ: <b class="math-content">1800</b>', html)
        self.assertNotIn('class="sol-body"', html)
        self.assertIn('<h3>Ответ</h3>', html)
        html = self.client.get(_url(self.p_cut)).content.decode()
        self.assertIn('<h3>Решение</h3>', html)
        self.assertIn('Полное решение задачи длиннее тридцати знаков.', html)
        self.assertIn('Ответ: <b class="math-content">42</b>', html)
        html = self.client.get(_url(self.p_review)).content.decode()
        self.assertNotIn('ещё не проверено человеком', html)
        self.assertIn('Ответ: <b class="math-content">7</b>', html)
        self.assertNotIn('id="sol-btn"', self.client.get(_url(self.p_bare)).content.decode())

    def test_solution_needs_soft_confirmation_before_reveal(self):
        html = self.client.get(_url(self.p_named)).content.decode()
        self.assertIn('id="sol-confirm"', html)
        self.assertIn('Открыть решение до отправки?', html)
        self.assertIn('id="sol-yes"', html)
        self.assertIn('id="sol-no"', html)

    def test_parts_live_inside_the_statement(self):
        html = self.client.get(_url(self.p_named)).content.decode()
        self.assertIn('<ol class="parts">', html)
        self.assertIn('<b>а)</b>', html)
        self.assertIn('одно на всю задачу, подпункты внутри', html)

    def test_test_options_are_playable_tiles(self):
        """Этап 7: варианты теста — кнопки игры, а не статичные плитки."""
        html = self.client.get(_url(self.p_test)).content.decode()
        self.assertEqual(html.count('aria-pressed="false"'), 3)
        self.assertIn('<span class="opt-l">а</span>', html)
        self.assertEqual(html.count('Показать ответ'), 1)
        self.assertNotIn('id="sol-btn"', html)
        self.assertNotIn('Ответ: <b class="math-content">б</b>', html)

    def test_similar_cards_and_link(self):
        others = [make_problem('Похожая %d.' % i, topic=self.mon, difficulty=3) for i in range(4)]
        hidden = make_problem('Скрытая похожая.', flagged=True)
        self.p_named.similar_problems.set(others + [hidden])
        html = self.client.get(_url(self.p_named)).content.decode()
        self.assertEqual(html.count('class="sim-card"'), 4)
        self.assertIn('<a href="/catalog/?q=', html)
        self.assertIn('style="--gc: var(--map-g-micro)">Монополия и ценовая дискриминация</span>', html)
        self.assertIn('<span class="ct-stars">★★★☆☆</span>', html)
        self.assertIn('без решения', html)
        self.assertNotIn('class="sim"', self.client.get(_url(self.p_bare)).content.decode())

    def test_save_button_only_for_logged_in_and_reflects_state(self):
        self.assertNotIn('id="save-btn"', self.client.get(_url(self.p_named)).content.decode())
        user = make_user('reader')
        self.client.force_login(user)
        html = self.client.get(_url(self.p_named)).content.decode()
        self.assertIn('id="save-btn"', html)
        self.assertIn('<span id="save-label">Сохранить</span>', html)
        SavedProblem.objects.create(owner=user, catalog_problem=self.p_named)
        html = self.client.get(_url(self.p_named)).content.decode()
        self.assertIn('class="pd-act is-on"', html)
        self.assertIn('<span id="save-label">Сохранено</span>', html)

    def test_teacher_gets_homework_button(self):
        self.client.force_login(make_user('tutor', role='teacher'))
        html = self.client.get(_url(self.p_named)).content.decode()
        self.assertIn('id="hw-btn-%d"' % self.p_named.pk, html)
        self.assertIn('function toggleHwDropdown', html)
        self.client.force_login(make_user('pupil'))
        html = self.client.get(_url(self.p_named)).content.decode()
        self.assertNotIn('toggleHwDropdown', html)

    def test_ai_card_needs_an_available_model(self):
        # Без ключа ИИ карточки нет вовсе (правило нуля); с моделью — есть.
        with self.settings(AI_PROVIDER='anthropic'):
            self.assertNotIn('<h2>Спросить ИИ</h2>', self.client.get(_url(self.p_named)).content.decode())
        with self.settings(AI_PROVIDER='fake'):
            html = self.client.get(_url(self.p_named)).content.decode()
        self.assertIn('<h2>Спросить ИИ</h2>', html)
        self.assertIn('Данные профиля ему не передаются', html)
