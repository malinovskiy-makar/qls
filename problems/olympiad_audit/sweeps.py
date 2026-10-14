# -*- coding: utf-8 -*-
r"""Автопроверки эталона ВП/МОШ: 9 классов подозрительного (только чтение).

Перенесено из инструментов ночной сессии v4 (13.10.2026,
`weconomics-data\olympiads\v4_work\sweeps.py`) без изменения правил:
на v4 те же числа по классам (ВП 153/1/2/33/1/471/10/0/270, МОШ
532/12/6/64/22/832/46/4/628 — инвариант сессии v5, 14.10.2026).

Классы: 1 смесь кириллицы и латиницы; 2 повтор «Ответ:»; 3 ответ без
источника на странице; 4 сноска без текста; 5 артефакты (нечитаемо, U+00AD,
остатки переносов); 6 слово неизвестно словарю pymorphy3; 7 рисунок/таблица
не привязаны; 8 служебный блок как задание; 9 потеря текста слоя PDF.
Шумные классы — 1, 6, 9: это списки подозрительного, а не ошибок.

Изменение при переносе одно — откуда берутся данные: `Ctx(key, rows,
digitized, layers)`; `layers` — папки заплаток страниц по старшинству
(для v4 — `pages_v3`, для v5 — `pages_v5`, `pages_v3`), затем `pages`.
"""
import collections
import json
import os
import re
import unicodedata

from problems.olympiad_audit.fixes import put_field as put
from problems.olympiad_audit.fixes import task_pages, text_fields

CYR = 'А-Яа-яЁё'
LAT = 'A-Za-z'
SUP = '¹²³⁴⁵⁶⁷⁸⁹'


def norm(s):
    return re.sub(r'[^0-9a-zа-я]', '', s.lower().replace('ё', 'е'))


_morph = None


def morph():
    global _morph
    if _morph is None:
        import pymorphy3
        _morph = pymorphy3.MorphAnalyzer()
    return _morph


class Ctx:
    def __init__(s, key, rows, digitized, layers=('pages_v3',)):
        s.key = key
        s.rows = rows
        s.d = digitized
        s.layers = tuple(layers)
        with open(os.path.join(digitized, 'pages_manifest.jsonl'), encoding='utf-8') as handle:
            man = [json.loads(line) for line in handle]
        s.h = {m['file'] + '#p%d' % m['page']: m['page_dir'].split('/')[-1] + '/p%d' % m['page']
               for m in man}
        s.tp = [task_pages(r, s.h) for r in rows]
        s._layer = {}
        s._json = {}
        s.page_tasks = collections.defaultdict(list)
        for k, p in enumerate(s.tp):
            for pg in p:
                s.page_tasks[pg].append(k)

    def layer(s, pg):
        if pg not in s._layer:
            f = os.path.join(s.d, 'pages', pg + '.txt')
            if os.path.exists(f):
                with open(f, encoding='utf-8') as handle:
                    s._layer[pg] = handle.read()
            else:
                s._layer[pg] = None
        return s._layer[pg]

    def pjson(s, pg):
        if pg not in s._json:
            h, p = pg.split('/')
            j = None
            for folder in s.layers + ('pages',):
                f = os.path.join(s.d, folder, h, p + '.json')
                if os.path.exists(f):
                    with open(f, encoding='utf-8') as handle:
                        x = json.load(handle)
                    if 'blocks' in x:
                        j = x
                        break
            s._json[pg] = j
        return s._json[pg]


def strip_math(t):
    t=re.sub(r'\$\$.*?\$\$',' ',t,flags=re.S); t=re.sub(r'\$[^$\n]*\$',' ',t); return t
def F(cls,ctx,k,field,snip,fix=''):
    r=ctx.rows[k]
    return dict(cls=cls,set=ctx.key,idx=k,event=r['event_id'],number=r['number'],variant=r['task_variant'],field=field if isinstance(field,str) else 'parts[%d]'%field[1],snippet=snip.replace('\n','⏎')[:160],autofix=fix,pages=' '.join(sorted(ctx.tp[k])))
