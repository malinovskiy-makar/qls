"""repair_review_shell — оболочка слепой оценки починок. ТОЛЬКО ЧТЕНИЕ.

По образцу export_review_bundle: работает с file:// без сети, KaTeX вшит,
вердикты живут в localStorage и выгружаются одним JSON, есть горячие клавиши.

⚠️ ОЦЕНКА СЛЕПАЯ. На экране НЕ показывается, каким способом сделана починка
(A — подсказка только категорией, B — категория плюс комментарий ревьюера).
Порядок экранов перемешан, чтобы два варианта одной задачи не шли подряд.

⚠️ ОБА ТЕКСТА ОТРЕНДЕРЕНЫ по умолчанию — так их увидит ученик. Сырой текст
открывается кнопкой. На сыром тексте правильная разметка формул читается как
порча, мы на этом уже спотыкались.

⚠️ Свои CSS-классы только с префиксом qls-. KaTeX внутри .katex-html сам
раздаёт узлам классы text/mord/base/strut/mfrac/sqrt, а CSS матчит по ТОКЕНУ
класса — одноимённое правило протащило бы рамку прямо в формулу.

Запуск:
    venv\\Scripts\\python manage.py repair_review_shell
"""

import hashlib
import html as html_lib
import io
import json
import os
import random

from django.core.management.base import BaseCommand

from problems.management.commands.repair_gate import katex_head, engine_only

OUT_DIR = 'reports/repair_experiment'
SEED = 20260818

VERDICTS = [
    ('full', '1', 'Починено полностью'),
    ('partial', '2', 'Починено частично, дефект остался'),
    ('nochange', '3', 'Не помогло, по сути ничего не изменилось'),
    ('worse', '4', 'Стало хуже'),
]


def screen_id(problem_id, method):
    """Непрозрачный ключ экрана: способ по нему не восстанавливается."""
    raw = '%d|%s|%d' % (problem_id, method, SEED)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]


def esc(s):
    return html_lib.escape(s or '', quote=False)


def field_rows(fields):
    """Поля задачи в порядке показа."""
    rows = []
    if fields.get('statement'):
        rows.append(('Условие', fields['statement']))
    for p in fields.get('parts') or []:
        label = (p.get('label') or '').strip()
        txt = p.get('statement') or ''
        if p.get('answer'):
            txt += '\n→ ответ: ' + p['answer']
        rows.append(('Подпункт ' + label, txt))
    if fields.get('solution'):
        rows.append(('Решение', fields['solution']))
    if fields.get('answer'):
        rows.append(('Ответ', fields['answer']))
    return rows


def side_html(fields):
    out = []
    for label, text in field_rows(fields):
        out.append(
            '<div class="qls-lbl">' + esc(label) + '</div>'
            '<div class="qls-fld">'
            '<div class="qls-rendered qls-tex">' + esc(text) + '</div>'
            '<div class="qls-raw">' + esc(text) + '</div>'
            '</div>')
    return ''.join(out) or '<div class="qls-empty">— пусто —</div>'


def apply_fields(before, patch):
    """«ПОСЛЕ» — исходные поля, поверх которых легли правленые."""
    after = json.loads(json.dumps(before))
    for k in ('statement', 'solution', 'answer', 'parts'):
        if k in (patch or {}):
            after[k] = patch[k]
    return after


