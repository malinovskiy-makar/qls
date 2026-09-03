"""Сторож источников: что изменилось на страницах, откуда взяты факты.

⚠️ ГЛАВНОЕ ПРАВИЛО: КОМАНДА НЕ ТРОГАЕТ ДАННЫЕ. Она только смотрит, не
изменилась ли страница, с которой факт списан, и если изменилась —
заводит ПРЕДЛОЖЕНИЕ правки (`FactUpdateProposal`). Решает человек.
Автоматическая перезапись была бы худшим из возможных поведений: сайт
вуза переверстали — и проходной балл в разделе молча стал другим.

⚠️ НЕДОСТУПНЫЙ ИСТОЧНИК НЕ ЗАТИРАЕТ ПРЕЖНЕЕ. Сайт лёг на десять минут —
это не повод считать, что хеша у нас больше нет. Пишем `http_status`,
а `content_hash` оставляем как был.

Ограничение, о котором надо знать: хеш считается по телу ответа целиком.
Страницы, где в разметку зашит счётчик посещений или метка сборки,
меняются на каждый заход, и предложения по ним будут ложными. Лечится
не здесь, а выбором источника: у приказа и PDF такой беды нет.
"""
import hashlib
import time
import urllib.error
import urllib.parse
import urllib.request

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from olympiads.models import (FactSource, FactUpdateProposal, Olympiad,
                              OlympiadBenefit, OlympiadEvent,
                              OlympiadLevelYear, OlympiadScore,
                              OlympiadVariant)

USER_AGENT = 'WeconomicsBot/1.0 (+https://weconomics.site)'
TIMEOUT = 30
# Вежливость: не меньше секунды между запросами. Источники раздела кучкуются
# по доменам (pravo.gov.ru, hse.ru), и частить по ним нельзя.
DELAY_SECONDS = 1.0

# Кто ссылается на источник. Одно место списка: появится новая модель со
# ссылкой — добавлять сюда, иначе её факты останутся без сторожа.
DEPENDENTS = (
    (Olympiad, 'олимпиада'),
    (OlympiadLevelYear, 'уровень'),
    (OlympiadEvent, 'дата'),
    (OlympiadScore, 'проходной балл'),
    (OlympiadBenefit, 'льгота'),
    (OlympiadVariant, 'комплект'),
)


def fetch(url):
    """(тело, код) или (None, код/None). Исключений наружу не выпускает.

    ⚠️ СХЕМУ ПРОВЕРЯЕМ ДО ОТКРЫТИЯ. `urlopen` честно исполняет `file:` и
    другие схемы, а адрес источника — это ДАННЫЕ: их вводит человек в
    админке, и опечатка (или чужая правка) превратила бы сторожа в
    читалку локальных файлов. Нашёл bandit (B310), и находка настоящая.
    """
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ('http', 'https'):
        return None, None

    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        # noqa: S310 — схема уже сужена до http/https выше.
        with urllib.request.urlopen(request,  # nosec B310
                                    timeout=TIMEOUT) as response:
            return response.read(), response.getcode()
    except urllib.error.HTTPError as error:
        return None, error.code
    except Exception:
        return None, None


class Command(BaseCommand):
    help = ('Обходит источники фактов и заводит предложения правок для тех, '
            'чьи страницы изменились. Данные не трогает.')

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Напечатать план и ничего не писать.')
        parser.add_argument('--delay', type=float, default=DELAY_SECONDS,
                            help='Пауза между запросами, секунд.')

    def handle(self, *args, **options):
        dry = options['dry_run']
        sources = list(FactSource.objects.exclude(url='').order_by('pk'))
        if not sources:
            self.stdout.write('Источников с адресом нет.')
            return

        same = changed = failed = 0
        proposals = 0
        for number, source in enumerate(sources):
            if number:
                time.sleep(options['delay'])
            body, status = fetch(source.url)

            if body is None:
                failed += 1
                self.stdout.write('  НЕДОСТУПЕН {:<3} {}'.format(
                    status or '—', source.url[:70]))
                if not dry:
                    # ⚠️ Хеш НЕ трогаем: недоступность — не изменение.
                    FactSource.objects.filter(pk=source.pk).update(
                        http_status=status)
                continue

            digest = hashlib.sha256(body).hexdigest()
            if source.content_hash and digest != source.content_hash:
                changed += 1
                made = self._propose(source, digest, dry)
                proposals += made
                self.stdout.write('  ИЗМЕНИЛСЯ   {:<3} {} (+{} предложений)'
                                  .format(status, source.url[:60], made))
                if not dry:
                    FactSource.objects.filter(pk=source.pk).update(
                        http_status=status, fetched_at=timezone.now())
                continue

            same += 1
            if not dry:
                FactSource.objects.filter(pk=source.pk).update(
                    http_status=status, fetched_at=timezone.now(),
                    content_hash=digest)

        self.stdout.write('')
        self.stdout.write('Источников: {}. Без изменений: {}. Изменилось: {}. '
                          'Недоступно: {}. Предложений: {}.'.format(
                              len(sources), same, changed, failed, proposals))
        if dry:
            self.stdout.write('Это был --dry-run: в базу не записано ничего.')

    def _propose(self, source, digest, dry):
        """Предложения по фактам, висящим на изменившемся источнике."""
        targets = []
        for model, human in DEPENDENTS:
            for obj in model.objects.filter(source=source):
                targets.append((model, human, obj))
        if not targets:
            # Источник ни к чему не привязан — предложение всё равно нужно:
            # изменение замечено, и человек должен об этом узнать.
            targets = [(FactSource, 'источник', source)]

        made = 0
        for model, human, obj in targets:
            app_label = model._meta.app_label
            model_name = model.__name__
            # ⚠️ Не плодим второе предложение по тому же факту: сторож
            # ходит по расписанию, и за неделю их накопилось бы семь.
            exists = FactUpdateProposal.objects.filter(
                target_app=app_label, target_model=model_name,
                target_pk=obj.pk, field_name='source',
                status=FactUpdateProposal.Status.PENDING).exists()
            if exists:
                continue
            made += 1
            if dry:
                continue
            with transaction.atomic():
                FactUpdateProposal.objects.create(
                    target_app=app_label, target_model=model_name,
                    target_pk=obj.pk, field_name='source',
                    old_value='sha256 {}\nтекущее значение ({}): {}'.format(
                        source.content_hash[:16], human, obj),
                    new_value='sha256 {}\nстраница изменилась — проверьте '
                              'значение глазами'.format(digest[:16]),
                    source=source)
        return made
