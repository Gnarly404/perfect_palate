/* Perfect Palate - small English / Swahili string table for client-side text.
 * Server-rendered pages get the same strings from i18n.py.  The language is the <html lang>.
 * Swahili strings are first-draft translations and should be checked by a native speaker.
 */
(function (root) {
  'use strict';
  const S = {
    en: {
      'ui.eyebrow': 'Personalised For You', 'ui.h1': 'Your <em>Curated</em><strong>Recipes</strong>',
      'ui.search': 'Search recipes, ingredients…',
      'ui.any': 'Any', 'ui.easy': 'Easy', 'ui.medium': 'Medium', 'ui.hard': 'Hard',
      'ui.ingredients': 'Ingredients', 'ui.instructions': 'Instructions', 'ui.nutrition': 'Nutrition per serving',
      'ui.tips': 'Tips for this recipe', 'ui.share': 'Share this recipe', 'ui.reviews': 'Ratings &amp; Reviews',
      'ui.back': 'Back', 'ui.startCook': '🔥 Start Cook Mode', 'ui.cookMode': 'Cook Mode', 'ui.readAloud': 'Read Aloud',
      'ui.stopReading': 'Stop Reading', 'ui.exit': '✕ Exit', 'ui.next': 'Next', 'ui.step': 'STEP',
      'ui.startTimer': 'start timer', 'ui.pauseTimer': 'tap to pause', 'ui.done': 'Done!', 'ui.timerDone': '⏰ Timer complete!',
      'ui.servings': 'Servings', 'ui.servingsWord': 'servings', 'ui.reset': 'Reset', 'ui.fewer': 'Fewer servings', 'ui.more': 'More servings',
      'ui.scaled': 'Amounts are scaled from {a} to {b} servings. Amounts written inside the instructions are not scaled, and cooking times and pan sizes may need adjusting.',
      'cook.awake': 'Screen stays on while you cook',
      'cook.awakeNo': 'This browser cannot keep the screen on, so it may dim while you cook.',
      'cook.voice': 'Voice commands',
      'cook.voiceStop': 'Stop voice',
      'cook.voiceHint': 'Listening. Say "next", "back", "repeat" or "start timer".',
      'cook.voiceDenied': 'Microphone is blocked. Allow it in your browser site settings to use voice commands.',
      'cook.voiceNet': 'Voice commands need an internet connection in this browser, and you are offline.',
      'cook.voiceNo': 'Voice commands are not supported in this browser. Chrome and Edge support them.',
      'cook.voiceHeard': 'Heard: {t}',
      'cook.ingredients': 'Ingredients for {n} servings',
      'cook.scaledNote': 'Amounts inside the steps are for the original {n} servings.',
      'cook.noTimer': 'No timer on this step.',
      'cook.last': 'That was the last step.',
      'cook.first': 'This is the first step.',
      'offline.ready': 'Saved for offline cooking',
      'offline.update': 'A new version is ready. Reload to update.',
      'offline.reload': 'Reload',
      'offline.offline': 'You are offline. Saved recipes still work.',
      'install.cta': 'Install app',
      'cost.title': 'Estimated cost',
      'cost.total': 'About KES {lo}–{hi} for {n} servings',
      'cost.per': 'KES {lo}–{hi} per serving',
      'cost.note': 'A rough range, not a quote. {cov}% of the ingredients were priced, and only {ver}% of the amount rests on official Kenyan prices (KNBS, September 2026); the rest are developer estimates. Real prices vary by town, season and shop.',
      'cost.none': 'Not enough ingredients could be priced to give a useful estimate.',
    },
    sw: {
      'ui.eyebrow': 'Umetengenezewa Wewe', 'ui.h1': 'Mapishi <em>Yaliyochaguliwa</em><strong>Kwako</strong>',
      'ui.search': 'Tafuta mapishi, viungo…',
      'ui.any': 'Yoyote', 'ui.easy': 'Rahisi', 'ui.medium': 'Wastani', 'ui.hard': 'Ngumu',
      'ui.ingredients': 'Viungo', 'ui.instructions': 'Maelekezo', 'ui.nutrition': 'Lishe kwa kila mtu',
      'ui.tips': 'Vidokezo vya mapishi haya', 'ui.share': 'Shiriki mapishi haya', 'ui.reviews': 'Ukadiriaji na Maoni',
      'ui.back': 'Rudi', 'ui.startCook': '🔥 Anza Kupika', 'ui.cookMode': 'Hali ya Kupika', 'ui.readAloud': 'Soma kwa Sauti',
      'ui.stopReading': 'Acha Kusoma', 'ui.exit': '✕ Toka', 'ui.next': 'Mbele', 'ui.step': 'HATUA',
      'ui.startTimer': 'anza kipima muda', 'ui.pauseTimer': 'gusa kusitisha', 'ui.done': 'Imekwisha!', 'ui.timerDone': '⏰ Kipima muda kimekwisha!',
      'ui.servings': 'Watu', 'ui.servingsWord': 'watu', 'ui.reset': 'Weka upya', 'ui.fewer': 'Watu wachache', 'ui.more': 'Watu zaidi',
      'ui.scaled': 'Vipimo vimebadilishwa kutoka watu {a} hadi {b}. Vipimo vilivyoandikwa ndani ya maelekezo havijabadilishwa, na muda wa kupika na ukubwa wa sufuria vinaweza kuhitaji marekebisho.',
      'cook.awake': 'Skrini itabaki imewaka unapopika',
      'cook.awakeNo': 'Kivinjari hiki hakiwezi kuweka skrini ikiwaka, kwa hiyo inaweza kuzima unapopika.',
      'cook.voice': 'Amri za sauti',
      'cook.voiceStop': 'Zima sauti',
      'cook.voiceHint': 'Nasikiliza. Sema "mbele", "nyuma", "rudia" au "anza kipima muda".',
      'cook.voiceDenied': 'Maikrofoni imezuiwa. Iruhusu kwenye mipangilio ya tovuti ya kivinjari chako ili utumie amri za sauti.',
      'cook.voiceNet': 'Amri za sauti zinahitaji intaneti kwenye kivinjari hiki, na huna mtandao sasa.',
      'cook.voiceNo': 'Kivinjari hiki hakitumii amri za sauti. Chrome na Edge zinazitumia.',
      'cook.voiceHeard': 'Nimesikia: {t}',
      'cook.ingredients': 'Viungo vya watu {n}',
      'cook.scaledNote': 'Vipimo vilivyo ndani ya hatua ni vya watu {n} wa mapishi ya awali.',
      'cook.noTimer': 'Hatua hii haina kipima muda.',
      'cook.last': 'Hiyo ilikuwa hatua ya mwisho.',
      'cook.first': 'Hii ndiyo hatua ya kwanza.',
      'offline.ready': 'Imehifadhiwa kwa kupika bila mtandao',
      'offline.update': 'Toleo jipya liko tayari. Pakia upya ili usasishe.',
      'offline.reload': 'Pakia upya',
      'offline.offline': 'Huna mtandao. Mapishi yaliyohifadhiwa bado yanafanya kazi.',
      'install.cta': 'Sakinisha programu',
      'cost.title': 'Makadirio ya gharama',
      'cost.total': 'Takriban KES {lo}–{hi} kwa watu {n}',
      'cost.per': 'KES {lo}–{hi} kwa kila mtu',
      'cost.note': 'Kiwango cha makadirio, si bei rasmi. Viungo {cov}% vilipatiwa bei, na ni {ver}% tu ya kiasi kinachotokana na bei rasmi za Kenya (KNBS, Septemba 2026); zilizobaki ni makadirio ya msanidi. Bei halisi hutofautiana kwa mji, msimu na duka.',
      'cost.none': 'Viungo vilivyopatiwa bei havitoshi kutoa makadirio yenye maana.',
    },
  };
  function lang() {
    const l = (document.documentElement.lang || 'en').slice(0, 2).toLowerCase();
    return S[l] ? l : 'en';
  }
  function t(key, vars) {
    let s = (S[lang()] && S[lang()][key]) || S.en[key] || key;
    if (vars) Object.keys(vars).forEach(k => { s = s.split('{' + k + '}').join(vars[k]); });
    return s;
  }
  /** Fill [data-i18n] (text), [data-i18n-html] (markup we wrote ourselves) and [data-i18n-placeholder]. */
  function apply(scope) {
    (scope || document).querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
    (scope || document).querySelectorAll('[data-i18n-html]').forEach(el => { el.innerHTML = t(el.dataset.i18nHtml); });
    (scope || document).querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  }
  root.PPI18N = { t, lang, apply, strings: S };
})(window);
