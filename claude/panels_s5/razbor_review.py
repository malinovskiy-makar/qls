"""Файл для владельца: что осталось и что убрано в начале «Разбора» (правка А4, сессия 5).
python3 claude/panels_s5/razbor_review.py  → claude/panels_s5/razbor_review.md и claude/panels_s5/A4_removed.json"""
import json, re
B = json.load(open('claude/panels_s5/razbor_before.json'))
A = json.load(open('claude/panels_s5/razbor_after.json'))
IF = [r'тянуть', r'тяните', r'перетаскива', r'мыш(ью|кой)', r'переключат', r'переключите', r'можно писать', r'пишите',
      r'(^|[^а-яё])пол(е|я|ем)([^а-яё]|$)', r'ползун', r'\(роль|роль [DSM]', r'пуст(ое|ым) пол', r'включите', r'задайте',
      r'двигайте', r'двигая', r'вводятся', r'способ[ау]? ввода', r'тройн(ой|ым) поиск', r'ищется численно', r'движок',
      r'калькулятор', r'строка принимает', r'в карточке', r'становится ползунком', r'Формулы можно']
def sents(t):
    return [x.strip() for x in re.split(r'(?<=[.!?])\s+', t) if x.strip()]
def words(s):
    return set(w[:5] for w in re.findall(r'[a-zа-я0-9]{2,}', s.lower().replace('ё', 'е')))
def sim(a, b):
    A_, B_ = words(a), words(b)
    return len(A_ & B_) / max(1, min(len(A_), len(B_)))
def norm(s):
    return re.sub(r'[\s​]+', ' ', s).strip()
out = ['# «Разбор»: что перенесено из «Условия» и «Ответа» и что убрано (сессия 5, правка А4)', '',
       'Правило (README пакета 6, 10; решение «никаких подсказок, объяснения только в «Разборе»», Notion …81eb…): в начале',
       '«Разбора» остаются экономика и математика модели. Убрано: интерфейс («тянуть мышью», переключатели, «можно писать»,',
       '«поле», «ползунок», «роль D», как устроен поиск внутри) и повторы вопросов и ответов «Разбора» ниже (та же мысль).',
       'Капс, сырое «_» и моноширинный шрифт переписаны. Ниже — стартовое состояние каждой модели; тексты других состояний',
       '(субсидия, пол, МРОТ, квота монополии) правились в тех же источниках.', '']
removed = {}
for key in B:
    bs = [(p['from'], norm(s)) for p in B[key]['tr'] for s in sents(p['text'])]
    a_s = [norm(s) for p in A[key]['tr'] for s in sents(p['text'])]
    qa = [norm(x) for x in B[key]['qs']]
    kept = [p for p in A[key]['tr']]
    gone = []
    pool = list(a_s)
    for frm, s in bs:
        if s in pool:
            pool.remove(s)
            continue
        if s in a_s:
            gone.append((s, 'повтор: та же фраза уже стоит выше (из «Ответа»)'))
            continue
        best = max(a_s, key=lambda t: sim(s, t), default='')
        if best and sim(s, best) >= 0.6 and not any(re.search(r, s, re.I) for r in IF):
            gone.append((s, 'переписано: «' + best[:90] + '»'))
            continue
        if any(re.search(r, s, re.I) for r in IF):
            gone.append((s, 'интерфейс'))
        else:
            q = max(qa, key=lambda t: sim(s, t), default='')
            gone.append((s, 'повтор' + (': вопрос «' + q.split('?')[0][:70] + '?»' if q and sim(s, q) >= 0.3 else ' соседнего абзаца')))
    out.append('## ' + key)
    out.append('')
    out.append('Осталось:' if kept else 'Осталось: ничего (перенесённых абзацев нет).')
    for p in kept:
        out.append('- ' + {'cond': '«Условие»', 'answer': '«Ответ»', 'interv': 'вмешательство'}[p['from']] + ': ' + norm(p['text'])[:110] + ('…' if len(p['text']) > 110 else ''))
    if gone:
        out.append('')
        out.append('Убрано или переписано:')
        for s, why in gone:
            out.append('- «' + s + '» — ' + why)
        removed[key] = [{'text': s, 'why': why} for s, why in gone]
    out.append('')
open('claude/panels_s5/razbor_review.md', 'w').write('\n'.join(out))
json.dump(removed, open('claude/panels_s5/A4_removed.json', 'w'), ensure_ascii=False, indent=1)
n = sum(len(v) for v in removed.values())
print('моделей с правками', len(removed), 'фраз', n, 'из них интерфейс', sum(1 for v in removed.values() for x in v if x['why'] == 'интерфейс'),
      'повтор', sum(1 for v in removed.values() for x in v if x['why'].startswith('повтор')), 'переписано', sum(1 for v in removed.values() for x in v if x['why'].startswith('переписано')))
