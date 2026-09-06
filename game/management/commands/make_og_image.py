"""
Брендовая картинка-превью для ссылок на забег (Open Graph, 1200×630).

Картинка СТАТИЧНАЯ и одна на все результаты: счёт и режим едут в тексте
og:title/og:description, который мессенджер показывает рядом. Рисовать
персональную картинку на сервере под каждый забег — значит держать очередь
рендера ради ссылки, которой поделятся раз в сотню забегов; персональная
карточка и так рисуется в браузере игрока (кнопка «Поделиться картинкой»).

⚠️ ЗНАК «W» — НАСТОЯЩИЙ, ИЗ ЛОГОТИПА. Тот же path, что в
`templates/_rush_logo.html` и `static/img/logo-mark.svg`, а не нарисованная
заново похожая закорючка: знак у бренда один. Растеризуем его здесь сами
(разбор кривых Безье ниже) — cairosvg в зависимостях нет, а тащить его
ради одной картинки, которую рисуют раз в полгода, незачем.

Запуск (результат коммитим в репозиторий, каждый раз он не нужен):
    ./venv/bin/python manage.py make_og_image

Шрифт ищем среди системных с кириллицей. Не нашли — рисуем без текста,
но не падаем: картинка-заливка лучше отсутствующей картинки.
"""
import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand

W, H = 1200, 630
BG = (13, 13, 18)
ACCENT = (255, 77, 148)      # малиновый тёмной темы — на тёмном фоне читается
WHITE = (255, 255, 255)
MUTED = (150, 150, 165)

# Кандидаты в порядке предпочтения: DejaVu (есть с matplotlib/PIL),
# затем системные macOS/Linux/Windows с кириллицей.
FONT_CANDIDATES = [
    'DejaVuSans-Bold.ttf',
    'C:/Windows/Fonts/arialbd.ttf',
    '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
    '/System/Library/Fonts/Helvetica.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/Library/Fonts/Arial Bold.ttf',
]

# Путь знака и его плотный bbox — ровно те же числа, что в _rush_logo.html.
MARK_SVG = os.path.join('static', 'img', 'logo-mark.svg')
MARK_BOX = (513.38, 428.75, 411.00, 298.78)   # x, y, ширина, высота

NUM = re.compile(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?')
CMD = re.compile(r'([MmLlHhVvCcSsZz])')


def _bezier(p0, p1, p2, p3, steps=24):
    """Кубическая кривая → ломаная. 24 шага при ширине 400 px дают
    погрешность меньше пикселя, а полигон остаётся лёгким."""
    out = []
    for i in range(1, steps + 1):
        t = i / float(steps)
        u = 1 - t
        out.append((
            u * u * u * p0[0] + 3 * u * u * t * p1[0]
            + 3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1]
            + 3 * u * t * t * p2[1] + t * t * t * p3[1]))
    return out


def parse_path(d):
    """SVG-путь → список замкнутых ломаных (в координатах самого пути).

    Поддержаны команды M/m L/l H/h V/v C/c S/s Z/z — всё, что встречается в
    знаке. Неизвестная команда роняет разбор с ошибкой, а не тихо рисует
    кляксу: молча искажённый логотип хуже отсутствующего.
    """
    tokens = [t for t in CMD.split(d) if t.strip()]
    subpaths, cur = [], []
    x = y = 0.0
    start = (0.0, 0.0)
    prev_c2 = None
    i = 0
    while i < len(tokens):
        cmd = tokens[i]
        if not CMD.fullmatch(cmd):
            raise ValueError('неожиданный токен в пути: %r' % cmd)
        args = []
        if i + 1 < len(tokens) and not CMD.fullmatch(tokens[i + 1]):
            args = [float(v) for v in NUM.findall(tokens[i + 1])]
            i += 1
        i += 1
        rel = cmd.islower()
        up = cmd.upper()

        if up == 'Z':
            if cur:
                subpaths.append(cur)
                cur = []
            x, y = start
            prev_c2 = None
            continue

        step = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'S': 4}[up]
        if not args or len(args) % step:
            raise ValueError('%s: аргументов %d' % (cmd, len(args)))
        for k in range(0, len(args), step):
            chunk = args[k:k + step]
            if up == 'M':
                x, y = (x + chunk[0], y + chunk[1]) if rel else tuple(chunk)
                if cur:
                    subpaths.append(cur)
                cur = [(x, y)]
                start = (x, y)
                up = 'L'          # последующие пары у M — это неявный L
                prev_c2 = None
            elif up == 'L':
                x, y = (x + chunk[0], y + chunk[1]) if rel else tuple(chunk)
                cur.append((x, y))
                prev_c2 = None
            elif up == 'H':
                x = x + chunk[0] if rel else chunk[0]
                cur.append((x, y))
                prev_c2 = None
            elif up == 'V':
                y = y + chunk[0] if rel else chunk[0]
                cur.append((x, y))
                prev_c2 = None
            else:
                if up == 'C':
                    c1 = (x + chunk[0], y + chunk[1]) if rel \
                        else (chunk[0], chunk[1])
                    c2 = (x + chunk[2], y + chunk[3]) if rel \
                        else (chunk[2], chunk[3])
                    end = (x + chunk[4], y + chunk[5]) if rel \
                        else (chunk[4], chunk[5])
                else:                       # S — первая точка зеркальна
                    c1 = (2 * x - prev_c2[0], 2 * y - prev_c2[1]) \
                        if prev_c2 else (x, y)
                    c2 = (x + chunk[0], y + chunk[1]) if rel \
                        else (chunk[0], chunk[1])
                    end = (x + chunk[2], y + chunk[3]) if rel \
                        else (chunk[2], chunk[3])
                cur.extend(_bezier((x, y), c1, c2, end))
                x, y = end
                prev_c2 = c2
    if cur:
        subpaths.append(cur)
    return subpaths


