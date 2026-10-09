"""Разговор с сайтом «Высшей пробы» olymp46.hse.ru.

Страница schoolwinners.html — пустая оболочка на Dojo; данные отдаёт фреймворк
`mill` POST-запросами `query=<xml>` на адреса `/hseAnonymous/<вид>`:

* `cursor.xml` / `batch.xml` — выборки (сезоны, туры, предметы, классы);
* `xsltreport.xml` — шаблон `SchoolWinners`: список дипломантов одной степени;
* `executeoleobjectmethod` — `TAbiturientStatus.GetWorkImage(ID)`: PDF работы.

Механизм выяснен по исходнику `/schoolwinners.js` и `/milljs/mill.js`
(разведка 09.10.2026, RECON.md в папке данных). Куки не нужны.

Вежливость к чужому серверу — здесь, а не у вызывающего: не чаще одного
запроса в секунду, понятный User-Agent, три повтора с паузой 5/15/45 с;
403/429/капча — `Blocked`, и дальше никто не идёт.
"""
import http.client
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

SITE = 'https://olymp46.hse.ru'
BASE = SITE + '/hseAnonymous/'
USER_AGENT = ('WeconomicsResearchBot/1.0 (+https://weconomics.ai; '
              'olympiad works corpus for research; max 1 request/second)')
MIN_INTERVAL = 1.0
RETRY_PAUSES = (5, 15, 45)
TIMEOUT = 60


class Blocked(Exception):
    """Сервер отказал (403/429/капча). Остановиться, а не обходить."""


class SiteError(Exception):
    """Сбой, который не вылечили повторы, или ошибка в ответе `mill`."""


# ---------------------------------------------------------------- запросы
# Чистые функции: строят ровно тот XML, что строит mill.js в браузере.

def _item(part, name, value=None, special=None):
    attrs = 'part=%s name=%s' % (quoteattr(str(part)), quoteattr(name))
    if value is not None:
        attrs += ' value=%s' % quoteattr(str(value))
    if special is not None:
        attrs += ' special=%s' % quoteattr(str(special))
    return '<item %s/>' % attrs


def q_seasons():
    """Сезоны, у которых опубликованы работы (`PublishSchOlymp=1`)."""
    return ('<query class="TAdmissionYear">'
            + _item(0, 'ID') + _item(0, 'OlympLearnYear$D')
            + _item(1, 'PublishSchOlymp', 1)
            + _item(2, 'OlympLearnYear$D', special=7) + '</query>')


def q_rounds(season_id):
    """Олимпиадные «туры» сезона — по одному на класс."""
    return ('<root><query class="TBachRound" fetchall="1">'
            + _item(0, 'ID') + _item(1, 'Master', season_id)
            + _item(1, 'BachRoundType$N', 'brtOlimpic') + '</query></root>')


def q_subjects(round_ids):
    """Названия предметов (вкладки слева) по турам сезона."""
    return ('<query class="TRoundComp">' + _item(0, 'Name')
            + _item(1, 'Master', ';'.join(round_ids)) + _item(3, 'Name')
            + '</query>')


def q_grades(round_ids, subject_name):
    """Блоки «Олимпиада NN класс» одного предмета."""
    return ('<query class="TRoundComp">'
            + _item(0, 'Master') + _item(0, 'Master$N') + _item(0, 'Name')
            + _item(0, 'ID') + _item(1, 'Name', subject_name)
            + _item(1, 'Master', ';'.join(round_ids)) + _item(2, 'Master$N')
            + _item(3, 'Master') + _item(3, 'Master$N') + _item(3, 'Name')
            + _item(3, 'ID') + '</query>')


DEGREES = {1: 'rrFirstDegree', 2: 'rrSecondDegree', 3: 'rrThirdDegree'}


def q_winners(season_id, grade_label, subject_name, degree):
    """Список дипломантов одной степени (`local.loadWinners`)."""
    params = {'AdmissionYear': season_id, 'BachRoundName': grade_label,
              'RoundCompName': subject_name, 'RoundResultName': DEGREES[degree]}
    row = ''.join('<%s>%s</%s>' % (k, escape(str(v)), k) for k, v in params.items())
    return ('<execute eof="1" class="TRoundAbiturSt" template="SchoolWinners">'
            '<row>%s</row></execute>' % row)


def q_work(work_id):
    """PDF работы (`local.getWork`). Имя файла — нейтральное, без ФИО:
    браузер подставляет сюда фамилию, нам она не нужна."""
    wid = escape(str(int(work_id)))
    return ('<execute eof="1" class="TAbiturientStatus" method="GetWorkImage" '
            'filename="work_%s.pdf"><row><ID>%s</ID></row></execute>' % (wid, wid))


def work_source_url(work_id):
    """Адрес PDF без куки: тот же запрос GET-ом (сайт его принимает)."""
    return BASE + 'executeoleobjectmethod?' + urllib.parse.urlencode(
        {'query': q_work(work_id)})


