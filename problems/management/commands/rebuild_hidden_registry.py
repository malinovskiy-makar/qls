import csv
import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from problems.models import Problem, SourceReference


class Command(BaseCommand):
    help = (
        'Собирает реестр скрытых ILE-задач: патчи дают список кандидатов + причины, '
        'база подтверждает реальный статус. '
        'Задачи из meta.hide, у которых status != hidden — считаются возвращёнными и в реестр не попадают.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dir', default='reports/ai_cleanup_ile')
        parser.add_argument('--out', default='reports/ai_cleanup_ile/hidden_registry.csv')

    def handle(self, *args, **opts):
        base = Path(opts['dir'])
        out = Path(opts['out'])

        if not base.exists():
            self.stderr.write(self.style.ERROR(f'Директория не найдена: {base}'))
            return

        # 1. Из патчей: все id, когда-либо упомянутые в meta.hide, + причины
        patch_info = {}       # int id → {'reason': str, 'batch': str}
        all_patch_hide_ids = set()

        for af in sorted(base.glob('*apply*.json')):
            if 'backup' in af.name:
                continue
            try:
                patch = json.loads(af.read_text(encoding='utf-8'))
            except Exception as e:
                self.stdout.write(f'пропускаю {af.name}: {e}')
                continue

            meta = patch.get('meta', {})
            hide = [int(x) for x in (meta.get('hide') or [])]
            reasons = {str(k): v for k, v in (meta.get('hide_reasons') or {}).items()}
            batch = str(meta.get('batch', af.stem))

            all_patch_hide_ids.update(hide)
            for hid in hide:
                sid = str(hid)
                reason = reasons.get(sid, '(не зафиксирована)')
                if hid not in patch_info:
                    patch_info[hid] = {'reason': reason, 'batch': batch}

        # 2. Реальный статус из базы — только для id из патчей
        db_status = {
            p.id: p.status
            for p in Problem.objects.filter(id__in=all_patch_hide_ids).only('id', 'status')
        }
        db_title = {
            p.id: (p.title or '')
            for p in Problem.objects.filter(id__in=all_patch_hide_ids).only('id', 'title')
        }

        # URL из SourceReference
        urls = {}
        for sr in SourceReference.objects.filter(
            problem_id__in=all_patch_hide_ids
        ).only('problem_id', 'url'):
            if sr.problem_id not in urls and sr.url:
                urls[sr.problem_id] = sr.url

        # 3. Разделяем: реально скрытые vs возвращённые
        still_hidden = {pid for pid in all_patch_hide_ids
                        if db_status.get(pid) == Problem.Status.HIDDEN}
        returned_ids = all_patch_hide_ids - still_hidden

        self.stdout.write(
            f'возвращённых на сайт (есть в патчах как hide, но в базе НЕ hidden): {len(returned_ids)}'
            + (f' {sorted(returned_ids)}' if returned_ids else '')
        )

        # 4. Реестр — только реально скрытые
        rows = []
        for pid in sorted(still_hidden):
            info = patch_info.get(pid, {})
            rows.append({
                'id': str(pid),
                'batch': info.get('batch', ''),
                'title': db_title.get(pid, ''),
                'url': urls.get(pid, ''),
                'reason': info.get('reason', '(не зафиксирована)'),
            })

        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['id', 'batch', 'title', 'url', 'reason'])
            w.writeheader()
            for r in rows:
                w.writerow(r)

        self.stdout.write(self.style.SUCCESS(f'Реестр: {out} — строк: {len(rows)}'))

        c = Counter(r['batch'] for r in rows if r['batch'])
        if c:
            self.stdout.write('по батчам: ' + ', '.join(f'{b}={n}' for b, n in sorted(c.items())))

        no_reason = sum(1 for r in rows if r['reason'] == '(не зафиксирована)')
        if no_reason:
            self.stdout.write(self.style.WARNING(f'без зафиксированной причины: {no_reason}'))
        else:
            self.stdout.write('у всех записей причина зафиксирована ✓')
