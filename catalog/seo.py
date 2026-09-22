# -*- coding: utf-8 -*-
"""SEO сайта: robots.txt, sitemap.xml, распознавание краулеров, заголовки
и описания страниц для выдачи Google и Яндекса (19.09.2026, решение Notion
«SEO-фикс: боты не тратят бюджет умного поиска…»).

Всё, что про поисковых ботов, лежит здесь одним местом: правки текстов
заголовков не должны требовать обхода десяти шаблонов.

⚠️ ЧТО ЗДЕСЬ И ЗАЧЕМ.
- `robots_txt` закрывает от краулеров адреса `/catalog/?q=…`: каждый такой
  переход — платный вызов переранжирования и строка `SearchLog`.
- `is_crawler` — страховка на случай, если бот всё же пришёл на `?q=`
  (уже проиндексированные адреса дожимаются годами): переранжирование и
  журнал ему не достаются, обычная выдача — достаётся.
- Заголовки страниц задачи берут `heading` из `_problem_context` — там уже
  решено, что делать с обрубком (решение владельца 17.09.2026: обрубок
  заменён `title_candidate` в самих данных, `titles_from_candidates`).
"""
import re

from django.contrib.sitemaps import Sitemap
from django.http import HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from .filters import base_queryset
from .preview import tex_preview
from .topic_blocks import is_known

SITE_URL = 'https://weconomics.ai'
BRAND = 'Weconomics.ai'
#: Число в описаниях — по решению владельца, а не живой подсчёт: описание
#: в выдаче не должно прыгать каждый раз, когда задачу скрыли или вернули.
BANK_SIZE = '14 000+'

# ── Краулеры ────────────────────────────────────────────────────────────────
#: Куски User-Agent известных краулеров (в нижнем регистре). Список
#: намеренно явный: общее слово «bot» задело бы и чужие браузеры, и наши
#: собственные проверки. Пустой User-Agent краулером НЕ считается.
CRAWLER_MARKERS = (
    'googlebot', 'googleother', 'google-inspectiontool', 'adsbot-google',
    'mediapartners-google', 'apis-google', 'storebot-google',
    'amazonbot', 'bingbot', 'bingpreview', 'msnbot',
    'yandexbot', 'yandexmobilebot', 'yandeximages', 'yandexaccessibilitybot',
    'semrushbot', 'ahrefsbot', 'mj12bot', 'dotbot', 'petalbot', 'bytespider',
    'ccbot', 'gptbot', 'chatgpt-user', 'oai-searchbot', 'claudebot',
    'claude-web', 'anthropic-ai', 'perplexitybot', 'applebot', 'duckduckbot',
    'baiduspider', 'facebookexternalhit', 'meta-externalagent', 'seznambot',
    'dataforseobot', 'barkrowler', 'blexbot', 'serpstatbot',
    'crawler', 'spider',
)


def is_crawler(request):
    """Пришёл ли запрос от поискового или иного краулера (по User-Agent)."""
    agent = (request.META.get('HTTP_USER_AGENT') or '').lower()
    return bool(agent) and any(marker in agent for marker in CRAWLER_MARKERS)


# ── robots.txt ──────────────────────────────────────────────────────────────
ROBOTS_TXT = '\n'.join([
    'User-agent: *',
    # Выдача по строке поиска: платный ИИ-вызов на каждый переход.
    'Disallow: /catalog/?q=*',
    # То же, когда `q` идёт не первым параметром (фильтры + запрос).
    'Disallow: /catalog/*&q=',
    # Попытки «Высшей пробы» — личные страницы человека (чужому 404), ботам там нечего
    # искать. `/vp/r/` НЕ закрыт намеренно: результат открывается по ссылке, и бот
    # обязан дойти до страницы, чтобы прочитать её `noindex` (закрытый адрес индекс
    # не запрещает — он лишь не даёт прочитать запрет).
    'Disallow: /vp/a/',
    '',
    'Sitemap: %s/sitemap.xml' % SITE_URL,
    '',
])


@require_GET
def robots_txt(request):
    return HttpResponse(ROBOTS_TXT, content_type='text/plain; charset=utf-8')