def sweep1_mixed(ctx):
    out=[]
    for k,r in enumerate(ctx.rows):
        for p,t in text_fields(r):
            plain=strip_math(t)
            for m in re.finditer(r'[A-Za-zА-Яа-яЁё]{2,}',plain):
                w=m.group(0)
                if re.search('['+CYR+']',w) and re.search('['+LAT+']',w):
                    out.append(F('1_смесь_алфавитов',ctx,k,p,w))
            for m in re.finditer(r'\$\$(.*?)\$\$|\$([^$\n]*)\$',t,flags=re.S):
                f=m.group(1) or m.group(2) or ''
                g=re.sub(r'\\(?:text|textbf|mathrm|textit|mbox|operatorname)\{[^{}]*\}',' ',f)
                if re.search('[АВСЕНКМОРТХУавсекмнортху]',g) and re.search('['+LAT+']',re.sub(r'\\[A-Za-z]+','',g)):
                    out.append(F('1_смесь_алфавитов',ctx,k,p,'формула: '+f[:60]))
            for m in re.finditer(r'(?<![А-Яа-яЁё\w])(?<!Раздел )(?<!Часть )(?<!Глава )(?<!№ )(?<!№)Х(?![А-Яа-яЁё\w])|(?<![А-Яа-яЁё\w])У(?=[,;.:)]|\s+(?:и|или|являются|является|а)\b|\s*$)',plain,flags=re.M):
                out.append(F('1_смесь_алфавитов',ctx,k,p,'отдельная кириллическая «%s» (переменная?): «%s»'%(m.group(0),plain[max(0,m.start()-20):m.end()+15])))
            # одиночная кириллическая омоглифа рядом с латиницей/цифрой вне формул: "Qd=14-Р", "V А"
            for m in re.finditer(r'(?<=[A-Za-z0-9=\-+])[АВСЕНКМОРТХУ](?![А-Яа-яЁё])|(?<![А-Яа-яЁё])[АВСЕНКМОРТХУ](?=[=\-+]\w?)',plain):
                a=plain[max(0,m.start()-12):m.end()+12]
                if re.search('[A-Za-z0-9]',a): out.append(F('1_смесь_алфавитов',ctx,k,p,'«'+a+'»'))
    return out
ANS=re.compile(r'^\s*(?:\*\*)?Ответ(?:\*\*)?\s*:?\s*(?:\*\*)?\s*(.*)$')
def sweep2_dupans(ctx,fix=False):
    out=[]
    for k,r in enumerate(ctx.rows):
        for p,t in list(text_fields(r)):
            if p=='title': continue
            if re.search(r'Ответ:\s*\*\*Ответ:?\*\*|\*\*Ответ:?\*\*\s*Ответ:',t):
                out.append(F('2_дубль_Ответ',ctx,k,p,re.search(r'.{0,20}Ответ:\s*\*\*Ответ.{0,30}',t,re.S).group(0) if re.search(r'.{0,20}Ответ:\s*\*\*Ответ.{0,30}',t,re.S) else 'двойное «Ответ:»','Ответ: **Ответ:** → Ответ:'))
                if fix: put(r,p,re.sub(r'Ответ:\s*\*\*Ответ:?\*\*','**Ответ:**',t))
                continue
            lines=t.split('\n'); seen={}; drop=[]
            for i,l in enumerate(lines):
                m=ANS.match(l)
                if m and l.strip().lower().lstrip('*').startswith('ответ'):
                    body=norm(m.group(1))
                    if body and body in seen: drop.append(i); out.append(F('2_дубль_Ответ',ctx,k,p,l.strip(),'удалить повтор'))
                    else: seen[body]=i
            if drop and fix:
                put(r,p,'\n'.join(l for i,l in enumerate(lines) if i not in set(drop)))
    return out
