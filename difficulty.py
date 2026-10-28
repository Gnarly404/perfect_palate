"""
Perfect Palate - Recipe difficulty

The dataset has no difficulty column, so a level is *derived* from what the recipe
actually asks of the cook:

  * how many steps it has
  * how many ingredients it uses
  * whether it needs techniques that are easy to get wrong (kneading, deep frying,
    folding, proofing, caramelising, ...)

The score is a simple sum, so it is easy to explain: every recipe carries the short
list of reasons that produced its level.
"""
import re

LEVELS = ('Easy', 'Medium', 'Hard')

# (label shown to the cook, regex over the instructions)
_TECHNIQUES = [
    ('Needs kneading', r'\bknead'),
    ('Needs proofing or rising time', r'\bproof|let (it|the dough|the mixture|everything) rise|leave (it )?to rise|\brise for\b|\brising time|\bdouble in (size|volume)'),
    ('Involves fermenting', r'\bferment'),
    ('Deep frying', r'\bdeep[- ]?fr(y|ied)|\bfry in (hot|plenty of) oil|\bheat (the )?oil'),
    ('Folding or whipping', r'\bfold(ing)? (in|gently)|\bgently fold|\bstiff peaks|\bsoft peaks|\bwhip(ped)?\b|\bbeat until'),
    ('Caramelising or tempering', r'\bcaramel|\btemper(ing)?\b'),
    ('Shaping or rolling dough', r'\broll out|\bpleat|\bpipe\b|\bpiping|\bshape (the )?dough|\bfill (and|then) (seal|fold)'),
    ('Slow braising', r'\bbraise|\b(simmer|slow[- ]cook|stew)\b[^.]{0,40}\b[2-9]\s*(hours|hrs)'),
    ('Careful temperature control', r'\bpreheat|\boven to\b|\b\d{3}\s*°?\s*[fc]\b'),
]
_HARD_TECH_WEIGHT = {
    'Needs kneading': 1, 'Needs proofing or rising time': 1, 'Involves fermenting': 1,
    'Deep frying': 1, 'Folding or whipping': 1, 'Caramelising or tempering': 1,
    'Shaping or rolling dough': 1, 'Slow braising': 1, 'Careful temperature control': 0,
}
_TECH_RES = [(label, re.compile(rx, re.I)) for label, rx in _TECHNIQUES]


def _band(value, cuts):
    """0 for value <= cuts[0], 1 for <= cuts[1], ... len(cuts) beyond the last cut."""
    for i, cut in enumerate(cuts):
        if value <= cut:
            return i
    return len(cuts)


def split_steps(instructions_raw):
    return [s.strip() for s in re.split(r'\d+\.\s+', instructions_raw or '') if s.strip()]


def count_ingredients(ingredients_raw):
    """Count real ingredient lines (skip 'For the sauce:' style headers and empty bits)."""
    parts = [p.strip() for p in re.split(r',\s*(?![^()]*\))', (ingredients_raw or '').replace('▢', ',')) if p.strip()]
    n = 0
    for p in parts:
        low = p.lower().strip()
        if not re.search(r'[a-z]', low):
            continue
        if low.endswith(':') or re.match(r'^(for|to)\s+(the\s+)?[a-z ]+:?$', low):
            continue
        if low in {'to taste', 'optional', 'diced', 'minced', 'chopped', 'sliced', 'grated', 'cubed', 'softened'}:
            continue
        n += 1
    return n


def rate_difficulty(ingredients_raw, instructions_raw):
    steps = split_steps(instructions_raw)
    n_steps = len(steps)
    n_ing = count_ingredients(ingredients_raw)
    text = ' '.join(steps)

    step_score = _band(n_steps, (4, 8, 13))          # 0..3
    ing_score = min(2, _band(n_ing, (6, 11, 17)))     # 0..2 (a long shopping list is not a hard technique)
    found = [label for label, rx in _TECH_RES if rx.search(text)]
    tech_score = min(3, sum(_HARD_TECH_WEIGHT[label] for label in found))

    score = step_score + ing_score + tech_score      # 0..8
    if score <= 1:
        level = 'Easy'
    elif score <= 4 or (tech_score == 0 and score < 7):
        level = 'Medium'   # long, but no technique that is easy to get wrong
    else:
        level = 'Hard'

    reasons = []
    reasons.append(f'{n_steps} step{"s" if n_steps != 1 else ""}')
    reasons.append(f'{n_ing} ingredient{"s" if n_ing != 1 else ""}')
    reasons.extend(label for label in found if _HARD_TECH_WEIGHT[label])
    return {'level': level, 'score': score, 'rank': LEVELS.index(level) + 1, 'reasons': reasons}