# ── sitemap.xml ─────────────────────────────────────────────────────────────
class ProblemSitemap(Sitemap):
    """Задачи, которые видит гость: ровно шлюз страницы задачи.

    `base_queryset('catalog')` — опубликовано, без брака, с исправным
    текстом и проверено человеком; это те же условия, при которых
    `problem_detail` не отдаёт 404. Скрытая задача в карте была бы ссылкой
    на страницу «не найдено».
    """
    protocol = 'https'
    changefreq = 'monthly'
    priority = 0.6

    def items(self):
        return base_queryset('catalog').only('pk', 'updated_at').order_by('pk')

    def location(self, problem):
        return reverse('catalog:problem_detail', args=[problem.pk])

    def lastmod(self, problem):
        return problem.updated_at


class StaticSitemap(Sitemap):
    """Постоянные входы: главная, каталог, калькулятор, игра, карта тем, «Высшая проба»."""
    protocol = 'https'
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return ['home', 'catalog:problem_list', 'catalog:topic_map',
                'calc2:calculator', 'game:page', 'vp:index']

    def location(self, name):
        return reverse(name)


class VPSitemap(Sitemap):
    """Страницы опубликованных вариантов «Высшей пробы» (`/vp/<слаг>/`).

    ⚠️ ТОЛЬКО опубликованные: черновик отдаёт 404 всем, кроме персонала. Страниц попыток
    и результатов (`/vp/a/…`, `/vp/r/…`) в карте нет и быть не может — это личные
    адреса людей (на них `noindex`, попытки закрыты и в `robots.txt`).
    """
    protocol = 'https'
    changefreq = 'monthly'
    priority = 0.7

    def items(self):
        from vp.models import VPVariant     # приложение сезонное: не тянем его при импорте
        return VPVariant.objects.filter(is_published=True).only('slug', 'created_at').order_by('order', 'id')

    def location(self, variant):
        return reverse('vp:intro', args=[variant.slug])

    def lastmod(self, variant):
        return variant.created_at


SITEMAPS = {'static': StaticSitemap, 'problems': ProblemSitemap, 'vp': VPSitemap}


# ── Заголовки и описания ────────────────────────────────────────────────────
#: Короткие названия олимпиад для заголовка. Полные названия из `OlympiadRef`
#: («Всероссийская олимпиада школьников по экономике») дали бы «задача
#: Всероссийская олимпиада… по экономике по экономике», поэтому только
#: те, у которых есть устоявшаяся короткая форма. Остальные — как задача
#: без олимпиады: лучше без названия, чем с кривой фразой.
OLYMPIAD_SHORT = {
    'vseros': 'ВсОШ',
    'vp': '«Высшая проба»',
    'mosh': 'МОШ',
    'ieo': 'IEO',
}

TITLE_HEADING_MAX = 70

HOME_TITLE = 'Weconomics.ai — подготовка к олимпиадам по экономике'
HOME_DESCRIPTION = (
    'Банк из 14 000+ задач с решениями, ИИ-ассистент, умный поиск, тренажёр '
    'тестов и личный кабинет — платформа для подготовки к ВсОШ, МОШ, ВП, IEO '
    'и другим олимпиадам по экономике.')
CALC_TITLE = 'Графический калькулятор по экономике — онлайн | Weconomics.ai'
CALC_DESCRIPTION = (
    'Бесплатный графический калькулятор по экономике: кривые спроса и '
    'предложения, эластичность, монополия и другие модели — стройте графики '
    'онлайн на Weconomics.ai.')
GAME_TITLE = 'Wecon Rush — игра для подготовки к олимпиадам по экономике | Weconomics.ai'
GAME_DESCRIPTION = (
    'Образовательная игра по экономике: решайте тесты на скорость, '
    'соревнуйтесь с друзьями и готовьтесь к олимпиадам интересно на '
    'Weconomics.ai.')

# ⚠️ «Без регистрации» отсюда убрано 22.09.2026 вместе со стеной регистрации:
# описание в выдаче не должно обещать того, чего страница больше не даёт.
VP_DESCRIPTION = (
    'Варианты 1 тура олимпиады «Высшая проба» по экономике онлайн: решайте на время, '
    'получайте автоматическую проверку, разбор змейки и тестов.')


def vp_landing_meta(has_demo):
    """`seo_title` и `seo_description` посадочной `/vp/`.

    Слово «демоверсия» — в заголовке, только если демонстрационный вариант
    опубликован: люди ищут именно его, но обещать его в выдаче, когда его нет, значило
    бы обманывать.
    """
    what = 'тренажёр и демоверсия' if has_demo else 'тренажёр с автопроверкой'
    return {
        'seo_title': 'Высшая проба, 1 тур по экономике – %s | %s' % (what, BRAND),
        'seo_description': VP_DESCRIPTION,
    }