def sweep3_answer_src(ctx):
    """«Ответ: …» с числом/словом, которого нет в тексте страниц PDF (только где есть текстовый слой)."""
    out=[]
    for k,r in enumerate(ctx.rows):
        pgs=ctx.tp[k]; lay=[ctx.layer(p) for p in pgs]; lay=[x for x in lay if x]
        if not lay: continue
        L=norm(' '.join(lay))
        for p,t in text_fields(r):
            if p in ('title',): continue
            for l in t.split('\n'):
                m=ANS.match(l)
                if not (m and re.match(r'\s*(\*\*)?Ответ',l)): continue
                body=m.group(1)
                if not body.strip(): continue
                nums=re.findall(r'\d[\d\s.,]*\d|\d',strip_math(body)+' '+' '.join(re.findall(r'\$([^$]*)\$',body)))
                nn=[norm(x) for x in nums if norm(x)]
                words=[norm(w) for w in re.findall(r'[А-Яа-яЁё]{5,}',body)]
                miss=[x for x in nn if x not in L]+[w for w in words if w[:6] not in L]
                if (nn or words) and miss: out.append(F('3_ответ_без_источника',ctx,k,p,l.strip()+'  [нет на странице: '+', '.join(miss[:4])+']'))
    return out
def sweep4_footnotes(ctx):
    out=[]
    # (a) маркер без текста
    for k,r in enumerate(ctx.rows):
        for p,t in text_fields(r):
            if p=='title': continue
            for m in re.finditer('['+SUP+']|(?<=[А-Яа-яЁё.,;:»”)])\\^\\{?[1-9]\\}?(?!\\d)',strip_math(t)):
                mk=m.group(0); dg=re.sub(r'\D','',mk) or str(SUP.index(mk)+1)
                lines=t.split('\n'); starts=any(l.strip().startswith(mk) or l.strip().startswith(SUP[int(dg)-1]) or re.match(r'\^\{?%s\}?\s'%dg,l.strip()) for l in lines)
                if not starts: out.append(F('4_сноска_маркер_без_текста',ctx,k,p,strip_math(t)[max(0,m.start()-30):m.end()+10]))
    # (b) страничный слой: подстрочные строки, которых нет в тексте заданий страницы
    seen=set()
    for pg,ks in ctx.page_tasks.items():
        lay=ctx.layer(pg)
        if not lay: continue
        corpus=norm(' '.join(' '.join(t for _,t in text_fields(ctx.rows[k])) for k in ks))
        lines=[l.strip() for l in lay.split('\n') if l.strip()]
        for l in lines[-14:]:
            m=re.match(r'^([1-4])\s?((?:[А-ЯЁA-Z«]|https?://|www\.)[^\n]{20,})$',l)
            if m and norm(m.group(2))[:22] not in corpus:
                out.append(dict(cls='4_сноска_нет_в_тексте',set=ctx.key,idx=ks[0],event=ctx.rows[ks[0]]['event_id'],number=ctx.rows[ks[0]]['number'],variant=ctx.rows[ks[0]]['task_variant'],field='page',snippet=m.group(0)[:150],autofix='',pages=pg))
                break
    return out
ART=[('[нечитаемо','артефакт модели'),('[ша]','артефакт модели'),('[noise','артефакт модели'),('\u00ad','мягкий перенос U+00AD'),('\ufffd','символ-замена �'),('[unreadable','артефакт модели'),('<unreadable','артефакт модели')]
def sweep5_artifacts(ctx,fix=False):
    out=[]
    for k,r in enumerate(ctx.rows):
        for p,t in list(text_fields(r)):
            for a,why in ART:
                if a in t:
                    i=t.index(a); out.append(F('5_артефакты',ctx,k,p,why+': …'+t[max(0,i-25):i+25]+'…','убрать U+00AD' if a=='\u00ad' else ''))
            if fix and '\u00ad' in t: put(r,p,t.replace('\u00ad',''))
            for m in re.finditer(r'(?<![А-Яа-яЁё-])([а-яё]{1,4})-([а-яё]{2,6})(?![А-Яа-яЁё-])',strip_math(t)):
                a,b=m.groups(); j=a+b
                mm=morph()
                if mm.word_is_known(j) and not mm.word_is_known(a+'-'+b) and (not mm.word_is_known(a) or not mm.word_is_known(b) or len(a)<=2) and a not in ('по','во','из','кто','что'):
                    out.append(F('5_артефакты',ctx,k,p,'остаток переноса: «%s-%s» → «%s»'%(a,b,j)))
    return out
