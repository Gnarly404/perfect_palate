"""Compare Perfect Palate's hand-typed nutrition table with the Kenya Food Composition Tables (2018).

The tables are published by FAO and the Government of Kenya (an Excel file and a PDF are linked from
https://www.fao.org/food-composition/tables-and-databases/detail/kenya-food-composition-tables/en ).
Download the Excel file, then:

    python tools/validate_nutrition.py --kfct "Kenya Food Composition Tables 2018.xlsx" --out report.csv

How it works
  * every entry in nutrition._TABLE is matched to a food in the Kenyan tables, first through the
    explicit mapping in tools/kfct_map.json (ingredient -> exact food name), then by name overlap
  * kcal, protein, carbohydrate, fat, fibre and sodium are compared per 100 g
  * rows that differ by more than --tolerance (default 15%, ignoring tiny absolute gaps) are flagged

Automatic matches are only suggestions.  Check the flagged rows by eye, add the right food names to
kfct_map.json, and re-run.  Nothing here edits nutrition.py: a person decides which source wins.
"""
import argparse
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

FIELDS = ('kcal', 'protein', 'carbs', 'fat', 'fiber', 'sodium')
# header patterns, tried in order, on lower-cased header text
HEADERS = {
    'name': [r'food name', r'^name$', r'description', r'food item', r'^food$'],
    'kcal': [r'energy.*kcal', r'^kcal$', r'enerc.*kcal', r'energy \(kcal'],
    'kj': [r'energy.*kj', r'enerc.*kj'],
    'protein': [r'^protein', r'procnt'],
    'fat': [r'^fat\b', r'total fat', r'^fat$', r'fat\s*\(g'],
    'carbs': [r'carbohydrate.*avail', r'choavl', r'^carbohydrate', r'carbohydrate'],
    'fiber': [r'fib(er|re)', r'fibtg'],
    'sodium': [r'^sodium', r'^na\b', r'sodium \(mg'],
}
PENALISE = re.compile(r'\b(cooked|boiled|fried|roasted|stewed|steamed|canned|tinned|juice|soup|cake|bread|dish|mix)\b')
PREFER = re.compile(r'\b(raw|dry|dried|flour|fresh|whole)\b')


def _tokens(text):
    out = []
    for w in re.findall(r'[a-z]+', str(text).lower()):
        if len(w) > 3 and w.endswith('ies'):
            w = w[:-3] + 'y'
        elif len(w) > 3 and w.endswith('es') and not w.endswith('oes'):
            w = w[:-2]
        elif len(w) > 3 and w.endswith('s'):
            w = w[:-1]
        out.append(w)
    return out


def find_columns(headers):
    """Map our field names to column indexes by looking at the header text."""
    low = [re.sub(r'\s+', ' ', str(h or '')).strip().lower() for h in headers]
    cols = {}
    for key, patterns in HEADERS.items():
        for pattern in patterns:
            hit = next((i for i, h in enumerate(low) if re.search(pattern, h) and i not in cols.values()), None)
            if hit is not None:
                cols[key] = hit
                break
    return cols


def load_kfct(path, sheet=None):
    """Return ({food name: {field: value}}, columns found). Works for .xlsx and .csv."""
    if path.lower().endswith(('.xlsx', '.xlsm', '.xls')):
        import pandas as pd
        sheets = pd.read_excel(path, sheet_name=sheet if sheet else None, header=None)
        frames = [(n, f.values.tolist()) for n, f in (sheets.items() if isinstance(sheets, dict) else [(sheet, sheets)])]
    else:
        with open(path, newline='', encoding='utf-8-sig') as handle:
            frames = [('csv', list(csv.reader(handle)))]
    best = ({}, {})
    for _name, rows in frames:
        for header_at in range(min(25, len(rows))):
            cols = find_columns(rows[header_at])
            if 'name' in cols and ('kcal' in cols or 'kj' in cols) and 'protein' in cols:
                foods = {}
                for row in rows[header_at + 1:]:
                    label = row[cols['name']] if cols['name'] < len(row) else None
                    if not isinstance(label, str) or not label.strip():
                        continue
                    values = {}
                    for key in ('kcal', 'protein', 'carbs', 'fat', 'fiber', 'sodium', 'kj'):
                        if key in cols and cols[key] < len(row):
                            try:
                                values[key] = float(str(row[cols[key]]).replace(',', '.'))
                            except ValueError:
                                pass
                    if 'kcal' not in values and 'kj' in values:
                        values['kcal'] = values['kj'] / 4.184
                    if 'kcal' in values:
                        foods[label.strip()] = values
                if len(foods) > len(best[0]):
                    best = (foods, cols)
                break
    return best


