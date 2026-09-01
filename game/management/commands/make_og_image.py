"""
Брендовая картинка-превью для ссылок на результат (Open Graph, 1200×630).

Картинка СТАТИЧНАЯ и одна на все результаты: счёт и режим едут в тексте
og:title/og:description, который мессенджер показывает рядом. Рисовать
персональную картинку на сервере под каждый забег — значит держать очередь
рендера ради ссылки, которой поделятся раз в сотню забегов; персональная
карточка и так рисуется в браузере игрока (кнопка «Поделиться картинкой»).

Запуск (результат коммитим в репозиторий, каждый раз он не нужен):
    ./venv/bin/python manage.py make_og_image

Шрифт ищем среди системных с кириллицей. Не нашли — рисуем без текста,
но не падаем: картинка-заливка лучше отсутствующей картинки.
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand

W, H = 1200, 630
BG = (13, 13, 18)
ACCENT = (255, 77, 148)      # малиновый тёмной темы — на тёмном фоне читается
WHITE = (255, 255, 255)
MUTED = (150, 150, 165)

# Кандидаты в порядке предпочтения: DejaVu (есть с matplotlib/PIL),
# затем системные macOS/Linux с кириллицей.
FONT_CANDIDATES = [
    'DejaVuSans-Bold.ttf',
    '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
    '/System/Library/Fonts/Helvetica.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/Library/Fonts/Arial Bold.ttf',
]


class Command(BaseCommand):
    help = 'Рисует game/static/game/og_default.png (превью ссылок, 1200×630)'

    def add_arguments(self, parser):
        parser.add_argument('--out', default=None, help='куда сохранить PNG')

    def handle(self, *args, **opts):
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            self.stderr.write('Нужен Pillow: ./venv/bin/pip install Pillow')
            return

        out = opts['out'] or os.path.join(
            settings.BASE_DIR, 'game', 'static', 'game', 'og_default.png')
        os.makedirs(os.path.dirname(out), exist_ok=True)

        img = Image.new('RGB', (W, H), BG)
        d = ImageDraw.Draw(img)

        # малиновая полоса слева — тот же акцент, что на сайте
        d.rectangle([0, 0, 14, H], fill=ACCENT)
        # мягкое пятно акцента в углу
        for i in range(70):
            k = i / 70
            r = int(420 * (1 - k))
            d.ellipse([W - 260 - r, -180 - r, W - 260 + r, -180 + r],
                      fill=(int(BG[0] + (40 - BG[0]) * k * .5),
                            int(BG[1] + (18 - BG[1]) * k * .5),
                            int(BG[2] + (40 - BG[2]) * k * .5)))

        def font(size):
            for path in FONT_CANDIDATES:
                try:
                    return ImageFont.truetype(path, size)
                except (OSError, IOError):
                    continue
            return None

        f_title, f_sub, f_small = font(96), font(40), font(28)
        if f_title is None:
            # Шрифта с кириллицей нет — сохраняем фон без текста.
            img.save(out, 'PNG', optimize=True)
            self.stdout.write(self.style.WARNING(
                f'Шрифт не найден — сохранил заливку без текста: {out}'))
            return

        d.text((80, 180), 'Econ Rush', font=f_title, fill=WHITE)
        d.text((80, 300), 'Игра на скорость по олимпиадной экономике',
               font=f_sub, fill=MUTED)
        d.text((80, 380), '3 жизни · 4 режима · обгонишь?', font=f_sub, fill=ACCENT)
        d.text((80, H - 90), 'Weconomics', font=f_small, fill=MUTED)

        img.save(out, 'PNG', optimize=True)
        self.stdout.write(self.style.SUCCESS(
            f'Готово: {out} ({os.path.getsize(out) // 1024} КБ)'))
