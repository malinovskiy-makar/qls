/* Звук Wecon Rush.

   СИНТЕЗ через Web Audio API, БЕЗ звуковых файлов. Довод тот же, по
   которому графики рисуются руками, а не библиотекой: нет мегабайтов, нет
   вопросов о лицензии — и, главное, высота тона верного ответа поднимается
   по ступеням комбо простой арифметикой, а не подбором двадцати сэмплов.

   Наружу торчит одна window.rushSound. Всё остальное — в замыкании.

   ⚠️ Звук нигде не единственный канал: всё, что он сообщает, видно
   глазами (сердца, полоса времени, цвет карточки). Выключенный звук не
   лишает игрока информации.

   ⚠️ Браузеры не дают запустить AudioContext до первого действия
   пользователя. Здесь это не проблема: первым действием и так является
   нажатие «Начать» — контекст создаётся лениво, в первом же вызове. */
(function () {
  'use strict';

  var KEY = 'econ_rush_sound';   // 'on' | 'off', по умолчанию включён
  var ctx = null;                // AudioContext, создаётся лениво
  var master = null;

  function enabled() {
    try { return localStorage.getItem(KEY) !== 'off'; }
    catch (e) { return true; }   // приватный режим — звук не выключаем
  }

  function setEnabled(on) {
    try { localStorage.setItem(KEY, on ? 'on' : 'off'); } catch (e) {}
    // ⚠️ Планировщик сердцебиения НЕ останавливаем: по его ударам
    // пульсируют виньетка и полоса времени, а они нужны и без звука.
  }

  /* ⚠️ КОНТЕКСТ САМОВОССТАНАВЛИВАЕТСЯ, И ЭТО НЕ ПЕРЕСТРАХОВКА.
     Chrome на Windows усыпляет AudioContext при уходе со вкладки, а при
     смене устройства вывода оставляет его в состоянии running, но звука в
     нём уже нет. Ни то ни другое клиенту не сообщается — звук просто
     пропадает до перезагрузки страницы. Отсюда три правила ниже:
     закрытый контекст пересоздаём, спящий будим перед каждым звуком,
     остановившиеся часы (currentTime не движется) считаем мёртвым
     контекстом и тоже пересоздаём.

     ⚠️ Точную причину пропажи звука без воспроизведения не назвать — все
     три механизма известны по симптомам, а не по замеру. Лечатся они
     одним приёмом, поэтому чиним все три сразу. */
  function audio() {
    // Закрытый контекст остаётся объектом и молча не играет: `if (ctx)`
    // без этой проверки возвращал бы труп до конца сессии.
    if (ctx && ctx.state === 'closed') { ctx = null; master = null; }
    if (ctx) return ctx;
    var Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    try {
      ctx = new Ctx();
      master = ctx.createGain();
      master.gain.value = 0.18;   // тихо: игра не должна пугать
      master.connect(ctx.destination);
    } catch (e) { ctx = null; master = null; }
    return ctx;
  }

  /* Разбудить контекст перед звуком. Зовётся первой строкой в tone(),
     thump() и heartbeat.start(): раньше resume() был только в tone(), и
     после сна вкладки ноты играли, а пульс молчал. */
  function wake() {
    var c = audio();
    if (!c) return null;
    try {
      if (c.state !== 'running' && c.resume) c.resume();
    } catch (e) { /* звук не критичен */ }
    return c;
  }

  /* Сторож часов: контекст в состоянии running, а currentTime не движется —
     значит, он мёртв (типично после смены устройства вывода). Пересоздаём
     и повторяем звук РОВНО ОДИН РАЗ: бесконечная цепочка пересозданий хуже
     тишины. Флаг снимается, как только часы снова пошли, — иначе вторая
     смена наушников за сессию осталась бы без лечения. */
  var clock = { timer: null, retried: false };
  var CLOCK_WAIT = 250;   // мс: столько ждём движения currentTime

  function respawn() {
    try { if (ctx && ctx.close) ctx.close(); } catch (e) {}
    ctx = null; master = null;
    var c = audio();
    // ⚠️ Часы нового контекста идут с нуля, а hb.next назначен по старым:
    // назначенные удары оказались бы в далёком будущем, и сердцебиение
    // замолчало бы навсегда. Переназначаем от новых часов.
    if (c && hb.on) hb.next = hbNow() + 0.05;
    return c;
  }

  function watchClock(replay) {
    if (clock.timer) return;          // один сторож за раз
    var c = ctx;
    if (!c) return;
    var was = c.currentTime;
    clock.timer = setTimeout(function () {
      clock.timer = null;
      try {
        if (ctx !== c) return;              // контекст уже сменился
        if (c.state !== 'running') return;  // спит — это лечит wake()
        if (c.currentTime !== was) { clock.retried = false; return; }
        if (clock.retried) return;          // вторая неудача подряд — молчим
        clock.retried = true;
        respawn();
        if (replay) replay();
      } catch (e) { /* звук не критичен */ }
    }, CLOCK_WAIT);
  }

  /* Одна нота: тип волны, частота, длительность, громкость, скольжение. */
  function tone(opts) {
    if (!enabled()) return;
    var c = wake();
    if (!c || !master) return;
    watchClock(function () { tone(opts); });
    var osc = c.createOscillator();
    var gain = c.createGain();
    var t0 = c.currentTime + (opts.delay || 0);
    var dur = opts.dur || 0.12;
    osc.type = opts.type || 'sine';
    osc.frequency.setValueAtTime(opts.freq, t0);
    if (opts.slideTo) {
      osc.frequency.exponentialRampToValueAtTime(opts.slideTo, t0 + dur);
    }
    // мягкая огибающая: щелчок на резком старте слышен сильнее самой ноты
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(opts.vol || 0.6, t0 + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(gain);
    gain.connect(master);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
  }

  /* Полутоновая лестница от опорной ноты: тон верного ответа растёт со
     ступенями комбо (×1 → ×2 → ×3 → ×4) — арифметикой, не сэмплами. */
  function semitone(base, steps) {
    return base * Math.pow(2, steps / 12);
  }

  /* ─── СЕРДЦЕБИЕНИЕ ────────────────────────────────────────────────────
     Заменяет прежний фоновый гул последней жизни: два разных звука об
     одной и той же опасности спорили бы друг с другом.

     ⚠️ ПЛАНИРОВЩИК РАБОТАЕТ И ПРИ ВЫКЛЮЧЕННОМ ЗВУКЕ. Удар — это ещё и
     событие `rush:beat`, по которому пульсируют виньетка и полоса времени.
     Замолчи планировщик вместе со звуком — картинка застыла бы у того, кто
     играет без звука, а это половина игроков.

     ⚠️ ВРЕМЯ БЕРЁТСЯ У AudioContext, а не у setInterval. setInterval
     плывёт на десятки миллисекунд, и удары начали бы «шататься»
     относительно друг друга. Здесь классическая схема: раз в 25 мс
     заглядываем на 120 мс вперёд и назначаем удары на точные моменты
     звуковых часов. Если AudioContext создать не удалось (нет Web Audio,
     нет жеста пользователя) — те же удары идут по performance.now(),
     чтобы картинка всё равно жила. */
  var hb = { on: false, bpm: 70, next: 0, timer: null, silent: false };
  var HB_LOOKAHEAD = 0.12;   // на сколько секунд вперёд назначаем
  var HB_POLL = 25;          // как часто заглядываем, мс

  /* Один «туп»: синус 55 → 40 Гц с быстрым спадом. Низко и коротко —
     это удар, а не нота. */
  function thump(t0, vol) {
    // ⚠️ Здесь тоже wake(), а не голый ctx: resume() стоял только в tone(),
    // и после сна вкладки ноты играли, а пульс молчал.
    var c = wake();
    if (!c || !master) return;
    // Повтора у удара нет: он назначен на точный момент, который уже
    // прошёл бы. Планировщик и так заглядывает вперёд каждые 25 мс.
    watchClock(null);
    var osc = c.createOscillator();
    var gain = c.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(55, t0);
    osc.frequency.exponentialRampToValueAtTime(40, t0 + 0.12);
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(vol, t0 + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.12);
    osc.connect(gain);
    gain.connect(master);
    osc.start(t0);
    osc.stop(t0 + 0.14);
  }

  /* «Туп-туп»: второй удар через 140 мс и тише — так стучит сердце. */
  function beatAt(t0) {
    if (enabled() && !hb.silent) {
      thump(t0, 0.5);
      thump(t0 + 0.14, 0.3);
    }
    var delay = Math.max(0, (t0 - hbNow()) * 1000);
    setTimeout(function () {
      try {
        window.dispatchEvent(new CustomEvent('rush:beat'));
      } catch (e) { /* старый браузер — пульса картинки не будет, звук есть */ }
    }, delay);
  }

  function hbNow() {
    return ctx ? ctx.currentTime : performance.now() / 1000;
  }

  function hbTick() {
    if (!hb.on) return;
    var period = 60 / hb.bpm;
    var horizon = hbNow() + HB_LOOKAHEAD;
    while (hb.next < horizon) {
      beatAt(hb.next);
      hb.next += period;
    }
    hb.timer = setTimeout(hbTick, HB_POLL);
  }

  var heartbeat = {
    /* Запустить. Первый удар — сразу, чтобы тревога не «включалась
       молча» на полсекунды. */
    start: function (bpm) {
      if (hb.on) { heartbeat.set(bpm); return; }
      wake();                        // может вернуть null — это нормально
      hb.on = true;
      hb.bpm = bpm || 70;
      hb.next = hbNow() + 0.05;
      clearTimeout(hb.timer);
      hbTick();
    },
    /* Сменить темп на ходу: уже назначенные удары не трогаем, следующий
       период считается новым. */
    set: function (bpm) {
      if (bpm) hb.bpm = Math.max(40, Math.min(200, bpm));
    },
    stop: function () {
      hb.on = false;
      clearTimeout(hb.timer);
      hb.timer = null;
    },
    isOn: function () { return hb.on; },
    bpm: function () { return hb.bpm; }
  };

  var api = {
    isOn: enabled,
    toggle: function () { setEnabled(!enabled()); return enabled(); },
    set: setEnabled,

    /* Старт забега — короткий подъём. */
    start: function () {
      tone({ freq: 330, dur: 0.10, type: 'triangle' });
      tone({ freq: 494, dur: 0.14, type: 'triangle', delay: 0.09 });
    },

    /* Верный ответ. mult — множитель комбо (1/2/3/4): чем длиннее серия,
       тем выше тон. Игрок слышит собственный разгон. */
    correct: function (mult) {
      var steps = [0, 4, 7, 12][Math.min(Math.max((mult || 1) - 1, 0), 3)];
      tone({ freq: semitone(523.25, steps), dur: 0.11, type: 'triangle' });
      tone({ freq: semitone(659.25, steps), dur: 0.10, type: 'triangle',
             delay: 0.07, vol: 0.35 });
    },

    /* Неверный ответ — глухо и коротко. */
    wrong: function () {
      tone({ freq: 200, slideTo: 150, dur: 0.16, type: 'sawtooth', vol: 0.35 });
    },

    /* ПОТЕРЯ ЖИЗНИ — отдельное событие, тяжелее неверного ответа.
       Игрок обязан слышать разницу: ошибка бывает и без потери жизни
       (если жизни ещё будут возвращать), а сердце гаснет один раз. */
    lifeLost: function () {
      tone({ freq: 160, slideTo: 80, dur: 0.34, type: 'square', vol: 0.4 });
      tone({ freq: 110, slideTo: 55, dur: 0.40, type: 'sine', vol: 0.5,
             delay: 0.04 });
    },

    /* Тик последних секунд. */
    tick: function () {
      tone({ freq: 880, dur: 0.05, type: 'square', vol: 0.22 });
    },

    /* Конец забега. */
    over: function () {
      tone({ freq: 392, dur: 0.18, type: 'triangle' });
      tone({ freq: 294, dur: 0.22, type: 'triangle', delay: 0.16 });
      tone({ freq: 196, dur: 0.34, type: 'triangle', delay: 0.34 });
    },

    /* Личный рекорд. */
    record: function () {
      [523.25, 659.25, 783.99, 1046.5].forEach(function (f, i) {
        tone({ freq: f, dur: 0.14, type: 'triangle', delay: i * 0.09 });
      });
    },

    heartbeat: heartbeat
  };

  /* Возврат на вкладку. Chrome на Windows усыпляет контекст, пока вкладка
     в фоне, и без этого звук молчал бы до следующей перезагрузки страницы.
     Слушатель вешается ОДИН раз при загрузке модуля. */
  try {
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) {
        try { wake(); } catch (e) { /* звук не критичен */ }
      }
    });
  } catch (e) { /* нет document — модуль всё равно должен собраться */ }

  window.rushSound = api;
})();
