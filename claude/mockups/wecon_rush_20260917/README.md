# Макеты и спецификации редизайна Wecon Rush — 17.09.2026

Папка кладётся в репозиторий: `claude/mockups/wecon_rush_20260917/`. Это единственный способ показать
Claude Code макеты (браузер и холст ему недоступны).

## Что здесь
- `*.dc.html` — 35 досок холста «Wecon Rush — экраны, концепция» (снимок 17.09.2026, **с ручными
  правками владельца**: вкладка «Статистика», сердца крупнее, блок «Где ошиблись»).
- `canvas.json` — раскладка холста: названия досок (`title`) и подписи рядов (`notes`) — читай их,
  в названиях сказано, какое состояние показано и какие данные условные.
- `SPEC/P1…P8_*.md` — спецификации фаз единого прогона. Лаунчер-промпт (его вставляет владелец)
  говорит, в каком порядке их читать. **Читай файл фазы только когда дошёл до неё.**

## Как читать `.dc.html`
Это статичная спецификация, а не код для копирования в проект:
- внутри `<x-dc>` — разметка экрана; в `<helmet><style>` — все стили (кегли, отступы, радиусы, тени);
- `{{имя}}` — подстановка значения из `renderVals()` в `<script data-dc-script>` внизу файла;
  `<sc-if value="{{флаг}}">` — блок показывается при истинном флаге; `<sc-for list="{{список}}"
  as="x">` — повтор; `<dc-import name="Main" who="student">` — та же доска `Main.dc.html` с другими
  параметрами (так сделаны `Student`, `Dark`, `RoundWrong`, `RoundClassic`, `RoundRapid`,
  `RoundStart`, `RoundDuel`, `DuelLobbyReady`, `PracticeMany`);
- `data-props` на теге скрипта — переключатели состояния (who, state, theme, mode, many…): пройдись
  по их значениям, чтобы увидеть все состояния экрана;
- данные в `renderVals()` — пример наполнения. Комментарии там говорят, что настоящее (с боя), а что
  условное. Логика в `renderVals()` — иллюстрация поведения, серверную логику бери из спецификации.
- Цвета в макетах заданы CSS-переменными в `.rush { … }` — это копия `templates/_tokens.html`.
  В коде проекта используй `var(--…)` из `_tokens.html`, не хексы; недостающие токены (`--skip`,
  `--green-tint`, `--error-tint`, `--accent-ring` и т. п.) заводи в `_tokens.html` для обеих тем.

## Доски по экранам
| Экран | Доски | Фаза |
|---|---|---|
| Главная | Main, Student, Dark, Mobile | P1 |
| Раунд | Round, RoundWrong, RoundClassic, RoundRapid, RoundStart, RoundDuel, RoundMobile | P2 |
| Служебные окна раунда | DialogQuit, DialogQuitSet, DialogLost, DialogOffline | P2 |
| Итог раунда | Result, ResultMobile | P3 |
| Дуэль | DuelCreate, DuelInvite, DuelLobby, DuelLobbyReady, DuelResult | P3 |
| Вызов дня | Daily, DailyBoard, DailyMobile | P4 |
| Бесконечные тесты | Practice, PracticeMany, PracticeResult, PracticeMobile | P5 |
| Страница набора (ученик) | SetPage | P6 |
| Результат по ссылке | ResultPublicMobile, ResultPublic | P6 |
| Кабинет учителя: наборы | TeacherSets, TeacherSetBuilder, TeacherSetDetail | P7 |
