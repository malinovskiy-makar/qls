> **Владелец:** Макар
> **Обновлён:** 2026-08-22
> **Статус:** действует

# ADR 0014. У Referrer-Policy и X-Content-Type-Options один владелец — Django

**Источник:** та же сессия «конфликт заголовков», 22.08.2026, ветка
`feat/prod-deploy`. Найдено попутно при разборе [ADR 0013](0013-x-frame-options-owner.md)
(X-Frame-Options) — та же причина, тот же класс дубля, но не решалось сразу:
для `Referrer-Policy` нужно было решение владельца о значении, а не только
о том, кто заголовок ставит.

## Контекст

`Referrer-Policy` управляет тем, что браузер сообщает чужому сайту в
заголовке `Referer` при переходе по ссылке с наших страниц. `X-Content-Type-Options: nosniff`
запрещает браузеру домысливать тип файла по содержимому — без него
загруженный файл, «похожий» на HTML, может выполниться как HTML.

Оба заголовка ставили одновременно два источника:

| Заголовок | nginx (`deploy/nginx/available/django.conf`) | Django (`config/settings_production.py`) |
|---|---|---|
| `Referrer-Policy` | `strict-origin-when-cross-origin` | `same-origin` (`SECURE_REFERRER_POLICY`) |
| `X-Content-Type-Options` | `nosniff` | `nosniff` (`SECURE_CONTENT_TYPE_NOSNIFF = True`) |

### Что реально приходило в браузер

Замерено `curl -sI https://weconomics.site/` и `.../login/` **22.08.2026**,
живой сайт, уже ПОСЛЕ применения ADR 0013 (X-Frame-Options к этому моменту
уже не дублировался):

```
x-frame-options: DENY
x-content-type-options: nosniff                        ← Django
referrer-policy: same-origin                            ← Django
x-content-type-options: nosniff                         ← nginx (дубль, значение то же)
referrer-policy: strict-origin-when-cross-origin         ← nginx (дубль, значение ДРУГОЕ)
```

**Правило разрешения конфликта у этого заголовка другое, чем у
`X-Frame-Options`.** У `X-Frame-Options` браузеры при двух разных значениях
закрываются в строгую сторону (`DENY` побеждал сам по себе). У
`Referrer-Policy` при повторении заголовка **побеждает ПОСЛЕДНЕЕ значение** —
а nginx дописывает свою строку ПОСЛЕ той, что пришла от Django (`add_header`
добавляет в конец). Значит, до этой правки реально действовало значение
**nginx**, `strict-origin-when-cross-origin` — более слабое: оно сообщает
чужому сайту домен нашего сайта при переходе по внешней ссылке, `same-origin`
не сообщает ничего. `SECURE_REFERRER_POLICY` в Django при этом был мёртвой
настройкой — стоял в коде, но не действовал.

У `X-Content-Type-Options` конфликта значений не было (`nosniff` с обеих
сторон) — только дублирование строки, шум без вреда.

## Решение

**Владелец обоих заголовков — Django.** Значения — `SECURE_REFERRER_POLICY = 'same-origin'`
и `SECURE_CONTENT_TYPE_NOSNIFF = True` в `config/settings_production.py`
(правку в Django не потребовалось — там уже стояли нужные значения, просто
раньше они реально не доходили до браузера из-за nginx-дубля).

Строки `add_header Referrer-Policy strict-origin-when-cross-origin always;`
и `add_header X-Content-Type-Options nosniff always;` убраны из
`deploy/nginx/available/django.conf` и его активной копии
`deploy/nginx/conf.d/weconomics.conf`. На их месте — комментарий с причиной,
общий с X-Frame-Options (все три заголовка объяснены одним блоком, так как
довод один и тот же).

## Почему Django, а не nginx

Те же четыре довода, что в ADR 0013, плюс один специфичный для
`Referrer-Policy`:

1. **Довод «nginx прикроет статику и media» не работает** — доказано в
   ADR 0013 тем же замером: у `location /static/` и `/media/` свои
   `add_header`, серверные заголовки туда не доходят в любом случае.
2. **`same-origin` — осознанно выбранная политика**, задокументированная в
   `config/settings_production.py`: «чужой сайт не узнает из заголовка
   Referer, с какой именно нашей страницы ушёл человек — только то, что с
   нашего домена». nginx-значение эту политику молча ослабляло.
3. **Django-значения под тестом.** `test_content_type_nosniff` и
   `test_referrer_policy` в `problems/tests/test_production_settings.py`
   держат оба значения. У строк в nginx не было ни теста, ни проверки.
4. **Порядок конфликта делает дубль хуже, чем у X-Frame-Options.** Там
   браузер сам подстраховывал строгим значением; здесь — наоборот, тихо
   действовало более слабое. Молчаливое ослабление политики — худший вид
   дубля: выглядит настроенным, а на деле не работает.

### Что отвергнуто

- **Назначить владельцем nginx.** Пришлось бы либо принять более слабую
  политику `Referrer-Policy` как окончательную, либо переносить туда же
  логику из `config/settings_production.py` — дублирование источника
  правды вместо заголовка.
- **Оставить только `Referrer-Policy` как есть, раз уже «так работало».**
  То, что работало, — это НЕ решение владельца, а случайный порядок
  `add_header` в файле. Опереться на порядок строк как на политику
  безопасности — то же самое везение, что и с X-Frame-Options до ADR 0013.

## Что это меняет на живом сайте

**Referrer-Policy реально становится строже** — было `strict-origin-when-cross-origin`
де-факто, станет `same-origin`. Единственное наблюдаемое отличие: переходы
по ссылкам с сайта на внешние ресурсы (например, CDN-документация, внешние
статьи) перестанут получать в заголовке `Referer` даже голый домен
`weconomics.site` — это ожидаемо и есть цель правки, не побочный эффект.
`X-Content-Type-Options` не меняется по значению, только по числу копий в
ответе.

Вступает в силу только после переноса конфига на сервер и перезагрузки
nginx — порядок в [docs/SERVER.md](../SERVER.md).

### Проверка после выкатки

```bash
# Обе строки — РОВНО по одной.
curl -sI https://weconomics.site/ | grep -ciE '^(x-content-type-options|referrer-policy):'   # 2 (по одной каждая)
curl -sI https://weconomics.site/ | grep -iE  '^(x-content-type-options|referrer-policy):'
# x-content-type-options: nosniff
# referrer-policy: same-origin
```
