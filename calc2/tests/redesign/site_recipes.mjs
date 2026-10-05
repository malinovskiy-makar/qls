/* Рецепты состояний сайта под эталоны макета (reference/INDEX.md).
   Набор → список { file, w, h, theme, key, run(page), pending }.
   pending — рецепт появится вместе с частью нового экрана, которой он нужен. */

const KEYS = ['m-graph', 'm-transform', 'm-optimum', 'm-tangent', 'm-minmax', 'm-constraint', 'ppf', 'ppfsum', 'trade',
  'tradeprice', 'sd', 'sdsum', 'taxes', 'ceil', 'quota', 'elast', 'ext', 'prod', 'costs', 'plants', 'isoquant', 'mono',
  'mono-nat', 'mono-d1', 'mono-d3', 'mono-kink', 'labor', 'labor-mono', 'labor-union', 'labor-bilat', 'smallopen',
  'monoexport', 'consumer', 'cons-slutsky', 'adas', 'islm', 'phillips', 'money', 'loanable', 'fx', 'ineq', 'laffer'];
const DARK = ['sd', 'taxes', 'ceil', 'mono', 'costs', 'm-tangent', 'islm', 'ppf', 'labor'];
const N1280 = ['sd', 'taxes', 'ceil', 'mono', 'costs', 'm-tangent'];

export const RECIPES = {
  models: KEYS.map(k => ({ file: k + '.png', w: 1440, h: 760, key: k })),
  models_dark: DARK.map(k => ({ file: k + '.png', w: 1440, h: 760, key: k, theme: 'dark' })),
  models_1280: N1280.map(k => ({ file: k + '.png', w: 1280, h: 700, key: k })),
};
