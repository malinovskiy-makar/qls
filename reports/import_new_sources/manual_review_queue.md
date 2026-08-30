# Очередь ручного разбора — три новых источника

Собрано командой `new_sources_manual_queue` (только чтение).
Сюда попадает то, что автоматика чинить НЕ должна: у одних задач
нет исходного материала (картинки), у других дефект в самом
материале. **Автоматической правки по этому списку нет и быть
не должно.**

## Сводка

| Раздел | Задач |
|---|---:|
| Отказы шлюза рендера | 440 |
| Ссылка на картинку без файла | 305 |
| `plain` с маркером картинки — не публиковать | 12 |
| ЛЭШ без решения | 40 |
| **Всего строк очереди** | **797** |

⚠️ Одна задача может попасть в несколько разделов — это строки очереди, а не уникальные задачи.

## Отказы шлюза рендера — 440

### `R-CMD` — 330

| id | источник | что увидел шлюз |
|---|---|---|
| 53735 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 53748 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 53832 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 53847 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 53866 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 53906 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 53932 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 53942 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 53946 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics |
| 53947 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 53949 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 53956 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 53959 | shkolkovo | Часть б: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 53963 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 53965 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 53967 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth, \textsuperscript |
| 53968 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 53969 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 53976 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 53979 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 53986 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 53988 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 53999 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54014 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54028 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54037 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \parbox, \textwidth |
| 54043 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54044 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54049 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54055 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54067 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54076 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54078 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54081 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54082 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54091 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54094 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54096 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54101 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54106 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54109 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54110 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54113 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54114 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54115 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54123 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \textbackslash |
| 54156 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54160 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54171 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54180 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54189 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54195 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54213 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54217 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54247 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54249 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54251 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54253 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54255 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54263 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54273 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54274 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54281 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54282 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54284 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54285 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54289 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54292 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54294 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54298 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54302 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54306 | shkolkovo | Часть в: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54310 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54314 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54327 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54335 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54342 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54347 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54349 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54350 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54352 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54354 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54355 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54356 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54357 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54358 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54361 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54362 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54367 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54371 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54373 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54375 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54381 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54384 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54390 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54392 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54393 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54399 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \textit |
| 54401 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54402 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54404 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \textit |
| 54405 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54409 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54419 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54423 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54426 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54429 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \textgreater, \textless |
| 54438 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54439 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54447 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54449 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54451 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54482 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54497 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54512 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54514 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54523 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54542 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54544 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54569 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54587 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54605 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54628 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54629 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54631 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54652 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54653 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54655 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54676 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54677 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54679 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54700 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54702 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54718 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54729 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54736 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54747 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54754 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54765 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54772 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54774 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54775 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54796 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54797 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54798 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54799 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54820 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54821 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54822 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54823 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54847 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54871 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54895 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54917 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54918 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54919 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54941 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54942 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54943 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54967 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54990 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54992 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55013 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55037 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55061 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55085 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55098 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55109 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55110 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55111 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55125 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55134 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55136 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55144 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55154 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55155 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \frac |
| 55182 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55184 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55191 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55200 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55206 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55207 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55208 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55210 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55269 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \pi |
| 55322 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \pi |
| 55328 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55370 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55407 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55440 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55442 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55477 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55479 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55484 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \Pi |
| 55502 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \Rightarrow |
| 55516 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55518 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55519 | shkolkovo | Часть а: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55524 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \pi |
| 55554 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55556 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55614 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55623 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \text |
| 55681 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55684 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55686 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55688 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55689 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55690 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55691 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55693 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55695 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55720 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55727 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55728 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55729 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55730 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55731 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55753 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55754 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55755 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55759 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55765 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55766 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55769 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55770 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55775 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55777 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55778 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55781 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55782 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55800 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55802 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55803 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55817 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55819 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55827 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55832 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55833 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55834 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55847 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55848 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55850 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55852 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55854 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55856 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55858 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55860 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55875 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55876 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55879 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55880 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55923 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55925 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55927 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55928 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55930 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 55984 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56066 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56082 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \text |
| 56093 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \text |
| 56103 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56104 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56117 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56144 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \approx, \frac, \pi |
| 56146 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56168 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56178 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56183 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56302 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56314 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56321 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56323 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56326 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56327 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56330 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56332 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56339 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56361 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56481 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 56491 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 56518 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56529 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56580 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56581 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56587 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 56612 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 56614 | shkolkovo | Ответ: уцелевшие TeX-команды в видимом тексте: \text |
| 56615 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 56623 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 56627 | shkolkovo | Часть в: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 56652 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 56743 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 56744 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 56746 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 56861 | shkolkovo | Условие: сырой LaTeX в видимом тексте: \[ |
| 57020 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 57029 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 57033 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 57037 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 57051 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 57098 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 57099 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 57101 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 57107 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 57123 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 57124 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \linewidth |
| 57567 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \quad |
| 57779 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \pi |
| 57891 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \frac |
| 58061 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \frac |
| 58167 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \cdot, \frac, \quad |
| 58212 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \Rightarrow, \frac, \quad, \sqrt, \text |
| 58875 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \cdot, \frac |
| 58944 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \frac, \left, \right |
| 59347 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \Pi, \quad |
| 59362 | solvehub | Условие: уцелевшие TeX-команды в видимом тексте: \cdot |
| 59815 | solvehub | Ответ: уцелевшие TeX-команды в видимом тексте: \frac |
| 60589 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \quad |
| 60760 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \frac |
| 61234 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \frac |
| 61240 | solvehub | Условие: уцелевшие TeX-команды в видимом тексте: \leq |
| 61299 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \approx, \frac, \left, \right, \text |
| 61318 | solvehub | Условие: уцелевшие TeX-команды в видимом тексте: \cdot |
| 61649 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \frac, \pi |
| 62626 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \cdot, \quad |
| 62811 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \cdot |
| 62992 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \Leftrightarrow, \frac, \quad, \text |
| 63020 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \leq, \quad |
| 63228 | solvehub | Условие: уцелевшие TeX-команды в видимом тексте: \beta |

### `K-ERR` — 26

| id | источник | что увидел шлюз |
|---|---|---|
| 53763 | shkolkovo | Решение: KaTeX parse error в 1 формул(ах): KaTeX parse error: Invalid delimiter type 'ordgroup' at position 10: AC'=\bigg{̲(̲}̲\frac{TC(Q)}{Q}… |
| 53768 | shkolkovo | Решение: KaTeX parse error в 1 формул(ах): KaTeX parse error: Invalid delimiter type 'ordgroup' at position 10: AC'=\bigg{̲(̲}̲\frac{TC(Q)}{Q}… |
| 54034 | shkolkovo | Решение: KaTeX parse error в 2 формул(ах): KaTeX parse error: Expected & or \\ or \cr or \end at end of input: … G + d\Delta G,; KaTeX parse error: Expected 'EO |
| 56483 | shkolkovo | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: No such environment: tabular at position 35: …\|c\|c\|c\|} \begin{̲t̲a̲b̲u̲l̲a̲r̲}̲{lllll}\textbf{… |
| 56484 | shkolkovo | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: No such environment: tabular at position 29: …}{\|c\|c\|} \begin{̲t̲a̲b̲u̲l̲a̲r̲}̲{ll}\textbf{\te… |
| 57371 | solvehub | Решение: KaTeX parse error в 3 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 100: …2X) = 273000 \\$̲; KaTeX parse error: Can't  |
| 57435 | solvehub | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲  |
| 57647 | solvehub | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: Expected group after '_' at position 53: …1 will be a(n) _̲__  |
| 57824 | solvehub | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲ |
| 57971 | solvehub | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲ |
| 58268 | solvehub | Решение: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 148: …Y^2 + 1296Y. \\$̲  |
| 58312 | solvehub | Часть б: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 4: 250$̲, \text{а турис… |
| 58424 | solvehub | Часть а: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲  |
| 59577 | solvehub | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲  |
| 59840 | solvehub | Часть а: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲  |
| 60453 | solvehub | Часть а: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲  |
| 60705 | solvehub | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲ |
| 60839 | solvehub | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲  |
| 61010 | solvehub | Решение: KaTeX parse error в 6 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲   **\text{Утве…; KaTeX parse error: Can't  |
| 61611 | solvehub | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲    |
| 61719 | solvehub | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 4: 200$̲  \text{и были … |
| 62149 | solvehub | Решение: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲ ***\text{Крите… |
| 62363 | solvehub | Часть а: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲ |
| 62738 | solvehub | Условие: KaTeX parse error в 3 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 79: … \text{потом }B$̲ ).  2) \text{В…; KaTeX pars |
| 63081 | solvehub | Часть а: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲  |
| 63297 | lesh | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: No such environment: tabular at position 7: \begin{̲t̲a̲b̲u̲l̲a̲r̲}̲{\|c\|c\|c\|c\|} \hl… |

### `R-CMD+R-ENV` — 18

| id | источник | что увидел шлюз |
|---|---|---|
| 53966 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \end, \item |
| 54016 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \cline, \end, \hline, \includegraphics, \multicolumn, \textwidth |
| 54022 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \end, \hline, \multicolumn |
| 54040 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \end, \hline |
| 54159 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \end |
| 54510 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \end, \item |
| 55088 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \end, \hline, \multicolumn |
| 55853 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \end, \hline, \multicolumn |
| 55953 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \end, \hline, \multicolumn |
| 56068 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \cline, \end, \hline, \multicolumn |
| 56169 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \end, \hline, \multicolumn |
| 56223 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \end, \hline, \multicolumn |
| 56264 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \end, \hline, \multicolumn |
| 56338 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \end, \hline |
| 62797 | solvehub | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \end, \text, \textcolor |
| 63260 | lesh | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \end, \hline |
| 63293 | lesh | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \end |
| 63309 | lesh | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \end |

### `K-STRICT` — 16

| id | источник | что увидел шлюз |
|---|---|---|
| 53891 | shkolkovo | Решение: strict-предупреждения KaTeX: newLineInDisplayMode |
| 56557 | shkolkovo | Условие: strict-предупреждения KaTeX: unknownSymbol |
| 57641 | solvehub | Условие: strict-предупреждения KaTeX: commentAtEnd |
| 58277 | solvehub | Условие: strict-предупреждения KaTeX: mathVsTextAccents |
| 58395 | solvehub | Условие: strict-предупреждения KaTeX: unknownSymbol |
| 58738 | solvehub | Условие: strict-предупреждения KaTeX: mathVsTextAccents |
| 58852 | solvehub | Условие: strict-предупреждения KaTeX: unknownSymbol |
| 59716 | solvehub | Условие: strict-предупреждения KaTeX: commentAtEnd |
| 60452 | solvehub | Условие: strict-предупреждения KaTeX: commentAtEnd |
| 61181 | solvehub | Условие: strict-предупреждения KaTeX: commentAtEnd |
| 62122 | solvehub | Условие: strict-предупреждения KaTeX: commentAtEnd |
| 62643 | solvehub | Условие: strict-предупреждения KaTeX: unknownSymbol |
| 62750 | solvehub | Условие: strict-предупреждения KaTeX: unknownSymbol |
| 62758 | solvehub | Решение: strict-предупреждения KaTeX: commentAtEnd |
| 63063 | solvehub | Решение: strict-предупреждения KaTeX: commentAtEnd |
| 63119 | solvehub | Условие: strict-предупреждения KaTeX: commentAtEnd |

### `PLOT+R-CMD` — 15

| id | источник | что увидел шлюз |
|---|---|---|
| 53726 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \draw, \end, \node |
| 53727 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \draw, \end, \node |
| 53728 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \draw, \end, \node |
| 53729 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \draw, \end |
| 53844 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \addlegendentry, \addplot, \begin, \end |
| 53948 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \coordinate, \draw, \end, \fill, \node, \small |
| 53974 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \draw, \end, \foreach |
| 54004 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \draw, \end, \fill, \node |
| 54052 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \coordinate, \draw, \end, \fill, \node |
| 54060 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \draw, \end, \includegraphics, \node, \textwidth |
| 56480 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \draw, \end, \fill, \node |
| 56538 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \coordinate, \draw, \end, \fill, \node |
| 56611 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \Nvalue, \Yequal, \Yintercept, \Ykink, \Zintercept, \Zkink, \begin, \coordinate |
| 56638 | shkolkovo | Решение: уцелевшие TeX-команды в видимом тексте: \begin, \clip, \coordinate, \draw, \end, \fill, \node, \small |
| 63300 | lesh | Условие: уцелевшие TeX-команды в видимом тексте: \begin, \bfseries, \coordinate, \draw, \end, \filldraw, \foreach, \large |

### `K-ERR+R-CMD` — 8

| id | источник | что увидел шлюз |
|---|---|---|
| 57299 | solvehub | Решение: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 44: …} = f(y) = 0 \\$̲   \text{При } |
| 59168 | solvehub | Условие: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 3: \\$̲  |
| 59370 | solvehub | Решение: KaTeX parse error в 2 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 198: …n(1-\theta)} \\$̲   ; KaTeX parse error: Can |
| 59440 | solvehub | Условие: KaTeX parse error в 4 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 31: …x + 6) \, dx \\$̲   ; KaTeX parse error: Can' |
| 59687 | solvehub | Решение: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 147: …{5} = 20{,}1 \\$̲ |
| 62556 | solvehub | Решение: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 74: …- 100)^2}{4} \\$̲  |
| 62721 | solvehub | Решение: KaTeX parse error в 4 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 43: …> AVC_1 \iff \\$̲ ; KaTeX parse error: Can't  |
| 62939 | solvehub | Решение: KaTeX parse error в 1 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 34: … 800(Z + 40) \\$̲  |

