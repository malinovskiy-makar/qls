/* calc-core.js — ядро живого макета «Графики» (редизайн, 27.09.2026).
   Палитры, разбор формул, численные методы, числа по-русски и геометрия
   графика. Только данные и чистые функции: разметку строят артборды.
   Настоящий движок калькулятора живёт в calc2/static/calc2/; здесь его
   упрощённая копия — ровно столько, чтобы макет считал правду. */
(function () {
  'use strict';
  var E = (window.CalcEngine = window.CalcEngine || {});

  /* ── 1. ПАЛИТРЫ ────────────────────────────────────────────────────────
     Интерфейс берёт ТОЛЬКО смысловые токены (--bg, --surface, --text, --accent…).
     Смена палитры сайта = новая таблица значений здесь, разметка не меняется.
     Цвета кривых фиксированы (как в calc2.css и дизайн-системе) и одинаковы
     во всех палитрах. Холст берёт цвет сайта (светлая тема: --surface, тёмная:
     --bg), и каждая кривая держит к нему контраст не ниже 3 : 1 в обеих темах;
     ради этого «было» и FC чуть темнее, чем в calc2.css (там 2,5 : 1). */
  var CURVES = {
    d: '#2F6FED', s: '#E0563B', mr: '#8B3FE0', mc: '#119C8A', tax: '#2E9E44',
    dwl: '#8C8C84', reg: '#B5791F', ghost: '#948C7E',
    atc: '#2F6FED', avc: '#B5791F', afc: '#8B3FE0', vc: '#5B6472', tc: '#2A3140', fc: '#838C9C',
    // линия рыночной цены у фирмы: свой цвет, как --c-price в calc2 (охра занята AVC)
    price: '#B0338C'
  };
  E.CURVES = CURVES;
  /* Те же цвета ссылками на переменные: разметка красит var(--c-*), поэтому
     смена темы или палитры не требует пересчёта геометрии. */
  var CV = {};
  Object.keys(CURVES).forEach(function (k) { CV[k] = 'var(--c-' + k + ')'; });
  E.CV = CV;
  /* «Чернильные» кривые (TC, VC) — единственное исключение из фиксированной
     палитры: на тёмном холсте #2A3140 даёт 1,36:1 и пропадает (в calc2 сейчас
     на #10141c — 1,42:1). В тёмной теме они светлеют; цвета спроса, предложения
     и прочих не меняются. */
  var CURVES_DARK = { tc: '#e8e2d2', vc: '#a8a295' };

  var PALETTES = {
    weconomics: {
      title: 'Weconomics (сейчас на сайте)',
      light: {
        bg: '#f4eed2', surface: '#fffce6', 'surface-2': '#f4eed2', raised: '#fffef6',
        border: 'rgba(45,45,45,.14)', borderSoft: 'rgba(45,45,45,.08)', borderStrong: 'rgba(45,45,45,.26)',
        text: '#2d2d2d', text2: '#5c5346', text3: '#665e51',
        accent: '#00797a', accentInk: '#006c6d', accentDeep: '#016769', accentTint: 'rgba(0,108,109,.09)',
        accentRing: 'rgba(0,121,122,.32)', onAccent: '#ffffff',
        btnBg: '#2e2b27', btnBgHover: '#3d3933', onBtn: '#ffffff',
        navBg: '#3c3531', navText: '#f2ecd9', navText2: '#cfc6b1', navAccent: '#81b5b4', brandAmber: '#d6a525', brandAmberInk: '#1d1a16',
        focus: '#7d7466', focusRing: 'rgba(125,116,102,.22)', numLine: 'rgba(45,45,45,.34)',
        green: '#186e3c', greenTint: 'rgba(24,110,60,.09)', error: '#b93526', errorTint: 'rgba(185,53,38,.09)',
        amber: '#96500c', amberTint: 'rgba(150,80,12,.11)', info: '#f2e8bd', infoBorder: '#d6a525',
        shadowPop: '0 6px 20px rgba(0,0,0,.14)', scrim: 'rgba(29,26,22,.34)',
        surfaceInfo: '#f2e8bd', surfaceTool: '#81b5b4', chipBg: 'rgba(45,45,45,.07)', chipText: '#5c5346',
        greenInk: '#186e3c', greenBorder: 'rgba(24,110,60,.30)', errorInk: '#b93526', errorBorder: 'rgba(185,53,38,.28)', amberInk: '#723c09', amberBorder: 'rgba(150,80,12,.34)',
        // Холст берёт цвет сайта: в светлой теме это --surface (как панели и карточки), в тёмной --bg (как страница).
        // Сетка и серые заливки тёплые, заливки чуть плотнее: на кремовом синий иначе сереет.
        canvas: '#fffce6', ink: '#2d2d2d', inkSoft: '#6b6457', grid: 'rgba(92,83,70,.09)', gridStrong: 'rgba(92,83,70,.17)', halo: '#fffce6',
        fillCS: 'rgba(47,111,237,.22)', fillPS: 'rgba(224,86,59,.16)', fillTX: 'rgba(46,158,68,.21)', fillDWL: 'rgba(110,100,85,.26)',
        fillVC: 'rgba(17,156,138,.17)', fillProfit: 'rgba(46,158,68,.22)', fillLoss: 'rgba(185,53,38,.17)', fillReg: 'rgba(181,121,31,.19)',
        fillUser: 'rgba(0,121,122,.15)'
      },
      dark: {
        bg: '#1d1a16', surface: '#2c2925', 'surface-2': '#232019', raised: '#35312c',
        border: 'rgba(255,255,255,.13)', borderSoft: 'rgba(255,255,255,.07)', borderStrong: 'rgba(255,255,255,.24)',
        text: '#f2ecd9', text2: '#c3bca8', text3: '#b5ab99',
        accent: '#81b5b4', accentInk: '#81b5b4', accentDeep: '#9bc6c5', accentTint: 'rgba(129,181,180,.16)',
        accentRing: 'rgba(129,181,180,.40)', onAccent: '#1d1a16',
        btnBg: '#c4bba9', btnBgHover: '#d0c7b5', onBtn: '#23211d',
        navBg: '#3c3531', navText: '#f2ecd9', navText2: '#cfc6b1', navAccent: '#81b5b4', brandAmber: '#d6a525', brandAmberInk: '#1d1a16',
        focus: '#8a8172', focusRing: 'rgba(138,129,114,.26)', numLine: 'rgba(255,255,255,.34)',
        green: '#3fc77f', greenTint: 'rgba(63,199,127,.15)', error: '#ff8a8a', errorTint: 'rgba(255,138,138,.15)',
        amber: '#efa273', amberTint: 'rgba(239,162,115,.15)', info: '#504a2d', infoBorder: '#d6a525',
        shadowPop: '0 0 0 1px rgba(255,255,255,.07), 0 10px 28px rgba(0,0,0,.45)', scrim: 'rgba(0,0,0,.5)',
        surfaceInfo: '#504a2d', surfaceTool: '#2d504f', chipBg: 'rgba(255,255,255,.08)', chipText: '#c8c2b0',
        greenInk: '#bfecd4', greenBorder: 'rgba(63,199,127,.32)', errorInk: '#ffd2d2', errorBorder: 'rgba(255,138,138,.30)', amberInk: '#f9eae1', amberBorder: 'rgba(239,162,115,.34)',
        canvas: '#1d1a16', ink: '#efe8d6', inkSoft: '#b5ab99', grid: 'rgba(242,236,217,.07)', gridStrong: 'rgba(242,236,217,.13)', halo: '#1d1a16',
        // на тёплом тёмном заливки спокойнее и чуть светлее по тону: большие пятна не должны спорить с кривыми
        fillCS: 'rgba(77,141,255,.20)', fillPS: 'rgba(232,104,78,.20)', fillTX: 'rgba(72,180,96,.20)', fillDWL: 'rgba(214,204,184,.18)',
        fillVC: 'rgba(40,180,160,.19)', fillProfit: 'rgba(72,180,96,.22)', fillLoss: 'rgba(255,138,138,.19)', fillReg: 'rgba(214,165,37,.19)',
        fillUser: 'rgba(129,181,180,.20)'
      }
    },
    alt: {
      title: 'Другая палитра (проверка устойчивости)',
      light: {
        bg: '#eef1f5', surface: '#ffffff', 'surface-2': '#f3f5f9', raised: '#ffffff',
        border: 'rgba(22,32,52,.13)', borderSoft: 'rgba(22,32,52,.07)', borderStrong: 'rgba(22,32,52,.24)',
        text: '#1b2230', text2: '#475166', text3: '#566076',
        accent: '#3552c8', accentInk: '#2f4ab8', accentDeep: '#2a43a6', accentTint: 'rgba(53,82,200,.09)',
        accentRing: 'rgba(53,82,200,.30)', onAccent: '#ffffff',
        btnBg: '#1b2230', btnBgHover: '#2a3345', onBtn: '#ffffff',
        navBg: '#1b2230', navText: '#eef1f5', navText2: '#b9c1d0', navAccent: '#9db4ff', brandAmber: '#f0b429', brandAmberInk: '#1b2230',
        focus: '#6b7385', focusRing: 'rgba(107,115,133,.22)', numLine: 'rgba(22,32,52,.34)',
        green: '#1d7a45', greenTint: 'rgba(29,122,69,.09)', error: '#c0392b', errorTint: 'rgba(192,57,43,.09)',
        amber: '#9a5a0c', amberTint: 'rgba(154,90,12,.10)', info: '#e8edf8', infoBorder: '#9db4ff',
        shadowPop: '0 8px 24px rgba(20,30,50,.16)', scrim: 'rgba(15,20,28,.34)',
        surfaceInfo: '#e8edf8', surfaceTool: '#c9d4f2', chipBg: 'rgba(22,32,52,.07)', chipText: '#475166',
        greenInk: '#1d7a45', greenBorder: 'rgba(29,122,69,.30)', errorInk: '#c0392b', errorBorder: 'rgba(192,57,43,.28)', amberInk: '#6e3f06', amberBorder: 'rgba(154,90,12,.34)',
        canvas: '#ffffff', ink: '#1b2230', inkSoft: '#5d6678', grid: 'rgba(22,32,52,.07)', gridStrong: 'rgba(22,32,52,.13)', halo: '#ffffff',
        fillCS: 'rgba(47,111,237,.15)', fillPS: 'rgba(224,86,59,.14)', fillTX: 'rgba(46,158,68,.19)', fillDWL: 'rgba(140,140,132,.30)',
        fillVC: 'rgba(17,156,138,.13)', fillProfit: 'rgba(46,158,68,.20)', fillLoss: 'rgba(192,57,43,.14)', fillReg: 'rgba(181,121,31,.16)',
        fillUser: 'rgba(53,82,200,.13)'
      },
      dark: {
        bg: '#0f141c', surface: '#171e2a', 'surface-2': '#121823', raised: '#1e2735',
        border: 'rgba(255,255,255,.12)', borderSoft: 'rgba(255,255,255,.06)', borderStrong: 'rgba(255,255,255,.22)',
        text: '#e8edf5', text2: '#b4bdcc', text3: '#9aa4b5',
        accent: '#8fa6ff', accentInk: '#9db4ff', accentDeep: '#b0c2ff', accentTint: 'rgba(143,166,255,.16)',
        accentRing: 'rgba(143,166,255,.40)', onAccent: '#0f141c',
        btnBg: '#d7deea', btnBgHover: '#e4e9f2', onBtn: '#121823',
        navBg: '#121823', navText: '#e8edf5', navText2: '#b4bdcc', navAccent: '#9db4ff', brandAmber: '#f0b429', brandAmberInk: '#121823',
        focus: '#8a93a6', focusRing: 'rgba(138,147,166,.26)', numLine: 'rgba(255,255,255,.34)',
        green: '#44c98a', greenTint: 'rgba(68,201,138,.15)', error: '#ff8f8f', errorTint: 'rgba(255,143,143,.15)',
        amber: '#f0a86e', amberTint: 'rgba(240,168,110,.15)', info: '#1e2a44', infoBorder: '#9db4ff',
        shadowPop: '0 0 0 1px rgba(255,255,255,.06), 0 10px 28px rgba(0,0,0,.5)', scrim: 'rgba(0,0,0,.5)',
        surfaceInfo: '#1e2a44', surfaceTool: '#26345a', chipBg: 'rgba(255,255,255,.08)', chipText: '#b4bdcc',
        greenInk: '#c4f0d9', greenBorder: 'rgba(68,201,138,.32)', errorInk: '#ffd6d6', errorBorder: 'rgba(255,143,143,.30)', amberInk: '#fbe9dc', amberBorder: 'rgba(240,168,110,.34)',
        canvas: '#0f141c', ink: '#e8edf5', inkSoft: '#9aa4b5', grid: 'rgba(255,255,255,.07)', gridStrong: 'rgba(255,255,255,.13)', halo: '#0f141c',
        fillCS: 'rgba(47,111,237,.28)', fillPS: 'rgba(224,86,59,.26)', fillTX: 'rgba(46,158,68,.30)', fillDWL: 'rgba(160,160,150,.34)',
        fillVC: 'rgba(17,156,138,.26)', fillProfit: 'rgba(46,158,68,.30)', fillLoss: 'rgba(255,143,143,.22)', fillReg: 'rgba(240,180,41,.18)',
        fillUser: 'rgba(143,166,255,.20)'
      }
    }
  };
  E.PALETTES = PALETTES;

  function kebab(k) { return k.replace(/[A-Z]/g, function (m) { return '-' + m.toLowerCase(); }); }

  /* Строка custom properties для корня артборда: `--bg: …; --surface: …`. */
  E.themeVars = function (paletteKey, mode) {
    var p = (PALETTES[paletteKey] || PALETTES.weconomics)[mode === 'dark' ? 'dark' : 'light'];
    var out = [];
    Object.keys(p).forEach(function (k) { out.push('--' + kebab(k) + ': ' + p[k]); });
    Object.keys(CURVES).forEach(function (k) {
      var v = mode === 'dark' && CURVES_DARK[k] ? CURVES_DARK[k] : CURVES[k];
      out.push('--c-' + k + ': ' + v);
    });
    // имена переменных, которыми рисованы превью карточек в calc2.html
    out.push('--curve-d: ' + CURVES.d, '--curve-s: ' + CURVES.s, '--curve-mr: ' + CURVES.mr,
      '--curve-mc: ' + CURVES.mc, '--curve-tax: ' + CURVES.tax, '--curve-dwl: ' + CURVES.dwl,
      '--curve-reg: ' + CURVES.reg, '--curve-ghost: ' + CURVES.ghost, '--cost-mc: ' + CURVES.mc,
      '--cost-atc: ' + CURVES.atc, '--ink-soft: ' + p.inkSoft);
    return out.join('; ') + ';';
  };
  /* «Скачать»: в файл уходит белый лист со светлыми чернилами, какая бы тема ни стояла на экране. */
  E.paperVars = function (paletteKey) {
    return E.themeVars(paletteKey, 'light').replace(/--canvas: [^;]+;/, '--canvas: #ffffff;').replace(/--halo: [^;]+;/, '--halo: #ffffff;');
  };
  E.theme = function (paletteKey, mode) {
    return (PALETTES[paletteKey] || PALETTES.weconomics)[mode === 'dark' ? 'dark' : 'light'];
  };

  /* ── 2. ЧИСЛА ПО-РУССКИ ───────────────────────────────────────────────
     Десятичная запятая, узкий неразрывный пробел в тысячах, настоящий минус. */
  var NNBSP = ' ';
  var MINUS = '−';
  function fmt(v, dec) {
    if (v === null || v === undefined || typeof v !== 'number' || !isFinite(v)) return '–';
    var d = dec === undefined ? 2 : dec;
    var m = Math.pow(10, d);
    var r = Math.round(v * m) / m;
    if (r === 0) r = 0; // убрать −0
    var neg = r < 0;
    var s = Math.abs(r).toFixed(d);
    if (s.indexOf('.') >= 0) s = s.replace(/0+$/, '').replace(/\.$/, '');
    var parts = s.split('.');
    var ip = parts[0];
    if (ip.length > 3) ip = ip.replace(/\B(?=(\d{3})+(?!\d))/g, NNBSP);
    s = ip + (parts[1] ? ',' + parts[1] : '');
    return (neg ? MINUS : '') + s;
  }
  E.fmt = fmt;
  E.fmtDelta = function (v, dec) {
    if (v === null || v === undefined || !isFinite(v)) return '–';
    var s = fmt(v, dec);
    if (s === '0') return '0';
    return v > 0 ? '+' + s : s;
  };
  E.MINUS = MINUS;

  /* ── 3. ФОРМУЛЫ ────────────────────────────────────────────────────────
     Разбор записи вида «100 - 2Q», «Q^2/100 + 5», «30*L^2 - L^3», «sqrt(100-x^2)».
     Неявное умножение («2Q», «a(Q+1)»), десятичная запятая, «−», «·», «²».
     Буква, отличная от переменной оси, становится ползунком. */
  var FUNCS = { sqrt: 1, ln: 1, log: 1, exp: 1, abs: 1, min: 2, max: 2, sin: 1, cos: 1, tan: 1, nthroot: 2 };
  /* Константы, как в Math.js у calc2: ползунком они не становятся. */
  var CONSTS = { 'π': Math.PI, 'e': Math.E };

  function normalize(src) {
    return String(src || '')
      .replace(/[−–—]/g, '-')
      .replace(/[·⋅×]/g, '*')
      .replace(/÷/g, '/')
      .replace(/²/g, '^2').replace(/³/g, '^3')
      .replace(/√/g, 'sqrt')
      .replace(/≤/g, '<=').replace(/≥/g, '>=').replace(/≠/g, '!=')
      .replace(/∞/g, 'Infinity').replace(/≈/g, '==')
      .replace(/(\d)\s*%/g, '$1/100')
      // «и» / «или» между условиями: слова живут только между пробелами, иначе их не отличить от букв a·n·d
      .replace(/\s+(?:and|и)\s+/gi, '&').replace(/\s+(?:or|или)\s+/gi, '|')
      .replace(/(\d),(\d)/g, '$1.$2')
      .replace(/\s+/g, '');
  }

  function tokenize(s) {
    var toks = [], i = 0;
    while (i < s.length) {
      var c = s[i];
      if (/[0-9.]/.test(c)) {
        var j = i; while (j < s.length && /[0-9.]/.test(s[j])) j++;
        var num = s.slice(i, j);
        if ((num.match(/\./g) || []).length > 1) return { error: 'Лишняя точка в числе «' + num + '»' };
        toks.push({ t: 'num', v: parseFloat(num), raw: num }); i = j; continue;
      }
      if (/[A-Za-zА-Яа-яα-ωΑ-Ω]/.test(c)) {
        var k = i; while (k < s.length && /[A-Za-zА-Яа-яα-ωΑ-Ω]/.test(s[k])) k++;
        var word = s.slice(i, k);
        // известная функция целиком, иначе — отдельные буквы (aQ = a·Q)
        var lw = word.toLowerCase();
        if (FUNCS[lw] && s[k] === '(') { toks.push({ t: 'fn', v: lw }); i = k; continue; }
        if (word === 'NaN') { toks.push({ t: 'num', v: NaN, raw: 'NaN' }); i = k; continue; }
        if (word === 'Infinity') { toks.push({ t: 'num', v: Infinity, raw: '∞' }); i = k; continue; }
        for (var q = 0; q < word.length; q++) toks.push({ t: 'id', v: word[q] });
        i = k; continue;
      }
      if ('+-*/^'.indexOf(c) >= 0) { toks.push({ t: 'op', v: c }); i++; continue; }
      if (c === '(') { toks.push({ t: 'lp' }); i++; continue; }
      if (c === ')') { toks.push({ t: 'rp' }); i++; continue; }
      if (c === ';' || c === ',') { toks.push({ t: 'sep' }); i++; continue; }
      // сравнения и выбор: «Q < 20 ? 100 − 2Q : 80 − Q» — так движок calc2 понимает кусочную запись
      if (c === '<' || c === '>' || c === '!' || c === '=') {
        var two = s.substr(i, 2);
        if (two === '<=' || two === '>=' || two === '!=' || two === '==') { toks.push({ t: 'cmp', v: two }); i += 2; continue; }
        if (c === '<' || c === '>') { toks.push({ t: 'cmp', v: c }); i++; continue; }
        return { error: c === '=' ? 'Лишний знак «=»' : 'Не понимаю символ «' + c + '»' };
      }
      if (c === '?') { toks.push({ t: 'q' }); i++; continue; }
      if (c === ':') { toks.push({ t: 'colon' }); i++; continue; }
      if (c === '&') { toks.push({ t: 'and' }); i++; continue; }
      if (c === '|') { toks.push({ t: 'or' }); i++; continue; }
      if (c === '_') { i++; while (i < s.length && /[A-Za-zА-Яа-я0-9]/.test(s[i])) i++; continue; }   // индекс — часть имени: Q_d это Q
      return { error: 'Не понимаю символ «' + c + '»' };
    }
    return { toks: toks };
  }

  function Parser(toks) { this.t = toks; this.i = 0; }
  Parser.prototype.peek = function () { return this.t[this.i]; };
  Parser.prototype.next = function () { return this.t[this.i++]; };
  Parser.prototype.ternary = function () {
    var c = this.or();
    var p = this.peek();
    if (p && p.t === 'q') {
      this.next();
      if (!this.peek()) throw new Error('После «?» нужна формула');
      var a = this.ternary();
      if (!this.peek() || this.peek().t !== 'colon') throw new Error('После «?» нужна вторая ветка через «:»');
      this.next();
      if (!this.peek()) throw new Error('После «:» нужна формула');
      return { k: 'cond', c: c, a: a, b: this.ternary() };
    }
    return c;
  };
  Parser.prototype.or = function () {
    var a = this.and();
    while (this.peek() && this.peek().t === 'or') { this.next(); a = { k: 'or', a: a, b: this.and() }; }
    return a;
  };
  Parser.prototype.and = function () {
    var a = this.cmp();
    while (this.peek() && this.peek().t === 'and') { this.next(); a = { k: 'and', a: a, b: this.cmp() }; }
    return a;
  };
  Parser.prototype.cmp = function () {
    var first = this.expr();
    if (!this.peek() || this.peek().t !== 'cmp') return first;
    var items = [first], ops = [];
    while (this.peek() && this.peek().t === 'cmp') {
      ops.push(this.next().v);
      if (!this.peek()) throw new Error('После знака сравнения нужно число или буква');
      items.push(this.expr());
    }
    return { k: 'cmp', items: items, ops: ops };
  };
  Parser.prototype.expr = function () {
    var a = this.term();
    while (this.peek() && this.peek().t === 'op' && (this.peek().v === '+' || this.peek().v === '-')) {
      var op = this.next().v;
      if (!this.peek()) throw new Error('После «' + (op === '-' ? '−' : '+') + '» нужно число или буква');
      a = { k: 'bin', op: op, a: a, b: this.term() };
    }
    return a;
  };
  Parser.prototype.term = function () {
    var a = this.unary();
    for (;;) {
      var p = this.peek();
      if (p && p.t === 'op' && (p.v === '*' || p.v === '/')) {
        this.next();
        if (!this.peek()) throw new Error('После «' + (p.v === '*' ? '·' : '/') + '» нужно число или буква');
        a = { k: 'bin', op: p.v, a: a, b: this.unary() };
      } else if (p && (p.t === 'num' || p.t === 'id' || p.t === 'lp' || p.t === 'fn')) {
        a = { k: 'bin', op: '*', a: a, b: this.power(), implicit: true };
      } else break;
    }
    return a;
  };
  Parser.prototype.unary = function () {
    var p = this.peek();
    if (p && p.t === 'op' && p.v === '-') { this.next(); return { k: 'neg', a: this.unary() }; }
    if (p && p.t === 'op' && p.v === '+') { this.next(); return this.unary(); }
    return this.power();
  };
  Parser.prototype.power = function () {
    var base = this.primary();
    var p = this.peek();
    if (p && p.t === 'op' && p.v === '^') {
      this.next();
      if (!this.peek()) throw new Error('После «^» нужна степень');
      return { k: 'bin', op: '^', a: base, b: this.unary() };
    }
    return base;
  };
  Parser.prototype.primary = function () {
    var p = this.next();
    if (!p) throw new Error('Запись оборвалась: не хватает числа или буквы');
    if (p.t === 'num') return { k: 'num', v: p.v };
    if (p.t === 'id') return { k: 'var', v: p.v };
    if (p.t === 'fn') {
      if (!this.peek() || this.peek().t !== 'lp') throw new Error('После «' + p.v + '» нужна скобка');
      this.next();
      var args = [this.ternary()];
      while (this.peek() && this.peek().t === 'sep') { this.next(); args.push(this.ternary()); }
      if (!this.peek() || this.peek().t !== 'rp') throw new Error('Не хватает закрывающей скобки');
      this.next();
      return { k: 'fn', v: p.v, args: args };
    }
    if (p.t === 'lp') {
      var e = this.ternary();
      if (!this.peek() || this.peek().t !== 'rp') throw new Error('Не хватает закрывающей скобки');
      this.next();
      return { k: 'par', a: e };
    }
    if (p.t === 'rp') throw new Error('Лишняя закрывающая скобка');
    if (p.t === 'op') throw new Error('Два знака подряд: «' + (p.v === '-' ? '−' : p.v) + '»');
    if (p.t === 'cmp') throw new Error('Перед знаком сравнения нужно число или буква');
    if (p.t === 'q' || p.t === 'colon') throw new Error('Перед «' + (p.t === 'q' ? '?' : ':') + '» нужна формула');
    throw new Error('Не понимаю запись');
  };

  function parse(src) {
    var n = normalize(src);
    if (!n) return { error: 'Формула пустая' };
    var tk = tokenize(n);
    if (tk.error) return { error: tk.error };
    var P = new Parser(tk.toks);
    try {
      var ast = P.ternary();
      if (P.i < tk.toks.length) {
        var rest = tk.toks[P.i];
        if (rest.t === 'rp') return { error: 'Лишняя закрывающая скобка' };
        if (rest.t === 'colon') return { error: 'Перед «:» нужно условие со знаком «?»' };
        return { error: 'Не понимаю запись после «' + n.slice(0, 12) + '…»' };
      }
      return { ast: ast };
    } catch (e) { return { error: e.message }; }
  }
  E.parse = parse;

  function evalAst(n, sc) {
    switch (n.k) {
      case 'num': return n.v;
      case 'var': return sc[n.v] !== undefined ? sc[n.v] : (CONSTS[n.v] !== undefined ? CONSTS[n.v] : NaN);
      case 'cmp': {
        var prev = evalAst(n.items[0], sc);
        for (var ci = 0; ci < n.ops.length; ci++) {
          var nx = evalAst(n.items[ci + 1], sc), op = n.ops[ci];
          var hold = op === '<' ? prev < nx : op === '>' ? prev > nx : op === '<=' ? prev <= nx : op === '>=' ? prev >= nx : op === '!=' ? prev !== nx : prev === nx;
          if (!hold) return 0;
          prev = nx;
        }
        return 1;
      }
      case 'and': return (evalAst(n.a, sc) && evalAst(n.b, sc)) ? 1 : 0;
      case 'or': return (evalAst(n.a, sc) || evalAst(n.b, sc)) ? 1 : 0;
      case 'cond': { var cv = evalAst(n.c, sc); return (cv && cv === cv) ? evalAst(n.a, sc) : evalAst(n.b, sc); }
      case 'par': return evalAst(n.a, sc);
      case 'neg': return -evalAst(n.a, sc);
      case 'bin': {
        var a = evalAst(n.a, sc), b = evalAst(n.b, sc);
        switch (n.op) {
          case '+': return a + b; case '-': return a - b; case '*': return a * b;
          case '/': return b === 0 ? NaN : a / b; case '^': return Math.pow(a, b);
        }
        return NaN;
      }
      case 'fn': {
        var v = n.args.map(function (x) { return evalAst(x, sc); });
        switch (n.v) {
          case 'sqrt': return v[0] < 0 ? NaN : Math.sqrt(v[0]);
          case 'ln': return v[0] <= 0 ? NaN : Math.log(v[0]);
          case 'log': return v[0] <= 0 ? NaN : (v.length > 1 ? Math.log(v[0]) / Math.log(v[1]) : Math.log(v[0]));
          case 'nthroot': return v[1] ? (v[0] < 0 && Math.abs(v[1] % 2) === 1 ? -Math.pow(-v[0], 1 / v[1]) : Math.pow(v[0], 1 / v[1])) : NaN;
          case 'exp': return Math.exp(v[0]);
          case 'abs': return Math.abs(v[0]);
          case 'min': return Math.min.apply(null, v);
          case 'max': return Math.max.apply(null, v);
          case 'sin': return Math.sin(v[0]); case 'cos': return Math.cos(v[0]); case 'tan': return Math.tan(v[0]);
        }
      }
    }
    return NaN;
  }

  function lettersOf(n, acc) {
    acc = acc || {};
    if (!n) return acc;
    if (n.k === 'var' && CONSTS[n.v] === undefined) acc[n.v] = true;
    if (n.a) lettersOf(n.a, acc);
    if (n.b) lettersOf(n.b, acc);
    if (n.c) lettersOf(n.c, acc);
    if (n.args) n.args.forEach(function (x) { lettersOf(x, acc); });
    if (n.items) n.items.forEach(function (x) { lettersOf(x, acc); });
    return acc;
  }

  /* ── КУСОЧНАЯ ЗАПИСЬ ────────────────────────────────────────────────────
     Движок calc2 хранит кусочную функцию цепочкой выбора «условие ? то : иначе»
     (её собирает конструктор pwFormula в 82-input.js). Макет понимает ту же
     запись и умеет развернуть её обратно в строки «формула · от · до». */
  function unpar(n) { while (n && n.k === 'par') n = n.a; return n; }
  function constVal(n) {
    if (!n || Object.keys(lettersOf(n)).length) return null;
    var v = evalAst(n, {});
    return (typeof v === 'number' && v === v) ? v : null;
  }
  var FLIP = { '<': '>', '>': '<', '<=': '>=', '>=': '<=', '!=': '!=', '==': '==' };
  /* Условие вида «v ≥ a и v < b» (или одна из половин, или цепочка a ≤ v < b) → границы участка. */
  function boundsOf(c, names) {
    var out = { from: null, to: null, fromInc: true, toInc: false };
    function isAx(n) { n = unpar(n); return !!n && n.k === 'var' && names.indexOf(n.v) >= 0; }
    function one(cmp) {
      cmp = unpar(cmp);
      if (!cmp || cmp.k !== 'cmp') return false;
      for (var i = 0; i < cmp.ops.length; i++) {
        var L = cmp.items[i], R = cmp.items[i + 1], op = cmp.ops[i];
        var lv = isAx(L), rv = isAx(R);
        if (lv === rv) return false;
        var cv = constVal(unpar(lv ? R : L));
        if (cv === null) return false;
        if (!lv) op = FLIP[op];
        if (op === '>=' || op === '>') { if (cv !== -Infinity) { out.from = cv; out.fromInc = op === '>='; } }
        else if (op === '<' || op === '<=') { if (cv !== Infinity) { out.to = cv; out.toInc = op === '<='; } }
        else return false;
      }
      return true;
    }
    c = unpar(c);
    if (c && c.k === 'and') return one(c.a) && one(c.b) ? out : null;
    return one(c) ? out : null;
  }
  function pwRows(ast, names) {
    var rows = [], n = unpar(ast), guard = 0;
    while (n && n.k === 'cond' && guard++ < 24) {
      var b = boundsOf(n.c, names);
      if (!b) return null;
      rows.push({ ast: unpar(n.a), from: b.from, to: b.to, fromInc: b.fromInc, toInc: b.toInc, rest: false });
      n = unpar(n.b);
    }
    if (!rows.length) return null;
    // хвост «иначе»: NaN значит «дальше функции нет», отдельным куском не идёт
    if (n && !(n.k === 'num' && n.v !== n.v)) rows.push({ ast: n, from: null, to: null, fromInc: true, toInc: false, rest: true });
    return rows;
  }
  /* Числа, с которыми запись сравнивает переменную оси: там функция может ломаться или рваться. */
  function breaksOf(ast, names) {
    var acc = [];
    (function walk(n) {
      if (!n) return;
      if (n.k === 'cmp') {
        for (var i = 0; i < n.ops.length; i++) {
          var L = unpar(n.items[i]), R = unpar(n.items[i + 1]);
          var lv = L && L.k === 'var' && names.indexOf(L.v) >= 0, rv = R && R.k === 'var' && names.indexOf(R.v) >= 0;
          if (lv === rv) continue;
          var cv = constVal(lv ? R : L);
          if (cv !== null && isFinite(cv)) acc.push(cv);
        }
      }
      walk(n.a); walk(n.b); walk(n.c);
      (n.args || []).forEach(walk); (n.items || []).forEach(walk);
    })(ast);
    acc.sort(function (x, y) { return x - y; });
    return acc.filter(function (x, i) { return !i || Math.abs(x - acc[i - 1]) > 1e-12; });
  }

  /* compile('100 - aQ', 'Q') → { ok, f(x, params), letters: ['a'], breaks, rows, error } */
  E.compile = function (src, axisVar, allowed) {
    var r = parse(src);
    if (r.error) return { ok: false, error: r.error };
    var ls = Object.keys(lettersOf(r.ast));
    var ax = axisVar || 'Q';
    var alt = { Q: ['q'], P: ['p'], x: ['X'], L: ['l'], Y: ['y'] };
    var names = [ax].concat(alt[ax] || []);
    var letters = ls.filter(function (l) {
      return names.indexOf(l) < 0 && (!allowed || allowed.indexOf(l) < 0);
    });
    var ast = r.ast;
    function scope(x, params) {
      var sc = {}; if (params) for (var k in params) sc[k] = params[k];
      names.forEach(function (a) { sc[a] = x; });
      return sc;
    }
    var rows = pwRows(ast, names);
    return {
      ok: true, ast: ast, letters: letters, v: ax,
      f: function (x, params) { return evalAst(ast, scope(x, params)); },
      breaks: breaksOf(ast, names),
      rows: rows ? rows.map(function (rw) {
        return { from: rw.from, to: rw.to, fromInc: rw.fromInc, toInc: rw.toInc, rest: rw.rest, ast: rw.ast,
          f: function (x, params) { return evalAst(rw.ast, scope(x, params)); } };
      }) : null
    };
  };

  /* Строки конструктора → запись для движка (та же цепочка, что pwFormula в calc2).
     Участок куска: от «от» включительно до «до» не включая; пустая граница — открытая. */
  E.pwText = function (pieces, v) {
    var out = null;
    for (var i = pieces.length - 1; i >= 0; i--) {
      var pc = pieces[i], f = '(' + (E.splitEq(pc.expr).rhs.trim() || '0') + ')';
      var conds = [];
      if (String(pc.from === undefined || pc.from === null ? '' : pc.from).trim() !== '') conds.push(v + ' >= ' + String(pc.from).trim());
      if (String(pc.to === undefined || pc.to === null ? '' : pc.to).trim() !== '') conds.push(v + ' < ' + String(pc.to).trim());
      var cond = conds.length ? '(' + conds.join(' and ') + ')' : '';
      if (out === null) out = cond ? cond + ' ? ' + f + ' : NaN' : f;
      else if (!cond) out = f;                         // кусок без границ перекрывает всё ниже
      else out = cond + ' ? ' + f + ' : (' + out + ')';
    }
    return out || '0';
  };
  /* Формула обратно в текст (для строк конструктора из уже набранной цепочки). */
  function astText(n) {
    if (!n) return '';
    switch (n.k) {
      case 'num': return n.v !== n.v ? 'NaN' : n.v === Infinity ? '∞' : String(Math.round(n.v * 1e9) / 1e9);
      case 'var': return n.v;
      case 'par': return '(' + astText(n.a) + ')';
      case 'neg': return '-' + astText(n.a);
      case 'fn': return n.v + '(' + n.args.map(astText).join('; ') + ')';
      case 'bin': return astText(n.a) + (n.op === '^' ? '^' : n.implicit ? '' : ' ' + n.op + ' ') + astText(n.b);
      case 'cmp': return n.items.map(function (it, i) { return (i ? ' ' + n.ops[i - 1] + ' ' : '') + astText(it); }).join('');
      case 'and': return astText(n.a) + ' and ' + astText(n.b);
      case 'or': return astText(n.a) + ' or ' + astText(n.b);
      case 'cond': return astText(n.c) + ' ? ' + astText(n.a) + ' : ' + astText(n.b);
    }
    return '';
  }
  E.astText = astText;
  /* Условие участка токенами: «0 ≤ Q < 20», «Q ≥ 20», «Q < 20»; пусто — «иначе». */
  E.condToks = function (row, v) {
    var V = { k: 'v', t: v }, N = function (x) { return { k: 'n', t: fmt(x, 6) }; }, O = function (t) { return { k: 'o', t: t }; };
    var hasF = row.from !== null && row.from !== undefined, hasT = row.to !== null && row.to !== undefined;
    if (hasF && hasT) return [N(row.from), O(row.fromInc ? '≤' : '<'), V, O(row.toInc ? '≤' : '<'), N(row.to)];
    if (hasF) return [V, O(row.fromInc ? '≥' : '>'), N(row.from)];
    if (hasT) return [V, O(row.toInc ? '≤' : '<'), N(row.to)];
    return [];
  };
  E.condText = function (row, v) {
    var t = E.condToks(row, v);
    return t.length ? t.map(function (x) { return x.t; }).join(' ') : '';
  };

  /* Запись с левой частью: «Qd = 120 − 2P», «P = 100 − Q». Левую часть
     отрезаем, но запоминаем: по ней видно, в какой форме человек пишет. */
  E.splitEq = function (src) {
    var s = String(src || '');
    // левая часть — одно имя («P», «Qd», «TC(Q)»); «=» внутри «>=», «<=», «!=», «==» знаком равенства не считается
    var m = /^\s*([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9_′'₀-₉]*(?:\s*\(\s*[A-Za-zА-Яа-я]\s*\))?)\s*=(?!=)/.exec(s);
    if (!m) return { lhs: '', rhs: s };
    return { lhs: m[1].replace(/\s+/g, ''), rhs: s.slice(m[0].length) };
  };
  /* Форма записи, как в calc2 (80-ui.js, curveSrcForm): есть P и нет Q — это
     Q = f(P), иначе P = f(Q). Олимпиадные условия почти всегда дают Qd(P). */
  E.srcForm = function (src, axis) {
    if ((axis || 'Q') !== 'Q') return 'PQ';
    var sp = E.splitEq(src);
    if (/^Q/i.test(sp.lhs)) return 'QP';
    if (/^P/i.test(sp.lhs)) return 'PQ';
    var r = parse(sp.rhs);
    if (r.error) return 'PQ';
    var ls = lettersOf(r.ast);
    var hasQ = !!(ls.Q || ls.q), hasP = !!(ls.P || ls.p);
    return (hasP && !hasQ) ? 'QP' : 'PQ';
  };
  /* Компиляция с учётом формы: всегда отдаёт P = f(Q) (канон движка).
     Q(P) обращается: линейная — точно, иначе численно (бисекция по цене). */
  E.compileFn = function (src, axis) {
    axis = axis || 'Q';
    var form = E.srcForm(src, axis);
    var rhs = E.splitEq(src).rhs;
    if (form === 'PQ') {
      var c = E.compile(rhs, axis);
      if (c.ok) c.form = 'PQ';
      return c;
    }
    var cq = E.compile(rhs, 'P', ['Q', 'q']);
    if (!cq.ok) return cq;
    function lin(params) {
      if (cq.breaks.length) return null;               // кусочная Q(P) одной прямой не бывает
      var q0 = cq.f(0, params), q1 = cq.f(1, params), q9 = cq.f(97, params);
      if (![q0, q1, q9].every(isFinite)) return null;
      var d = q1 - q0;
      if (Math.abs(q0 + d * 97 - q9) > 1e-7 * (1 + Math.abs(q9))) return null;
      return { c: q0, d: d };
    }
    return {
      ok: true, form: 'QP', letters: cq.letters, ast: cq.ast, v: 'P',
      linear: lin, g: cq.f, rowsP: cq.rows, breaksP: cq.breaks,
      // изломы в единицах оси Q: значения Q(P) по обе стороны каждой границы по цене
      breaks: [],
      breaksQ: function (params) {
        var out = [];
        cq.breaks.forEach(function (b) {
          [cq.f(b - 1e-9, params), cq.f(b + 1e-9, params), cq.f(b, params)].forEach(function (q) { if (isFinite(q)) out.push(Math.round(q * 1e6) / 1e6); });
        });
        out.sort(function (x, y) { return x - y; });
        return out.filter(function (x, i) { return !i || Math.abs(x - out[i - 1]) > 1e-7; });
      },
      f: function (q, params) {
        var L = lin(params);
        if (L) return Math.abs(L.d) < 1e-12 ? NaN : (q - L.c) / L.d;
        var g = function (p) { return cq.f(p, params) - q; };
        var lo = 0, prev = g(0);
        for (var i = 1; i <= 80; i++) {
          var p = i * 12.5, v = g(p);
          if (isFinite(prev) && isFinite(v) && (prev < 0) !== (v < 0)) return bisect(g, lo, p, 50);
          lo = p; prev = v;
        }
        return NaN;
      }
    };
  };

  /* ── 3б. НАБОР ФОРМУЛЫ ДЛЯ ЭКРАНА ───────────────────────────────────────
     Токены для разметки: k = n (число), v (буква, курсив), r (обозначение прямо),
     o (знак), p (скобка), f (функция); sup / sub — вложенные списки.
     Разметка рисует их шрифтом STIX Two: так выглядит KaTeX в calc2. */
  function tNum(v) { return { k: 'n', t: v === Infinity ? '∞' : v === -Infinity ? MINUS + '∞' : fmt(v, 6) }; }
  var CMPSYM = { '<': '<', '>': '>', '<=': '≤', '>=': '≥', '!=': '≠', '==': '=' };
  function needParen(n, parentOp, side) {
    if (n.k === 'cond' || n.k === 'cmp' || n.k === 'and' || n.k === 'or') return !!parentOp;
    if (n.k !== 'bin') return n.k === 'neg' && (parentOp === '^' || parentOp === '*' && side === 'b');
    var prec = { '+': 1, '-': 1, '*': 2, '/': 2, '^': 3 };
    if (prec[n.op] < prec[parentOp]) return true;
    if (parentOp === '^' && side === 'a') return prec[n.op] <= 3;
    if (side === 'b' && (parentOp === '-' || parentOp === '/') && prec[n.op] === prec[parentOp]) return true;
    return false;
  }
  function wrap(toks) { return [{ k: 'p', t: '(' }].concat(toks, [{ k: 'p', t: ')' }]); }
  function tset(n, parentOp, side) {
    var out;
    switch (n.k) {
      case 'num': out = [tNum(n.v)]; break;
      case 'var': out = [{ k: 'v', t: n.v }]; break;
      case 'par': out = tset(n.a); if (n.a.k === 'bin' || n.a.k === 'neg') out = wrap(out); break;
      case 'neg': out = [{ k: 'o', t: MINUS, u: true }].concat(tset(n.a, '*', 'b')); break;
      case 'fn':
        out = [{ k: 'f', t: n.v === 'sqrt' ? '√' : n.v }];
        var inner = [];
        n.args.forEach(function (a, i) { if (i) inner.push({ k: 'o', t: '; ', u: true }); inner = inner.concat(tset(a)); });
        out = out.concat(wrap(inner));
        break;
      case 'bin': {
        if (n.op === '^') {
          out = tset(n.a, '^', 'a').concat([{ k: 'sup', items: tset(n.b) }]);
          break;
        }
        var a = tset(n.a, n.op, 'a'), b = tset(n.b, n.op, 'b');
        if (n.op === '*') {
          var juxt = (n.a.k === 'num' || n.a.k === 'var' || n.a.k === 'bin' && n.a.op === '^') &&
            (n.b.k === 'var' || n.b.k === 'par' || n.b.k === 'fn' || n.b.k === 'bin' && n.b.op === '^' && n.b.a.k === 'var');
          if (n.a.k === 'var' && n.b.k === 'num') juxt = false;
          out = juxt ? a.concat(b) : a.concat([{ k: 'o', t: '·' }], b);
        } else {
          out = a.concat([{ k: 'o', t: n.op === '-' ? MINUS : n.op }], b);
        }
        break;
      }
      case 'cmp':
        out = tset(n.items[0]);
        n.ops.forEach(function (op, i) { out = out.concat([{ k: 'o', t: CMPSYM[op] }], tset(n.items[i + 1])); });
        break;
      case 'and': out = tset(n.a).concat([{ k: 'r', t: ' и ' }], tset(n.b)); break;
      case 'or': out = tset(n.a).concat([{ k: 'r', t: ' или ' }], tset(n.b)); break;
      case 'cond': {
        // в одну строку: «100 − 2Q, если Q < 20; 80 − Q»
        var els = unpar(n.b), noElse = els && els.k === 'num' && els.v !== els.v;
        out = tset(unpar(n.a)).concat([{ k: 'r', t: ', если ' }], tset(unpar(n.c)), noElse ? [] : [{ k: 'r', t: '; ' }].concat(tset(els)));
        break;
      }
      default: out = [];
    }
    if (parentOp && needParen(n, parentOp, side) && n.k !== 'par') out = wrap(out);
    return out;
  }
  E.typeset = function (src) {
    var r = parse(E.splitEq(src).rhs);
    if (r.error) return [{ k: 'raw', t: String(src || '') }];
    return tset(r.ast);
  };
  E.typesetAst = function (ast) { return tset(unpar(ast)); };

  /* Лёгкий «LaTeX» для текстов объяснений: $P_b - P_s$, $S_{после} = (1 + \tau) \cdot S$.
     Группы заглавных (MR, MC, CS, DWL, ATC) — прямым, одиночные буквы — курсивом. */
  var TEXMAP = { '\\tau': 'τ', '\\cdot': '·', '\\alpha': 'α', '\\beta': 'β', '\\pi': 'π', '\\Delta': 'Δ', '\\le': '≤', '\\ge': '≥', '\\times': '×', '\\lambda': 'λ', '\\sigma': 'σ', '\\approx': '≈' };
  E.mathTokens = function (src) {
    var s = String(src), out = [], i = 0;
    function pushText(t, kind) { if (t) out.push({ k: kind, t: t }); }
    function group(start) {
      if (s[start] === '{') { var j = s.indexOf('}', start); return { t: s.slice(start + 1, j), end: j + 1 }; }
      return { t: s[start], end: start + 1 };
    }
    while (i < s.length) {
      var c = s[i];
      if (c === '\\') {
        var m = s.slice(i).match(/^\\[a-zA-Z]+/);
        var cmd = m ? m[0] : '\\';
        if (cmd === '\\text' || cmd === '\\mathrm') { var g0 = group(i + cmd.length); pushText(g0.t, 'r'); i = g0.end; continue; }
        pushText(TEXMAP[cmd] || '', cmd === '\\cdot' || cmd === '\\le' || cmd === '\\ge' || cmd === '\\approx' || cmd === '\\times' ? 'o' : 'v');
        i += cmd.length; continue;
      }
      if (c === '_' || c === '^') {
        var g = group(i + 1);
        var inner = /[А-Яа-я]/.test(g.t) ? [{ k: 'r', t: g.t }] : g.t === '*' ? [{ k: 'n', t: '*' }] : E.mathTokens(g.t);
        out.push({ k: c === '_' ? 'sub' : 'sup', items: inner });
        i = g.end; continue;
      }
      if (/[A-Z]/.test(c) && /[A-Z]/.test(s[i + 1] || '')) {
        var j2 = i; while (j2 < s.length && /[A-Z]/.test(s[j2])) j2++;
        pushText(s.slice(i, j2), 'r'); i = j2; continue;
      }
      if (/[A-Za-z]/.test(c)) { pushText(c, 'v'); i++; continue; }
      if (/[0-9.,]/.test(c)) { var j3 = i; while (j3 < s.length && /[0-9.,]/.test(s[j3])) j3++; pushText(s.slice(i, j3).replace('.', ','), 'n'); i = j3; continue; }
      if (c === '-') { pushText(MINUS, 'o'); i++; continue; }
      if ('+=<>'.indexOf(c) >= 0) { pushText(c, 'o'); i++; continue; }
      if (c === '*') { pushText('·', 'o'); i++; continue; }
      if (c === '(' || c === ')' || c === '|') { pushText(c, 'p'); i++; continue; }
      if (c === ' ') { if (out.length && out[out.length - 1].k === 'r' && /[А-Яа-яё]$/.test(out[out.length - 1].t)) pushText(' ', 'r'); i++; continue; }
      if (/[А-Яа-яё]/.test(c)) { var j4 = i; while (j4 < s.length && /[А-Яа-яё]/.test(s[j4])) j4++; pushText(s.slice(i, j4), 'r'); i = j4; continue; }
      pushText(c, 'n'); i++;
    }
    return out;
  };

  /* Абзац с $…$ → сегменты [{text}|{math: tokens}] для разметки. */
  E.richText = function (src) {
    var parts = String(src).split('$');
    var out = [];
    parts.forEach(function (p, i) {
      if (!p) return;
      if (i % 2 === 1) out.push({ isMath: true, toks: E.mathTokens(p) });
      else out.push({ isMath: false, text: p });
    });
    return out;
  };

  /* Линейна ли функция на отрезке: y = a + b·x. */
  E.linearOf = function (f, lo, hi) {
    var xs = [lo, (lo + hi) / 2, hi, lo + (hi - lo) * 0.27];
    var ys = xs.map(function (x) { return f(x); });
    if (ys.some(function (y) { return !isFinite(y); })) return null;
    var b = (ys[2] - ys[0]) / (xs[2] - xs[0]);
    var a = ys[0] - b * xs[0];
    var tol = 1e-7 * (1 + Math.abs(a) + Math.abs(b) * Math.abs(hi));
    for (var i = 0; i < xs.length; i++) if (Math.abs(a + b * xs[i] - ys[i]) > tol) return null;
    return { a: a, b: b };
  };

  /* Запись линейной функции: (100, −1, 'Q') → «100 − Q». */
  E.linearText = function (a, b, v, slopeFirst) {
    v = v || 'Q';
    var r6 = function (x) { return Math.round(x * 1e6) / 1e6; };
    a = r6(a); b = r6(b);
    var ab = Math.abs(b), coef = ab === 1 ? '' : String(ab) + '*';
    if (slopeFirst && b !== 0) {
      var s1 = (b < 0 ? '-' : '') + coef + v;
      if (a !== 0) s1 += (a < 0 ? ' - ' : ' + ') + String(Math.abs(a));
      return s1;
    }
    var s = '';
    if (a !== 0) s = String(a);
    if (b !== 0) {
      if (s) s += (b < 0 ? ' - ' : ' + ') + coef + v;
      else s = (b < 0 ? '-' : '') + coef + v;
    }
    return s || '0';
  };

  /* Запись для копирования и подписей: «60 − 0,5Q», «2x − 1». */
  E.prettyExpr = function (t) {
    return String(t)
      .replace(/(\d)\*([A-Za-zА-Яа-я(])/g, '$1$2')
      .replace(/\*/g, '·')
      .replace(/(\d)\.(\d)/g, '$1,$2')
      .replace(/-/g, '−');
  };

  /* ── 4. ЧИСЛЕННЫЕ МЕТОДЫ ──────────────────────────────────────────────── */
  function bisect(g, lo, hi, it) {
    var flo = g(lo);
    for (var i = 0; i < (it || 90); i++) {
      var mid = (lo + hi) / 2, fm = g(mid);
      if (!isFinite(fm)) return mid;
      if ((flo < 0) === (fm < 0)) { lo = mid; flo = fm; } else hi = mid;
    }
    return (lo + hi) / 2;
  }
  E.bisect = bisect;

  /* Все корни g на [lo, hi]: скан с постоянной плотностью + бисекция. */
  E.roots = function (g, lo, hi, n) {
    n = n || 800;
    var out = [], prevX = lo, prev = g(lo);
    if (Math.abs(prev) < 1e-12) out.push(lo);
    for (var i = 1; i <= n; i++) {
      var x = lo + (hi - lo) * i / n, v = g(x);
      if (isFinite(prev) && isFinite(v)) {
        if (v === 0) out.push(x);
        else if ((prev < 0) !== (v < 0) && prev !== 0) out.push(bisect(g, prevX, x));
      }
      prevX = x; prev = v;
    }
    var ded = [];
    out.forEach(function (r) {
      if (!ded.length || Math.abs(r - ded[ded.length - 1]) > (hi - lo) * 1e-6) ded.push(r);
    });
    return ded;
  };
  E.firstRoot = function (g, lo, hi, n) { var r = E.roots(g, lo, hi, n); return r.length ? r[0] : null; };

  /* Интеграл: Симпсон; для надёжности на изломах — узлы в переданных точках. */
  E.integrate = function (g, a, b, n, breaks) {
    if (!(b > a)) return 0;
    var pts = [a].concat((breaks || []).filter(function (x) { return x > a && x < b; }).sort(function (x, y) { return x - y; }), [b]);
    var total = 0;
    for (var s = 0; s < pts.length - 1; s++) {
      var lo = pts[s], hi = pts[s + 1], m = n || 240;
      if (m % 2) m++;
      var h = (hi - lo) / m, acc = g(lo) + g(hi);
      for (var i = 1; i < m; i++) acc += g(lo + i * h) * (i % 2 ? 4 : 2);
      total += acc * h / 3;
    }
    return total;
  };

  E.deriv = function (f, x) {
    var h = 1e-4 * Math.max(1, Math.abs(x));
    return (f(x + h) - f(x - h)) / (2 * h);
  };

  /* x, при котором f(x) = y (первый на [lo, hi]); null — если нет. */
  E.solveFor = function (f, y, lo, hi) {
    return E.firstRoot(function (x) { return f(x) - y; }, lo, hi, 1200);
  };

  /* ── 5. МАСШТАБ И ДЕЛЕНИЯ ─────────────────────────────────────────────── */
  E.niceStep = function (span, target) {
    var raw = span / (target || 8);
    var p = Math.pow(10, Math.floor(Math.log10(raw)));
    var m = raw / p;
    var step = m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10;
    return step * p;
  };
  E.niceCeil = function (v) {
    if (!(v > 0)) return 10;
    var p = Math.pow(10, Math.floor(Math.log10(v)));
    var steps = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
    for (var i = 0; i < steps.length; i++) if (steps[i] * p >= v - 1e-9) return steps[i] * p;
    return 10 * p;
  };
  function ticks(lo, hi, target) {
    var st = E.niceStep(hi - lo, target);
    var out = [], v = Math.ceil(lo / st - 1e-9) * st;
    for (; v <= hi + st * 1e-6; v += st) out.push(Math.round(v / st) * st);
    return { step: st, list: out };
  }
  E.ticks = ticks;

  /* ── 6. ГЕОМЕТРИЯ ГРАФИКА ─────────────────────────────────────────────
     Панель — прямоугольник холста со своим окном и шкалами (как registerPanel
     в calc2). Поля оставлены под цифры делений, чтобы ничто не лежало на кривых. */
  /* Окно с учётом ручных границ («Вид графика») и масштаба кнопками:
     lock = {x1, y1} — верх осей вручную; view = {k, px, py} — во сколько раз
     приблизили и куда сдвинули центр (в долях окна). */
  E.viewWindow = function (win, lock, view) {
    var w = { x0: win.x0, x1: win.x1, y0: win.y0, y1: win.y1 };
    if (lock) {
      if (lock.x1 > w.x0) w.x1 = +lock.x1;
      if (lock.y1 > w.y0) w.y1 = +lock.y1;
      // «Только первая четверть» выключена: показываем и отрицательную часть
      if (lock.full && w.x0 >= 0 && w.y0 >= 0) { w.x0 = -(w.x1 - w.x0) * 0.12; w.y0 = -(w.y1 - w.y0) * 0.12; }
    }
    if (view && (view.k !== 1 || view.px || view.py)) {
      var k = view.k || 1, W = w.x1 - w.x0, H = w.y1 - w.y0;
      var cx = w.x0 + W / 2 + (view.px || 0) * W, cy = w.y0 + H / 2 + (view.py || 0) * H;
      w = { x0: cx - W / k / 2, x1: cx + W / k / 2, y0: cy - H / k / 2, y1: cy + H / k / 2 };
    }
    return w;
  };
  E.panel = function (box, win, opt) {
    opt = opt || {};
    var m = opt.margin || { l: 46, r: 34, t: 32, b: 32 };
    var plot = { x: box.x + m.l, y: box.y + m.t, w: Math.max(40, box.w - m.l - m.r), h: Math.max(40, box.h - m.t - m.b) };
    win = E.viewWindow(win, opt.lock, opt.view);
    var P = {
      id: opt.id || 'main', box: box, win: win, plot: plot,
      sx: function (x) { return plot.x + (x - win.x0) / (win.x1 - win.x0) * plot.w; },
      sy: function (y) { return plot.y + plot.h - (y - win.y0) / (win.y1 - win.y0) * plot.h; },
      ix: function (px) { return win.x0 + (px - plot.x) / plot.w * (win.x1 - win.x0); },
      iy: function (py) { return win.y0 + (plot.y + plot.h - py) / plot.h * (win.y1 - win.y0); }
    };
    var gx = ticks(win.x0, win.x1, opt.xTicks || Math.max(4, Math.round(plot.w / 68)));
    var gy = ticks(win.y0, win.y1, opt.yTicks || Math.max(4, Math.round(plot.h / 54)));
    var dense = opt.grid === 'dense';
    var grid = [];
    if (opt.grid !== 'none') {
      var sub = dense ? 2 : 1;
      for (var i = 0; i < gx.list.length * sub; i++) {
        var vx = gx.list[0] + i * gx.step / sub;
        if (vx < win.x0 - 1e-9 || vx > win.x1 + 1e-9) continue;
        grid.push({ x1: r1(P.sx(vx)), y1: plot.y, x2: r1(P.sx(vx)), y2: plot.y + plot.h, major: i % sub === 0 });
      }
      for (var j = 0; j < gy.list.length * sub; j++) {
        var vy = gy.list[0] + j * gy.step / sub;
        if (vy < win.y0 - 1e-9 || vy > win.y1 + 1e-9) continue;
        grid.push({ x1: plot.x, y1: r1(P.sy(vy)), x2: plot.x + plot.w, y2: r1(P.sy(vy)), major: j % sub === 0 });
      }
    }
    // Оси: через ноль, если он в окне, иначе по краю.
    var axY = (win.y0 <= 0 && win.y1 >= 0) ? P.sy(0) : plot.y + plot.h;
    var axX = (win.x0 <= 0 && win.x1 >= 0) ? P.sx(0) : plot.x;
    P.axis = {
      x: { x1: plot.x, y1: r1(axY), x2: plot.x + plot.w + 8, y2: r1(axY) },
      y: { x1: r1(axX), y1: plot.y + plot.h, x2: r1(axX), y2: plot.y - 8 },
      arrowX: 'M' + (plot.x + plot.w + 9) + ',' + r1(axY) + ' l-9,-4 l0,8 z',
      arrowY: 'M' + r1(axX) + ',' + (plot.y - 9) + ' l-4,9 l8,0 z',
      // имена осей — у концов стрелок, вне поля делений: Q справа от стрелки, P над стрелкой
      nameX: { x: plot.x + plot.w + 13, y: r1(axY) + 6, t: (opt.names && opt.names.x) || opt.xName || 'Q' },
      nameY: { x: r1(axX), y: plot.y - 15, t: (opt.names && opt.names.y) || opt.yName || 'P' }
    };
    var hideX = opt.hideTicksX || [], hideY = opt.hideTicksY || [];
    P.ticksX = gx.list.filter(function (v) { return v >= win.x0 - 1e-9 && v <= win.x1 + 1e-9; })
      .filter(function (v) { return !(v === 0 && win.y0 < 0 && win.x0 < 0); })
      .filter(function (v) { return hideX.every(function (h) { return Math.abs(h - v) > gx.step * 0.34; }); })
      .map(function (v) { return { x: r1(P.sx(v)), y: r1(axY) + 17, t: fmt(v, 3) }; });
    P.ticksY = gy.list.filter(function (v) { return v >= win.y0 - 1e-9 && v <= win.y1 + 1e-9; })
      .filter(function (v) { return !(v === 0 && win.x0 < 0 && win.y0 < 0); })
      .filter(function (v) { return !(v === 0 && win.x0 === 0 && win.y0 === 0); })
      .filter(function (v) { return hideY.every(function (h) { return Math.abs(h - v) > gy.step * 0.34; }); })
      .map(function (v) { return { x: r1(axX) - 7, y: r1(P.sy(v)) + 4, t: fmt(v, 3) }; });
    P.grid = grid;
    P.stepX = gx.step; P.stepY = gy.step;
    return P;
  };
  function r1(v) { return Math.round(v * 10) / 10; }
  E.r1 = r1;

  /* Путь кривой y = f(x) в панели; разрывы — на NaN и на скачках за окно. */
  E.pathOf = function (f, P, x0, x1, n, breaks) {
    var w = P.win;
    var a = Math.max(x0 === undefined ? w.x0 : x0, w.x0), b = Math.min(x1 === undefined ? w.x1 : x1, w.x1);
    if (!(b > a)) return '';
    n = n || 220;
    var ylo = w.y0 - (w.y1 - w.y0) * 2, yhi = w.y1 + (w.y1 - w.y0) * 2;
    var eps = (w.x1 - w.x0) * 1e-7, jump = (w.y1 - w.y0) * 2e-3;
    var bks = (breaks || []).filter(function (x) { return x > a + eps && x < b - eps; }).sort(function (p, q) { return p - q; });
    var d = '', pen = false;
    function put(x, y) {
      if (!isFinite(y) || y < ylo || y > yhi) { pen = false; return; }
      d += (pen ? ' L' : ' M') + r1(P.sx(x)) + ',' + r1(P.sy(y));
      pen = true;
    }
    // излом получает свой узел (линия проходит ровно через него), на скачке перо поднимается
    var segs = [a].concat(bks, [b]);
    for (var s = 0; s < segs.length - 1; s++) {
      var lo = segs[s], hi = segs[s + 1];
      var m = Math.max(2, Math.round(n * (hi - lo) / (b - a)));
      if (s > 0) {
        var yl = f(lo - eps), yr = f(lo + eps);
        if (!isFinite(yl) || !isFinite(yr) || Math.abs(yl - yr) > jump) pen = false;
        put(lo, yr);
      } else { var y0 = f(lo); put(lo, isFinite(y0) ? y0 : f(lo + eps)); }   // край области: берём предел изнутри
      for (var i = 1; i < m; i++) { var x = lo + (hi - lo) * i / m; put(x, f(x)); }
      if (s < segs.length - 2) put(hi, f(hi - eps));
      else { var y1 = f(hi); put(hi, isFinite(y1) ? y1 : f(hi - eps)); }
    }
    return d.trim();
  };
  /* Скачки функции в изломах: слева и справа от границы значения разные.
     inc — с какой стороны точка принадлежит графику ('l' или 'r'). */
  E.jumpsOf = function (f, breaks, P) {
    var w = P.win, eps = (w.x1 - w.x0) * 1e-7, jump = (w.y1 - w.y0) * 2e-3, out = [];
    (breaks || []).forEach(function (b) {
      if (b < w.x0 || b > w.x1) return;
      var yl = f(b - eps), yr = f(b + eps), yb = f(b);
      var hasL = isFinite(yl), hasR = isFinite(yr);
      if (hasL && hasR && Math.abs(yl - yr) <= jump) return;
      if (!hasL && !hasR) return;
      out.push({ x: b, yl: hasL ? yl : null, yr: hasR ? yr : null, inc: isFinite(yb) && hasR && Math.abs(yb - yr) <= jump ? 'r' : isFinite(yb) && hasL && Math.abs(yb - yl) <= jump ? 'l' : '' });
    });
    return out;
  };
  /* Путь по точкам в координатах модели. */
  E.pathPts = function (pts, P) {
    return pts.map(function (p, i) { return (i ? 'L' : 'M') + r1(P.sx(p[0])) + ',' + r1(P.sy(p[1])); }).join(' ');
  };
  /* Многоугольник между верхней и нижней функциями на [x0, x1]. */
  E.polyBetween = function (fTop, fBot, x0, x1, P, n) {
    if (!(x1 > x0)) return '';
    n = n || 80;
    var top = [], bot = [];
    for (var i = 0; i <= n; i++) {
      var x = x0 + (x1 - x0) * i / n;
      var yt = fTop(x), yb = fBot(x);
      if (!isFinite(yt) || !isFinite(yb)) continue;
      top.push(r1(P.sx(x)) + ',' + r1(P.sy(yt)));
      bot.push(r1(P.sx(x)) + ',' + r1(P.sy(yb)));
    }
    return top.concat(bot.reverse()).join(' ');
  };
  E.rectPoly = function (x0, x1, y0, y1, P) {
    var a = r1(P.sx(x0)), b = r1(P.sx(x1)), c = r1(P.sy(y0)), d = r1(P.sy(y1));
    return a + ',' + c + ' ' + b + ',' + c + ' ' + b + ',' + d + ' ' + a + ',' + d;
  };
  E.clamp = function (v, lo, hi) { return Math.max(lo, Math.min(hi, v)); };

  /* Подпись кривой у края окна: последняя видимая точка, чуть в сторону. */
  E.endLabel = function (f, P, x0, x1, prefer) {
    var w = P.win;
    var a = Math.max(x0 === undefined ? w.x0 : x0, w.x0), b = Math.min(x1 === undefined ? w.x1 : x1, w.x1);
    var n = 160, best = null;
    for (var i = n; i >= 0; i--) {
      var x = a + (b - a) * i / n, y = f(x);
      if (isFinite(y) && y >= w.y0 && y <= w.y1) { best = { x: x, y: y }; break; }
    }
    if (!best) return null;
    var px = P.sx(best.x), py = P.sy(best.y);
    var nearRight = px > P.plot.x + P.plot.w - 30, nearTop = py < P.plot.y + 24;
    return {
      x: r1(nearRight ? px - 10 : px + 8),
      y: r1(nearTop ? py + 18 : py - 8),
      anchor: nearRight ? 'end' : 'start'
    };
  };
})();
