"""У2 на настоящей базе: у 60011 (2025/26, 11 кл., 2 тур, задача 8) нет полей «Ответ»,
у теста из комплекта с тестовой частью поле или варианты есть."""
from django.test import Client
from olympiads import training_engine as engine
from olympiads import navigator as nav
from problems import problem_types

c = Client(HTTP_HOST='127.0.0.1')
c.post('/olympiads/vseros/variant/562/start/', {'timer': '0'})
items = engine.variant_items(nav.base_variants().get(pk=562))
index = next(n for n, i in enumerate(items, 1) if i.catalog_problem_id == 60011)
html = c.get('/olympiads/vseros/variant/562/take/?task=%d' % index).content.decode()
pane = html[html.index('data-task="%d"' % index, html.index('id="exam-form"')):]
pane = pane[:pane.find('class="om-taskpane"') if 'class="om-taskpane"' in pane else None]
print('60011: полей «Ответ»', pane.count('answer-short'), '| «Ответ а»', pane.count('Ответ а'), '| «Решение»', 'Решение' in pane)
for v in nav.base_variants().select_related('olympiad'):
    its = engine.package_items(v)
    tests = [n for n, i in enumerate(its, 1) if problem_types.is_test(i.problem.problem_type)]
    if tests:
        c2 = Client(HTTP_HOST='127.0.0.1')
        c2.post('/olympiads/%s/variant/%d/start/' % (v.olympiad.slug, v.pk), {'timer': '0'})
        h = c2.get('/olympiads/%s/variant/%d/take/?task=%d' % (v.olympiad.slug, v.pk, tests[0])).content.decode()
        p = h[h.index('data-task="%d"' % tests[0], h.index('id="exam-form"')):]
        p = p[:p.find('class="om-taskpane"') if 'class="om-taskpane"' in p else None]
        print('тест: комплект', v.pk, 'задание', tests[0], '| поле ответа', 'answer-short' in p, '| варианты', 'om-opt' in p)
        break