### `EMPTY` — 7

| id | источник | что увидел шлюз |
|---|---|---|
| 57587 | solvehub | непустой исходный блок стал пустым на экране: ['Ответ'] |
| 57778 | solvehub | непустой исходный блок стал пустым на экране: ['Ответ'] |
| 58542 | solvehub | непустой исходный блок стал пустым на экране: ['Ответ'] |
| 58759 | solvehub | непустой исходный блок стал пустым на экране: ['Ответ'] |
| 60645 | solvehub | непустой исходный блок стал пустым на экране: ['Ответ'] |
| 61786 | solvehub | непустой исходный блок стал пустым на экране: ['Ответ'] |
| 63082 | solvehub | непустой исходный блок стал пустым на экране: ['Ответ'] |

### `ENV-BAL+R-CMD+R-ENV` — 6

| id | источник | что увидел шлюз |
|---|---|---|
| 53714 | shkolkovo | Решение: незакрытые [], лишние \end ['document'] |
| 54343 | shkolkovo | Условие: незакрытые ['tabular'], лишние \end [] |
| 54351 | shkolkovo | Условие: незакрытые ['tabular'], лишние \end [] |
| 54359 | shkolkovo | Условие: незакрытые ['tabular'], лишние \end [] |
| 63247 | lesh | Часть 1: незакрытые ['enumerate'], лишние \end [] |
| 63255 | lesh | Часть 1: незакрытые ['itemize'], лишние \end [] |

