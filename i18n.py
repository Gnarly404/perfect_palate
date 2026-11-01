"""Perfect Palate - English / Swahili interface strings for server-rendered pages.

Only the interface is translated (navigation, footer, offline page, Cook Mode).  The recipes
themselves - titles, ingredients, instructions - are English in the dataset and stay English.
The Swahili text is a first draft and should be reviewed by a native speaker before launch.
"""
from urllib.parse import urlparse

LANGS = ('en', 'sw')
LANG_NAMES = {'en': 'English', 'sw': 'Kiswahili'}
COOKIE = 'pp_lang'

STRINGS = {
    'en': {
        'nav.home_label': 'Perfect Palate home', 'nav.main': 'Main',
        'nav.dashboard': 'Dashboard', 'nav.recipes': 'Recipes', 'nav.plan': 'Meal Plan',
        'nav.favourites': 'Favourites', 'nav.shopping': 'Shopping', 'nav.tips': 'Tips',
        'nav.profile': 'Your profile', 'nav.prefs': 'Dietary preferences', 'nav.signed_in': 'Signed in',
        'nav.logout': 'Log out', 'nav.signin': 'Sign in', 'nav.cook_now': 'Cook now',
        'nav.open_menu': 'Open menu', 'nav.close_menu': 'Close menu',
        'nav.profile_edit': 'View and edit your profile', 'nav.language': 'Language',
        'foot.taste': 'Taste the', 'foot.origin': 'origin.',
        'foot.lede': '{n} Kenyan and East African recipes, each rated for difficulty and nutrition, and read aloud one step at a time while you cook.',
        'foot.browse': 'Browse recipes', 'foot.share': 'Share Perfect Palate', 'foot.cook': 'Cook',
        'foot.tips': 'Cooking tips', 'foot.planner': 'Meal planner', 'foot.shopping': 'Shopping list',
        'foot.kitchen': 'Your kitchen', 'foot.start': 'Get started', 'foot.signin_up': 'Sign in or create an account',
        'foot.about': 'About Perfect Palate', 'foot.good': 'Good to know.',
        'foot.note': 'Nutrition figures are estimates worked out from each ingredient list, and diet and allergy filters are a guide, not a guarantee. Always check the ingredients yourself, and ask a doctor or dietitian about medical diets. Perfect Palate is not medical advice.',
        'foot.made': 'Made in Kenya with', 'foot.in': 'in Nairobi', 'foot.top': 'Back to top',
        'foot.install': 'Install the app', 'foot.copied': 'Link copied', 'foot.copy_prompt': 'Copy this link:',
        'foot.share_text': 'Kenyan and East African recipes, read aloud as you cook.',
        'offline.title': 'You are offline', 'offline.head1': 'No signal,', 'offline.head2': 'still cooking.',
        'offline.body': 'This page is not saved on your phone yet. Recipes you have opened before, and Cook Mode, still work without a connection.',
        'offline.recipes': 'Open saved recipes', 'offline.retry': 'Try again',
    },
    'sw': {
        'nav.home_label': 'Perfect Palate nyumbani', 'nav.main': 'Kuu',
        'nav.dashboard': 'Dashibodi', 'nav.recipes': 'Mapishi', 'nav.plan': 'Ratiba ya Milo',
        'nav.favourites': 'Vipendwa', 'nav.shopping': 'Ununuzi', 'nav.tips': 'Vidokezo',
        'nav.profile': 'Wasifu wako', 'nav.prefs': 'Mapendeleo ya chakula', 'nav.signed_in': 'Umeingia',
        'nav.logout': 'Toka', 'nav.signin': 'Ingia', 'nav.cook_now': 'Pika sasa',
        'nav.open_menu': 'Fungua menyu', 'nav.close_menu': 'Funga menyu',
        'nav.profile_edit': 'Tazama na hariri wasifu wako', 'nav.language': 'Lugha',
        'foot.taste': 'Onja', 'foot.origin': 'asili.',
        'foot.lede': 'Mapishi {n} ya Kenya na Afrika Mashariki, kila moja likipimwa ugumu na lishe, na kusomwa kwa sauti hatua kwa hatua unapopika.',
        'foot.browse': 'Tazama mapishi', 'foot.share': 'Shiriki Perfect Palate', 'foot.cook': 'Pika',
        'foot.tips': 'Vidokezo vya kupika', 'foot.planner': 'Mpangaji wa milo', 'foot.shopping': 'Orodha ya ununuzi',
        'foot.kitchen': 'Jiko lako', 'foot.start': 'Anza', 'foot.signin_up': 'Ingia au fungua akaunti',
        'foot.about': 'Kuhusu Perfect Palate', 'foot.good': 'Ni vizuri kujua.',
        'foot.note': 'Takwimu za lishe ni makadirio yanayotokana na orodha ya viungo vya kila mapishi, na vichujio vya lishe na mzio ni mwongozo tu, si hakikisho. Daima kagua viungo mwenyewe, na muulize daktari au mtaalamu wa lishe kuhusu mlo wa kitabibu. Perfect Palate si ushauri wa kimatibabu.',
        'foot.made': 'Imetengenezwa Kenya kwa', 'foot.in': 'jijini Nairobi', 'foot.top': 'Rudi juu',
        'foot.install': 'Sakinisha programu', 'foot.copied': 'Kiungo kimenakiliwa', 'foot.copy_prompt': 'Nakili kiungo hiki:',
        'foot.share_text': 'Mapishi ya Kenya na Afrika Mashariki, yanayosomwa kwa sauti unapopika.',
        'offline.title': 'Huna mtandao', 'offline.head1': 'Hakuna mtandao,', 'offline.head2': 'bado tunapika.',
        'offline.body': 'Ukurasa huu bado haujahifadhiwa kwenye simu yako. Mapishi uliyowahi kufungua, na Hali ya Kupika, bado yanafanya kazi bila mtandao.',
        'offline.recipes': 'Fungua mapishi yaliyohifadhiwa', 'offline.retry': 'Jaribu tena',
    },
}


def best_language(cookie_value, accept_languages):
    """Cookie choice wins; otherwise Swahili only if the browser asks for it ahead of English."""
    if cookie_value in LANGS:
        return cookie_value
    for code in accept_languages:
        code = code.lower()[:2]
        if code in LANGS:
            return code
    return 'en'


def translate(key, lang='en', **vars):
    text = STRINGS.get(lang, STRINGS['en']).get(key) or STRINGS['en'].get(key) or key
    return text.format(**vars) if vars else text


def safe_next(target, fallback='/'):
    """Only same-site relative paths, so the language switch cannot be used as an open redirect."""
    if not target or not target.startswith('/') or target.startswith('//') or '\\' in target:
        return fallback
    parts = urlparse(target)
    return target if not parts.scheme and not parts.netloc else fallback
