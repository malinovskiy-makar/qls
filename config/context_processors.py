# -*- coding: utf-8 -*-
"""Общие сведения для шапки сайта: версия, меню по роли, плашка пользователя.

⚠️ ПОЧЕМУ МЕНЮ СОБИРАЕТСЯ ЗДЕСЬ, А НЕ В ШАБЛОНЕ. До 04.09.2026 `_nav.html`
держал ЧЕТЫРЕ копии одного ряда ссылок (учитель / ученик / прочие / гость),
и каждая ссылка несла свой инлайновый стиль с двумя условиями подсветки —
32 атрибута `style` на файл. Любая правка требовала повторить её четырежды,
а расхождение никак не ловилось. Здесь список строится ОДИН раз, роль решает
только его состав, и «где я сейчас» считается в одном месте.

Заодно это проверяемо тестом без разбора разметки.
"""
from django.conf import settings

from problems.feedback_options import FEEDBACK_OPTIONS, page_key_for


def _match(request, *, namespace=None, url_name=None, url_name_has=None,
           path_has=None, path_prefix=None):
    """Совпал ли текущий адрес с признаком пункта меню."""
    resolver = getattr(request, 'resolver_match', None)
    if path_prefix and request.path.startswith(path_prefix):
        return True
    if path_has and path_has in request.path:
        return True
    if resolver is None:
        return False
    if namespace and resolver.namespace == namespace:
        if url_name is None:
            return True
        return resolver.url_name == url_name
    if url_name and resolver.url_name == url_name:
        return True
    if url_name_has:
        name = resolver.url_name or ''
        return any(part in name for part in url_name_has)
    return False


def _initials(user):
    """Кружок профиля: первая буква имени + первая буква фамилии.

    Если имя и фамилия пусты — первая буква логина. Логин у нас же и
    подпись на сайте там, где имени нет.
    """
    first = (user.first_name or '').strip()
    last = (user.last_name or '').strip()
    letters = (first[:1] + last[:1]).strip()
    if not letters:
        letters = (user.get_username() or '?')[:1]
    return letters.upper()


def _menu(request):
    """Пункты шапки в порядке слева направо. Состав зависит от роли.

    Порядок задан владельцем 04.09.2026: «Учебник» стоит сразу после
    «Каталога». Пункт «Статистика» из шапки ученика убран — статистика
    живёт в профиле.

    ⚠️ «Календарь» из шапки убран 08.09.2026 (решение владельца). Убрана
    ТОЛЬКО ссылка: маршрут `/calendar/` и приложение `calendar_stub` живы,
    страница открывается по прямому адресу.
    """
    user = getattr(request, 'user', None)
    items = []

    def add(url, label, **match):
        items.append({'url': url, 'label': label, 'active': _match(request, **match)})

    authed = bool(user and user.is_authenticated)
    role = getattr(user, 'role', None) if authed else None
    profile = getattr(user, 'profile', None) if authed else None

    if role == 'teacher':
        add('/teacher/groups/', 'Ученики', url_name_has=('group', 'student'))
    elif role == 'student':
        add('/student/', 'Занятия', namespace='student', url_name='dashboard')
    elif authed and profile is not None and getattr(profile, 'is_parent', False):
        add('/parent/', 'Мои дети', url_name_has=('parent',))

    add('/catalog/', 'Каталог', namespace='catalog')
    add('/textbook/', 'Учебник', url_name='textbook')
    add('/olympiads/', 'Олимпиады', namespace='olympiads')
    add('/calc2/', 'Графики', path_has='calc2')
    add('/game/', 'Wecon Rush', path_has='/game/')

    if authed and user.is_staff:
        add('/admin/', 'Админка', path_prefix='/admin/')

    return items


def _avatar_url(user):
    """Адрес аватара или пусто. Метка `?v=` — чтобы кэш не держал старое.

    ⚠️ Профиль читается ЧЕРЕЗ getattr с запасным значением: у части старых
    аккаунтов профиля может не быть вовсе, и шапка из-за этого падать не
    должна.
    """
    profile = getattr(user, 'profile', None)
    if profile is None or not getattr(profile, 'avatar', None):
        return ''
    stamp = int(profile.updated_at.timestamp()) if profile.updated_at else 0
    return '/profile/avatar/%d/?v=%d' % (user.pk, stamp)


def site_meta(request):
    """Версия сайта, меню шапки и плашка пользователя."""
    user = getattr(request, 'user', None)
    authed = bool(user and user.is_authenticated)
    return {
        'site_version': settings.SITE_VERSION,
        'nav_items': _menu(request),
        'nav_user_initials': _initials(user) if authed else '',
        'nav_user_name': (user.get_full_name() or user.get_username()) if authed else '',
        'nav_avatar_url': _avatar_url(user) if authed else '',
        # ⚠️ СПИСОК ВАРИАНТОВ ОТДАЁТ СЕРВЕР, КЛИЕНТ ЕГО НЕ ДУБЛИРУЕТ: иначе
        # к первой правке формулировок было бы два списка — один в питоне
        # (по нему разбирают жалобы) и один в разметке (его читает человек).
        #
        # ⚠️ ОДНИМ СЛОВАРЁМ И ЧЕРЕЗ `json_script`, А НЕ `mark_safe`. Первая
        # версия склеивала JSON строкой и помечала его безопасным — и это
        # честная находка bandit (B703/B308): `mark_safe` над строкой,
        # собранной в питоне, придётся пересматривать при каждой правке
        # источника. `json_script` экранирует `<`, `>` и `&` сам, а ключ
        # экрана уезжает внутрь того же словаря — значит и тег нужен один.
        'feedback_data': {
            'page': page_key_for(request.path),
            'options': FEEDBACK_OPTIONS,
        },
    }