class Command(BaseCommand):
    help = 'Собрать оболочку слепой оценки починок. Только чтение.'

    def say(self, line):
        try:
            self.stdout.write(line)
        except UnicodeEncodeError:
            self.stdout.write(line.encode('ascii', 'replace').decode())

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0,
                            help='Взять первые N экранов (для проверки оболочки).')
        parser.add_argument('--out', default='review_repairs.html')
        parser.add_argument('--light', action='store_true',
                            help='Без шрифтов KaTeX — только для проверки механики.')

    def handle(self, *args, **options):
        sample = {r['id']: r for r in json.load(
            io.open(f'{OUT_DIR}/sample.json', encoding='utf-8'))}
        repairs = json.load(io.open(f'{OUT_DIR}/repairs.json', encoding='utf-8'))
        gate = {}
        if os.path.exists(f'{OUT_DIR}/gate.json'):
            for g in json.load(io.open(f'{OUT_DIR}/gate.json', encoding='utf-8')):
                gate['%d|%s' % (g['id'], g['method'])] = g

        screens = []
        for rep in repairs:
            rec = sample.get(rep['id'])
            if rec is None:
                continue
            after = apply_fields(rec['before'], rep.get('fields') or {})
            g = gate.get('%d|%s' % (rep['id'], rep['method']), {})
            screens.append({
                # ⚠️ Идентификатор экрана НЕПРОЗРАЧНЫЙ: буква способа в нём
                # читалась бы и в данных страницы, и в выгруженном JSON, а
                # оценка должна быть слепой. Соответствие лежит отдельно, в
                # screen_key.json, и открывается уже при разборе.
                'screen_id': screen_id(rep['id'], rep['method']),
                'problem_id': rep['id'],
                # ⚠️ method в разметку НЕ попадает — оценка слепая. Он есть
                # только здесь, чтобы уехать в выгружаемый JSON после оценки.
                'method': rep['method'],
                'group': rec['group'],
                'categories': rec['category_labels'],
                'comment': rec['comment'],
                'action': rep['action'],
                'explain': rep.get('explain') or '',
                'gate_flags': g.get('gate_flags', []),
                'before_html': side_html(rec['before']),
                'after_html': side_html(after),
            })

        # ⚠️ Перемешиваем так, чтобы два варианта одной задачи не оказались
        # рядом: иначе оценка второго будет опираться на память о первом.
        rnd = random.Random(SEED)
        rnd.shuffle(screens)
        screens = spread_pairs(screens)
        if options.get('limit'):
            screens = screens[:options['limit']]

        page = self.build_page(screens, light=options.get('light'))
        with io.open(f'{OUT_DIR}/' + options['out'], 'w', encoding='utf-8') as fh:
            fh.write(page)

        # Ключ соответствия — отдельно, чтобы разбирать выгрузку после оценки.
        if not options.get('limit'):
          with io.open(f'{OUT_DIR}/screen_key.json', 'w', encoding='utf-8') as fh:
            json.dump([{'screen_id': s['screen_id'], 'problem_id': s['problem_id'],
                        'method': s['method'], 'group': s['group']}
                       for s in screens], fh, ensure_ascii=False, indent=1)

        self.say('Экранов: %d' % len(screens))
        self.say('Файл: %s/%s' % (OUT_DIR, options['out']))

    def build_page(self, screens, light=False):
        payload = json.dumps([{
            'screen_id': s['screen_id'], 'problem_id': s['problem_id'],
            'categories': s['categories'], 'comment': s['comment'],
            'action': s['action'], 'explain': s['explain'],
            'gate_flags': s['gate_flags'],
            'before': s['before_html'], 'after': s['after_html'],
        } for s in screens], ensure_ascii=False)

        btns = ''.join(
            '<button class="qls-vbtn" data-v="%s"><b>%s</b> %s</button>'
            % (key, hot, esc(label)) for key, hot, label in VERDICTS)

        head = engine_only() if light else katex_head()
        return PAGE.replace('__KATEX__', head) \
                   .replace('__BTNS__', btns) \
                   .replace('__PAYLOAD__', payload) \
                   .replace('__TOTAL__', str(len(screens)))


def spread_pairs(screens):
    """Развести варианты одной задачи как можно дальше друг от друга."""
    out = []
    pending = list(screens)
    last_seen = {}
    while pending:
        placed = False
        for i, s in enumerate(pending):
            prev = last_seen.get(s['problem_id'])
            if prev is None or len(out) - prev >= 8:
                out.append(s)
                last_seen[s['problem_id']] = len(out) - 1
                pending.pop(i)
                placed = True
                break
        if not placed:               # развести дальше некуда — берём первый
            s = pending.pop(0)
            out.append(s)
            last_seen[s['problem_id']] = len(out) - 1
    return out


PAGE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Оценка починок — ЭкЗадачи</title>
__KATEX__
<style>
:root{--ink:#1a1c22;--muted:#8a8f99;--line:#e2e4e9;--bg:#f6f7f9;--acc:#BE185D}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif;
     color:var(--ink);background:var(--bg)}
.qls-wrap{max-width:1240px;margin:0 auto;padding:16px}
.qls-top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.qls-count{font-size:13px;color:var(--muted)}
.qls-card{background:#fff;border:1px solid var(--line);border-radius:12px;
          padding:16px 18px;margin-bottom:14px}
.qls-verdict{background:#fff7ed;border-left:3px solid #b26b00;padding:8px 12px;
             border-radius:6px;margin-bottom:12px;font-size:14px}