### `MACRO+R-CMD` — 6

| id | источник | что увидел шлюз |
|---|---|---|
| 54290 | shkolkovo | Условие: уцелевшие TeX-команды в видимом тексте: \includegraphics, \textwidth |
| 54293 | shkolkovo | Решение: неизвестные макросы: \eqno |
| 54388 | shkolkovo | Решение: неизвестные макросы: \eqno |
| 54389 | shkolkovo | Решение: неизвестные макросы: \eqno |
| 54396 | shkolkovo | Решение: неизвестные макросы: \label |
| 54398 | shkolkovo | Решение: неизвестные макросы: \eqno |

### `MACRO` — 3

| id | источник | что увидел шлюз |
|---|---|---|
| 54278 | shkolkovo | Решение: неизвестные макросы: \eqno |
| 55367 | shkolkovo | Решение: неизвестные макросы: \hfill |
| 55371 | shkolkovo | Решение: неизвестные макросы: \hfill |

### `K-TEXT` — 2

| id | источник | что увидел шлюз |
|---|---|---|
| 62154 | solvehub | Условие: текст/Unicode в math mode: 597 случ. (пример:   млрд. в год). Вступление в ВТО добровольное. Почему страны добровольно вступаю) |
| 62384 | solvehub | Решение: текст/Unicode в math mode: 17 случ. (пример: Рн) |