def vp_variants_meta():
    """`seo_title` и `seo_description` экрана выбора варианта `/vp/variants/`."""
    return {
        'seo_title': 'Варианты 1 тура «Высшей пробы» по экономике | %s' % BRAND,
        'seo_description': (
            'Варианты 1 тура отборочного этапа олимпиады «Высшая проба» по экономике '
            'для 9\u201310 и 11 классов: демоверсии и пробные, на время или без таймера, '
            'с автопроверкой и разбором.'),
    }


def vp_variant_meta(title, band_label, year):
    """`seo_title` и `seo_description` страницы варианта `/vp/<слаг>/`."""
    return {
        'seo_title': '%s – вариант 1 тура «Высшая проба» по экономике | %s' % (title, BRAND),
        'seo_description': (
            'Вариант 1 тура олимпиады «Высшая проба» по экономике, %s, %s год: пройдите '
            'на время или без таймера: автопроверка и разбор ответов сразу после сдачи.'
            % (band_label, year)),
    }


_RX_SPACE = re.compile(r'\s+')
#: Разметка формул, которой в `<title>` и в описании не место.
_RX_TEX_JUNK = re.compile(r'\\[a-zA-Z]+|[$\\{}]')
_LITERAL_DOLLAR = '\x01'


def _plain(text, limit):
    r"""Текст без разметки формул: в `<title>` и в описании доллары и
    `\frac` выглядели бы мусором. Формула остаётся её содержимым
    («$Q = 10 - P$» → «Q = 10 - P»), валюта `\$3` — знаком «$»."""
    text = tex_preview(text or '', limit).replace('\\$', _LITERAL_DOLLAR)
    text = _RX_TEX_JUNK.sub('', text).replace(_LITERAL_DOLLAR, '$')
    return _RX_SPACE.sub(' ', text).strip()


def olympiad_short_name(problem):
    """Короткое название олимпиады задачи, если оно известно, иначе ''."""
    for slug in problem.olympiad_refs.values_list('olympiad_slug', flat=True):
        if slug in OLYMPIAD_SHORT:
            return OLYMPIAD_SHORT[slug]
    return ''


def main_topic_name(problem):
    """Основная (первая каноническая) тема задачи или ''."""
    for topic in problem.topics.all():
        if is_known(topic.name):
            return topic.name
    return ''


def problem_meta(problem, heading):
    """`seo_title` и `seo_description` страницы задачи.

    `heading` — заголовок с экрана задачи (`_problem_context`): настоящее
    название либо «Задача: тема» / «Задача», если название — обрубок условия.
    Пустых скобок и «None» в тексте нет: чего нет — той части фразы нет.
    """
    name = _plain(heading, TITLE_HEADING_MAX) or 'Задача'
    olympiad = olympiad_short_name(problem)
    topic = main_topic_name(problem)
    if olympiad:
        title = '%s — задача %s по экономике | %s' % (name, olympiad, BRAND)
    else:
        title = '%s — олимпиадная задача по экономике | %s' % (name, BRAND)
    bank = ('%s — база из %s задач для подготовки к олимпиадам по экономике.'
            % (BRAND, BANK_SIZE))
    if topic and olympiad:
        head = 'Задача по «%s» с олимпиады %s, с подробным решением и ИИ-ассистентом.' % (topic, olympiad)
    elif topic:
        head = 'Задача по теме «%s» с подробным решением и ИИ-ассистентом.' % topic
    elif olympiad:
        head = 'Задача с олимпиады %s, с подробным решением и ИИ-ассистентом.' % olympiad
    else:
        head = 'Олимпиадная задача по экономике с подробным решением и ИИ-ассистентом.'
    return {'seo_title': title, 'seo_description': '%s %s' % (head, bank)}


def topic_meta(topic_name, total):
    """`seo_title` и `seo_description` каталога, отфильтрованного одной темой."""
    return {
        'seo_title': 'Задачи по теме «%s» — олимпиадная экономика | %s' % (topic_name, BRAND),
        'seo_description': (
            'Подборка задач по теме «%s» с решениями и ИИ-ассистентом — для '
            'подготовки к олимпиадам по экономике. %s задач на %s'
            % (topic_name, total, BRAND)),
    }
