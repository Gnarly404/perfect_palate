"""Tests for tools/validate_nutrition.py, using a tiny made-up table in the layout we expect."""
import csv
import os
import tempfile
import unittest

from tools import validate_nutrition as v


def _write_sample(path):
    rows = [
        ['Kenya Food Composition Tables (sample for tests only)'],
        [],
        ['Code', 'Food name', 'Energy (kcal)', 'Protein (g)', 'Fat (g)', 'Carbohydrate, available (g)', 'Fibre (g)', 'Sodium (mg)'],
        ['01', 'Maize flour, whole', 362, 7.0, 3.9, 76.0, 7.0, 7],
        ['02', 'Maize flour, boiled', 90, 1.9, 1.0, 19.0, 1.8, 2],
        ['03', 'Rice, white, raw', 200, 7.0, 0.7, 80.0, 1.3, 5],   # deliberately wrong energy
    ]
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        csv.writer(handle).writerows(rows)


class ValidateNutritionTests(unittest.TestCase):
    def test_header_row_and_columns_are_found_below_a_title(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'k.csv')
            _write_sample(path)
            foods, cols = v.load_kfct(path)
        self.assertEqual(len(foods), 3)
        self.assertEqual(foods['Maize flour, whole']['kcal'], 362)
        self.assertEqual(set(cols) >= {'name', 'kcal', 'protein', 'fat', 'carbs', 'fiber', 'sodium'}, True)

    def test_auto_match_prefers_the_raw_food_over_the_cooked_one(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'k.csv')
            _write_sample(path)
            foods, _ = v.load_kfct(path)
        entry = {'name': 'maize flour', 'aliases': ['maize flour', 'unga']}
        self.assertEqual(v.match(entry, foods, {})[0], 'Maize flour, whole')

    def test_explicit_mapping_wins(self):
        foods = {'Maize flour, whole': {'kcal': 362}, 'Maize flour, boiled': {'kcal': 90}}
        entry = {'name': 'maize flour', 'aliases': ['maize flour']}
        self.assertEqual(v.match(entry, foods, {'maize flour': 'Maize flour, boiled'}), ('Maize flour, boiled', 'mapped'))

    def test_tolerance_and_noise_floor(self):
        rows, flagged = v.compare({'kcal': 365, 'protein': 7.2, 'carbs': 76, 'fat': 3.9, 'fiber': 7.3, 'sodium': 7},
                                  {'kcal': 362, 'protein': 7.0, 'carbs': 76, 'fat': 3.9, 'fiber': 7.0, 'sodium': 5}, 0.15)
        self.assertFalse(flagged)        # small and tiny gaps are not worth flagging
        _, flagged = v.compare({'kcal': 365}, {'kcal': 200}, 0.15)
        self.assertTrue(flagged)

    def test_full_run_writes_a_report_and_flags_the_wrong_value(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, 'k.csv'), os.path.join(d, 'r.csv')
            _write_sample(src)
            counts, _, _ = v.run(src, out, None, 0.15)
            with open(out, encoding='utf-8') as handle:
                report = {r['ingredient']: r for r in csv.DictReader(handle)}
        self.assertGreaterEqual(counts['compared'], 2)
        self.assertEqual(report['maize flour']['flag'], 'ok')
        self.assertEqual(report['rice']['flag'], 'CHECK')


if __name__ == '__main__':
    unittest.main()
