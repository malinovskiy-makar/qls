"""Экспортёр офлайн-пакетов для ручного ревью внешнего вида задач.

Что делает: для каждой ВИДИМОЙ задачи (published, не за качественным шлюзом)
рендерит НАСТОЯЩУЮ страницу problem_detail через Django test client — те же
вьюхи, шаблоны, CSS и JS, что видит посетитель сайта, — и сохраняет HTML-снимок
в пакет. Пакет открывается офлайн с file:// без интернета: KaTeX и шрифты
вендорены в assets/, CDN-ссылки и /static/-/media/-пути переписаны на
относительные. Рядом кладутся manifest.json/manifest.js (список задач + категории
вердиктов из problems/review_categories.py) и оболочка ревьюера reviewer.html.

Примеры:
    ./venv/bin/python manage.py export_review_bundle --source-id 2 \
        --out reports/review_bundles/ile_20260721
    ./venv/bin/python manage.py export_review_bundle --ids-file ids.txt --out /tmp/b

В снимке всё раскрыто без кликов (ответы, решение): инъекция CSS поверх
боевого HTML (пост-обработка сокрытий, сам конвейер рендера не трогается).
Решения, скрытые на сайте (solution_needs_review), скрыты и в снимке — ревью
смотрит ровно то, что видит посетитель.
"""

import json
import re
import shutil
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.staticfiles import finders
from django.test import Client
from django.utils import timezone

from problems.models import Problem
from problems.review_categories import BUNDLE_FORMAT, REVIEW_CATEGORIES

# Каталог с вендорными ассетами пакета (KaTeX + оболочка ревьюера).
ASSETS_SRC = Path(__file__).resolve().parents[2] / 'review_bundle_assets'

# Боевой base.html грузит KaTeX с CDN — в офлайн-пакете переписываем на вендор.
KATEX_CDN_PREFIX = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/'
KATEX_LOCAL_PREFIX = '../assets/vendor/katex/'

# Инъекция в <head> снимка: раскрыть скрытое, обезвредить навигацию.
# .reveal-content — блоки «Ответ»/«Решение» страницы задачи (display:none на
# сайте, раскрываются кнопкой); в снимке раскрыты всегда, кнопки спрятаны.
# Ссылки отключены целиком: из офлайн-снимка навигация ведёт в никуда.
SNAPSHOT_OVERRIDES = """<style id="review-snapshot-overrides">
.reveal-content { display: block !important; }
.reveal-btn { display: none !important; }
a { pointer-events: none; cursor: default; }
</style>
"""

# href/src, указывающие в /static/ или /media/ — переписываются и копируются.
ASSET_ATTR_RE = re.compile(r'\b(href|src)="(/(?:static|media)/[^"]+)"')
# url(...) внутри CSS-файлов (для докопирования шрифтов/картинок, на которые
# ссылается скопированный CSS).
CSS_URL_RE = re.compile(r'url\(\s*[\'"]?([^\'")?#]+)')