### `K-ERR+K-TEXT+R-CMD+R-ENV` — 1

| id | источник | что увидел шлюз |
|---|---|---|
| 59378 | solvehub | Решение: KaTeX parse error в 3 формул(ах): KaTeX parse error: Can't use function '$' in math mode at position 121: … \end{cases} \\$̲ Аналогично мож…; KaTeX par |

### `K-TEXT+R-CMD` — 1

| id | источник | что увидел шлюз |
|---|---|---|
| 60620 | solvehub | Решение: текст/Unicode в math mode: 50 случ. (пример:  т.е. ) |

### `K-STRICT+R-CMD` — 1

| id | источник | что увидел шлюз |
|---|---|---|
| 60676 | solvehub | Условие: strict-предупреждения KaTeX: commentAtEnd |


## Ссылка на картинку без файла — 305

Ссылка осталась в тексте ЦЕЛОЙ и видна на экране — это сделано намеренно. Маркер `[[FIGURE:…]]` без строки `ProblemFigure` на экране просто исчезает, то есть картинка пропала бы молча.

Для Школково файлов нет в принципе: `QuestionFiles` пуст у всех 3 414 записей выгрузки, а 453 скачанные картинки принадлежат 328 другим задачам (пересечение идентификаторов — ноль). Нужна повторная выгрузка картинок с сайта источника по этим id.