def sweep6_spell(ctx,freq=None):
    out=[]; mm=morph()
    cnt=collections.Counter()
    for r in ctx.rows:
        for p,t in text_fields(r):
            for w in set(re.findall(r'[а-яё]{4,}',strip_math(t).lower())): cnt[w]+=1
    cache={}
    def known(w):
        if w not in cache: cache[w]=mm.word_is_known(w)
        return cache[w]
    for k,r in enumerate(ctx.rows):
        lay=' '.join(x for x in (ctx.layer(p) for p in ctx.tp[k]) if x).lower().replace('ё','е')
        bad=[]
        for p,t in text_fields(r):
            if p=='title': continue
            plain=strip_math(t)
            for m in re.finditer(r'(?<![А-Яа-яЁё\w-])([а-яё]{4,})(?![А-Яа-яЁё\w-])',plain.lower()):
                w=m.group(1)
                if known(w) or cnt[w]>3: continue
                inl=lay and w.replace('ё','е') in lay
                bad.append((w,'есть в слое PDF' if inl else 'нет в слое' if lay else 'нет слоя (скан)',p))
        seenw=set()
        for w,why,p in bad:
            if w in seenw: continue
            seenw.add(w); out.append(F('6_орфография',ctx,k,p,'«%s» — %s'%(w,why)))
    return out
def sweep7_figs_tables(ctx):
    out=[]
    for pg,ks in ctx.page_tasks.items():
        pj=ctx.pjson(pg)
        if not pj: continue
        fl=pj.get('flags') or {}; bl=pj.get('blocks') or []
        has_fig=fl.get('has_figure') or any(b.get('type')=='figure' for b in bl)
        has_tab=fl.get('has_table') or any('|---' in (b.get('text') or '') for b in bl)
        N=int(pg.split('/p')[1])
        if has_fig:
            got=any(isinstance(f,dict) and f.get('page')==N for k in ks for f in (ctx.rows[k]['figures'] or [])+(ctx.rows[k]['solution_figures'] or []))
            if not got:
                k=ks[0]; out.append(dict(cls='7_рисунок_не_привязан',set=ctx.key,idx=k,event=ctx.rows[k]['event_id'],number=ctx.rows[k]['number'],variant=ctx.rows[k]['task_variant'],field='page',snippet='на странице есть рисунок/график, а у заданий страницы нет вырезанного рисунка с этой страницы',autofix='',pages=pg))
        if has_tab:
            if not any(re.search(r'^\s*\|.+\|\s*$',t,re.M) or re.search(r'<table',t) for k in ks for _,t in text_fields(ctx.rows[k])):
                k=ks[0]; out.append(dict(cls='7_таблица_не_передана',set=ctx.key,idx=k,event=ctx.rows[k]['event_id'],number=ctx.rows[k]['number'],variant=ctx.rows[k]['task_variant'],field='page',snippet='на странице есть таблица, в тексте заданий страницы таблиц нет',autofix='',pages=pg))
    return out
