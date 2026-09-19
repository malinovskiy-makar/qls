"""Демо-репетитор для проверки и снимков корзины «Стола» (S5, 18.09.2026).

`manage.py shell -c "exec(open('scripts/stol_demo_teacher.py', encoding='utf-8').read())"`

Создаёт (или пересоздаёт) ОТДЕЛЬНОГО пользователя `stol-teacher@test.local` с
двумя занятиями и тремя работами — как на снимке 23 («ДЗ 6. Монополия» 12
задач · 9Б и т. д.). Чужие данные не трогает: удаляет и пишет только занятия и
работы этого пользователя. Задачи — первые видимые из каталога, только ссылки.
"""
from django.contrib.auth import get_user_model

from problems.models import Assignment, Problem, StudentGroup
from problems.models_platform import AssignmentItem

User = get_user_model()
teacher, _ = User.objects.get_or_create(username='stol-teacher@test.local',
                                        defaults={'email': 'stol-teacher@test.local'})
teacher.role = 'teacher'
teacher.first_name = 'Демо'
teacher.last_name = 'Репетитор'
teacher.save()
Assignment.objects.filter(author=teacher).delete()
StudentGroup.objects.filter(teacher=teacher).delete()

visible = list(Problem.objects.filter(
    status=Problem.Status.PUBLISHED, needs_quality_review=False, hidden_pending_review=False,
    content_status=Problem.ContentStatus.OK).order_by('-id').values_list('pk', flat=True)[:40])
g9 = StudentGroup.objects.create(name='9Б', teacher=teacher)
g10 = StudentGroup.objects.create(name='10А', teacher=teacher)
for name, group, ids in (('ДЗ 6. Монополия', g9, visible[1:13]),
                         ('ДЗ 7. Ценовая дискриминация', g10, visible[4:8]),
                         ('Контрольная 2', g10, visible[20:29])):
    a = Assignment.objects.create(name=name, author=teacher, group=group)
    a.problems.set(ids)
    AssignmentItem.objects.bulk_create([AssignmentItem(assignment=a, catalog_problem_id=pk, order=i)
                                        for i, pk in enumerate(ids)])
print('TEACHER=%d' % teacher.pk)