.qls-explain{background:#f2f7fb;border-left:3px solid #0C447C;padding:8px 12px;
             border-radius:6px;margin-bottom:12px;font-size:14px}
.qls-gate{background:#fcebeb;border-left:3px solid #791F1F;padding:8px 12px;
          border-radius:6px;margin-bottom:12px;font-size:13px}
.qls-cols{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:860px){.qls-cols{grid-template-columns:1fr}}
.qls-side{min-width:0}
.qls-sidetitle{font-size:11px;text-transform:uppercase;letter-spacing:.05em;
               color:var(--muted);margin-bottom:8px}
.qls-lbl{font-size:11px;text-transform:uppercase;letter-spacing:.04em;
         color:#aab;margin:10px 0 3px}
.qls-fld{font-size:14px}
.qls-rendered{white-space:pre-wrap;word-wrap:break-word;overflow-x:auto}
.qls-raw{display:none;white-space:pre-wrap;font-family:ui-monospace,Consolas,
         monospace;font-size:12px;background:#f6f7f9;border:1px solid #e0e4ea;
         border-radius:6px;padding:6px 9px;margin-top:5px;overflow-x:auto}
body.qls-show-raw .qls-raw{display:block}
.qls-empty{color:#bbb;font-style:italic}
.qls-btn{border:1px solid #c9cbd2;background:#fff;border-radius:9px;
         padding:7px 13px;font-size:14px;cursor:pointer}
.qls-btn:hover{border-color:var(--acc)}
.qls-vbtn{display:block;width:100%;text-align:left;border:1px solid #c9cbd2;
          background:#fff;border-radius:9px;padding:9px 13px;font-size:14px;
          cursor:pointer;margin-bottom:7px}
.qls-vbtn b{display:inline-block;width:20px;color:var(--acc)}
.qls-vbtn.qls-on{background:var(--acc);color:#fff;border-color:var(--acc)}
.qls-vbtn.qls-on b{color:#fff}
.qls-stop{display:block;width:100%;text-align:left;border:1px solid #791F1F;
          background:#fff;color:#791F1F;border-radius:9px;padding:9px 13px;
          font-size:14px;cursor:pointer;margin:12px 0 8px}
.qls-stop.qls-on{background:#791F1F;color:#fff}
.qls-note{width:100%;border:1px solid #c9cbd2;border-radius:9px;padding:8px 10px;
          font:14px inherit;min-height:56px;resize:vertical}
.qls-help{font-size:12px;color:var(--muted);margin-top:10px;line-height:1.7}
.qls-done{background:#eaf3de;border-left:3px solid #27500A;padding:8px 12px;
          border-radius:6px;font-size:13px;margin-bottom:10px}
.qls-instr{background:#fff;border:1px solid var(--line);border-radius:12px;
           padding:16px 20px;margin-bottom:14px;font-size:14px}
.qls-instr h2{margin:0 0 8px;font-size:17px}
.qls-instr ul{margin:6px 0 6px 18px;padding:0}
.qls-warn{background:#fcebeb;border-left:3px solid #791F1F;padding:10px 14px;border-radius:8px;margin-bottom:12px;font-size:14px;color:#791F1F}
.katex .text{font-family:KaTeX_Main,-apple-system,"Segoe UI",sans-serif}
:is(table,.katex-display){overflow-x:auto}
</style></head><body>
<div class="qls-wrap">

<div class="qls-instr" id="qls-instr">
<h2>Что тут оценивается</h2>
<p>Человек (ты) уже отметил в этих задачах дефекты. Модель попробовала их
починить. Твоя задача — сказать, получилось ли. <b>Задачи в базе не менялись:
это только предложения правок.</b></p>
<ul>
<li>Слева — как задача выглядит <b>сейчас</b>, справа — <b>после починки</b>.
Оба вида отрендерены, как их увидит ученик. Сырой текст с долларами — по
кнопке «Исходник», если нужно разобраться в разметке.</li>
<li>Наверху видно, какой дефект ты отметил и что модель сообщила о своей правке.</li>
<li><b>Не показано, каким способом сделана починка</b> — это нарочно, оценка
слепая. Одна и та же задача может встретиться дважды: это разные попытки, и
оценивать их надо независимо.</li>
</ul>
<h2>Кнопки</h2>
<ul>
<li><b>1</b> — починено полностью: дефекта больше нет.</li>
<li><b>2</b> — починено частично: стало лучше, но дефект остался.</li>
<li><b>3</b> — не помогло: по сути ничего не изменилось.</li>
<li><b>4</b> — стало хуже, чем было.</li>
<li><b>9</b> — отдельный переключатель «изменился смысл, числа или слова
автора». <b>Он важнее самой оценки.</b> Ставь его всегда, когда заметил, что
правка тронула содержание, даже если внешне стало красивее.</li>
<li><b>Enter</b> — подтвердить и перейти дальше. <b>←</b> и <b>→</b> — листать.
<b>0</b> — показать/скрыть исходник.</li>
</ul>
<p>Экранов: <b>__TOTAL__</b>. При темпе ревью ILE (около 2 секунд на задачу это
для простой пометки; тут вчитываться дольше, ~20–30 секунд на экран) выйдет
примерно <b>40–60 минут</b>. Можно делать в несколько заходов: вердикты
сохраняются в браузере сами.</p>
<p>Когда закончишь — кнопка <b>«Скачать оценки (JSON)»</b> внизу, и пришли
файл Макару.</p>
<p><button class="qls-btn" id="qls-hide-instr">Свернуть инструкцию</button></p>
</div>

<div class="qls-top">
  <button class="qls-btn" id="qls-prev">← назад</button>
  <button class="qls-btn" id="qls-next">вперёд →</button>
  <button class="qls-btn" id="qls-raw">Исходник</button>
  <button class="qls-btn" id="qls-first">К первому неоценённому</button>
  <span class="qls-count" id="qls-count">—</span>
</div>

<div class="qls-card" id="qls-screen"></div>

<div class="qls-card">
  <div id="qls-buttons">__BTNS__</div>
  <button class="qls-stop" id="qls-stopbtn"><b>9</b> ⚠ изменился смысл, числа
    или слова автора</button>
  <textarea class="qls-note" id="qls-note"
            placeholder="Комментарий (необязательно)"></textarea>
  <div class="qls-help">Enter — подтвердить и дальше. Оценки сохраняются в
    браузере автоматически.</div>
  <p style="margin-top:12px">
    <button class="qls-btn" id="qls-download">Скачать оценки (JSON)</button>
    <span class="qls-count" id="qls-dlhint"></span>
  </p>
</div>

</div>
<script>window.SCREENS = __PAYLOAD__;</script>
<script>
(function(){
  var KEY='qls-repair-review-v1';
  var S=window.SCREENS, idx=0, state={};
  function $(id){return document.getElementById(id);}

  // ⚠️ Хранилище может быть недоступно (приватное окно, file:// с запретом,
  // data:-адрес). Тогда работаем в памяти — но об этом надо СКАЗАТЬ вслух:
  // молча потерянные оценки хуже, чем неудобное предупреждение.
  var storeOk=true;
  try{ localStorage.setItem(KEY+'::probe','1'); localStorage.removeItem(KEY+'::probe'); }
  catch(e){ storeOk=false; }
  try{ state=storeOk?(JSON.parse(localStorage.getItem(KEY))||{}):{}; }catch(e){ state={}; }
  function save(){ if(!storeOk) return;
    try{ localStorage.setItem(KEY,JSON.stringify(state)); }catch(e){} }
  if(!storeOk){
    var w=document.createElement('div');
    w.className='qls-warn';
    w.textContent='⚠ Браузер не даёт сохранять оценки между перезагрузками. '+
      'Работать можно, но не закрывай вкладку и скачай JSON, когда закончишь.';
    document.querySelector('.qls-wrap').insertBefore(w,
      document.getElementById('qls-instr'));
  }

  function cur(){ return S[idx]; }
  function rec(){ var s=cur(); return state[s.screen_id]||(state[s.screen_id]={}); }

  function draw(){
    var s=cur(), r=state[s.screen_id]||{};
    var gate = s.gate_flags && s.gate_flags.length
      ? '<div class="qls-gate">⚠ Автоматический шлюз отметил: '+
        s.gate_flags.join(', ')+'</div>' : '';
    var comment = s.comment
      ? '<div>Твой комментарий тогда: «'+s.comment+'»</div>' : '';
    var act = {fixed:'модель правила задачу',
               nothing_to_fix:'модель решила, что чинить нечего',
               unclear:'модель не поняла, в чём дефект'}[s.action]||s.action;
    $('qls-screen').innerHTML =
      '<div class="qls-verdict"><b>Ты отметил:</b> '+s.categories.join(', ')+
      comment+'</div>'+
      '<div class="qls-explain"><b>Модель:</b> '+act+
      (s.explain?('. '+s.explain):'')+'</div>'+ gate +
      '<div class="qls-cols">'+
      '<div class="qls-side"><div class="qls-sidetitle">сейчас в базе</div>'+
        s.before+'</div>'+
      '<div class="qls-side"><div class="qls-sidetitle">после починки</div>'+
        s.after+'</div></div>';
    if(typeof renderMathInElement!=='undefined'){
      $('qls-screen').querySelectorAll('.qls-tex').forEach(function(el){
        try{ renderMathInElement(el,{delimiters:[
          {left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],
          throwOnError:false}); }catch(e){}
      });
    }
    document.querySelectorAll('.qls-vbtn').forEach(function(b){
      b.classList.toggle('qls-on', r.verdict===b.dataset.v);
    });
    $('qls-stopbtn').classList.toggle('qls-on', !!r.meaning_changed);
    $('qls-note').value = r.note||'';
    var done=Object.keys(state).filter(function(k){return state[k].verdict;}).length;
    $('qls-count').textContent='Экран '+(idx+1)+' из '+S.length+
      ' · оценено '+done;
    $('qls-dlhint').textContent = done? ('готово оценок: '+done) : '';
  }

  function go(i){ if(i<0||i>=S.length) return; saveNote(); idx=i; draw(); }
  function saveNote(){ var r=rec(); r.note=$('qls-note').value; save(); }

  function setVerdict(v){ var r=rec(); r.verdict=v; r.at=new Date().toISOString();
    save(); draw(); }
  function toggleStop(){ var r=rec(); r.meaning_changed=!r.meaning_changed;
    save(); draw(); }

  document.querySelectorAll('.qls-vbtn').forEach(function(b){
    b.addEventListener('click',function(){ setVerdict(b.dataset.v); });
  });
  $('qls-stopbtn').addEventListener('click',toggleStop);
  $('qls-prev').addEventListener('click',function(){ go(idx-1); });
  $('qls-next').addEventListener('click',function(){ go(idx+1); });
  $('qls-raw').addEventListener('click',function(){
    document.body.classList.toggle('qls-show-raw'); });
  $('qls-hide-instr').addEventListener('click',function(){
    $('qls-instr').style.display='none'; });
  $('qls-first').addEventListener('click',function(){
    for(var i=0;i<S.length;i++){ if(!(state[S[i].screen_id]||{}).verdict){ go(i); return; } }
  });
  $('qls-note').addEventListener('blur',saveNote);

  document.addEventListener('keydown',function(e){
    if(e.target.tagName==='TEXTAREA') return;
    if(e.key>='1'&&e.key<='4'){
      setVerdict(['full','partial','nochange','worse'][+e.key-1]); e.preventDefault();
    } else if(e.key==='9'){ toggleStop(); e.preventDefault();
    } else if(e.key==='0'){ document.body.classList.toggle('qls-show-raw'); e.preventDefault();
    } else if(e.key==='Enter'){ go(idx+1); e.preventDefault();
    } else if(e.key==='ArrowLeft'){ go(idx-1); e.preventDefault();
    } else if(e.key==='ArrowRight'){ go(idx+1); e.preventDefault(); }
  });

  $('qls-download').addEventListener('click',function(){
    saveNote();
    var rows=S.map(function(s){
      var r=state[s.screen_id]||{};
      return {screen_id:s.screen_id, problem_id:s.problem_id,
              verdict:r.verdict||null, meaning_changed:!!r.meaning_changed,
              note:r.note||'', at:r.at||null};
    });
    var payload={format:'qls-repair-verdicts-v1',
                 exported_at:new Date().toISOString(),
                 count:rows.filter(function(x){return x.verdict;}).length,
                 verdicts:rows};
    var a=document.createElement('a');
    a.href=URL.createObjectURL(new Blob([JSON.stringify(payload,null,1)],
      {type:'application/json'}));
    a.download='repair_verdicts.json';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  });

  window.QLS_TEST={ go:go, setVerdict:setVerdict, toggleStop:toggleStop,
                    state:function(){return state;}, idx:function(){return idx;},
                    key:KEY };
  draw();
})();
</script>
</body></html>
"""