| id | источник | ссылка в тексте |
|---|---|---|
| 57606 | SolveHub | `https://iloveeconomics.ru/system/files/images/u36249/ravenstvoibratstv` |
| 58066 | SolveHub | `data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAeQAAAB7CAYAAACl6fPbAAAA` |
| 60157 | SolveHub | `data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAATMAAACFCAIAAAC43ojVAAAX` |
| 60493 | SolveHub | `https://iloveeconomics.ru/sites/default/files/u80/Graph.jpg` |
| 60699 | SolveHub | `https://iloveeconomics.ru/system/files/images/u38969/bezymyannyy71-ilo, https://iloveeconomics.ru/system/files/images/u38969/bezymyannyy73-ilo` |
| 61116 | SolveHub | `https://iloveeconomics.ru/system/files/images/u40523/4-iloveeconomics.` |
| 61176 | SolveHub | `data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAX0AAAE2CAYAAACN5kL+AAAA` |
| 53735 | Школково | `ela.png` |
| 53748 | Школково | `eq.png` |
| 53832 | Школково | `graph_04_1.png` |
| 53847 | Школково | `graph_03_1.png` |
| 53866 | Школково | `ааа.png` |
| 53906 | Школково | `fer.png` |
| 53932 | Школково | `ggg-2.png` |
| 53942 | Школково | `ccc.jpg` |
| 53946 | Школково | `111.png, 222.png, 333.png` |
| 53947 | Школково | `tg_image_3713616615.png, tg_image_3904720575.png` |
| 53949 | Школково | `gr1.png, gr2.png` |
| 53956 | Школково | `hg.png` |
| 53959 | Школково | `ааа.jpg` |
| 53963 | Школково | `Снимок экрана 2026-01-31 230031.png, Снимок экрана 2026-01-31 230155.png, изображение_2026-01-31_225606885.png` |
| 53965 | Школково | `gt1.png, gt2.png` |
| 53967 | Школково | `gh1.png` |
| 53968 | Школково | `изображение_2026-01-31_230537512.png` |
| 53969 | Школково | `Снимок экрана 2026-02-01 013805.png` |
| 53976 | Школково | `изображение_2026-02-03_195419726.png` |
| 53979 | Школково | `изображение_2026-02-03_223028560.png, изображение_2026-02-03_223259251.png, изображение_2026-02-03_223523919.png` |
| 53986 | Школково | `изображение_2026-02-03_225758918.png` |
| 53988 | Школково | `изображение_2026-02-03_231827344.png` |
| 53999 | Школково | `изображение_2026-02-04_150600125.png` |
| 54014 | Школково | `изображение_2026-02-04_205353060.png, изображение_2026-02-04_205922338.png` |
| 54016 | Школково | `изображение_2026-02-04_210109630.png` |
| 54028 | Школково | `изображение_2026-02-04_204034851.png, изображение_2026-02-04_204237225.png` |
| 54043 | Школково | `изображение_2026-03-22_012735622.png, изображение_2026-03-22_012918941.png, изображение_2026-03-22_012959827` |
| 54044 | Школково | `изображение_2026-03-22_014728172.png` |
| 54049 | Школково | `изображение_2026-03-22_025615869.png, изображение_2026-03-22_025652006.png, изображение_2026-03-22_025753031.png` |
| 54055 | Школково | `Снимок экрана 2026-02-21 104530.png` |
| 54060 | Школково | `изображение_2026-02-21_110204887.png, изображение_2026-02-21_110344090.png` |
| 54067 | Школково | `изображение_2026-02-21_113334413.png` |
| 54076 | Школково | `изображение_2026-02-21_115039817.png` |
| 54078 | Школково | `изображение_2026-02-21_115339256.png` |
| 54081 | Школково | `изображение_2026-02-21_131947056.png` |
| 54082 | Школково | `Снимок экрана 2026-02-21 132219.png` |
| 54091 | Школково | `изображение_2026-02-21_133950053.png` |
| 54094 | Школково | `изображение_2026-02-21_141754041.png` |
| 54096 | Школково | `изображение_2026-02-21_142616858.png, изображение_2026-02-21_142726595.png, изображение_2026-02-21_143029141.png` |
| 54101 | Школково | `изображение_2026-02-21_143950385.png, изображение_2026-02-21_144313424.png` |
| 54106 | Школково | `изображение_2026-02-21_192324230.png, изображение_2026-02-21_192434580.png` |
| 54109 | Школково | `изображение_2026-02-21_193357631.png` |
| 54110 | Школково | `Снимок экрана 2026-02-21 192322.png, Снимок экрана 2026-02-21 192409.png` |
| 54113 | Школково | `Снимок экрана 2026-02-21 193345.png` |
| 54114 | Школково | `изображение_2026-02-23_214408902.png` |
| 54115 | Школково | `Снимок экрана 2026-02-23 214639.png` |
| 54156 | Школково | `изображение_2026-02-26_130354828.png` |
| 54160 | Школково | `изображение_2026-02-26_131146430.png` |
| 54171 | Школково | `изображение_2026-02-27_215252957.png` |
| 54180 | Школково | `изображение_2026-02-27_220416335.png` |
| 54189 | Школково | `Снимок экрана 2026-02-27 221301.png` |
| 54195 | Школково | `изображение_2026-02-27_222148803.png` |
| 54213 | Школково | `изображение_2026-02-27_224447576.png` |
| 54217 | Школково | `Снимок экрана 2026-02-27 224442.png` |
| 54247 | Школково | `1.png` |
| 54249 | Школково | `2.png` |
| 54251 | Школково | `3.png, 4.png, 5.png` |
| 54253 | Школково | `6.png` |
| 54255 | Школково | `7.png` |
| 54263 | Школково | `8.png` |
| 54273 | Школково | `1.png` |
| 54274 | Школково | `2.png` |
| 54281 | Школково | `3.png` |
| 54282 | Школково | `4.png` |
| 54284 | Школково | `5.png` |
| 54285 | Школково | `6.png, 7.png, 8.png` |
| 54289 | Школково | `9.png` |
| 54290 | Школково | `10.png` |
| 54292 | Школково | `11.png` |
| 54293 | Школково | `14.png` |
| 54294 | Школково | `15.png` |
| 54298 | Школково | `16.png, 17.png` |
| 54302 | Школково | `18.png` |
| 54306 | Школково | `19.png, 20.png` |
| 54310 | Школково | `21.png` |
| 54314 | Школково | `22.png, 23.png` |
| 54327 | Школково | `24.png` |
| 54335 | Школково | `25.png` |
| 54342 | Школково | `26.png` |
| 54347 | Школково | `27.png` |
| 54349 | Школково | `28.png` |
| 54350 | Школково | `29.png` |
| 54352 | Школково | `31.png` |
| 54354 | Школково | `32.png` |
| 54355 | Школково | `33.png` |
| 54356 | Школково | `34.png` |
| 54357 | Школково | `35.png, 36.png` |
| 54358 | Школково | `37.png` |
| 54361 | Школково | `39.png` |
| 54362 | Школково | `40.png` |
| 54367 | Школково | `41.png` |
| 54371 | Школково | `42.png, 43.png, 44.png` |
| 54373 | Школково | `45.png, 46.png` |
| 54375 | Школково | `47.png` |
| 54381 | Школково | `48.png` |
| 54384 | Школково | `49.png, 50.png, 51.png` |
| 54388 | Школково | `52.png` |
| 54389 | Школково | `53.png, 54.png, 55.png` |
| 54390 | Школково | `57.png` |
| 54392 | Школково | `58.png` |
| 54393 | Школково | `59.png` |
| 54396 | Школково | `60.png` |
| 54398 | Школково | `61.png, 62.png` |
| 54401 | Школково | `63.png, 64.png` |
| 54402 | Школково | `65.png, 66.png` |
| 54405 | Школково | `67.png` |
| 54409 | Школково | `68.png, 69.png` |
| 54419 | Школково | `70.png, Снимок экрана 2026-04-02 102116.png` |
| 54423 | Школково | `71.png, 72.png` |
| 54426 | Школково | `Снимок экрана 2026-04-02 103449.png, Снимок экрана 2026-04-02 103520.png` |
| 54438 | Школково | `73.png, 74.png` |
| 54439 | Школково | `75.png, 76.png, 77.png` |
| 54447 | Школково | `78.png, 79.png` |
| 54449 | Школково | `80.png, 81.png` |
| 54451 | Школково | `82.png` |
| 54482 | Школково | `83.png` |
| 54497 | Школково | `84.png, 85.png` |
| 54512 | Школково | `6.png, 7.png` |
| 54514 | Школково | `image002_6.png` |
| 54523 | Школково | `Снимок экрана 2026-05-01 014732.png` |
| 54542 | Школково | `Снимок экрана 2026-05-01 014752.png` |
| 54544 | Школково | `Снимок экрана 2026-05-01 014803.png` |
| 54569 | Школково | `Снимок экрана 2026-05-03 121618.png, Снимок экрана 2026-05-03 121628.png` |
| 54587 | Школково | `Снимок экрана 2026-05-03 121618.png, Снимок экрана 2026-05-03 121628.png` |
| 54605 | Школково | `Снимок экрана 2026-05-03 121618.png, Снимок экрана 2026-05-03 121628.png` |
| 54628 | Школково | `Снимок экрана 2026-05-03 122124.png` |
| 54629 | Школково | `Снимок экрана 2026-05-03 122133.png` |
| 54631 | Школково | `Снимок экрана 2026-05-03 122144.png` |
| 54652 | Школково | `Снимок экрана 2026-05-03 122124.png` |
| 54653 | Школково | `Снимок экрана 2026-05-03 122133.png` |
| 54655 | Школково | `Снимок экрана 2026-05-03 122144.png` |
| 54676 | Школково | `Снимок экрана 2026-05-03 122124.png` |
| 54677 | Школково | `Снимок экрана 2026-05-03 122133.png` |
| 54679 | Школково | `Снимок экрана 2026-05-03 122144.png` |
| 54700 | Школково | `Снимок экрана 2026-05-01 014819.png` |
| 54702 | Школково | `Снимок экрана 2026-05-01 014830.png` |
| 54718 | Школково | `Снимок экрана 2026-05-03 121818.png` |
| 54729 | Школково | `Снимок экрана 2026-05-03 121843.png, Снимок экрана 2026-05-03 121903.png` |
| 54736 | Школково | `Снимок экрана 2026-05-03 121818.png` |
| 54747 | Школково | `Снимок экрана 2026-05-03 121843.png, Снимок экрана 2026-05-03 121903.png` |
| 54754 | Школково | `Снимок экрана 2026-05-03 121818.png` |
| 54765 | Школково | `Снимок экрана 2026-05-03 121843.png, Снимок экрана 2026-05-03 121903.png` |
| 54772 | Школково | `1.png` |
| 54774 | Школково | `2.png, 3.png` |
| 54775 | Школково | `4.png` |
| 54796 | Школково | `5.png` |
| 54797 | Школково | `6.png` |
| 54798 | Школково | `7.png, 8.png` |
| 54799 | Школково | `9.png` |
| 54820 | Школково | `10.png` |
| 54821 | Школково | `11.png` |
| 54822 | Школково | `12.png, 13.png` |
| 54823 | Школково | `14.png` |
| 54847 | Школково | `15.png, 16.png` |
| 54871 | Школково | `17.png, 18.png` |
| 54895 | Школково | `19.png, 20.png` |
| 54917 | Школково | `21.png, 22.png` |
| 54918 | Школково | `23.png` |
| 54919 | Школково | `24.png, 25.png, 26.png` |
| 54941 | Школково | `27.png, 28.png` |
| 54942 | Школково | `29.png` |
| 54943 | Школково | `30.png, 31.png, 32.png` |
| 54967 | Школково | `33.png, 34.png` |
| 54990 | Школково | `35.png, 36.png` |
| 54992 | Школково | `37.png` |
| 55013 | Школково | `38.png` |
| 55037 | Школково | `39.png` |
| 55061 | Школково | `40.png, 41.png` |
| 55085 | Школково | `42.png, 43.png, 44.png` |
| 55098 | Школково | `45.png` |
| 55109 | Школково | `46.png` |
| 55110 | Школково | `47.png` |
| 55111 | Школково | `48.png` |
| 55125 | Школково | `49.png` |
| 55134 | Школково | `50.png` |
| 55136 | Школково | `51.png, 52.png` |
| 55144 | Школково | `53.png` |
| 55154 | Школково | `54.png` |
| 55182 | Школково | `55.png` |
| 55184 | Школково | `56.png` |
| 55191 | Школково | `57.png` |
| 55200 | Школково | `58.png` |
| 55206 | Школково | `59.png` |
| 55207 | Школково | `60.png, 61.png` |
| 55208 | Школково | `62.png` |
| 55210 | Школково | `63.png, 64.png, 65.png` |
| 55328 | Школково | `69.png` |
| 55370 | Школково | `70.png` |
| 55407 | Школково | `71.png` |
| 55440 | Школково | `72.png, 73.png` |
| 55442 | Школково | `74.png, 75.png, 76.png` |
| 55477 | Школково | `77.png` |
| 55479 | Школково | `78.png, 79.png` |
| 55516 | Школково | `81.png, 82.png, 83.png` |
| 55518 | Школково | `Снимок экрана 2026-05-03 122352.png` |
| 55519 | Школково | `84.png, 85.png, 86.png` |
| 55554 | Школково | `92.png` |
| 55556 | Школково | `93.png, 94.png` |
| 55614 | Школково | `95.png, 96.png, 97.png` |
| 55681 | Школково | `1.png, 2.png` |
| 55684 | Школково | `3.png` |
| 55686 | Школково | `4.png, 5.png` |
| 55688 | Школково | `6.png` |
| 55689 | Школково | `7.png, изображение_2026-06-01_171216741.png` |
| 55690 | Школково | `8.png, 9.png` |
| 55691 | Школково | `10.png` |
| 55693 | Школково | `11.png, 12.png` |
| 55695 | Школково | `13.png, 14.png` |
| 55720 | Школково | `Снимок экрана 2026-06-01 170901.png` |
| 55727 | Школково | `15.png` |
| 55728 | Школково | `16.png, 17.png, 18.png` |
| 55729 | Школково | `19.png` |
| 55730 | Школково | `20.png` |
| 55731 | Школково | `21.png` |
| 55753 | Школково | `22.png` |
| 55754 | Школково | `23.png` |
| 55755 | Школково | `24.png` |
| 55759 | Школково | `25.png` |
| 55765 | Школково | `26.png` |
| 55766 | Школково | `27.png` |
| 55769 | Школково | `28.png` |
| 55770 | Школково | `29.png` |
| 55775 | Школково | `30.png` |
| 55777 | Школково | `31.png, 32.png` |
| 55778 | Школково | `33.png, 34.png` |
| 55781 | Школково | `35.png, 36.png` |
| 55782 | Школково | `37.png, 38.png` |
| 55800 | Школково | `39.png` |
| 55802 | Школково | `40.png` |
| 55803 | Школково | `41.png` |
| 55817 | Школково | `42.png` |
| 55819 | Школково | `43.png` |
| 55827 | Школково | `изображение_2026-06-01_171525349.png` |
| 55832 | Школково | `44.png, изображение_2026-06-01_171739247.png` |
| 55833 | Школково | `45.png, 46.png` |
| 55834 | Школково | `47.png, 48.png` |
| 55847 | Школково | `49.png` |
| 55848 | Школково | `50.png` |
| 55850 | Школково | `51.png` |
| 55852 | Школково | `52.png` |
| 55854 | Школково | `53.png` |
| 55856 | Школково | `54.png` |
| 55858 | Школково | `55.png` |
| 55860 | Школково | `56.png` |
| 55875 | Школково | `57.png` |
| 55876 | Школково | `изображение_2026-06-01_172433878.png` |
| 55879 | Школково | `58.png` |
| 55880 | Школково | `59.png, 60.png, 61.png` |
| 55923 | Школково | `73.png, 74.png` |
| 55925 | Школково | `75.png, 76.png` |
| 55927 | Школково | `77.png` |
| 55928 | Школково | `78.png, 79.png` |
| 55930 | Школково | `80.png, 81.png` |
| 55984 | Школково | `82.png, 83.png, 84.png` |
| 56066 | Школково | `изображение_2026-06-01_175303959.png, изображение_2026-06-01_175341122.png` |
| 56103 | Школково | `93.png` |
| 56104 | Школково | `Снимок экрана 2026-06-01 172806.png` |
| 56117 | Школково | `94.png` |
| 56146 | Школково | `95.png` |
| 56168 | Школково | `96.png` |
| 56178 | Школково | `100.png, 101.png, 103.png` |
| 56183 | Школково | `108.png` |
| 56302 | Школково | `110.png` |
| 56314 | Школково | `111.png` |
| 56321 | Школково | `112.png, 113.png, 114.png` |
| 56323 | Школково | `116.png` |
| 56326 | Школково | `117.png` |
| 56327 | Школково | `118.png, 119.png, 120.png` |
| 56330 | Школково | `122.png` |
| 56332 | Школково | `123.png, 124.png, 125.png` |
| 56339 | Школково | `Снимок экрана 2026-06-01 175915.png` |
| 56361 | Школково | `ppf_points_kpv.png` |
| 56481 | Школково | `grag.png` |
| 56491 | Школково | `ggg.png.jpg, решение.jpg` |
| 56518 | Школково | `graph8_1.png` |
| 56529 | Школково | `56.png` |
| 56580 | Школково | `изображение_2026-01-26_153920910.png` |
| 56581 | Школково | `Снимок экрана 2026-01-26 153916.png` |
| 56587 | Школково | `12.jpg` |
| 56612 | Школково | `dummy.png` |
| 56615 | Школково | `bbb.png` |
| 56623 | Школково | `ссс.png` |
| 56627 | Школково | `ddd.jpg` |
| 56652 | Школково | `evt.jpg, image-2.jpg` |
| 56743 | Школково | `hhh.png` |
| 56744 | Школково | `lll.png` |
| 56746 | Школково | `frg.png` |
| 57020 | Школково | `sin.png` |
| 57029 | Школково | `tin.png` |
| 57033 | Школково | `rio.png` |
| 57037 | Школково | `evt.png` |
| 57051 | Школково | `ri.png` |
| 57098 | Школково | `ppt.png` |
| 57099 | Школково | `tt.png` |
| 57101 | Школково | `uuu.png` |
| 57107 | Школково | `ll.png` |
| 57123 | Школково | `kk.png` |
| 57124 | Школково | `hh.png` |

