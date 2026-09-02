u"""
answer_dispute_review — пакет разбора расхождений по ответу и его импорт.

Экспорт делает ОДИН самодостаточный HTML-файл: по каждому спорному вопросу
условие, варианты, ответ банка, ответ модели и три кнопки «кто прав».
Файл открывается с file:// без интернета и сохраняет вердикты в JSON.

Импорт делает две вещи, и обе штатными путями:
  • «прав банк» → AnswerSecondOpinion.resolved = True, задача сама
    возвращается в пул при следующей пересборке;
  • «права модель» → та же отметка ПЛЮС ReviewVerdict с категорией
    `wrong_answer`. Дальше работает обычный human_review_mark, который и
    проставит `human_review='defect'`. Второго механизма пометки брака мы
    не заводим: он бы разъехался с первым.

⚠️ КОМАНДА НЕ ТРОГАЕТ `answer`. Даже когда ревьюер согласился с моделью,
правильный ответ в банке не переписывается: задача помечается браком, и
её чинит человек. Это запрет P0.

Запуск:
    manage.py answer_dispute_review --export --out reports/answer_disputes
    manage.py answer_dispute_review --import verdicts.json --reviewer anich
    manage.py answer_dispute_review --import verdicts.json --reviewer anich --apply
"""
import io
import json
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from problems.models import AnswerSecondOpinion, Problem, ReviewVerdict

FORMAT = 'qls-answer-disputes-v1'
CHOICES = [
    ('bank_right', u'Прав банк', '1'),
    ('model_right', u'Права модель, задача в брак', '2'),
    ('unclear', u'Вопрос сам по себе спорный', '3'),
]

PAGE_CSS = u"""
body{font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;
 background:#f7f7f5;color:#1c1c1c}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #e2e2df;
 padding:12px 20px;display:flex;gap:16px;align-items:center;z-index:5}
main{max-width:900px;margin:0 auto;padding:20px}
.card{background:#fff;border:1px solid #e2e2df;border-radius:10px;
 padding:18px 20px;margin:0 0 18px}
.q{font-size:17px;margin:0 0 12px;white-space:pre-wrap}
.opts{margin:0 0 14px;padding-left:20px;color:#333}
.answers{display:flex;gap:14px;margin:0 0 14px;flex-wrap:wrap}
.ans{flex:1 1 220px;border:1px solid #ddd;border-radius:8px;padding:10px 12px}
.ans b{display:block;font-size:13px;color:#666;font-weight:600;
 text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px}
.val{font-size:18px;font-weight:600}
.btns{display:flex;gap:8px;flex-wrap:wrap}
button{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid #ccc;
 background:#fff;cursor:pointer}
button.on{background:#1c1c1c;color:#fff;border-color:#1c1c1c}
.done{opacity:.5}
.meta{font-size:13px;color:#777;margin-bottom:8px}
#save{background:#1c1c1c;color:#fff;border-color:#1c1c1c}
#count{font-variant-numeric:tabular-nums}
"""

PAGE_JS = u"""
var VERDICTS = {};
function mark(id, key, el){
  VERDICTS[id] = key;
  var card = el.closest('.card');
  card.querySelectorAll('button').forEach(function(b){b.classList.remove('on');});
  el.classList.add('on');
  card.classList.add('done');
  document.getElementById('count').textContent = Object.keys(VERDICTS).length;
}
function save(){
  var data = {format: FORMAT, bundle: BUNDLE, verdicts: VERDICTS};
  var blob = new Blob([JSON.stringify(data, null, 1)], {type:'application/json'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = BUNDLE + '_verdicts.json';
  a.click();
}
document.addEventListener('keydown', function(e){
  var card = document.querySelector('.card:not(.done)');
  if(!card) return;
  var btn = card.querySelector('button[data-key="' + e.key + '"]');
  if(btn){ btn.click(); card.scrollIntoView({block:'start'}); }
});
"""


def esc(text):
    return (text or '').replace('&', '&amp;').replace(
        '<', '&lt;').replace('>', '&gt;')