# ------------------------------------------------------------- ответы

def parse_rows(xml_bytes):
    """Строки ответа `mill` как список словарей «тег → текст».

    Ошибка `mill` приходит корнем `<error>` — это `SiteError`. Вложенные
    `<row>` в `batch.xml` (корень → query → row) разворачиваются.
    """
    # Ответы mill объявлений DTD не содержат никогда; с `<!DOCTYPE` — не
    # разбираем (бомба внутренних сущностей, как в parse_vsosh_municip).
    if b'<!DOCTYPE' in xml_bytes[:2000]:
        raise SiteError('Ответ сайта с DOCTYPE — так mill не отвечает; не разбираю.')
    try:
        root = ET.fromstring(xml_bytes)  # nosec B314 — DOCTYPE отсечён выше
    except ET.ParseError as error:
        raise SiteError('Ответ сайта — не XML: %s' % error)
    if root.tag == 'error':
        raise SiteError('Сайт вернул ошибку: %s'
                        % ' '.join(root.itertext()).strip()[:300])
    rows = root.iter('row') if root.find('row') is None else root.findall('row')
    return [{child.tag: (child.text or '').strip() for child in row} for row in rows]


def looks_blocked(status, content_type, body):
    """403/429 или страница-капча вместо данных — признак отказа."""
    if status in (403, 429):
        return True
    head = body[:4000].lower()
    if 'text/html' in (content_type or '') and (b'captcha' in head or b'robot' in head):
        return True
    return False


# ------------------------------------------------------------- клиент

class Client:
    """Вежливый клиент: интервал, повторы, остановка на отказе.

    `opener` и `sleep` подменяются в тестах — сеть в тестах не трогается.
    """

    def __init__(self, opener=None, sleep=time.sleep, clock=time.monotonic,
                 log=None):
        self.opener = opener or urllib.request.build_opener()
        self.sleep = sleep
        self.clock = clock
        self.log = log or (lambda message: None)
        self._last = None
        self.requests = 0

    def _wait_turn(self):
        if self._last is not None:
            gap = MIN_INTERVAL - (self.clock() - self._last)
            if gap > 0:
                self.sleep(gap)

    def post(self, endpoint, query, expect='xml'):
        """Один запрос с повторами. Возвращает байты ответа."""
        data = urllib.parse.urlencode({'query': query}).encode('utf-8')
        last_error = None
        for attempt in range(len(RETRY_PAUSES) + 1):
            if attempt:
                pause = RETRY_PAUSES[attempt - 1]
                self.log('  повтор %d через %d с (%s)' % (attempt, pause, last_error))
                self.sleep(pause)
            self._wait_turn()
            request = urllib.request.Request(BASE + endpoint, data=data, headers={
                'User-Agent': USER_AGENT,
                'Disable-Basic-Auth': 'yes',
                'Referer': SITE + '/schoolwinners.html',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            })
            self.requests += 1
            try:
                with self.opener.open(request, timeout=TIMEOUT) as response:
                    status = getattr(response, 'status', 200)
                    content_type = response.headers.get('Content-Type', '')
                    body = response.read()
            except urllib.error.HTTPError as error:
                self._last = self.clock()
                if error.code in (403, 429):
                    raise Blocked('Сайт ответил %d на %s — останавливаюсь.'
                                  % (error.code, endpoint))
                last_error = 'HTTP %d' % error.code
                continue
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError,
                    http.client.HTTPException) as error:
                # HTTPException — в том числе IncompleteRead: обрыв посреди PDF.
                self._last = self.clock()
                last_error = '%s: %s' % (type(error).__name__, error)
                continue
            self._last = self.clock()
            if looks_blocked(status, content_type, body):
                raise Blocked('Похоже на капчу/отказ на %s — останавливаюсь.' % endpoint)
            if expect == 'pdf' and not body.startswith(b'%PDF'):
                last_error = 'ответ не PDF (%s, %d байт)' % (content_type, len(body))
                continue
            return body
        raise SiteError('%s: не удалось после %d повторов — %s'
                        % (endpoint, len(RETRY_PAUSES), last_error))

    # Удобные обёртки ровно под шаги страницы.
    def seasons(self):
        return parse_rows(self.post('cursor.xml', q_seasons()))

    def round_ids(self, season_id):
        return [r['ID'] for r in parse_rows(self.post('batch.xml', q_rounds(season_id)))]

    def subjects(self, round_ids):
        return [r['Name'] for r in parse_rows(self.post('cursor.xml', q_subjects(round_ids)))]

    def grades(self, round_ids, subject_name):
        return parse_rows(self.post('cursor.xml', q_grades(round_ids, subject_name)))

    def winners(self, season_id, grade_label, subject_name, degree):
        return parse_rows(self.post(
            'xsltreport.xml', q_winners(season_id, grade_label, subject_name, degree)))

    def work_pdf(self, work_id):
        return self.post('executeoleobjectmethod', q_work(work_id), expect='pdf')
