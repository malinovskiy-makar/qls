"""
Контактный лист сессии фиксов после приёмки — reports/fix/index.html.

Открывается ДВОЙНЫМ КЛИКОМ, без сервера: все пути относительные, картинки
лежат рядом. Порядок намеренный и совпадает с порядком чтения отчёта:
СНАЧАЛА результат расследования из фазы 1 (главное, ради чего сессия),
потом экраны по фазам, потом сквозной сценарий шаг за шагом.

Запуск из корня проекта:  ./venv/bin/python scripts/fix_index.py
"""
import html
import io
import json
import os
import re

ROOT = 'reports/fix'
INVESTIGATION = '01-investigation.md'

# Порядок и подписи разделов. Ключ — папка внутри reports/fix.
SECTIONS = [
    ('02-states', 'Фаза 2. Четыре состояния проверки',
     '«Ждёт проверки» больше не ноль, янтарные позиции есть сами по себе, '
     'задачи без ответа получили честный ноль вместо прочерка.'),
    ('03-check-block', 'Фаза 3. Блок проверки на карточке',
     'Одна кнопка вместо двух, короткий текст, эталон не показан трижды, '
     'заголовок отделён от рабочей части чертой.'),
    ('04-points-lock', 'Фаза 4. Баллы заперты после первой сдачи',
     'Цифра осталась крупной, править нельзя, наверху одна строка о том, '
     'почему.'),
    ('06-talk', 'Фаза 6. Переписка по задаче',
     'Разделитель весомее, реплика ученика на подложке, метка видимости '
     'заметна. Светлая и тёмная тема, с сообщениями и без.'),
    ('07-small', 'Фаза 7. Мелочи',
     'Номер у названия, метка источника отдельным объектом, нейтральный '
     'фокус, кнопка в тёмной теме. Три ширины, две темы.'),
]

CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; font: 15px/1.6 -apple-system, BlinkMacSystemFont,
       'Segoe UI', sans-serif; background: #f5f5f3; color: #1a1a1a; }
@media (prefers-color-scheme: dark) {
  body { background: #10141c; color: #e7e9ef; }
  .card, .verdict { background: #161b25; border-color: rgba(255,255,255,.13); }
  a { color: #FF4D94; }
  .cap, .sub { color: #a7aebc; }
  .verdict { border-left-color: #3fc77f; }
}
.wrap { max-width: 1100px; margin: 0 auto; padding: 32px 20px 80px; }
h1 { font-size: 26px; margin: 0 0 6px; }
.sub { color: #5b6472; font-size: 14px; margin-bottom: 26px; }
h2 { font-size: 18px; margin: 34px 0 4px; }
.cap { color: #5b6472; font-size: 13px; margin-bottom: 12px; }
.grid { display: grid; gap: 14px;
        grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); }
.card { background: #fff; border: 1px solid rgba(22,26,38,.12);
        border-radius: 10px; overflow: hidden; }
.card img { width: 100%; display: block; }
.name { font-size: 12px; padding: 8px 10px; color: #5b6472;
        overflow-wrap: anywhere; }
a { color: #BE185D; }
.step { display: flex; gap: 16px; align-items: flex-start; margin-bottom: 18px;
        flex-wrap: wrap; }
.step .card { flex: 1 1 460px; }
.step p { flex: 1 1 240px; margin: 0; font-size: 14px; }
/* Результат расследования — первым и заметно: ради него сессия и была. */
.verdict { background: #fff; border: 1px solid rgba(22,26,38,.12);
           border-left: 4px solid #1d7e45; border-radius: 0 10px 10px 0;
           padding: 18px 22px; margin-bottom: 12px; }
.verdict h3 { margin: 0 0 8px; font-size: 17px; }
.verdict p { margin: 0 0 10px; }
.verdict p:last-child { margin-bottom: 0; }
"""


def images(folder):
    path = os.path.join(ROOT, folder)
    if not os.path.isdir(path):
        return []
    return sorted(f for f in os.listdir(path) if f.endswith('.png'))


def card(src, name):
    return (
        '<a class="card" href="%s" style="text-decoration:none;display:block">'
        '<img src="%s" alt="%s" loading="lazy">'
        '<div class="name">%s</div></a>'
        % (src, src, html.escape(name), html.escape(name)))


def verdict_block():
    """Короткий ответ фазы 1 — вытаскиваем из самого отчёта, не дублируем.

    ⚠️ Пересказывать вывод расследования во втором месте нельзя: два текста
    об одном и том же расходятся, и владелец прочитает не тот.
    """
    path = os.path.join(ROOT, INVESTIGATION)
    if not os.path.exists(path):
        return []
    text = io.open(path, encoding='utf-8').read()
    match = re.search(r'## Короткий ответ\s*(.+?)\n## ', text, re.S)
    if match is None:
        return []
    body = match.group(1).strip()
    # Кусок кода и горизонтальную черту в выжимку не тащим: в отчёте они на
    # месте, а здесь превратились бы в строку из обратных кавычек.
    body = re.sub(r'```.*?```', '', body, flags=re.S)
    chunks = []
    for para in body.split('\n\n'):
        para = ' '.join(para.split())
        if not para or set(para) <= set('-'):
            continue
        para = re.sub(r'`([^`]+)`', r'<code>\1</code>', para)
        para = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', para)
        chunks.append('<p>%s</p>' % para)
    return ['<h2>Результат расследования</h2>',
            '<p class="cap">Почему за неверный ответ стоял полный балл. '
            'Полностью — в <a href="%s">%s</a>.</p>' % (INVESTIGATION,
                                                        INVESTIGATION),
            '<div class="verdict"><h3>Код исправен</h3>%s</div>'
            % ''.join(chunks)]


def main():
    out = ['<!doctype html><meta charset="utf-8">',
           '<title>Фиксы после приёмки ключевого экрана</title>',
           '<style>%s</style>' % CSS, '<div class="wrap">',
           '<h1>Фиксы после приёмки ключевого экрана</h1>',
           '<p class="sub">Контактный лист. Снимок открывается по клику. '
           'Порядок: сначала результат расследования, потом экраны по фазам, '
           'потом сквозной сценарий.</p>']

    out.extend(verdict_block())

    for folder, title, caption in SECTIONS:
        files = images(folder)
        if not files:
            continue
        out.append('<h2>%s</h2>' % html.escape(title))
        if caption:
            out.append('<p class="cap">%s</p>' % html.escape(caption))
        out.append('<div class="grid">')
        for name in files:
            out.append(card('%s/%s' % (folder, name), name))
        out.append('</div>')

    steps_file = os.path.join(ROOT, '08-end-to-end', 'shots.json')
    if os.path.exists(steps_file):
        steps = json.load(io.open(steps_file, encoding='utf-8'))
        out.append('<h2>Фаза 8. Сквозной сценарий</h2>')
        out.append('<p class="cap">Девять шагов из задания подряд: от '
                   'страницы задания до разбора глазами ученика.</p>')
        for step in steps:
            out.append('<div class="step">')
            out.append(card('08-end-to-end/%s' % step['file'], step['file']))
            out.append('<p>%s</p>' % html.escape(step['caption']))
            out.append('</div>')

    out.append('</div>')
    target = os.path.join(ROOT, 'index.html')
    io.open(target, 'w', encoding='utf-8').write('\n'.join(out))
    print('готово: %s' % target)


if __name__ == '__main__':
    main()
