"""У1 на настоящей базе: в HTML страниц раздела нет внешних адресов файлов.

    ./venv313/bin/python manage.py shell --settings=config.settings_olympiads_screens < этот файл
Главная, календарь, все видимые олимпиады (и с раскрытой первой клеткой),
вход каждого основного комплекта ВсОШ. Печатает «прошло / всего».
"""
from django.test import Client
from olympiads import navigator as nav
from olympiads.models import OlympiadVariantFile

urls = set(u for u in OlympiadVariantFile.objects.values_list('url', flat=True) if u)
c = Client(HTTP_HOST='127.0.0.1')
pages = ['/olympiads/', '/olympiads/calendar/']
for o in nav.visible_olympiads():
    pages.append('/olympiads/{}/'.format(o.slug))
for v in nav.base_variants().filter(olympiad__slug='vseros'):
    pages.append('/olympiads/vseros/?open=c{}'.format(v.pk))
    pages.append('/olympiads/vseros/variant/{}/'.format(v.pk))
bad = []
for p in pages:
    r = c.get(p)
    html = r.content.decode()
    hits = [u for u in urls if u in html] + [w for w in ('vso.edsoo.ru', 'accept=zip') if w in html]
    if r.status_code != 200 or hits:
        bad.append((p, r.status_code, hits[:2]))
print('У1 внешние адреса файлов: прошло {} / всего {}'.format(len(pages) - len(bad), len(pages)))
for b in bad[:10]:
    print('  ', b)
