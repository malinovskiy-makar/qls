/* Звук Econ Rush.

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
  var lowLayer = null;           // фоновый гул последней жизни

  function enabled() {
    try { return localStorage.getItem(KEY) !== 'off'; }
    catch (e) { return true; }   // приватный режим — звук не выключаем
  }

  function setEnabled(on) {
    try { localStorage.setItem(KEY, on ? 'on' : 'off'); } catch (e) {}
    if (!on) stopLowLayer();
  }

  function audio() {
    if (ctx) return ctx;
    var Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    try {
      ctx = new Ctx();
      master = ctx.createGain();
      master.gain.value = 0.18;   // тихо: игра не должна пугать
      master.connect(ctx.destination);
    } catch (e) { ctx = null; }
    return ctx;
  }

  /* Одна нота: тип волны, частота, длительность, громкость, скольжение. */
  function tone(opts) {
    if (!enabled()) return;
    var c = audio();
    if (!c) return;
    if (c.state === 'suspended' && c.resume) c.resume();
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

  function stopLowLayer() {
    if (!lowLayer) return;
    try {
      lowLayer.gain.gain.exponentialRampToValueAtTime(
        0.0001, ctx.currentTime + 0.3);
      lowLayer.osc.stop(ctx.currentTime + 0.4);
    } catch (e) {}
    lowLayer = null;
  }

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

    /* Низкий фоновый слой последней жизни: не мелодия, а давление.
       Включается один раз и висит до конца забега. */
    lowLayerOn: function () {
      if (lowLayer || !enabled()) return;
      var c = audio();
      if (!c) return;
      try {
        var osc = c.createOscillator();
        var gain = c.createGain();
        osc.type = 'sine';
        osc.frequency.value = 55;
        gain.gain.setValueAtTime(0.0001, c.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.14, c.currentTime + 0.6);
        osc.connect(gain);
        gain.connect(master);
        osc.start();
        lowLayer = { osc: osc, gain: gain };
      } catch (e) { lowLayer = null; }
    },
    lowLayerOff: stopLowLayer
  };

  window.rushSound = api;
})();
