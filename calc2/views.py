"""
Views для собственного графического движка (Этап Е, приложение calc2).

Это НОВЫЙ калькулятор на открытых библиотеках (D3.js + Math.js), который
со временем заменит калькулятор на Desmos (приложение graphs, страница /desmos/).
Старый калькулятор не трогаем — он продолжает работать как есть.

Пока в базе ничего не сохраняем (моделей у calc2 нет): это чистый
интерактивный инструмент. Сохранение графиков — задача будущих сессий.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView


# ── Компиляция через pdflatex ──────────────────────────────────────────────
# Экспорт подборок задач (catalog/latex_export.py) остаётся на xelatex: там
# документ с fontspec, и трогать работающую функцию незачем. Калькулятор же
# выпускает чистый TikZ с inputenc и T2A, который собирается ОБЫЧНЫМ pdflatex,
# поэтому у него своя маленькая сборка без общих зависимостей.

def _pdflatex_bin():
    """Путь к pdflatex: из настроек, иначе из PATH, иначе рядом с xelatex."""
    path = getattr(settings, 'PDFLATEX_PATH', None)
    if path:
        return path
    found = shutil.which('pdflatex')
    if found:
        return found
    # На macOS TeX Live прописывают одной строкой XELATEX_PATH — pdflatex лежит рядом.
    xe = getattr(settings, 'XELATEX_PATH', None)
    if xe:
        guess = os.path.join(os.path.dirname(xe), 'pdflatex')
        if os.path.isfile(guess):
            return guess
    return None


def pdflatex_available():
    """True, если на этом сервере есть чем собрать PDF."""
    binary = _pdflatex_bin()
    return bool(binary) and os.path.isfile(binary) and os.access(binary, os.X_OK)


def compile_pdf_pdflatex(tex_content):
    """Собирает .tex в PDF. Возвращает (bytes, None) или (None, лог ошибки)."""
    binary = _pdflatex_bin()
    if not binary:
        return None, 'pdflatex не найден на сервере'
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / 'graph.tex'
        pdf_path = Path(tmpdir) / 'graph.pdf'
        log_path = Path(tmpdir) / 'graph.log'
        tex_path.write_text(tex_content, encoding='utf-8')
        try:
            proc = subprocess.run(
                [binary, '-interaction=nonstopmode', '-halt-on-error',
                 '-output-directory', tmpdir, str(tex_path)],
                capture_output=True, timeout=40,
                # Рабочая папка — сама временная. Без неё MiKTeX на Windows
                # пытается писать вспомогательные файлы туда, откуда запущен
                # сервер, и на первом же промахе прав тихо падает, не оставляя
                # даже .log: сообщение об ошибке выходило пустым.
                cwd=tmpdir,
            )
        except FileNotFoundError:
            return None, 'pdflatex не найден на сервере'
        except subprocess.TimeoutExpired:
            return None, 'pdflatex превысил лимит времени (40 с)'
        if pdf_path.exists():
            return pdf_path.read_bytes(), None
        # Лога может не быть вовсе (компилятор упал до его создания) — тогда
        # показываем код возврата и вывод, иначе диагностировать нечем.
        if log_path.exists():
            return None, log_path.read_text(encoding='utf-8', errors='replace')
        out = (proc.stdout or b'').decode('utf-8', 'replace')
        err = (proc.stderr or b'').decode('utf-8', 'replace')
        return None, 'код возврата {}\n{}\n{}'.format(proc.returncode, out[-800:], err[-800:])


@method_decorator(login_required, name='dispatch')
class Calc2View(TemplateView):
    """Рендерит страницу нового графического калькулятора.

    Требует входа в систему (@login_required) — как и калькулятор Desmos.
    """
    template_name = 'calc2/calc2.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Честно говорим интерфейсу, умеет ли ЭТОТ сервер собирать PDF.
        # На бесплатном тарифе Render компилятора нет, поэтому кнопка
        # «Скачать PDF» там не показывается вовсе — как это уже сделано на
        # странице экспорта подборок (catalog/collection_export.html).
        ctx['has_pdflatex'] = pdflatex_available()
        return ctx


# Команды LaTeX, которых наш генератор не выпускает и которые дают доступ
# к файловой системе или к оболочке. Файл .tex приходит с клиента, поэтому
# проверяем его перед запуском компилятора: pdflatex по умолчанию идёт без
# --shell-escape, но \input умеет вклеить в PDF содержимое чужого файла.
_TEX_FORBIDDEN = re.compile(
    r'\\(write18|input|include|openin|openout|read|catcode|csname|immediate'
    r'|directlua|usepackage\s*\{\s*shellesc)',
    re.IGNORECASE,
)


@login_required
@require_POST
def export_pdf(request):
    """Компилирует присланный .tex в PDF через pdflatex и отдаёт файл.

    Используется кнопкой «Скачать PDF» в окне экспорта калькулятора. Сам .tex
    собирает клиент (buildTex в calc2.html): он переводит нарисованный холст
    в TikZ. Здесь только компиляция.
    """
    if not pdflatex_available():
        return HttpResponse(
            'На этом сервере не установлен pdflatex. Скачайте .tex и '
            'скомпилируйте его в Overleaf.',
            status=503, content_type='text/plain; charset=utf-8',
        )

    tex = request.POST.get('tex', '')
    if not tex.strip():
        return HttpResponseBadRequest('Пустой файл .tex')
    if len(tex) > 900_000:
        return HttpResponseBadRequest('Файл .tex слишком большой')
    if _TEX_FORBIDDEN.search(tex):
        return HttpResponseBadRequest('В .tex есть команды, которые сервер не компилирует')

    pdf, err = compile_pdf_pdflatex(tex)
    if pdf is None:
        # Лог компилятора длинный; для окна экспорта хватает хвоста.
        return HttpResponse(
            'pdflatex не собрал PDF:\n' + (err or '')[-1500:],
            status=500, content_type='text/plain; charset=utf-8',
        )

    name = re.sub(r'[^\w \-.]+', '', request.POST.get('name', 'график'))[:60] or 'график'
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = 'attachment; filename="{}.pdf"'.format(name)
    return resp
