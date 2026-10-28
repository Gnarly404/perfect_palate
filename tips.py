"""
Perfect Palate - Cooking tips and techniques

A small, hand-written library of tips. Each tip has an id, a short title, the advice
itself, and a `when` rule that decides which recipes it is shown on (matched against
the recipe's ingredients, instructions and category). Food-safety tips are marked
kind='safety' and are always listed first.

Food-safety figures follow the US government's foodsafety.gov minimum-temperature chart
(poultry 165F / 74C, ground beef 160F / 71C, whole cuts of beef and pork 145F / 63C with a
3 minute rest, fish 145F / 63C) and university-extension guidance on kidney beans, cassava
and cooked rice.
"""
import re

# kind: 'safety' | 'technique' | 'flavour' | 'kenyan'
TIPS = [
    # ---------------------------------------------------------------- safety
    {'id': 'safe-chicken', 'kind': 'safety', 'title': 'Cook poultry to 74 C (165 F)',
     'text': 'Check the thickest part of the chicken with a thermometer. Juices running clear is not a reliable sign of doneness.',
     'when': {'ing': r'\bchicken\b|\bturkey\b|\bkienyeji\b|\bgizzard|\bduck\b'}},
    {'id': 'safe-mince', 'kind': 'safety', 'title': 'Cook minced meat through to 71 C (160 F)',
     'text': 'Ground beef and sausage must be cooked all the way through, because grinding spreads bacteria from the surface into the middle.',
     'when': {'ing': r'\bground beef|\bminced? (beef|meat|lamb|goat)|\bmince\b|\bsausage|\bmeatball|\bburger'}},
    {'id': 'safe-beef-pork', 'kind': 'safety', 'title': 'Steaks, chops and roasts: 63 C (145 F) plus a rest',
     'text': 'Cook whole cuts of beef, pork and lamb to 63 C (145 F), then rest them for 3 minutes before cutting.',
     'when': {'ing': r'\bsteak|\bribs?\b|\broast|\bpork|\bbrisket|\bflank|\boxtail|\blamb|\bmutton|\bgoat|\bmbuzi'}},
    {'id': 'safe-fish', 'kind': 'safety', 'title': 'Fish is done at 63 C (145 F)',
     'text': 'The flesh should turn opaque and flake easily with a fork. Prawns and shrimp are done when pearly white.',
     'when': {'ing': r'\bfish\b|\btilapia|\bsalmon|\bsnapper|\bomena|\bperch|\bcod\b|\btuna|\bshrimp|\bprawn|\bfillet'}},
    {'id': 'safe-beans', 'kind': 'safety', 'title': 'Boil dry kidney beans properly',
     'text': 'Raw red kidney beans contain a toxin that makes people sick. Soak dry beans for at least 5 hours, discard the soaking water, then boil in fresh water for at least 30 minutes. Do not cook them only in a slow cooker.',
     'when': {'ing': r'\bkidney bean|\brosecoco|\bred bean|\bbeans?\b', 'not_ing': r'\bcanned\b|\btinned\b|\bblack bean|\bgreen bean|\bfrench bean|\bcan\b'}},
    {'id': 'safe-cassava', 'kind': 'safety', 'title': 'Never eat cassava raw',
     'text': 'Cassava contains compounds that can release cyanide. Peel it completely and cook it thoroughly. Cooking alone does not remove all of it, so soaking and drying or fermenting traditionally helps for flour. If you buy a bitter variety, ask the seller how to prepare it.',
     'when': {'ing': r'\bcassava|\bmuhogo|\bmanioc'}},
    {'id': 'safe-rice', 'kind': 'safety', 'title': 'Cool leftover rice quickly',
     'text': 'Cooked rice can carry bacteria whose toxin survives reheating. Cool it as soon as you can (within about 2 hours), keep it in the fridge, and reheat only the portion you will eat.',
     'when': {'ing': r'\brice\b|\bpilau|\bbiryani'}},
    {'id': 'safe-eggs', 'kind': 'safety', 'title': 'Cook egg dishes to 71 C (160 F)',
     'text': 'Egg dishes such as omelettes, frittatas and quiche should be firm through the middle, with no runny egg.',
     'when': {'ing': r'\beggs?\b', 'cat': r'Main Dish|Breakfast|Vegetarian'}},
    {'id': 'safe-oil', 'kind': 'safety', 'title': 'Deep frying: keep water away from hot oil',
     'text': 'Pat food dry before it goes in, lower it in gently, never fill the pan more than halfway, and never leave hot oil unattended. If oil catches fire, cover the pan with a lid and turn off the heat. Do not use water.',
     'when': {'ins': r'\bdeep[- ]?fr(y|ied)|\bfry in (hot|plenty of) oil|\bheat (the )?oil|\bfor frying'}},
    {'id': 'safe-marinade', 'kind': 'safety', 'title': 'Do not reuse raw-meat marinade',
     'text': 'Marinate in the fridge. Bring a marinade to a boil before serving it as a sauce, or set some aside before it touches the raw meat.',
     'when': {'ins': r'\bmarinat'}},

    # ------------------------------------------------------------- technique
    {'id': 'mise', 'kind': 'technique', 'title': 'Prep everything before you light the stove',
     'text': 'Chop, measure and lay out ingredients first. Most Kenyan stovetop dishes move fast once the onions are in the pan.',
     'when': {'always': True}},
    {'id': 'sweat-onion', 'kind': 'technique', 'title': 'Cook onions slowly for a sweeter base',
     'text': 'Give onions 5 to 8 minutes on medium heat until soft and golden before adding tomatoes or spices. Rushing them leaves a sharp raw taste.',
     'when': {'ing': r'\bonions?\b', 'ins': r'\bsaut|\bfry|\bcook'}},
    {'id': 'tomato-cook-down', 'kind': 'technique', 'title': 'Cook tomatoes down until the oil separates',
     'text': 'For stews and sukuma wiki, let tomatoes break down into a thick paste. When oil starts to pool at the edges, the sauce has lost its raw acidity.',
     'when': {'ing': r'\btomato', 'ins': r'\bsimmer|\bstew|\bsaut|\bcook', 'not_cat': r'Salad|Beverage|Dessert'}},
    {'id': 'toast-spices', 'kind': 'technique', 'title': 'Wake up ground spices in warm oil',
     'text': 'Stir curry powder, cumin, paprika or garam masala into hot oil for 20 to 30 seconds before adding liquid. Do not let them burn.',
     'when': {'ing': r'\bcurry|\bcumin|\bpaprika|\bgaram masala|\bturmeric|\bcoriander (powder|seed)|\bmasala'}},
    {'id': 'rest-meat', 'kind': 'technique', 'title': 'Rest meat before slicing',
     'text': 'Let grilled or roasted meat rest for a few minutes under a loose cover so the juices settle and the slices stay moist.',
     'when': {'ing': r'\bsteak|\broast|\bribs?\b|\bchops?\b|\bbrisket|\bnyama choma|\bgrill'}},
    {'id': 'dont-crowd', 'kind': 'technique', 'title': 'Do not crowd the pan',
     'text': 'Too much food at once steams instead of browning. Fry meat, fritters and fries in batches.',
     'when': {'ins': r'\bfry|\bbrown|\bsear|\bgrill', 'ing': r'\bbeef|\bchicken|\bpork|\bpotato|\bcassava|\bfries|\bfritter|\bgoat|\blamb'}},
    {'id': 'dough-rest', 'kind': 'technique', 'title': 'Let dough rest',
     'text': 'Cover dough for 20 to 30 minutes after mixing. Resting relaxes the gluten, so chapati and mandazi roll out thinner and cook softer.',
     'when': {'ing': r'\bflour\b', 'cat': r'Bread|Baked Goods|Snack|Appetizer|Staple', 'ins': r'\bdough|\bknead|\broll|\bdivide'}},
    {'id': 'knead', 'kind': 'technique', 'title': 'How to tell dough is kneaded enough',
     'text': 'Press a finger into the dough. If it springs back slowly and the surface is smooth and slightly tacky rather than sticky, it is ready.',
     'when': {'ins': r'\bknead'}},
    {'id': 'chapati-layers', 'kind': 'kenyan', 'title': 'Layers in chapati come from oil and coiling',
     'text': 'Brush the rolled dough with oil, roll it into a rope, coil it like a snail, then roll it flat again. Cook on a hot, dry pan and brush with a little oil as it puffs.',
     'when': {'title': r'\bchapati|\bchapo'}},
    {'id': 'ugali-lumps', 'kind': 'kenyan', 'title': 'Smooth ugali',
     'text': 'Mix some of the flour with cold water into a smooth paste before adding it to boiling water, or add the flour gradually while stirring constantly. Keep stirring and press out lumps with the back of the spoon.',
     'when': {'title': r'\bugali|\bsima|\bposho'}},
    {'id': 'fold-batter', 'kind': 'technique', 'title': 'Fold, do not stir, delicate batters',
     'text': 'When adding flour or whipped egg to a batter, use a spatula to cut down the middle and lift from the bottom. Over-mixing makes cakes and pancakes tough.',
     'when': {'ins': r'\bfold|\bwhip|\bbatter'}},
    {'id': 'room-temp', 'kind': 'technique', 'title': 'Bring baking ingredients to room temperature',
     'text': 'Butter, eggs and milk mix more evenly when they are not cold from the fridge, which gives a more even crumb.',
     'when': {'cat': r'Dessert|Baked Goods|Bread', 'ing': r'\bbutter|\beggs?\b'}},
    {'id': 'oven-preheat', 'kind': 'technique', 'title': 'Preheat the oven fully',
     'text': 'Give the oven 10 to 15 minutes to reach temperature, and do not open the door in the first half of baking. Ovens often run hotter or cooler than the dial says, so an oven thermometer is a good investment.',
     'when': {'ins': r'\bpreheat|\boven\b|\bbake\b'}},
    {'id': 'boil-pasta', 'kind': 'technique', 'title': 'Salt your pasta water and save a cup',
     'text': 'Cook pasta in well-salted boiling water. Before draining, keep a cup of the starchy water: a splash helps the sauce cling to the pasta.',
     'when': {'ing': r'\bpasta|\bspaghetti|\blinguine|\bmacaroni|\bfettuccine|\bpenne|\btagliatelle|\balfredo'}},
    {'id': 'greens-fast', 'kind': 'kenyan', 'title': 'Keep sukuma wiki bright and tender',
     'text': 'Slice the leaves thinly and add them last. Cook for only 3 to 5 minutes with a lid on so they stay green.',
     'when': {'ing': r'\bsukuma|\bkale\b|\bcollard|\bspinach|\bmanagu|\bterere|\bmrenda|\bmoringa'}},
    {'id': 'githeri-soak', 'kind': 'kenyan', 'title': 'Soak dried maize and beans overnight',
     'text': 'Soaking shortens the cooking time and helps the grains cook evenly. Drain the soaking water and cook in fresh water.',
     'when': {'ing': r'\bgitheri|\bdried (maize|corn)|\bnyoyo|\bmaize and beans|\bcowpeas?\b|\bnjahi|\bmbaazi|\bngwaci|\bndengu|\bgreen gram|\bbeans?\b', 'not_ing': r'\bcanned\b|\bcan\b|\btinned'}},
    {'id': 'coconut-gentle', 'kind': 'technique', 'title': 'Keep coconut milk at a gentle simmer',
     'text': 'A hard boil can make coconut milk split and look oily. Stir occasionally and keep the heat low.',
     'when': {'ing': r'\bcoconut (milk|cream)'}},
    {'id': 'matoke', 'kind': 'kenyan', 'title': 'Peel green bananas under water or with oiled hands',
     'text': 'Matoke sap can stain skin and clothes. Oil your hands or peel in a bowl of water, and drop the pieces into water so they do not darken.',
     'when': {'ing': r'\bmatoke|\bgreen banana|\bplantain|\bcooking banana'}},
    {'id': 'fish-gentle', 'kind': 'technique', 'title': 'Handle fish gently',
     'text': 'Pat fish dry before frying so it sears instead of steaming, and turn it only once. In stews, add the fish near the end so it does not fall apart.',
     'when': {'ing': r'\bfish\b|\btilapia|\bsalmon|\bsnapper|\bperch|\bomena|\bcod\b'}},
    {'id': 'avocado', 'kind': 'technique', 'title': 'Stop avocado browning',
     'text': 'A squeeze of lemon or lime juice slows browning. Cut avocado just before serving.',
     'when': {'ing': r'\bavocado'}},
    {'id': 'salad-dress', 'kind': 'technique', 'title': 'Dress salads at the last minute',
     'text': 'Salt and acid draw water out of vegetables. Toss kachumbari and green salads just before serving so they stay crisp.',
     'when': {'cat': r'Salad', 'ing': r'.'}},
    {'id': 'tea-boil', 'kind': 'kenyan', 'title': 'Boil Kenyan chai in the milk',
     'text': 'For a strong, creamy cup, simmer the tea leaves and spices with water and milk together, then strain. Add sugar at the end to taste.',
     'when': {'title': r'\bchai\b|\btea\b|\bkenyan tea|\bmasala tea', 'not_cat': r'Dessert'}},
    {'id': 'drink-taste', 'kind': 'technique', 'title': 'Taste drinks before serving',
     'text': 'Fruit varies in sweetness. Add sugar or honey a little at a time, then adjust with lemon or lime for balance.',
     'when': {'cat': r'Beverage'}},
    {'id': 'lemon-finish', 'kind': 'flavour', 'title': 'Finish with acid',
     'text': 'If a dish tastes flat, a squeeze of lemon or lime or a pinch of salt at the end usually fixes it before you add more spice.',
     'when': {'cat': r'Main Dish|Soup|Seafood|Meat|Vegetarian|Side Dish'}},
    {'id': 'taste-season', 'kind': 'flavour', 'title': 'Season in layers and taste as you go',
     'text': 'Add a little salt at each stage and taste before serving. Adjusting at the end only is harder than building flavour in steps.',
     'when': {'always': True}},
    {'id': 'fresh-herb', 'kind': 'flavour', 'title': 'Add fresh herbs at the end',
     'text': 'Dhania (coriander), parsley and basil lose their flavour with long cooking. Stir them in off the heat.',
     'when': {'ing': r'\bcilantro|\bdania|\bdhania|\bcoriander|\bparsley|\bbasil|\bdill|\bmint'}},
]
_BY_ID = {t['id']: t for t in TIPS}
_COMPILED = {}


