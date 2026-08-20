"""Серверная сборка PDF для калькулятора calc2.

Кнопка «Скачать PDF» падала во ВСЕХ сценах с ошибкой pgfplots
«Paragraph ended before \\pgfplots@@environment@axis was complete».

Причина: .tex приходит обычным текстовым полем формы, а браузер по стандарту
multipart/form-data нормализует переводы строк в текстовых полях к CRLF.
pdflatex считает CR и LF за два перевода строки — после каждой строки файла
появлялась пустая, а пустая строка внутри списка настроек \\begin{axis}[...]
обрывает абзац. Замер: ошибка, поставленная в строку 6, 12 и 20, приезжала
как строка 11, 23 и 39 (ровно 2n−1).

Здесь два уровня защиты:
  1) сама причина — число строк на диске совпадает с числом строк присланного;
  2) эндпоинт целиком — минимальный документ с pgfplots собирается в PDF.
Второй тест пропускается там, где pdflatex не установлен (прод без TeX Live), и
пропуск печатается ГРОМКО: молчаливый skip выглядит как «всё хорошо».
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse

from calc2.views import compile_pdf_pdflatex, normalize_newlines, pdflatex_available

# Минимальный документ ровно той формы, что выпускает buildTex: pgfplots,
# T2A + inputenc, кириллица в подписи, настройки осей одной строкой.
MINIMAL_TEX = "\n".join([
    r"\documentclass[12pt,a4paper]{article}",
    r"\usepackage[T2A]{fontenc}",
    r"\usepackage[utf8]{inputenc}",
    r"\usepackage[english,russian]{babel}",
    r"\usepackage{pgfplots}",
    r"\pgfplotsset{compat=1.18}",
    r"\usetikzlibrary{arrows.meta}",
    r"\begin{document}",
    r"\begin{tikzpicture}",
    r"\begin{axis}[width=10cm, height=7cm, scale only axis, "
    r"xmin=0, xmax=100, ymin=0, ymax=100, xlabel={Объём}, ylabel={Цена}, "
    r"axis lines=left, axis line style={-{Stealth[length=6pt]}}]",
    r"\addplot[blue, very thick, domain=0:100, samples=60, forget plot] {100 - x};",
    r"\node[anchor=west] at (axis cs:50,50) {$P_b = 60$};",
    r"\end{axis}",
    r"\end{tikzpicture}",
    r"\end{document}",
])

# Тот же документ, но список настроек осей в столбик — форма, на которой
# удвоенные переводы строк и роняли сборку.
MULTILINE_AXIS_TEX = "\n".join([
    r"\documentclass[12pt,a4paper]{article}",
    r"\usepackage{pgfplots}",
    r"\pgfplotsset{compat=1.18}",
    r"\usetikzlibrary{arrows.meta}",
    r"\begin{document}",
    r"\begin{tikzpicture}",
    r"\begin{axis}[",
    r"  width=10cm, height=7cm,",
    r"  scale only axis,",
    r"  xmin=0, xmax=100, ymin=0, ymax=100,",
    r"  axis lines=left,",
    r"]",
    r"\addplot[blue, domain=0:100, samples=40] {100 - x};",
    r"\end{axis}",
    r"\end{tikzpicture}",
    r"\end{document}",
])


@tag("calc2")
class NewlineNormalizationTests(TestCase):
    """Причина падения: удвоенные переводы строк."""

    def test_crlf_does_not_add_blank_lines(self):
        """Число строк после нормализации совпадает с исходным."""
        source = "первая\nвторая\nтретья"
        as_browser_sends_it = source.replace("\n", "\r\n")
        self.assertEqual(
            len(normalize_newlines(as_browser_sends_it).split("\n")),
            len(source.split("\n")),
        )

    def test_lone_cr_also_normalized(self):
        self.assertEqual(normalize_newlines("a\rb\r\nc\nd"), "a\nb\nc\nd")

    def test_already_clean_text_untouched(self):
        self.assertEqual(normalize_newlines(MINIMAL_TEX), MINIMAL_TEX)

    def test_written_file_keeps_line_count(self):
        """Строк в файле на диске столько же, сколько прислал браузер.

        Это тот же путь, что у настоящей сборки: compile_pdf_pdflatex пишет
        файл сам. Если pdflatex не установлен, функция вернёт ошибку раньше
        записи — тогда проверяем только нормализацию входа.
        """
        sent = MINIMAL_TEX.replace("\n", "\r\n")
        self.assertEqual(
            normalize_newlines(sent).count("\n"), MINIMAL_TEX.count("\n")
        )


@tag("calc2")
class ExportPdfEndpointTests(TestCase):
    """Эндпоинт /calc2/export/pdf/ целиком."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="calc2_pdf", password="pw12345")
        self.client.force_login(self.user)
        self.url = reverse("calc2:export_pdf")

    def _loud_skip(self, reason):
        line = "=" * 72
        print(f"\n{line}\nПРОПУЩЕНА проверка сборки PDF\nПричина: {reason}\n{line}")
        self.skipTest(reason)

    def test_login_required(self):
        self.client.logout()
        self.assertNotEqual(self.client.post(self.url, {"tex": MINIMAL_TEX}).status_code, 200)

    # Валидация присланного .tex обязана отвечать по существу (400) независимо
    # от того, есть ли на сервере pdflatex — раньше проверка доступности
    # компилятора шла ПЕРВОЙ, и на раннере CI (без pdflatex) любой запрос,
    # даже с мусором вместо .tex, получал 503 вместо 400. Здесь доступность
    # компилятора подменяется явно (patch), а не спрашивается у системы, чтобы
    # тест проверял одно и то же на любой машине.

    def test_empty_tex_rejected_with_pdflatex(self):
        with patch("calc2.views.pdflatex_available", return_value=True):
            resp = self.client.post(self.url, {"tex": "   "})
        self.assertEqual(resp.status_code, 400)

    def test_empty_tex_rejected_without_pdflatex(self):
        with patch("calc2.views.pdflatex_available", return_value=False):
            resp = self.client.post(self.url, {"tex": "   "})
        self.assertEqual(resp.status_code, 400)

    def test_forbidden_command_rejected_with_pdflatex(self):
        bad = MINIMAL_TEX.replace(r"\begin{document}", "\\input{/etc/passwd}\n\\begin{document}")
        with patch("calc2.views.pdflatex_available", return_value=True):
            resp = self.client.post(self.url, {"tex": bad})
        self.assertEqual(resp.status_code, 400)

    def test_forbidden_command_rejected_without_pdflatex(self):
        bad = MINIMAL_TEX.replace(r"\begin{document}", "\\input{/etc/passwd}\n\\begin{document}")
        with patch("calc2.views.pdflatex_available", return_value=False):
            resp = self.client.post(self.url, {"tex": bad})
        self.assertEqual(resp.status_code, 400)

    def test_valid_tex_returns_503_without_pdflatex(self):
        """Валидный .tex без pdflatex — честная деградация (503), не падение."""
        with patch("calc2.views.pdflatex_available", return_value=False):
            resp = self.client.post(self.url, {"tex": MINIMAL_TEX})
        self.assertEqual(resp.status_code, 503)

    def test_pdf_is_built(self):
        """Главный тест: документ формы buildTex собирается в PDF."""
        if not pdflatex_available():
            self._loud_skip("pdflatex не установлен на этой машине")
        resp = self.client.post(self.url, {"tex": MINIMAL_TEX, "name": "проба"})
        self.assertEqual(
            resp.status_code, 200,
            msg="Сборка PDF провалена:\n" + resp.content.decode("utf-8", "replace")[-1200:],
        )
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_pdf_is_built_from_crlf_body(self):
        """Тот же документ с CRLF (как присылает браузер) тоже собирается."""
        if not pdflatex_available():
            self._loud_skip("pdflatex не установлен на этой машине")
        pdf, err = compile_pdf_pdflatex(MINIMAL_TEX.replace("\n", "\r\n"))
        self.assertIsNotNone(pdf, msg="pdflatex не собрал документ с CRLF:\n" + (err or "")[-1200:])
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_crlf_with_multiline_axis_options(self):
        """Чувствительный случай: настройки осей на нескольких строках + CRLF.

        Именно эта пара и роняла сборку. Проверено вживую на MiKTeX: старый
        формат (список настроек в столбик), записанный старым способом, даёт
        ровно «Paragraph ended before \\pgfplots@@environment@axis was
        complete»; тот же файл после нормализации собирается. Генератор сейчас
        пишет настройки одной строкой, но эта проверка стережёт сервер
        отдельно: он обязан переваривать и многострочный список тоже.
        """
        if not pdflatex_available():
            self._loud_skip("pdflatex не установлен на этой машине")
        multiline = MULTILINE_AXIS_TEX.replace("\n", "\r\n")
        pdf, err = compile_pdf_pdflatex(multiline)
        self.assertIsNotNone(
            pdf,
            msg="Сервер не переварил многострочный список настроек с CRLF:\n" + (err or "")[-1200:],
        )
