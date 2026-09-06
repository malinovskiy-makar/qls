# -*- coding: utf-8 -*-
"""Сторож: у страниц сайта нет ни одной ссылки на чужую сеть.

Зачем нужен именно тест, а не разовая проверка. 04.09.2026 все библиотеки
браузера вложены в репозиторий (`static/vendor/`) ради доступности сайта из
России: когда CDN режут, страница открывается, но формулы, калькулятор,
статистика и календарь мертвы — худший вид отказа, потому что снаружи всё
выглядит рабочим. Одной ссылки, дописанной «на минуточку» в новый шаблон,
достаточно, чтобы вернуть эту мину. Тест ловит её в тот же день.

Обоснование решения — ADR 0070.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

# Домены, которых на страницах сайта быть не должно.
FORBIDDEN = (
    'cdn.jsdelivr.net',
    'cdnjs.cloudflare.com',
    'unpkg.com',
    'fonts.googleapis.com',
)

BASE = Path(settings.BASE_DIR)

# Что НЕ является страницей сайта и потому не проверяется.
#
# * `problems/management` и `problems/review_bundle_assets` — пакеты разбора
#   для живых ревьюеров: их открывают с диска двойным щелчком, Django их не
#   отдаёт, и «свой» адрес там не заработал бы вовсе.
# * `reports/` — машинные и человеческие отчёты, тот же случай.
# * `scripts/` — служебные пробы Playwright, запускаются разработчиком.
# * `materials/` — снятая копия чужой ветки для сравнения, не код сайта.
# * `node_modules`, `staticfiles`, `venv*` — не наши файлы.
EXCLUDED_PARTS = (
    'node_modules',
    'staticfiles',
    'materials',
    'review_bundle_assets',
)
EXCLUDED_TOP = ('reports', 'scripts', 'venv', 'venv312', 'venv313', '.git')


def _skip(path: Path) -> bool:
    rel = path.relative_to(BASE)
    parts = rel.parts
    if parts and parts[0] in EXCLUDED_TOP:
        return True
    if parts and parts[0].startswith('venv'):
        return True
    if any(p in EXCLUDED_PARTS for p in parts):
        return True
    # problems/management — команды, а не экраны.
    if len(parts) >= 2 and parts[0] == 'problems' and parts[1] == 'management':
        return True
    return False


def _site_files(pattern: str):
    """Файлы сайта, подходящие под маску, без исключённых веток."""
    for path in BASE.glob(pattern):
        if path.is_file() and not _skip(path):
            yield path


class NoExternalCdnTests(SimpleTestCase):
    """Ни один шаблон и ни один скрипт сайта не ходит в чужую сеть."""

    def _check(self, paths, what):
        offenders = []
        for path in paths:
            text = path.read_text(encoding='utf-8', errors='ignore')
            for domain in FORBIDDEN:
                if domain in text:
                    line = next(
                        (i for i, s in enumerate(text.splitlines(), 1)
                         if domain in s),
                        0,
                    )
                    offenders.append(
                        f'{path.relative_to(BASE)}:{line} → {domain}'
                    )
        self.assertEqual(
            offenders, [],
            f'{what}: библиотеки браузера лежат в static/vendor/, внешних CDN '
            f'у сайта нет (ADR 0070). Найдены ссылки наружу:\n  '
            + '\n  '.join(offenders),
        )

    def test_templates_have_no_cdn(self):
        """Шаблоны: общие в templates/ и все */templates/."""
        paths = list(_site_files('templates/**/*.html'))
        paths += list(_site_files('*/templates/**/*.html'))
        # Проверка самой проверки: файлы вообще нашлись.
        self.assertGreater(len(paths), 50, 'шаблоны сайта не найдены — маска сломана')
        self._check(paths, 'Шаблоны')

    def test_app_static_js_has_no_cdn(self):
        """Скрипты приложений и общая статика сайта."""
        paths = list(_site_files('*/static/**/*.js'))
        paths += list(_site_files('static/**/*.js'))
        self.assertGreater(len(paths), 10, 'скрипты сайта не найдены — маска сломана')
        # Вложенные библиотеки не проверяем на своё же имя: в бандлах чужих
        # библиотек домены встречаются в комментариях и строках, и к ссылкам
        # страницы это отношения не имеет.
        paths = [p for p in paths if 'vendor' not in p.relative_to(BASE).parts]
        self._check(paths, 'Скрипты')


class VendorTreeIsCompleteTests(SimpleTestCase):
    """Папки шрифтов скопированы целиком — иначе не соберётся боевая статика.

    `katex.min.css` ссылается на все три формата шрифта (woff2, woff, ttf), а
    `ManifestStaticFilesStorage` при `collectstatic` разбирает CSS и падает,
    если хоть одного файла нет. Проверяем счётом, чтобы «положил пару шрифтов»
    не прошло молча.
    """

    def test_font_folders(self):
        vendor = BASE / 'static' / 'vendor'
        katex = list((vendor / 'katex-0.16.9' / 'fonts').glob('*'))
        mathlive = list((vendor / 'mathlive-0.110.0' / 'fonts').glob('*'))
        self.assertEqual(len(katex), 60, 'шрифты KaTeX скопированы не полностью')
        self.assertEqual(len(mathlive), 20, 'шрифты MathLive скопированы не полностью')

    def test_no_source_map_references(self):
        """Ссылок на карты исходников нет: они роняют collectstatic.

        Карты в репозиторий не вкладываются (4,4 МБ ради отладки чужого кода),
        поэтому и ссылок на них в бандлах быть не должно — см. vendor/README.md.
        """
        vendor = BASE / 'static' / 'vendor'
        bad = [
            str(p.relative_to(BASE))
            for p in vendor.rglob('*.js')
            if re.search(r'//# sourceMappingURL=', p.read_text(encoding='utf-8', errors='ignore'))
        ]
        self.assertEqual(bad, [], 'остались ссылки на карты исходников')
