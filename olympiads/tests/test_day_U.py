"""День 30.10, часть У: правки экранов раздела после приёмки владельцем."""
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from olympiads.models import OlympiadVariantFile

from . import night_fixtures as fx

User = get_user_model()
MEDIA = tempfile.mkdtemp(prefix='day-u-')
PDF = b'%PDF-1.4\n% test\n'
ZIP_URL = 'https://vso.edsoo.ru/public.php/dav/files/eMb3/?accept=zip#Экономика'


def add_file(variant, kind, url, body=PDF, name='f.pdf', order=0):
    item = OlympiadVariantFile(variant=variant, kind=kind, url=url,
                               sha256='%064d' % (OlympiadVariantFile.objects.count() + 1),
                               order=order)
    item.file.save(name, ContentFile(body), save=False)
    item.save()
    return item


@override_settings(OLYMPIADS_PUBLIC=True, MEDIA_ROOT=MEDIA, OLYMPIAD_AI_CHECK=False)
class OwnPdfTests(TestCase):
    """У1: «PDF», «Условия в PDF», «Разборы тура» — только наша копия."""

    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.final = fx.stage(cls.olymp)
        cls.variant = fx.kit(cls.olymp, cls.final, '2025/26', tour='2')
        cls.mirror = add_file(cls.variant, 'условия',
                              'https://iloveeconomics.ru/sites/tur2.pdf', order=0)
        cls.tasks = add_file(cls.variant, 'условия',
                             'https://vos.olimpiada.ru/upload/tasks-tur2.pdf', order=1)
        cls.solutions = add_file(cls.variant, 'решения+критерии',
                                 'https://vos.olimpiada.ru/upload/sol-tur2.pdf', order=2)
        cls.archive = add_file(cls.variant, 'условия+решения+критерии', ZIP_URL,
                               body=b'PK\x03\x04zip', name='r.pdf', order=3)
        cls.user = User.objects.create_user('pupil', password='x')

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def file_url(self, item):
        return reverse('olympiads:variant_file', args=['vs', self.variant.pk, item.pk])

    def pages(self):
        intro = reverse('olympiads:training_intro', args=['vs', self.variant.pk])
        detail = reverse('olympiads:detail', args=['vs'])
        cell = 'c{}'.format(self.variant.pk)
        self.client.force_login(self.user)
        self.client.post(reverse('olympiads:training_start', args=['vs', self.variant.pk]),
                         {'timer': '0'})
        self.client.post(reverse('olympiads:training_finish', args=['vs', self.variant.pk]))
        result = reverse('olympiads:training_result', args=['vs', self.variant.pk])
        return {path: self.client.get(path).content.decode()
                for path in (reverse('olympiads:list'), detail, detail + '?open=' + cell,
                             intro, intro + '?mode=timed', result)}

    def test_no_external_file_address_on_any_page(self):
        urls = list(OlympiadVariantFile.objects.values_list('url', flat=True))
        for path, html in self.pages().items():
            self.assertNotIn('vso.edsoo.ru', html, path)
            self.assertNotIn('accept=zip', html, path)
            for url in urls:
                self.assertNotIn(url, html, path)

    def test_buttons_lead_to_own_copy_official_first(self):
        pages = self.pages()
        intro = reverse('olympiads:training_intro', args=['vs', self.variant.pk])
        self.assertIn(self.file_url(self.tasks), pages[intro])
        self.assertNotIn(self.file_url(self.mirror), pages[intro])
        result = reverse('olympiads:training_result', args=['vs', self.variant.pk])
        self.assertIn(self.file_url(self.solutions), pages[result])
        self.assertIn('Разборы тура', pages[result])

    def test_pdf_is_served_inline(self):
        response = self.client.get(self.file_url(self.solutions))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response['Content-Disposition'].startswith('inline'))
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(b''.join(response.streaming_content), PDF)

    def test_archive_and_foreign_file_are_404(self):
        self.assertEqual(self.client.get(self.file_url(self.archive)).status_code, 404)
        other = fx.kit(self.olymp, self.final, '2024/25', tour='1')
        url = reverse('olympiads:variant_file', args=['vs', other.pk, self.tasks.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_hidden_olympiad_file_is_404(self):
        self.olymp.is_published = False
        self.olymp.save(update_fields=['is_published'])
        self.assertEqual(self.client.get(self.file_url(self.tasks)).status_code, 404)

    def test_no_file_no_button(self):
        bare = fx.kit(self.olymp, self.final, '2023/24', tour='1')
        intro = reverse('olympiads:training_intro', args=['vs', bare.pk])
        self.assertNotIn('Условия в PDF', self.client.get(intro).content.decode())

    def test_archive_source_is_named_without_link(self):
        from olympiads.models import FactSource
        source = FactSource.objects.create(url=ZIP_URL, title='Требования к заключительному этапу')
        self.olymp.source = source
        self.olymp.save(update_fields=['source'])
        html = self.client.get(reverse('olympiads:detail', args=['vs'])).content.decode()
        self.assertIn('Требования к заключительному этапу', html)
        self.assertNotIn('vso.edsoo.ru', html)


@override_settings(OLYMPIADS_PUBLIC=True, MEDIA_ROOT=MEDIA, OLYMPIAD_AI_CHECK=False)
class AnswerFieldTests(TestCase):
    """У2: поле «Ответ» — только у теста, по типу задачи, а не по эталону."""

    @classmethod
    def setUpTestData(cls):
        from problems.models import ProblemPart
        cls.olymp = fx.olympiad('vs')
        cls.final = fx.stage(cls.olymp)
        cls.variant = fx.kit(cls.olymp, cls.final, '2025/26', tour='2', tasks=2)
        items = list(cls.variant.items.order_by('order'))
        cls.open_task = items[0].problem
        cls.open_task.answer = '1,5'
        cls.open_task.save(update_fields=['answer'])
        for label in 'абв':
            ProblemPart.objects.create(problem=cls.open_task, label=label,
                                       statement='Вопрос ' + label, answer='12')
        items[0].has_answer = True
        items[0].save(update_fields=['has_answer'])
        cls.test_task = items[1].problem
        cls.test_task.problem_type = 'тест: числовой ответ'
        cls.test_task.answer = '42'
        cls.test_task.save(update_fields=['problem_type', 'answer'])

    def page(self, task):
        self.client.post(reverse('olympiads:training_start', args=['vs', self.variant.pk]),
                         {'timer': '0'})
        url = reverse('olympiads:training_take', args=['vs', self.variant.pk])
        html = self.client.get(url + '?task=%d' % task).content.decode()
        start = html.index('data-task="%d"' % task, html.index('id="exam-form"'))
        end = html.find('class="om-taskpane"', start)
        return html[start:end if end > 0 else len(html)]

    def test_open_task_with_reference_has_no_answer_fields(self):
        pane = self.page(1)
        self.assertNotIn('answer-short', pane)
        self.assertNotIn('Ответ а', pane)
        self.assertIn('Решение', pane)

    def test_test_task_has_answer_field(self):
        self.assertIn('answer-short', self.page(2))

    def test_reference_answer_goes_to_ai_prompt(self):
        from olympiads import ai_check
        how = {'maximum': 12, 'approximate': True, 'text': 'Критерии'}
        prompt = ai_check.build_prompt(self.open_task, list(self.open_task.parts.all()),
                                       how, 'решение')
        self.assertIn('ЭТАЛОННЫЙ ОТВЕТ', prompt)
        self.assertIn('а) 12', prompt)


@override_settings(OLYMPIADS_PUBLIC=True, MEDIA_ROOT=MEDIA, OLYMPIAD_AI_CHECK=False)
class SubmitItemTests(TestCase):
    """У6: «Сдать задание» сдаёт ровно одно задание; тур — только «Завершить тур»."""

    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.final = fx.stage(cls.olymp)
        cls.variant = fx.kit(cls.olymp, cls.final, '2025/26', tour='2', tasks=8)

    def url(self, name):
        return reverse('olympiads:' + name, args=['vs', self.variant.pk])

    def test_two_items_of_eight_leave_attempt_open(self):
        from olympiads import training_engine as engine
        from olympiads.models import TrainingAttempt
        self.client.post(self.url('training_start'), {'timer': '0'})
        items = engine.variant_items(self.variant)
        for item in items[:2]:
            self.client.post(self.url('training_item_submit'), {
                'item_id': item.pk, 'solution_item_%d' % item.pk: 'решение'})
        attempt = TrainingAttempt.objects.get()
        self.assertIsNone(attempt.submitted_at)
        self.assertEqual(attempt.results.count(), 2)

    def test_late_autosave_of_submitted_item_is_not_409(self):
        from olympiads import training_engine as engine
        self.client.post(self.url('training_start'), {'timer': '0'})
        item = engine.variant_items(self.variant)[0]
        self.client.post(self.url('training_item_submit'), {
            'item_id': item.pk, 'solution_item_%d' % item.pk: 'решение'})
        response = self.client.post(self.url('training_autosave'),
                                    data={'item_id': item.pk, 'solution': 'ещё'},
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('saved'), False)


@override_settings(OLYMPIADS_PUBLIC=True, MEDIA_ROOT=MEDIA, OLYMPIAD_AI_CHECK=False)
class OwnDialogTests(TestCase):
    """У3: на странице тура — своё окно; общий exam.js не тронут."""

    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.final = fx.stage(cls.olymp)
        cls.variant = fx.kit(cls.olymp, cls.final, '2025/26', tour='2')

    def test_take_page_has_own_dialog_after_exam_js(self):
        self.client.post(reverse('olympiads:training_start', args=['vs', self.variant.pk]),
                         {'timer': '1'})
        html = self.client.get(reverse('olympiads:training_take',
                                       args=['vs', self.variant.pk])).content.decode()
        self.assertIn('id="om-dlg"', html)
        self.assertLess(html.index('platform/exam.js'), html.index('id="om-dlg"'))
        self.assertIn('stopImmediatePropagation', html)
        self.assertNotIn('window.confirm', html)
        self.assertNotIn('alert(', html)


@override_settings(OLYMPIADS_PUBLIC=True, MEDIA_ROOT=MEDIA, OLYMPIAD_AI_CHECK=False)
class NoInventedMaximumTests(TestCase):
    """У4: балл позиции неизвестен — числа нет; максимум тура — по правилу навигатора."""

    @classmethod
    def setUpTestData(cls):
        cls.olymp = fx.olympiad('vs')
        cls.final = fx.stage(cls.olymp)      # максимум этапа 48
        cls.scored = fx.kit(cls.olymp, cls.final, '2025/26', tour='2', tasks=4, score=12)
        cls.unscored = fx.kit(cls.olymp, cls.final, '2025/26', tour='1', tasks=4, score=None)

    def html(self, variant, name, timer='0'):
        self.client.post(reverse('olympiads:training_start', args=['vs', variant.pk]),
                         {'timer': timer})
        return self.client.get(reverse('olympiads:' + name, args=['vs', variant.pk])).content.decode()

    def test_item_without_score_has_no_ten_points(self):
        for name in ('training_intro', 'training_take'):
            html = self.html(self.unscored, name)
            self.assertNotIn('10 баллов', html, name)
            self.assertNotIn('3 балла', html, name)

    def test_tour_without_scores_is_out_of_stage_maximum(self):
        from olympiads.models import TrainingAttempt
        self.html(self.unscored, 'training_intro')
        self.client.post(reverse('olympiads:training_finish', args=['vs', self.unscored.pk]))
        attempt = TrainingAttempt.objects.get(variant=self.unscored)
        self.assertEqual(float(attempt.max_score), 48.0)
        result = self.client.get(reverse('olympiads:training_result',
                                         args=['vs', self.unscored.pk])).content.decode()
        self.assertIn('из 48', result)
        self.assertNotIn('из 40', result)

    def test_scored_tour_is_sum_of_positions(self):
        from olympiads.models import TrainingAttempt
        self.html(self.scored, 'training_intro')
        self.client.post(reverse('olympiads:training_finish', args=['vs', self.scored.pk]))
        self.assertEqual(float(TrainingAttempt.objects.get(variant=self.scored).max_score), 48.0)
        self.assertIn('12 баллов', self.html(self.scored, 'training_intro'))