class Command(BaseCommand):
    help = u'Пакет разбора расхождений по ответу и импорт вердиктов.'

    def add_arguments(self, parser):
        parser.add_argument('--export', action='store_true')
        parser.add_argument('--import', dest='import_path', default='')
        parser.add_argument('--apply', action='store_true',
                            help=u'без него импорт — сухой прогон')
        parser.add_argument('--reviewer', default='')
        parser.add_argument('--bundle', default='')
        parser.add_argument('--out', default=os.path.join(
            'reports', 'answer_disputes'))
        parser.add_argument('--limit', type=int, default=0)

    def handle(self, *args, **options):
        if options['import_path']:
            return self.do_import(options)
        if options['export']:
            return self.do_export(options)
        raise CommandError(u'укажите --export или --import <файл>')

    # -- экспорт ----------------------------------------------------------
    def do_export(self, options):
        from game.models import GameQuestion
        rows = (AnswerSecondOpinion.objects
                .filter(agrees=False, resolved=False)
                .select_related('problem').order_by('problem_id'))
        if options['limit']:
            rows = rows[:options['limit']]
        rows = list(rows)
        if not rows:
            self.stdout.write(u'Спорных ответов нет — пакет не нужен.')
            return

        by_problem = {}
        for gq in GameQuestion.objects.filter(
                problem_id__in=[r.problem_id for r in rows],
                is_generated=False):
            by_problem.setdefault(gq.problem_id, gq)

        bundle = options['bundle'] or 'answers_%s' % timezone.now().strftime(
            '%Y%m%d')
        os.makedirs(options['out'], exist_ok=True)
        path = os.path.join(options['out'], '%s.html' % bundle)

        parts = [u'<!doctype html><html lang="ru"><meta charset="utf-8">',
                 u'<title>Расхождения по ответам — %s</title>' % esc(bundle),
                 u'<style>%s</style>' % PAGE_CSS,
                 u'<header><b>Кто прав: банк или модель</b>',
                 u'<span>размечено <span id="count">0</span> из %d</span>'
                 % len(rows),
                 u'<button id="save" onclick="save()">Сохранить вердикты'
                 u'</button></header><main>']
        for op in rows:
            gq = by_problem.get(op.problem_id)
            if gq is None:
                continue
            parts.append(u'<div class="card" data-id="%d">' % op.problem_id)
            parts.append(u'<div class="meta">задача #%d · %s · уверенность '
                         u'модели %.2f</div>'
                         % (op.problem_id, esc(gq.question_type),
                            op.confidence))
            parts.append(u'<div class="q">%s</div>' % esc(gq.question))
            if gq.options:
                parts.append(u'<ol class="opts">%s</ol>' % ''.join(
                    u'<li>%s</li>' % esc(o) for o in gq.options))
            parts.append(u'<div class="answers">')
            parts.append(u'<div class="ans"><b>ответ банка</b>'
                         u'<div class="val">%s</div></div>'
                         % esc(op.bank_answer))
            parts.append(u'<div class="ans"><b>ответ модели</b>'
                         u'<div class="val">%s</div></div>'
                         % esc(op.model_answer))
            parts.append(u'</div><div class="btns">')
            for key, label, hotkey in CHOICES:
                parts.append(
                    u'<button data-key="%s" onclick="mark(%d,\'%s\',this)">'
                    u'%s. %s</button>' % (hotkey, op.problem_id, key,
                                          hotkey, esc(label)))
            parts.append(u'</div></div>')
        parts.append(u'</main><script>var FORMAT=%s;var BUNDLE=%s;%s</script>'
                     % (json.dumps(FORMAT), json.dumps(bundle), PAGE_JS))
        parts.append(u'</html>')
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(parts))
        self.stdout.write(self.style.SUCCESS(
            u'Пакет: %s (%d спорных)' % (path, len(rows))))

    # -- импорт -----------------------------------------------------------
    def do_import(self, options):
        with io.open(options['import_path'], encoding='utf-8') as fh:
            data = json.load(fh)
        if data.get('format') != FORMAT:
            raise CommandError(u'чужой формат файла: %r' % data.get('format'))
        verdicts = data.get('verdicts') or {}
        bundle = data.get('bundle') or 'answers'
        reviewer = options['reviewer']

        known = {k for k, _l, _h in CHOICES}
        bad = sorted({v for v in verdicts.values() if v not in known})
        if bad:
            raise CommandError(u'неизвестные вердикты: %s' % bad)

        counts = {}
        for value in verdicts.values():
            counts[value] = counts.get(value, 0) + 1
        for key, label, _h in CHOICES:
            self.stdout.write(u'  %-12s %s: %d' % (key, label,
                                                   counts.get(key, 0)))

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                u'Сухой прогон: в базу НЕ записано. Добавьте --apply.'))
            return

        defects = 0
        resolved = 0
        with transaction.atomic():
            for raw_id, value in verdicts.items():
                pid = int(raw_id)
                n = (AnswerSecondOpinion.objects
                     .filter(problem_id=pid, agrees=False, resolved=False)
                     .update(resolved=True, resolution=value))
                resolved += n
                if value != 'model_right':
                    continue
                problem = Problem.objects.filter(pk=pid).first()
                if problem is None:
                    continue
                _obj, created = ReviewVerdict.objects.get_or_create(
                    bundle=bundle, problem=problem, category='wrong_answer',
                    defaults={
                        'comment': u'слепая перепроверка: ответ модели не '
                                   u'сошёлся с банком',
                        'reviewer': reviewer,
                        'created_at': timezone.now(),
                    })
                defects += 1 if created else 0
        self.stdout.write(self.style.SUCCESS(
            u'Разобрано мнений: %d. Заведено вердиктов «неверный ответ»: %d.'
            % (resolved, defects)))
        self.stdout.write(u'Дальше — штатно: human_review_mark --apply, '
                          u'потом build_game_pool.')
