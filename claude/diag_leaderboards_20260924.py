# Только чтение: лидерборды Wecon Rush и ВП (фаза 7.0 сессии 24.09.2026).
# Запуск на бою: docker compose exec -T web python manage.py shell < ../claude/diag_leaderboards_20260924.py
from collections import Counter
from datetime import timedelta
from django.db.models import Count, Min, Q
from django.utils import timezone
from game.models import GameResult
from problems.models_platform import Event
now = timezone.now(); since = now - timedelta(days=30)
res = GameResult.objects.filter(created_at__gte=since)
ends = Event.objects.filter(name='game_end', ts__gte=since)
starts = Event.objects.filter(name='game_start', ts__gte=since)
print('game_start', starts.count(), 'game_end', ends.count(), 'GameResult', res.count())
# ⚠️ Сопоставление по режиму и времени, НЕ по очкам: событие `game_end`
# пишет очки клиента до поправки на точность, сервер хранит итоговые.
lost = 0
for e in ends.iterator():
    p = e.props or {}
    q = res.filter(mode=p.get('mode'),
                   created_at__gte=e.ts - timedelta(seconds=180), created_at__lte=e.ts + timedelta(seconds=30))
    if not q.exists():
        lost += 1
print('game_end без GameResult рядом по времени (потерянные):', lost)
print('по ranked/unranked_reason:', sorted(Counter((r['ranked'], r['unranked_reason']) for r in res.values('ranked', 'unranked_reason')).items(), key=lambda x: -x[1]))
print('ended_reason:', sorted(Counter(res.values_list('ended_reason', flat=True)).items(), key=lambda x: -x[1]))
# дата в таблице ≠ дате рекорда (очки, все время, v2)
mism = total = 0
ranked = GameResult.objects.filter(ranked=True, user__isnull=False)
for row in ranked.values('user_id', 'mode').annotate(first=Min('created_at')):
    best = ranked.filter(user_id=row['user_id'], mode=row['mode']).order_by('-score', 'created_at').first()
    total += 1
    if best and timezone.localtime(best.created_at).date() != timezone.localtime(row['first']).date():
        mism += 1
print('игрок×режим в таблице:', total, 'дата таблицы ≠ дате рекорда:', mism)
from vp.models import VPAttempt
open_expired = VPAttempt.objects.filter(is_ranked=True, submitted_at__isnull=True, expires_at__lt=now).count()
unpub = VPAttempt.objects.filter(is_ranked=True, submitted_at__isnull=False, variant__is_published=False).count()
timer_users = set(VPAttempt.objects.filter(with_timer=True, user__isnull=False).values_list('user_id', flat=True))
ranked_users = set(VPAttempt.objects.filter(is_ranked=True, user__isnull=False).values_list('user_id', flat=True))
print('ВП: открытые зачётные с истёкшим временем', open_expired, '| зачётные сданные на неопубликованных', unpub,
      '| людей с попыткой на время без зачётной', len(timer_users - ranked_users), 'из', len(timer_users))
print('ВП: всего попыток', VPAttempt.objects.count(), 'зачётных', VPAttempt.objects.filter(is_ranked=True).count())