def _rx(pattern):
    if pattern not in _COMPILED:
        _COMPILED[pattern] = re.compile(pattern, re.I)
    return _COMPILED[pattern]


def _matches(when, recipe):
    if when.get('always'):
        return True
    title = recipe['title']
    ing = recipe['ingredients']
    ins = recipe['instructions']
    cat = recipe['category']
    ok = False
    for key, hay in (('title', title), ('ing', ing), ('ins', ins), ('cat', cat)):
        if key in when:
            if not _rx(when[key]).search(hay):
                return False
            ok = True
    if 'not_ing' in when and _rx(when['not_ing']).search(ing):
        return False
    if 'not_cat' in when and _rx(when['not_cat']).search(cat):
        return False
    return ok


_KIND_ORDER = {'safety': 0, 'kenyan': 1, 'technique': 2, 'flavour': 3}
_GENERIC = {'mise', 'taste-season', 'lemon-finish', 'fresh-herb'}
MAX_TIPS = 5


def tips_for_recipe(title, category, ingredients, instructions, limit=MAX_TIPS):
    """Return a list of tip ids for a recipe, safety first, specific before generic."""
    recipe = {'title': title or '', 'category': category or '', 'ingredients': ingredients or '',
              'instructions': instructions or ''}
    hits = [t for t in TIPS if _matches(t['when'], recipe)]
    hits.sort(key=lambda t: (t['id'] in _GENERIC, _KIND_ORDER[t['kind']]))
    safety = [t for t in hits if t['kind'] == 'safety']
    rest = [t for t in hits if t['kind'] != 'safety']
    chosen = safety[:3] + rest
    return [t['id'] for t in chosen[:limit]]


def tip_payload():
    """All tips keyed by id, for sending to the browser once."""
    return {t['id']: {'k': t['kind'], 't': t['title'], 'x': t['text']} for t in TIPS}


def tip(tip_id):
    return _BY_ID.get(tip_id)
