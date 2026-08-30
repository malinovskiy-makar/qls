# -*- coding: utf-8 -*-
"""Картинки, ИМПОРТИРОВАННЫЕ вместе с задачей (не собранные из TikZ).

Механика показа общая с собранными (`test_problem_figures.py`), и
периметр безопасности здесь проверяется ЗАНОВО целиком, а не «он же уже
проверен рядом»: у растровых картинок другой путь отдачи (байты и
`Content-Type` вместо `svg`), и класс атаки «произвольный `src` из
текста задачи» обязан быть закрыт и на нём.
"""
import json
import os
import re
import tempfile

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from problems.corpus_converter.images import (
    image_hash, qualify_shkolkovo_images, replace_images, sniff_content_type,
)
from problems.corpus_converter.reconvert import shkolkovo_resolver
from problems.figures import render_figures
from problems.models import Problem, ProblemFigure
from problems.rendering import render_markdown

_IMG_RE = re.compile(r'<img[^>]*>', re.I)
#: Однопиксельный PNG — настоящие байты, а не выдуманные: тип
#: определяется по сигнатуре, и подделка здесь ничего не проверила бы.
PNG_1PX = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
    b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)


def imgs(html):
    return _IMG_RE.findall(html)


class ReplaceImagesTests(SimpleTestCase):
    """Замена ссылки на маркер — чистая функция по СЫРОМУ тексту."""

    def test_markdown_image_replaced_when_file_exists(self):
        text = 'график ниже\n\n![](https://api.solvehub.app/uploads/x.png)\n'
        out, found = replace_images(text, lambda _ref: True)
        self.assertEqual(len(found), 1)
        self.assertIn('[[FIGURE:' + found[0][0] + ']]', out)
        self.assertNotIn('![](', out)

    def test_unresolved_reference_is_left_alone(self):
        """Файла нет — ссылку НЕ трогаем.

        Маркер без строки `ProblemFigure` на экране исчезает, то есть
        картинка пропала бы молча. Пусть лучше останется видимая ссылка:
        её поймает шлюз и отправит задачу на ручной разбор."""
        text = '![](https://iloveeconomics.ru/dead.jpg)'
        out, found = replace_images(text, lambda _ref: False)
        self.assertEqual(found, [])
        self.assertEqual(out, text)

    def test_includegraphics_replaced(self):
        text = r'\includegraphics[width=0.8\textwidth]{Подборки/image.png}'
        out, found = replace_images(text, lambda _ref: True)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][1], 'Подборки/image.png')
        self.assertNotIn(r'\includegraphics', out)

    def test_math_wrapper_around_lone_image_is_removed(self):
        r"""`$$\includegraphics{...}$$` (живые ЛЭШ #63299, #63309).

        Маркер внутри `$$` KaTeX разбирал бы как математику."""
        out, _found = replace_images(
            r'$$\includegraphics[scale=0.35]{a.png}$$', lambda _ref: True)
        self.assertNotIn('$$', out)
        self.assertTrue(out.strip().startswith('[[FIGURE:'))

    def test_idempotent(self):
        """Повторный прогон по тексту с маркерами находит ноль ссылок."""
        once, _f = replace_images('![](a.png)', lambda _ref: True)
        twice, found = replace_images(once, lambda _ref: True)
        self.assertEqual(twice, once)
        self.assertEqual(found, [])

    def test_hash_is_stable_and_derived_from_reference(self):
        """Обе стороны — текст и выгрузка — приходят к хешу независимо."""
        self.assertEqual(image_hash('a.png'), image_hash(' a.png '))
        self.assertNotEqual(image_hash('a.png'), image_hash('b.png'))
        self.assertEqual(len(image_hash('a.png')), 64)


