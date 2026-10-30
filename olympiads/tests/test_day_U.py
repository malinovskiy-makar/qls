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
