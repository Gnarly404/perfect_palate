"""Tests for cleaning scraped ingredient text and the shopping list built from it."""
import json
import re
import unittest

import ingredient_text as it


class IngredientTextTests(unittest.TestCase):
    def test_checkbox_blob_becomes_separate_clean_lines(self):
        raw = '▢1 1/2 – 2 1/2pounds (453.60 g)beef brisket, ▢salt and pepperfor seasoning, ▢immaculatebites creole seasoningfor rubbing'
        self.assertEqual(it.split_lines(raw), [
            '1 1/2–2 1/2 pounds (453.60 g) beef brisket',
            'salt and pepper for seasoning',
            'Immaculate Bites creole seasoning for rubbing',
        ])

    def test_glued_units_and_sizes_are_separated_without_eating_names(self):
        self.assertEqual(it.split_lines('▢2green onion,thinly sliced'), ['2 green onion, thinly sliced'])
        self.assertEqual(it.split_lines('▢1largeegg'), ['1 large egg'])
        self.assertEqual(it.split_lines('▢1½-2cups (355-475ml)beef stock'), ['1½–2 cups (355–475 ml) beef stock'])

    def test_section_headers_are_dropped(self):
        self.assertEqual(it.split_lines('Proteins:\n - ▢2 eggs\nProduce:\n ▢1 onion'), ['2 eggs', '1 onion'])

    def test_quantity_and_shopping_name(self):
        qty, name = it.parse_line('6 slices (70 g) bacon, diced')
        self.assertEqual(qty, '6 slices (70 g)')
        self.assertEqual(it.shopping_name(name), 'bacon')
        self.assertEqual(it.shopping_name('salt and pepper for seasoning'), 'salt and pepper')

    def test_ordinary_recipe_formats_still_work(self):
        self.assertEqual(it.split_lines('Rice (1 cup), Garlic (3 cloves, minced), Onion (1)'),
                         ['Rice (1 cup)', 'Garlic (3 cloves, minced)', 'Onion (1)'])
        self.assertEqual(it.parse_line('Garlic (3 cloves, minced)'), ('3 cloves, minced', 'Garlic'))

    def test_no_dataset_recipe_collapses_into_one_line(self):
        import recommendations
        for recipe in recommendations.load_recipes():
            if '▢' in recipe['ing']:
                self.assertGreater(len(it.split_lines(recipe['ing'])), 1, recipe['t'])


class ShoppingListTileTests(unittest.TestCase):
    def setUp(self):
        import app as app_module
        from test_support import CsrfTestClient
        import uuid
        app_module.app.config['TESTING'] = True
        app_module.app.test_client_class = CsrfTestClient
        self.client = app_module.app.test_client()
        email = f'shop-{uuid.uuid4().hex[:8]}@example.com'
        self.client.post('/sign-up', json={'name': 'Shop Tester', 'email': email, 'password': 'Str0ng!Passw0rd#1'})
        self.client.post('/sign-in', json={'email': email, 'password': 'Str0ng!Passw0rd#1'})

    def test_brisket_plan_gives_one_tile_per_ingredient_and_a_numbered_detail(self):
        plan = self.client.post('/planner/create', json={'week_start_date': '2026-10-26'}).json['id']
        self.client.post('/planner/add-meal', json={'meal_plan_id': plan, 'day_of_week': 'Mon', 'meal_type': 'dinner', 'recipe_id': 243})
        page = self.client.get('/planner/shopping-list?week_start_date=2026-10-26').get_data(as_text=True)
        data = json.loads(re.search(r'<script id="shoppingListData"[^>]*>(.*?)</script>', page, re.S).group(1))
        names = [i['name'] for i in data['items']]
        self.assertEqual(names, ['Beef brisket', 'Salt and pepper', 'Immaculate Bites creole seasoning'])
        recipe = data['recipes']['243']
        self.assertEqual(len(recipe['lines']), 3)
        self.assertIn('id="ingDlg"', page)
        self.assertIn('onclick="openItem(', page)


if __name__ == '__main__':
    unittest.main()
