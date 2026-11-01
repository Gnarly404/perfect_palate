/* Perfect Palate - ingredient list parsing and servings scaling.
 * Pure functions, no DOM, so they can be tested in Node:  node static/js/recipe-tools.test.js
 */
(function (root) {
  'use strict';

  const VULGAR = { '¼': 0.25, '½': 0.5, '¾': 0.75, '⅓': 1 / 3, '⅔': 2 / 3, '⅛': 0.125, '⅜': 0.375, '⅝': 0.625, '⅞': 0.875 };
  const VG = Object.keys(VULGAR).join('');
  // one number: "1 1/2", "1½", "1/2", "2.5", "3"
  const NUM = '(?:\\d+\\s+\\d+\\s*/\\s*\\d+|\\d+\\s*[' + VG + ']|[' + VG + ']|\\d+\\s*/\\s*\\d+|\\d+(?:[.,]\\d+)?)';
  const RANGE = new RegExp('^(' + NUM + ')(?:\\s*(?:-|–|to)\\s*(' + NUM + '))?', 'i');

  function toNumber(s) {
    s = s.trim().replace(',', '.');
    let m;
    if ((m = s.match(/^(\d+)\s+(\d+)\s*\/\s*(\d+)$/))) return +m[1] + m[2] / m[3];
    if ((m = s.match(new RegExp('^(\\d+)\\s*([' + VG + '])$')))) return +m[1] + VULGAR[m[2]];
    if (VULGAR[s] !== undefined) return VULGAR[s];
    if ((m = s.match(/^(\d+)\s*\/\s*(\d+)$/))) return +m[1] / m[2];
    return parseFloat(s);
  }

  const FRACS = [[0, ''], [1 / 8, '⅛'], [1 / 4, '¼'], [1 / 3, '⅓'], [1 / 2, '½'], [2 / 3, '⅔'], [3 / 4, '¾'], [7 / 8, '⅞'], [1, '']];

  /** Format a quantity the way a cook writes it: 1½, ¾, 12, 2.5 kg stays 2.5. */
  function formatQty(x, unit) {
    if (!isFinite(x) || x <= 0) return '0';
    const metric = /^(g|kg|ml|l|litres?|liters?)\b/i.test(unit || '');
    if (x >= 20) return String(metric && x >= 100 ? Math.round(x / 5) * 5 : Math.round(x));
    if (metric && x >= 3) return String(Math.round(x * 10) / 10).replace(/\.0$/, '');
    const whole = Math.floor(x), frac = x - whole;
    let best = FRACS[0], bd = 9;
    for (const f of FRACS) { const d = Math.abs(frac - f[0]); if (d < bd) { bd = d; best = f; } }
    let w = whole, sym = best[1];
    if (best[0] === 1) { w += 1; sym = ''; }
    if (w === 0 && !sym) return '⅛';                 // never show 0 for something that was non-zero
    return (w ? String(w) : '') + sym;
  }

  /** Split an ingredient string into display items, keeping "(3 cloves, minced)" together
   *  and attaching stray prep words ("diced") to the ingredient before them. */
  function splitIngredients(raw) {
    const parts = String(raw || '').replace(/▢/g, ',').split(/,\s*(?![^()]*\))/).map(p => p.trim()).filter(Boolean);
    const out = [];
    for (const p of parts) {
      const isHeader = /:$/.test(p);
      const startsQty = new RegExp('^' + NUM).test(p);
      if (!isHeader && !startsQty && out.length && out[out.length - 1].kind === 'lead' && p.length <= 40 && !/\(/.test(p)
          && !/^(salt|pepper|water|oil|sugar|to taste)/i.test(p)) {
        out[out.length - 1].text += ', ' + p;         // "1 small red onion" + "diced"
        continue;
      }
      out.push({ text: p, kind: isHeader ? 'header' : startsQty ? 'lead' : 'named' });
    }
    return out;
  }

  function scaleNumberText(numText, factor, unit) {
    const m = numText.match(RANGE);
    if (!m) return null;
    const a = toNumber(m[1]);
    if (!isFinite(a)) return null;
    let s = formatQty(a * factor, unit);
    if (m[2]) {
      const b = toNumber(m[2]);
      s += '–' + formatQty(b * factor, unit);
    }
    return { text: s, len: m[0].length };
  }

  /** Scale one ingredient line by `factor`. Returns {text, scaled}. */
  function scaleIngredient(text, factor) {
    if (!factor || Math.abs(factor - 1) < 1e-9) return { text, scaled: false };
    // "Name (1 cup, chopped)"  - scale the leading quantity inside the last parenthesis
    const paren = text.match(/^(.*\()\s*(\d[^),]*?|[¼½¾⅓⅔⅛⅜⅝⅞][^),]*?)(\s*(?:,[^)]*)?\))$/);
    if (paren && !new RegExp('^' + NUM).test(text)) {
      const body = paren[2];
      const unit = (body.replace(RANGE, '').trim().match(/^[a-zA-Z]+/) || [''])[0];
      const r = scaleNumberText(body, factor, unit);
      if (r) return { text: paren[1] + r.text + body.slice(r.len) + paren[3], scaled: true };
    }
    // "2 cups of flour" / "400g of chicken" / "6 medium potatoes"
    if (new RegExp('^' + NUM).test(text)) {
      const unit = (text.replace(RANGE, '').trim().match(/^[a-zA-Z]+/) || [''])[0];
      const r = scaleNumberText(text, factor, unit);
      if (r) return { text: r.text + text.slice(r.len), scaled: true };
    }
    return { text, scaled: false };
  }

  function scaleIngredients(raw, factor) {
    return splitIngredients(raw).map(it => it.kind === 'header' ? { text: it.text, header: true, scaled: false } : Object.assign({ header: false }, scaleIngredient(it.text, factor)));
  }

  // Spoken commands (English and Swahili). Only short utterances count, so a sentence like
  // "add the next ingredient" said to someone in the kitchen does not move the recipe on.
  const COMMANDS = [
    ['stop-timer', /\b(stop|cancel|pause)( the)? timer\b|\b(simamisha|acha|sitisha) kipima muda\b/],
    ['timer', /\b(start|set)( the)? timer\b|^timer$|\b(anza|washa) kipima muda\b|^kipima muda$/],
    ['next', /^(next|next step|continue|go on|go next|done|okay next|forward)$|^(mbele|endelea|hatua inayofuata|inayofuata|nimemaliza)$/],
    ['back', /^(back|go back|previous|previous step|last step)$|^(nyuma|rudi|rudi nyuma|hatua iliyopita|iliyopita)$/],
    ['repeat', /^(repeat|say again|again|read|read it|read that|read step|repeat that)$|^(rudia|soma|soma tena|sema tena)$/],
  ];
  function matchCommand(transcript) {
    const t = String(transcript || '').toLowerCase().replace(/[.,!?;:]/g, ' ').replace(/\s+/g, ' ').trim();
    if (!t || t.split(' ').length > 4) return null;
    for (const [name, rx] of COMMANDS) if (rx.test(t)) return name;
    return null;
  }

  const api = { matchCommand, splitIngredients, scaleIngredient, scaleIngredients, formatQty, toNumber };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.PPTools = api;
})(typeof window !== 'undefined' ? window : globalThis);
