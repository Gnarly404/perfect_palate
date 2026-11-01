"""Perfect Palate - rough recipe cost in Kenyan shillings.

Prices live in Dataset/ingredient_prices.csv, one row per ingredient in the nutrition table, in KES per kg
(litres are treated as kg).  Every row says where its price came from and how far to trust it:

  verified   a published Kenyan price (KNBS Consumer Price Index) for that item
  reference  a market-reference list that is undated and says it is not a current quote
  rough      an estimate with no published source; replace it with KAMIS or shop prices

The result is always a RANGE, never one exact figure, and it says how much of the money rests on
verified prices.  Quantities come from the same parser the nutrition estimate uses.
"""
import csv
import os

from nutrition import parse_ingredient, split_ingredients

PRICE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Dataset', 'ingredient_prices.csv')
TIERS = ('verified', 'reference', 'rough')
# how far real prices can sit either side of the table value, by how much we trust it
SPREAD = {'verified': (0.9, 1.1), 'reference': (0.75, 1.3), 'rough': (0.6, 1.6)}
MIN_COVERAGE = 0.7      # share of the ingredient lines that must be priced
MIN_PRICED_LINES = 3

_prices = None


def load_prices(force=False):
    global _prices
    if _prices is None or force:
        with open(PRICE_FILE, newline='', encoding='utf-8') as handle:
            _prices = {row['ingredient']: row for row in csv.DictReader(handle)}
    return _prices


def price_as_of():
    """Oldest month of a dated price, for the note under the figure."""
    dates = sorted({r['as_of'] for r in load_prices().values() if r['as_of'][:2] == '20'})
    return dates[-1] if dates else ''


def _round(value):
    step = 10 if value >= 100 else 5
    return int(round(value / step) * step)


def estimate_cost(ingredients_raw, servings):
    """Return {'lo', 'hi', 'per_lo', 'per_hi', 'sv', 'cov', 'verified'} or None when too little could be priced."""
    prices = load_prices()
    items = [parse_ingredient(p) for p in split_ingredients(ingredients_raw)]
    counted = [i for i in items if i['status'] == 'counted']
    unmatched = [i for i in items if i['status'] == 'unmatched']
    considered = len(counted) + len(unmatched)
    priced = []
    for item in counted:
        row = prices.get(item['entry']['name'])
        if row:
            priced.append((item['grams'] / 1000.0 * float(row['kes_per_kg']), row['confidence']))
    if not considered or len(priced) < MIN_PRICED_LINES or len(priced) / considered < MIN_COVERAGE:
        return None
    mid = sum(v for v, _ in priced)
    lo = sum(v * SPREAD[t][0] for v, t in priced)
    hi = sum(v * SPREAD[t][1] for v, t in priced)
    verified = sum(v for v, t in priced if t == 'verified')
    servings = max(1, int(servings or 1))
    return {
        'lo': _round(lo), 'hi': _round(hi), 'mid': _round(mid),
        'per_lo': _round(lo / servings), 'per_hi': _round(hi / servings),
        'sv': servings, 'cov': round(len(priced) / considered, 2),
        'verified': round(verified / mid, 2) if mid else 0.0,
    }