def mark_polygons(base_dir, box):
    """Знак из logo-mark.svg, вписанный в прямоугольник box (x, y, w, h)."""
    path = os.path.join(base_dir, MARK_SVG)
    with open(path, encoding='utf-8') as fh:
        svg = fh.read()
    # Берём ПОСЛЕДНИЙ path: первый элемент файла — круг-подложка (rect),
    # а знак лежит в единственном <path>.
    m = re.findall(r'<path[^>]*\sd="([^"]+)"', svg)
    if not m:
        raise ValueError('в %s нет <path d="…">' % path)
    subpaths = parse_path(m[-1])

    src_x, src_y, src_w, src_h = MARK_BOX
    dst_x, dst_y, dst_w, dst_h = box
    k = min(dst_w / src_w, dst_h / src_h)
    off_x = dst_x + (dst_w - src_w * k) / 2
    off_y = dst_y + (dst_h - src_h * k) / 2
    return [[(off_x + (px - src_x) * k, off_y + (py - src_y) * k)
             for px, py in sub] for sub in subpaths]


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

        base = str(settings.BASE_DIR)
        out = opts['out'] or os.path.join(
            base, 'game', 'static', 'game', 'og_default.png')
        os.makedirs(os.path.dirname(out), exist_ok=True)

        # Рисуем с четырёхкратным разрешением и уменьшаем: у знака длинные
        # косые края, и без этого они рвутся ступеньками.
        S = 4
        img = Image.new('RGB', (W * S, H * S), BG)
        d = ImageDraw.Draw(img)

        d.rectangle([0, 0, 14 * S, H * S], fill=ACCENT)
        for i in range(70):
            k = i / 70
            r = int(420 * (1 - k)) * S
            cx, cy = (W - 260) * S, -180 * S
            d.ellipse([cx - r, cy - r, cx + r, cy + r],
                      fill=(int(BG[0] + (40 - BG[0]) * k * .5),
                            int(BG[1] + (18 - BG[1]) * k * .5),
                            int(BG[2] + (40 - BG[2]) * k * .5)))

        # Знак «W» — из логотипа, тем же путём, что и на сайте.
        mark_h = 86 * S
        mark_w = int(mark_h * MARK_BOX[2] / MARK_BOX[3])
        mark_left, mark_top = 80 * S, 168 * S
        try:
            for poly in mark_polygons(base, (mark_left, mark_top,
                                             mark_w, mark_h)):
                if len(poly) >= 3:
                    d.polygon(poly, fill=WHITE)
            mark_ok = True
        except (OSError, ValueError, KeyError) as exc:
            self.stderr.write('Знак не отрисован (%s) — рисую без него' % exc)
            mark_w, mark_ok = 0, False

        def font(size):
            for path in FONT_CANDIDATES:
                try:
                    return ImageFont.truetype(path, size)
                except (OSError, IOError):
                    continue
            return None

        f_title, f_sub, f_small = font(96 * S), font(40 * S), font(28 * S)
        if f_title is None:
            img.resize((W, H), Image.LANCZOS).save(out, 'PNG', optimize=True)
            self.stdout.write(self.style.WARNING(
                f'Шрифт не найден — сохранил фон со знаком: {out}'))
            return

        text_x = mark_left + (mark_w + 10 * S if mark_ok else 0)
        d.text((text_x, 150 * S), 'ECON', font=f_title, fill=WHITE)
        econ_w = d.textlength('ECON', font=f_title)
        d.text((text_x + econ_w + 26 * S, 150 * S), 'RUSH',
               font=f_title, fill=ACCENT)
        d.text((80 * S, 300 * S), 'Игра на скорость по олимпиадной экономике',
               font=f_sub, fill=MUTED)
        d.text((80 * S, 380 * S), '3 жизни · 4 режима · обгонишь?',
               font=f_sub, fill=ACCENT)
        d.text((80 * S, (H - 90) * S), 'Weconomics', font=f_small, fill=MUTED)

        img.resize((W, H), Image.LANCZOS).save(out, 'PNG', optimize=True)
        self.stdout.write(self.style.SUCCESS(
            f'Готово: {out} ({os.path.getsize(out) // 1024} КБ)'))