class Command(BaseCommand):
    help = ('Собрать офлайн-пакет снимков боевых страниц задач для ручного '
            'ревью внешнего вида (reviewer.html + manifest + assets).')

    def add_arguments(self, parser):
        parser.add_argument('--source-id', type=int, default=None,
                            help='Все видимые задачи этого источника (Source.id).')
        parser.add_argument('--ids-file', default=None,
                            help='Файл со списком id задач (по одному в строке); '
                                 'порядок файла сохраняется в манифесте.')
        parser.add_argument('--out', required=True,
                            help='Каталог пакета (создаётся).')
        parser.add_argument('--bundle-id', default=None,
                            help='Идентификатор пакета (по умолчанию — имя '
                                 'каталога --out). Ключ localStorage ревьюера.')
        parser.add_argument('--limit', type=int, default=None,
                            help='Ограничить число задач (для отладки).')

    # ── выбор задач ─────────────────────────────────────────────────────

    def _visible_qs(self):
        return Problem.objects.filter(status=Problem.Status.PUBLISHED,
                                      needs_quality_review=False)

    def _resolve_problems(self, opts):
        """Список видимых задач в порядке манифеста."""
        if bool(opts['source_id']) == bool(opts['ids_file']):
            raise CommandError('Нужен ровно один из --source-id / --ids-file.')

        if opts['source_id']:
            qs = (self._visible_qs()
                  .filter(source_references__source_id=opts['source_id'])
                  .distinct().order_by('id'))
            problems = list(qs)
        else:
            path = Path(opts['ids_file'])
            if not path.exists():
                raise CommandError(f'Файл не найден: {path}')
            ids = [int(line) for line in path.read_text().split() if line.strip()]
            by_id = {p.id: p for p in self._visible_qs().filter(id__in=ids)}
            problems = [by_id[i] for i in ids if i in by_id]
            invisible = [i for i in ids if i not in by_id]
            if invisible:
                self.stdout.write(self.style.WARNING(
                    f'Пропущено {len(invisible)} id (не published или за шлюзом): '
                    f'{invisible[:10]}{"…" if len(invisible) > 10 else ""}'))
        if opts['limit']:
            problems = problems[:opts['limit']]
        if not problems:
            raise CommandError('Не найдено ни одной видимой задачи.')
        return problems

    # ── ассеты ──────────────────────────────────────────────────────────

    def _copy_static(self, relpath: str, out_dir: Path) -> None:
        """Скопировать файл статики (+ то, на что ссылается его CSS)."""
        if relpath in self._copied:
            return
        self._copied.add(relpath)
        src = finders.find(relpath)
        if not src:
            self.stdout.write(self.style.WARNING(f'  статика не найдена: {relpath}'))
            return
        dst = out_dir / 'assets' / 'static' / relpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if relpath.endswith('.css'):
            css = Path(src).read_text(encoding='utf-8', errors='replace')
            base = Path(relpath).parent
            for ref in CSS_URL_RE.findall(css):
                ref = ref.strip()
                if ref.startswith(('data:', 'http:', 'https:', '//', '/')):
                    continue
                self._copy_static(str((base / ref).as_posix()), out_dir)

    def _copy_media(self, relpath: str, out_dir: Path) -> None:
        if relpath in self._copied:
            return
        self._copied.add(relpath)
        src = Path(settings.MEDIA_ROOT) / relpath
        if not src.exists():
            self.stdout.write(self.style.WARNING(f'  media не найдена: {relpath}'))
            return
        dst = out_dir / 'assets' / 'media' / relpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # ── обработка HTML ──────────────────────────────────────────────────

    def _process_html(self, html: str, out_dir: Path) -> str:
        """Переписать пути на относительные, собрать ассеты, раскрыть скрытое."""
        html = html.replace(KATEX_CDN_PREFIX, KATEX_LOCAL_PREFIX)

        def _rewrite(m):
            attr, url = m.group(1), m.group(2)
            kind, rel = url.lstrip('/').split('/', 1)  # 'static'|'media', хвост
            if kind == 'static':
                self._copy_static(rel, out_dir)
            else:
                self._copy_media(rel, out_dir)
            return f'{attr}="../assets/{kind}/{rel}"'

        html = ASSET_ATTR_RE.sub(_rewrite, html)
        html = html.replace('</head>', SNAPSHOT_OVERRIDES + '</head>', 1)
        return html

    # ── главный цикл ────────────────────────────────────────────────────

    def handle(self, *args, **opts):
        problems = self._resolve_problems(opts)
        out_dir = Path(opts['out'])
        bundle_id = opts['bundle_id'] or out_dir.name
        (out_dir / 'snapshots').mkdir(parents=True, exist_ok=True)
        self._copied = set()

        # Test client шлёт Host: testserver — разрешаем на время команды.
        if 'testserver' not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver']
        client = Client()

        # problem_detail публична; если вьюху когда-нибудь закроют логином —
        # редирект на login ловим и входим программно локальным пользователем.
        logged_in = False

        manifest_problems = []
        skipped = []
        total = len(problems)
        for i, problem in enumerate(problems, 1):
            url = f'/catalog/problem/{problem.pk}/'
            resp = client.get(url)
            if resp.status_code in (301, 302) and not logged_in:
                self._force_login(client)
                logged_in = True
                resp = client.get(url)
            if resp.status_code != 200:
                skipped.append((problem.pk, resp.status_code))
                continue

            html = self._process_html(resp.content.decode('utf-8'), out_dir)
            stamp = (f'<!-- qls-review-snapshot bundle={bundle_id} '
                     f'problem={problem.pk} -->\n')
            (out_dir / 'snapshots' / f'{problem.pk}.html').write_text(
                stamp + html, encoding='utf-8')

            ref = problem.source_references.select_related('source').first()
            manifest_problems.append({
                'id': problem.pk,
                'order': len(manifest_problems) + 1,
                'title': problem.title or f'Задача #{problem.pk}',
                'source': ref.source.name if ref else '',
                'file': f'snapshots/{problem.pk}.html',
            })
            if i % 100 == 0 or i == total:
                self.stdout.write(f'  {i}/{total}…')

        # Вендор KaTeX — целиком (CSS тянет шрифты относительными путями).
        vendor_src = ASSETS_SRC / 'vendor'
        vendor_dst = out_dir / 'assets' / 'vendor'
        if vendor_dst.exists():
            shutil.rmtree(vendor_dst)
        shutil.copytree(vendor_src, vendor_dst)

        # Оболочка ревьюера + манифест (json — канон, js — то же самое для
        # file:// в Chrome: fetch() локальных файлов там запрещён, <script> — нет).
        shutil.copy2(ASSETS_SRC / 'reviewer.html', out_dir / 'reviewer.html')
        manifest = {
            'format': BUNDLE_FORMAT,
            'bundle_id': bundle_id,
            'created_at': timezone.now().isoformat(),
            'count': len(manifest_problems),
            'categories': REVIEW_CATEGORIES,
            'problems': manifest_problems,
        }
        manifest_json = json.dumps(manifest, ensure_ascii=False, indent=1)
        (out_dir / 'manifest.json').write_text(manifest_json, encoding='utf-8')
        # </ внутри строк JSON закрыл бы <script> — экранируем.
        (out_dir / 'manifest.js').write_text(
            'window.REVIEW_MANIFEST = ' + manifest_json.replace('</', '<\\/') + ';\n',
            encoding='utf-8')

        size_mb = sum(f.stat().st_size for f in out_dir.rglob('*') if f.is_file()) / 1e6
        self.stdout.write(self.style.SUCCESS(
            f'Пакет {bundle_id}: снимков {len(manifest_problems)}, '
            f'пропущено {len(skipped)}, размер {size_mb:.1f} МБ → {out_dir}'))
        if skipped:
            self.stdout.write(self.style.WARNING(f'Пропуски (id, код): {skipped[:20]}'))

    def _force_login(self, client: Client) -> Optional[object]:
        from problems.models import User
        user = (User.objects.filter(is_superuser=True).first()
                or User.objects.first())
        if user is None:
            raise CommandError('Страница требует логина, а пользователей в базе нет.')
        client.force_login(user)
        self.stdout.write(f'Программный логин: {user.username}')
        return user