def sweep9_layer_loss(ctx,minmiss=8):
    """строки текстового слоя PDF, которых нет в тексте заданий страницы (потерянные таблицы, сноски, служебные строки)"""
    out=[]
    byfile=collections.defaultdict(list)
    for pg in ctx.page_tasks: byfile[pg.split('/')[0]].append(pg)
    for fk,pgs in byfile.items():
        words={pg:set(re.findall(r'[а-яё]{4,}',(ctx.layer(pg) or '').lower().replace('ё','е'))) for pg in pgs}
        furn=set()
        if len(pgs)>=4:
            cnt=collections.Counter(w for pg in pgs for w in words[pg]); furn={w for w,c in cnt.items() if c>=0.4*len(pgs)}
        for pg in pgs:
            lay=ctx.layer(pg)
            if not lay: continue
            ks=ctx.page_tasks[pg]
            corpus=norm(' '.join(' '.join(t for _,t in text_fields(ctx.rows[k])) for k in ks))
            lost=[]; allmiss=set()
            for l in lay.split('\n'):
                l=l.strip()
                toks=[w for w in re.findall(r'[а-яё]{4,}',l.lower().replace('ё','е')) if w not in furn]
                if re.search(r'олимпиад[аы] школьников|^\d+\s*класс|^Экономика\s*$',l): continue
                if len(toks)<2: continue
                miss=[w for w in toks if w[:5] not in corpus]; allmiss.update(miss)
                nl=norm(l)
                if nl[:18] in corpus: continue
                if (len(miss)>=3 and len(miss)/len(toks)>=0.6) or (len(toks)>=2 and len(miss)==len(toks)): lost.append(l[:90])
            # блоки из >=5 подряд коротких строк слоя (ячейки таблицы), которых нет в тексте
            ls=[l.strip() for l in lay.split('\n')]; blk=[]; blocks=[]
            for l in ls+['']:
                w=len(l.split())
                if l and w<=4 and not re.search(r'олимпиад[аы] школьников|^\d+\s*класс|^Экономика\s*$',l): blk.append(unicodedata.normalize('NFKC',l))
                else:
                    if len(blk)>=5: blocks.append(blk)
                    blk=[]
            for b in blocks:
                jn=norm(' '.join(b))
                has_tab=any(re.search(r'^\s*\|.+\|\s*$',t,re.M) for k in ks for _,t in text_fields(ctx.rows[k]))
                if (not has_tab) and jn[:30] not in corpus and len(set(norm(x) for x in b))>=4:
                    lost.append('[блок коротких строк: '+' | '.join(b[:8])+']')
            if lost or len(allmiss)>=minmiss*2:
                k=ks[0]; r=ctx.rows[k]
                out.append(dict(cls='9_потеря_текста_слоя',set=ctx.key,idx=k,event=r['event_id'],number=r['number'],variant=r['task_variant'],field='page',snippet=' // '.join(lost[:3]) or ('много слов слоя не найдено: '+', '.join(sorted(allmiss)[:10])),autofix='',pages=pg))
    return out
SERV=re.compile(r'отнесите|Соотнесите|Блок\s*\d|Раздел\s+[IVX]+|Внимание|Итого|Часть\s+[IVX]+|Решите задачи|приведите только ответ|Посмотрите внимательно|требуют|Задани[яе]\s*\d+\s*[–—-]',re.I)
OPT=re.compile(r'^\s*(?:[1-9]|[а-д]|[a-e])[).]\s',re.M)
def sweep8_service_tasks(ctx):
    out=[]
    for k,r in enumerate(ctx.rows):
        st=r['statement_md'] or ''
        if len(st)<500 and not OPT.search(st) and not (r['solution_md'] or '').strip() and not (r['answer'] or '').strip() and not (r['criteria_md'] or '').strip() and SERV.search(st) and not re.search(r'\?|Найдите|Определите|Рассчитайте|Вычислите|Сколько',st):
            out.append(F('8_служебный_блок_как_задание',ctx,k,'statement_md',st[:120]))
    return out
ALL=[('1',sweep1_mixed),('2',sweep2_dupans),('3',sweep3_answer_src),('4',sweep4_footnotes),('5',sweep5_artifacts),('6',sweep6_spell),('7',sweep7_figs_tables),('8',sweep8_service_tasks),('9',sweep9_layer_loss)]
def run_all(key,rows,digitized,layers=('pages_v3',)):
    ctx=Ctx(key,rows,digitized,layers); res=[]
    for n,f in ALL: res+=f(ctx)
    return res