def match(entry, foods, mapping):
    """Return (food name, how) for one table entry: explicit mapping first, then name overlap."""
    wanted = mapping.get(entry['name'])
    if wanted:
        for name in foods:
            if name.lower() == wanted.lower():
                return name, 'mapped'
        return None, 'mapped-but-missing'
    best, best_score = None, 0.0
    for alias in entry['aliases'][:4]:
        need = set(_tokens(alias))
        if not need:
            continue
        for name in foods:
            have = _tokens(name)
            if not need <= set(have):
                continue
            score = 10 - len(have) * 0.3 - (3 if PENALISE.search(name.lower()) else 0) + (1.5 if PREFER.search(name.lower()) else 0)
            if alias == entry['name']:
                score += 1
            if score > best_score:
                best, best_score = name, score
    return best, 'auto' if best else 'none'


def compare(ours, theirs, tolerance):
    rows, flagged = {}, False
    for key in FIELDS:
        a, b = ours.get(key), theirs.get(key)
        if a is None or b is None:
            rows[key] = (a, b, None)
            continue
        gap = a - b
        pct = gap / b if b else None
        # ignore noise: under 1 g (or 20 mg sodium, 10 kcal) is not worth a person's time
        floor = 20 if key == 'sodium' else 10 if key == 'kcal' else 1
        bad = abs(gap) > floor and (pct is None or abs(pct) > tolerance)
        rows[key] = (a, b, pct)
        flagged = flagged or bad
    return rows, flagged


def run(kfct_path, out_path, map_path, tolerance, sheet=None):
    import nutrition
    foods, cols = load_kfct(kfct_path, sheet)
    if not foods:
        raise SystemExit('Could not find a header row with food name, energy and protein columns. '
                         'Open the file, note the header row, and adjust HEADERS in this script.')
    mapping = {}
    if map_path and os.path.exists(map_path):
        with open(map_path, encoding='utf-8') as handle:
            mapping = {k: v for k, v in json.load(handle).items() if not k.startswith('_')}
    report, counts = [], {'compared': 0, 'flagged': 0, 'unmatched': 0}
    for entry in nutrition.INGREDIENTS:
        name, how = match(entry, foods, mapping)
        if not name:
            counts['unmatched'] += 1
            report.append({'ingredient': entry['name'], 'kfct_food': '', 'match': how, 'flag': 'UNMATCHED'})
            continue
        rows, flagged = compare(entry['n'], foods[name], tolerance)
        counts['compared'] += 1
        counts['flagged'] += int(flagged)
        line = {'ingredient': entry['name'], 'kfct_food': name, 'match': how, 'flag': 'CHECK' if flagged else 'ok'}
        for key, (a, b, pct) in rows.items():
            line[key + '_ours'] = a
            line[key + '_kfct'] = None if b is None else round(b, 1)
            line[key + '_diff_pct'] = None if pct is None else round(pct * 100)
        report.append(line)
    fields = ['ingredient', 'kfct_food', 'match', 'flag'] + [f'{k}_{s}' for k in FIELDS for s in ('ours', 'kfct', 'diff_pct')]
    with open(out_path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(report)
    return counts, cols, len(foods)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--kfct', required=True, help='Kenya Food Composition Tables .xlsx or .csv')
    parser.add_argument('--sheet', help='sheet name (default: search all sheets)')
    parser.add_argument('--map', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kfct_map.json'))
    parser.add_argument('--out', default='nutrition_validation.csv')
    parser.add_argument('--tolerance', type=float, default=0.15)
    args = parser.parse_args()
    counts, cols, total = run(args.kfct, args.out, args.map, args.tolerance, args.sheet)
    print(f'{total} Kenyan foods read; columns used: {cols}')
    print(f"{counts['compared']} of our ingredients compared, {counts['flagged']} differ by more than "
          f"{args.tolerance:.0%}, {counts['unmatched']} found no match. Report: {args.out}")


if __name__ == '__main__':
    main()