## `plain` с маркером картинки — не публиковать — 12

Пока все они закрыты от учеников (`draft` + `hidden_pending_review`), поэтому дефекта на экране нет. Инвариант закреплён тестом `PlainFormatMarkerGuardTests`: он краснеет, если такую задачу опубликуют.

| id | где маркер | сколько |
|---|---|---|
| 57647 | условие ×1 | 1 |
| 59687 | условие ×1, решение ×1 | 2 |
| 60453 | решение ×1 | 1 |
| 60705 | решение ×1 | 1 |
| 60839 | решение ×1 | 1 |
| 61010 | условие ×2 | 2 |
| 61318 | решение ×4 | 4 |
| 62363 | решение ×1 | 1 |
| 62384 | решение ×1 | 1 |
| 62992 | решение ×1 | 1 |
| 63228 | условие ×1 | 1 |
| 63309 | решение ×1 | 1 |

## ЛЭШ без решения — 40

Подбор решения по смыслу запрещён — пары id↔id ставит человек.

| id | название | первые слова условия |
|---|---|---|
| 63251 | Кредитные возможности и денежный мультипликатор | Норма избыточных резервов коммерческого банка составляет 20\%, а его совокупные резервы ра |
| 63252 | Мультипликатор в Лосьлэндии | Когда-то в Лосьлэндии были деньги, но не было банков; деньгами жителям острова служили зна |
| 63253 | Выводим денежный мультипликатор | Пусть коммерческие банки хранят долю $rr$ от депозитов в качестве обязательных резервов и  |
| 63254 | Монетарная политика в Лосьлэндии | В Лосьлэндии совокупный спрос задаётся уравнением количественной теории денег, кривая крат |
| 63255 | Инфляционное таргетирование и управление ключевой ставкой | С конца 2014 года Банк России проводит политику инфляионного таргетирования, цель которой  |
| 63256 |  | Акция компании «Вектор» сегодня стоит 100 руб. Через год она будет стоить 180 руб., если н |
| 63257 |  | Завтра состоится матч «Динамо» — «Спартак». Возможны ровно три исхода: победа «Динамо», ни |
| 63258 |  | Обозначим $(x)^{+} = \max(x, 0)$. Годовой доход человека равен $X$. Налог берётся по ступе |
| 63259 |  | В этой задаче нет ни акций, ни опционов, но в каждом сюжете возникает та же конструкция: н |
| 63260 |  | Рассмотрите сбалансированный рынок, на котором торгуются три следующие облигации с определ |
| 63261 | Накопление госдолга: задача для обсуждения на паре | Государственный долг является типичным явлением для большой части стран. По данным на граф |
| 63262 | Остров Мадагаскар | В закрытой экономике острова Мадагаскар потребление зависит от располагаемого дохода следу |
| 63263 | Бюджетные правила | Рассмотрим закрытую экономику, в которой функция потребления имеет вид $C=80+0,75Y^d$, инв |
| 63264 | Фискальная политика в модели AD-AS | Рассмотрим открытую экономику, в которой инвестиции, государственные закупки, налоги и чис |
| 63265 | Парадокс сбережений, вербальные интервенции и государственны | Экономики многих развитых стран характеризуются высоким уровнем государственного долга. Ра |
| 63266 | Влияние фискальной политики на потребление | В этом задании мы обсудим, как на решения домохозяйств о потреблении может влиять фискальн |
| 63268 |  | Некоторый автоконцерн занимается производством двух типов автомобилей — на внутренний рыно |
| 63272 | Разминка | Найдите максимум функции $y(x)$ в зависимости от параметра $a$: |
| 63273 | О пользе проверки ограничения | На рынке с функцией спроса $Q_d = 1 - P$ конкурируют две фирмы с нулевыми издержками, посл |
| 63274 | Оценка | Решите несколько не связанных между собой задач: |
| 63275 | Оптимальная цена при неизвестном спросе | Некоторая фирма-монополист хотела бы установить цену, максимизирующую выручку, однако функ |
| 63276 | Лотерея Яши | Знойным летним днём школьник Яша увидел, что в его учебном заведении проводится лотерея. Д |
| 63277 | Разминка | КПВ страны $X$ имеет вид $$y=\begin{cases} 200-2x;x\le 20\\ 180-x;20\le x\le 60\\ 240-2x;6 |
| 63278 | КТВ и инфраструктура | Страна, обладающая ресурсами в размере 100 единиц труда, производит два товара — иксы $X$  |
| 63279 | Заминка |   |
| 63280 | Разминка | На рынке товара присутствуют всего 2 продавца. Функция издержек первого имеет вид $TC_1=10 |
| 63282 | Заминка | На рынке некоторого товара с функцией спроса $Q^d=120-P$ конкурирует бесконечное число фир |
| 63299 | Товар $X$ в городе $M$ | Улицы города $M$ имеют минималистичную структуру, изображённую на рисунке: [[FIGURE:847050 |
| 63300 | Города и дороги | Страна $X$ состоит из трёх городов: М, С и К. За последние годы страна существенно урбаниз |
| 63303 | Налог и две группы покупателей | Фирма-монополист продаёт товар двум группам покупателей и обязана назначать им единую цену |
| 63304 | Прогрессивный налог | На рынке действует фирма-монополист. Обратная функция спроса имеет вид $P=24-Q.$ Если фирм |
| 63305 | Яблоки не дешевле | В районе работает много небольших садовых хозяйств, продающих яблоки единственному перераб |
| 63306 | Средняя цена | Фирма-монополист продаёт один и тот же товар в двух городах. Перепродажа товара между горо |
| 63311 | Слишком дешёвая подписка | Единственный в городе онлайн-кинотеатр выбирает цену подписки $P$ и качество каталога $x\g |
| 63313 |  | Монополист продает два цифровых товара $A$ и $B$. Предельные издержки производства обоих т |
| 63317 |  | На осеннюю ярмарку приехали два садовода — Алиса и Борис. У Алисы с собой $8$ корзин яблок |
| 63318 |  | В маленькой экономике живут два жителя — Первый и Второй. Единственный ресурс, который у н |
| 63319 |  | В небольшом городке живут два жителя. У каждого есть по 10 единиц частного блага $x$. Жите |
| 63320 |  | В закрытой и очень независимой республике Дач производятся всего две группы товаров — сель |
| 63321 |  | Рассмотрим две страны — Северную (С) и Южную (Ю) К. Экономики обеих стран состоят только и |