class SniffContentTypeTests(SimpleTestCase):
    """Тип показа — по БАЙТАМ, а не по имени файла."""

    def test_png_jpeg_gif_recognised(self):
        self.assertEqual(sniff_content_type(PNG_1PX), 'image/png')
        self.assertEqual(sniff_content_type(b'\xff\xd8\xff\xe0zzz'), 'image/jpeg')
        self.assertEqual(sniff_content_type(b'GIF89a...'), 'image/gif')

    def test_webp_recognised(self):
        self.assertEqual(
            sniff_content_type(b'RIFF\x00\x00\x00\x00WEBPVP8 '), 'image/webp')

    def test_not_an_image_is_rejected(self):
        """Что не картинка — то не отдаём, как бы ни назывался файл."""
        self.assertIsNone(sniff_content_type(b'<svg onload="alert(1)">'))
        self.assertIsNone(sniff_content_type(b'GIF89a'[:2] + b'\x00'))
        self.assertIsNone(sniff_content_type(b''))
        self.assertIsNone(sniff_content_type(b'\x00\x01\x02\x03'))


class RasterFigureDisplayTests(TestCase):
    """Растровая картинка показывается тем же маркером, что и собранная."""

    def setUp(self):
        self.problem = Problem.objects.create(statement='условие', answer='1')
        self.figure = ProblemFigure.objects.create(
            problem=self.problem, tikz_hash='a' * 64,
            tikz_source='https://api.solvehub.app/uploads/x.png', svg='',
            image_data=PNG_1PX, content_type='image/png',
            source_field='import')

    def test_marker_becomes_img_from_own_row(self):
        out = render_figures(
            render_markdown('график: [[FIGURE:' + 'a' * 64 + ']]'), self.problem)
        found = imgs(out)
        self.assertEqual(len(found), 1)
        self.assertIn('/catalog/figure/' + str(self.figure.pk) + '.svg', found[0])

    def test_view_serves_bytes_with_sniffed_type(self):
        response = self.client.get(
            reverse('catalog:problem_figure_svg', args=[self.figure.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(response.content, PNG_1PX)

    def test_view_keeps_all_three_defensive_headers(self):
        """Адрес кончается на .svg, а отдаётся PNG — тип решает заголовок.

        Поэтому `nosniff` здесь не формальность: без него браузер мог бы
        передумать про тип по расширению в адресе."""
        response = self.client.get(
            reverse('catalog:problem_figure_svg', args=[self.figure.pk]))
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn("default-src 'none'", response['Content-Security-Policy'])
        self.assertEqual(response['Content-Disposition'], 'inline')

    def test_svg_figure_still_served_as_svg(self):
        """Старый путь не сломан: пустой `image_data` — значит SVG."""
        svg_figure = ProblemFigure.objects.create(
            problem=self.problem, tikz_hash='f' * 64,
            tikz_source='\\begin{tikzpicture}\\end{tikzpicture}',
            svg='<svg><circle r="1"/></svg>')
        response = self.client.get(
            reverse('catalog:problem_figure_svg', args=[svg_figure.pk]))
        self.assertEqual(response['Content-Type'], 'image/svg+xml')
        self.assertIn(b'circle', response.content)


class PlainFormatMarkerGuardTests(TestCase):
    r"""`plain` + маркер = сырой `[[FIGURE:…]]` на экране у ученика.

    Ветка `plain` боевого шаблона — это `linebreaksbr`, без
    `render_figures`: маркер уходит на экран дословно. Добавить туда
    подстановку нельзя, не сняв экранирование со всей ветки, а вырезать
    маркер молча — потерять картинку.

    Поэтому инвариант такой: задача, ВИДИМАЯ ученику, не имеет права
    одновременно быть `plain` и содержать маркер. Сегодня таких 12, и все
    12 закрыты (`draft` + `hidden_pending_review`) — они в очереди
    ручного разбора. Тест краснеет, если такую задачу опубликуют.
    """

    def test_visible_plain_problem_must_not_contain_marker(self):
        marker = '[[FIGURE:' + 'a' * 64 + ']]'
        visible = Problem.objects.filter(
            status=Problem.Status.PUBLISHED,
            needs_quality_review=False,
            hidden_pending_review=False,
            content_format=Problem.ContentFormat.PLAIN,
        ).filter(statement__contains='[[FIGURE:')
        self.assertEqual(list(visible), [])

        # И сам механизм: у скрытой задачи маркер допустим, у видимой — нет.
        hidden = Problem.objects.create(
            statement=marker, answer='1',
            content_format=Problem.ContentFormat.PLAIN,
            status=Problem.Status.DRAFT, hidden_pending_review=True)
        self.assertEqual(
            Problem.objects.filter(
                id=hidden.id, status=Problem.Status.PUBLISHED,
                hidden_pending_review=False).count(), 0)

    def test_plain_branch_shows_marker_verbatim(self):
        """Свидетельство, а не рассуждение: вот что увидел бы ученик."""
        from django.template.defaultfilters import linebreaksbr
        marker = '[[FIGURE:' + 'a' * 64 + ']]'
        self.assertIn('[[FIGURE:', linebreaksbr('график: ' + marker))


class RasterSecurityPerimeterTests(TestCase):
    """Тот же класс атаки, что у собранных картинок, — на растровом пути.

    Список векторов повторён ЦЕЛИКОМ, а не урезан: у растровых другой
    путь отдачи, и «рядом уже проверено» здесь не доказательство.
    """

    def setUp(self):
        self.problem = Problem.objects.create(statement='условие', answer='1')
        self.other = Problem.objects.create(statement='чужая', answer='1')
        self.mine = ProblemFigure.objects.create(
            problem=self.problem, tikz_hash='a' * 64, tikz_source='x.png',
            svg='', image_data=PNG_1PX, content_type='image/png')
        self.foreign = ProblemFigure.objects.create(
            problem=self.other, tikz_hash='c' * 64, tikz_source='y.png',
            svg='', image_data=PNG_1PX, content_type='image/png')

    def _render(self, raw_text):
        return render_figures(render_markdown(raw_text), self.problem)

    def test_marker_with_url_body_yields_no_img(self):
        self.assertEqual(imgs(self._render(
            '[[FIGURE:https://attacker.example/x.png]]')), [])

    def test_marker_with_path_traversal_yields_no_img(self):
        self.assertEqual(imgs(self._render('[[FIGURE:../../../etc/passwd]]')), [])

    def test_marker_with_absolute_path_yields_no_img(self):
        self.assertEqual(imgs(self._render('[[FIGURE:/media/anything.png]]')), [])

    def test_raw_img_tag_in_problem_text_yields_no_img(self):
        out = self._render('<img src="https://attacker.example/x.png">')
        self.assertEqual(imgs(out), [])
        self.assertNotIn('<img', out)
        self.assertIn('&lt;img', out)

    def test_raw_svg_tag_in_problem_text_yields_no_svg(self):
        """Санитайзер ЭКРАНИРУЕТ тег, а не вырезает.

        Слово `onload` остаётся видимым ТЕКСТОМ — и это правильно:
        безвреден любой текст, который написал автор. Проверяем
        отсутствие рабочего элемента, а не отсутствие подстроки."""
        out = self._render('<svg onload="alert(1)"><circle r="1"/></svg>')
        self.assertNotIn('<svg', out)
        self.assertIn('&lt;svg', out)
        self.assertEqual(imgs(out), [])

    def test_markdown_image_syntax_yields_no_img(self):
        """Осталась неразрешённая ссылка — картинки нет, но и дыры нет."""
        self.assertEqual(imgs(self._render(
            '![подпись](https://attacker.example/x.png)')), [])

    def test_unknown_but_wellformed_hash_yields_no_img(self):
        self.assertEqual(imgs(self._render('[[FIGURE:' + 'd' * 64 + ']]')), [])

    def test_foreign_problem_figure_is_not_reachable(self):
        out = self._render('[[FIGURE:' + 'c' * 64 + ']]')
        self.assertEqual(imgs(out), [])
        self.assertNotIn(f'/catalog/figure/{self.foreign.pk}.svg', out)

    def test_uppercase_hash_is_not_accepted(self):
        self.assertEqual(imgs(self._render('[[FIGURE:' + 'A' * 64 + ']]')), [])

    def test_data_uri_in_markdown_image_yields_no_img(self):
        """У SolveHub три ссылки — инлайновые `data:`-картинки.

        Файла для них нет, значит маркера тоже нет; и никакого `<img>`
        через текст задачи не появляется."""
        self.assertEqual(imgs(self._render(
            '![](data:image/png;base64,iVBORw0KGgo=)')), [])


class ShkolkovoImageKeyTests(SimpleTestCase):
    r"""Ключ картинки Школково — «id сессии | имя файла», а не имя файла.

    ⚠️ Это исправление вывода прошлой сессии. Она сравнила ПРЕФИКСЫ имён
    скачанных файлов с `Id` задач, получила пересечение ноль и записала
    «453 файла принадлежат 328 ДРУГИМ задачам, картинок нет вовсе».
    Префикс — это `TexSessionId` службы latex-service, а не `Id` задачи;
    по нему пересечение полное: все 328 префиксов ведут ровно к тем 298
    задачам, у которых в тексте есть `\includegraphics`.

    В одной задаче условие и решение приходят РАЗНЫМИ сессиями, поэтому
    голое имя (`7.png`) ссылкой быть не может: оно указывает на разные
    файлы в разных задачах."""

    def test_reference_gets_session_prefix(self):
        text = r'график \includegraphics[width=0.3\linewidth]{ela.png} ниже'
        self.assertEqual(
            qualify_shkolkovo_images(text, 234414),
            r'график \includegraphics[width=0.3\linewidth]{234414|ela.png} ниже')

    def test_two_fields_of_one_problem_get_different_prefixes(self):
        """Условие и решение — разные сессии, значит разные ссылки."""
        st = qualify_shkolkovo_images(r'\includegraphics{7.png}', 111)
        sol = qualify_shkolkovo_images(r'\includegraphics{7.png}', 222)
        self.assertNotEqual(st, sol)
        self.assertNotEqual(image_hash('111|7.png'), image_hash('222|7.png'))

    def test_idempotent(self):
        """Второй прогон не должен приписать префикс дважды."""
        once = qualify_shkolkovo_images(r'\includegraphics{ela.png}', 234414)
        self.assertEqual(qualify_shkolkovo_images(once, 234414), once)

    def test_no_session_id_leaves_reference_alone(self):
        """Без id сессии ссылку не разрешить — оставляем видимой.

        Молча стирать её нельзя: маркер без строки `ProblemFigure` на
        экране исчезает (ADR 0035)."""
        text = r'\includegraphics{ela.png}'
        for empty in (0, None, ''):
            self.assertEqual(qualify_shkolkovo_images(text, empty), text)

    def test_markdown_image_not_touched(self):
        """У Школково картинки только LaTeX-ные; markdown-ссылку,
        если она вдруг встретится, трогать нечем — сессия не её."""
        text = '![](https://example.org/x.png)'
        self.assertEqual(qualify_shkolkovo_images(text, 111), text)

    def test_resolver_finds_file_by_session_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            images = os.path.join(tmp, 'images')
            os.makedirs(images)
            with open(os.path.join(images, '234414_ela.png'), 'wb') as f:
                f.write(PNG_1PX)
            with open(os.path.join(tmp, 'image_map.json'), 'w',
                      encoding='utf-8') as f:
                json.dump({'234414|ela.png': '234414_ela.png'}, f)
            resolver = shkolkovo_resolver(tmp)
            self.assertTrue(resolver('234414|ela.png'))
            self.assertFalse(resolver('ela.png'))
            self.assertFalse(resolver('999999|ela.png'))
            self.assertTrue(
                resolver.path_for('234414|ela.png').endswith('234414_ela.png'))
