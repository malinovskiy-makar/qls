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

    # Календарь занятий — только тем, у кого эти занятия есть.
    if role in ('teacher', 'student'):
        add('/calendar/', 'Календарь', namespace='calendar_stub')

    add('/calc2/', 'Графики', path_has='calc2')
    add('/game/', 'Тренажёр', path_has='/game/')

    if authed and user.is_staff:
        add('/admin/', 'Админка', path_prefix='/admin/')

    return items


def site_meta(request):
    """Версия сайта, меню шапки и плашка пользователя."""
    user = getattr(request, 'user', None)
    authed = bool(user and user.is_authenticated)
    return {
        'site_version': settings.SITE_VERSION,
        'nav_items': _menu(request),
        'nav_user_initials': _initials(user) if authed else '',
        'nav_user_name': (user.get_full_name() or user.get_username()) if authed else '',
    }
