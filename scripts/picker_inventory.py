"""
Опись кнопок и полей ручного поиска: HEAD против рабочей копии.

⚠️ ЗАЧЕМ. Правка вида не смеет убрать ни одной кнопки и не смеет добавить
новой (прямое требование владельца, п. 13). Проверять это глазами по двум
скриншотам — верный способ не заметить пропажу; здесь списки сверяются
механически.

Запуск ИЗ КОРНЯ проекта:
    ./venv/bin/python scripts/picker_inventory.py
Печатает оба списка и расхождения. Пустые «ПРОПАЛИ»/«ПОЯВИЛИСЬ» — успех.
"""
import re, subprocess, sys

FILES = ['teacher/templates/teacher/_picker_list.html',
         'teacher/templates/teacher/_picker_card.html',
         'teacher/templates/teacher/assignment_create.html',
         'teacher/templates/teacher/_picker_modal.html']

TAG = re.compile(r'<(button|input|select|textarea|a)\b[^>]*>', re.S)
NAME = re.compile(r'\b(?:name|id|data-add|data-preview|data-pane)="([^"]+)"')
TYPE = re.compile(r'\btype="([^"]+)"')

def items(text):
    out = []
    for m in TAG.finditer(text):
        raw = m.group(0)
        tag = m.group(1)
        name = NAME.search(raw)
        typ = TYPE.search(raw)
        key = tag + (':' + typ.group(1) if typ else '')
        key += ' | ' + (name.group(1) if name else '')
        if not name:
            # у ссылки/кнопки без имени берём подпись
            tail = text[m.end():m.end() + 120]
            label = re.sub(r'<[^>]*>', '', tail).strip().split('\n')[0][:40]
            key += label
        out.append(key)
    return sorted(set(out))

def collect(getter):
    seen = []
    for path in FILES:
        seen += ['%s :: %s' % (path.split('/')[-1], x) for x in items(getter(path))]
    return sorted(set(seen))

head = collect(lambda p: subprocess.run(['git', 'show', 'HEAD:' + p],
                                        capture_output=True, text=True).stdout)
now = collect(lambda p: open(p, encoding='utf-8').read())
gone = [x for x in head if x not in now]
added = [x for x in now if x not in head]
print('ДО:', len(head), 'элементов · ПОСЛЕ:', len(now))
print('\n--- ДО ---')
for x in head: print(' ', x)
print('\n--- ПОСЛЕ ---')
for x in now: print(' ', x)
print('\nПРОПАЛИ:', gone or 'нет')
print('ПОЯВИЛИСЬ:', added or 'нет')
