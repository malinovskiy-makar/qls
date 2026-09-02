/* Числа тревоги — вырезаем функции ПРЯМО ИЗ game.html и считаем ими.

   Почему из шаблона, а не копией здесь: копия разъедется с боевым кодом
   при первой же правке порога, и тест начнёт сторожить сам себя. Здесь
   проверяется ровно та арифметика, по которой краснеет экран.

   Запуск отдельно: node game/tests/alarm_check.mjs                       */
import fs from 'node:fs';

const src = fs.readFileSync('game/templates/game/game.html', 'utf8');

/* Вырезаем константы и три функции по именам. */
function grab(re, what) {
  const m = src.match(re);
  if (!m) throw new Error('не найдено в game.html: ' + what);
  return m[0];
}

const code = [
  grab(/var ALARM_TIME_SHARE = [\d.]+;/, 'ALARM_TIME_SHARE'),
  grab(/var ALARM_LAST_LIFE = [\d.]+;/, 'ALARM_LAST_LIFE'),
  grab(/var ALARM_BPM_MIN = \d+;/, 'ALARM_BPM_MIN'),
  grab(/var ALARM_BPM_MAX = \d+;/, 'ALARM_BPM_MAX'),
  grab(/function alarmByTime\(timeLeft, duration\) \{[\s\S]*?\n  \}/, 'alarmByTime'),
  grab(/function alarmLevel\(timeLeft, duration, lives\) \{[\s\S]*?\n  \}/, 'alarmLevel'),
  grab(/function alarmBpm\(timeLeft, duration\) \{[\s\S]*?\n  \}/, 'alarmBpm'),
  'return { alarmLevel, alarmBpm, ALARM_LAST_LIFE };',
].join('\n');

/* ⚠️ `new Function` здесь безопасен и намеренен: на вход идёт СОБСТВЕННЫЙ
   исходник репозитория (`game/templates/game/game.html`), вырезанный
   регулярками по именам конкретных функций, а не что-либо пришедшее
   снаружи. Скрипт тестовый и в браузер не попадает. Смысл именно в этом:
   считать боевой арифметикой, а не её копией. */
const { alarmLevel, alarmBpm, ALARM_LAST_LIFE } = new Function(code)();

const fails = [];
function eq(got, want, what) {
  if (Math.abs(got - want) > 1e-9) {
    fails.push(`${what}: получено ${got}, ожидалось ${want}`);
  }
}

// ── Три контрольные точки задания: Классика, запас 120 с, окно 10 % = 12 с.
eq(alarmLevel(12, 120, 3), 0, '12 с из 120, жизней 3');
eq(alarmLevel(6, 120, 3), 0.5, '6 с из 120, жизней 3');
eq(alarmLevel(0, 120, 3), 1, '0 с из 120, жизней 3');

// ── Тревога не начинается раньше окна и не переваливает за единицу.
eq(alarmLevel(120, 120, 3), 0, 'полный запас');
eq(alarmLevel(12.01, 120, 3), 0, 'на волосок до окна');
eq(alarmLevel(-5, 120, 3), 1, 'время ушло в минус');

// ── Последняя жизнь без нехватки времени — постоянная 0,35.
//    ⚠️ Сверяем с ЧИСЛОМ ИЗ ЗАДАНИЯ, а не с ALARM_LAST_LIFE из того же файла:
//    сравнение константы с самой собой прошло бы при любом её значении.
eq(alarmLevel(120, 120, 1), 0.35, 'последняя жизнь, времени полно');
eq(ALARM_LAST_LIFE, 0.35, 'сама константа последней жизни');
eq(alarmLevel(6, 120, 1), 0.5, 'последняя жизнь И время на исходе: берём большее');

// ── Окно считается от ЗАПАСА РЕЖИМА, а не от абсолютных секунд.
//    Пуля: 60 с запаса → окно 6 с.
eq(alarmLevel(6, 60, 3), 0, 'Пуля: 6 с из 60 — окно только начинается');
eq(alarmLevel(3, 60, 3), 0.5, 'Пуля: 3 с из 60');

// ── Темп ведёт ТОЛЬКО время: последняя жизнь оставляет спокойные 70.
eq(alarmBpm(120, 120), 70, 'темп при полном запасе');
eq(alarmBpm(6, 120), 100, 'темп на половине окна');
eq(alarmBpm(0, 120), 130, 'темп в конце');

if (fails.length) {
  console.error('ПАДЕНИЯ:\n  ' + fails.join('\n  '));
  process.exit(1);
}
console.log('ok: проверок ' + 15);
