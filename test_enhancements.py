"""Tests for profile customisation, nutrition, difficulty, tips and sharing."""
import csv
import os
import re
import sqlite3
import tempfile
import unittest
from urllib.parse import quote

import database
import difficulty
import nutrition
import recommendations
import tips
from app import app


class NutritionTableTest(unittest.TestCase):
    # Calories that do not come from protein, carbohydrate and fat, so the check cannot apply:
    # vanilla extract is mostly alcohol; baking powder's carbohydrate is largely non-digestible starch/salts.
    # Unsweetened cocoa's USDA energy value (228 kcal) uses food-specific factors; a third of it is fibre.
    EXEMPT = {'vanilla extract', 'baking powder', 'cocoa powder'}

    def test_every_row_is_internally_consistent(self):
        """kcal should roughly match 4*protein + 4*digestible carbs + 2*fibre + 9*fat (a typo shows up here)."""
        bad = []
        for e in nutrition.INGREDIENTS:
            for label, n in [('raw', e['n'])] + ([('cooked', e['cooked']['n'])] if 'cooked' in e else []):
                self.assertLessEqual(n['sugar'], n['carbs'] + 0.01, e['name'])
                self.assertLessEqual(n['fiber'], n['carbs'] + 0.01, e['name'])
                if e['name'] in self.EXEMPT:
                    continue
                expected = 4 * n['protein'] + 4 * (n['carbs'] - n['fiber']) + 2 * n['fiber'] + 9 * n['fat']
                if abs(expected - n['kcal']) > max(30, 0.25 * n['kcal']):
                    bad.append((e['name'], label, n['kcal'], round(expected)))
        self.assertEqual(bad, [])


class NutritionParseTest(unittest.TestCase):
    def grams(self, text):
        r = nutrition.parse_ingredient(text)
        self.assertEqual(r['status'], 'counted', text)
        return r['grams']

    def test_formats(self):
        self.assertAlmostEqual(self.grams('All-Purpose Flour (2 cups)'), 250, delta=1)
        self.assertAlmostEqual(self.grams('feta cheese (1/2 cup, crumbled)'), 75, delta=1)
        self.assertAlmostEqual(self.grams('1 1/2 cup of pumpkin'), 174, delta=1)
        self.assertAlmostEqual(self.grams('½ teaspoon of cumin'), 1.05, delta=0.1)
        self.assertAlmostEqual(self.grams('500g beef'), 500, delta=1)
        self.assertAlmostEqual(self.grams('1 kg of chicken breast'), 1000, delta=1)
        self.assertAlmostEqual(self.grams('3clovesgarlic'), 9, delta=1)
        self.assertAlmostEqual(self.grams('juice of 2 lemons'), 96, delta=1)

    def test_not_counted(self):
        for text in ('Salt and Pepper (to taste)', '1 cup of pasta water', 'For the sauce:', 'minced'):
            self.assertEqual(nutrition.parse_ingredient(text)['status'], 'skipped', text)
        self.assertEqual(nutrition.parse_ingredient('Vegetable oil for frying')['status'], 'frying')

    def test_coconut_milk_is_not_milk(self):
        self.assertEqual(nutrition.find_ingredient('coconut milk')['name'], 'coconut milk')
        self.assertEqual(nutrition.find_ingredient('milk')['name'], 'milk')

    def test_hand_calculated_recipe(self):
        # 250 g flour (3.64 kcal/g) + 2 tbsp oil (27.25 g * 8.84) = 1151 kcal, / 4 servings
        est = nutrition.estimate_nutrition('All-Purpose Flour (2 cups), Water (1 cup), Salt (1/2 tsp), Oil (2 tbsp)', 4)
        self.assertAlmostEqual(est['per_serving']['kcal'], 288, delta=3)
        self.assertEqual(est['confidence'], 'good')

    def test_refuses_to_guess(self):
        self.assertIsNone(nutrition.estimate_nutrition('Mystery Powder (2 cups), Unknown Herb (1 cup)', 4))
        # a big unrecognised ingredient (1 kg) makes any total meaningless
        self.assertIsNone(nutrition.estimate_nutrition('1 kg of Zorblax, Salt (1 tsp), Oil (1 tbsp), Onion (1)', 4))
        self.assertIsNone(nutrition.estimate_nutrition('', 4))


class DifficultyTest(unittest.TestCase):
    def test_levels(self):
        easy = difficulty.rate_difficulty('Flour (2 cups), Water (1 cup), Salt (1 tsp)', '1. Mix. 2. Cook. 3. Serve.')
        self.assertEqual(easy['level'], 'Easy')
        steps = ' '.join(f'{i}. Step number {i}.' for i in range(1, 22)) + ' Knead the dough, let it rise, then deep fry.'
        hard = difficulty.rate_difficulty(', '.join(f'Item{i} ({i} cup)' for i in range(20)), steps)
        self.assertEqual(hard['level'], 'Hard')
        self.assertTrue(any('kneading' in r for r in hard['reasons']))

    def test_long_list_without_technique_is_not_hard(self):
        steps = ' '.join(f'{i}. Toss gently {i}.' for i in range(1, 14))
        r = difficulty.rate_difficulty(', '.join(f'Item{i} (1 cup)' for i in range(20)), steps)
        self.assertEqual(r['level'], 'Medium')


class TipsTest(unittest.TestCase):
    def ids(self, title, cat, ing, ins=''):
        return tips.tips_for_recipe(title, cat, ing, ins)

    def test_safety_tips_attach_and_come_first(self):
        ids = self.ids('Roast Chicken', 'Main Dish', 'Chicken (1 whole), Rice (1 cup)', '1. Roast.')
        self.assertIn('safe-chicken', ids)
        self.assertIn('safe-rice', ids)
        self.assertEqual(tips.tip(ids[0])['kind'], 'safety')

    def test_cassava_and_beans(self):
        self.assertIn('safe-cassava', self.ids('Cassava Fries', 'Appetizer', 'Cassava (2)'))
        self.assertIn('safe-beans', self.ids('Beans', 'Main Dish', 'Dry red kidney beans (2 cups)'))
        self.assertNotIn('safe-beans', self.ids('Black beans', 'Main Dish', 'Black beans (1 can)'))

    def test_every_recipe_has_tips(self):
        for r in recommendations.load_recipes():
            self.assertGreaterEqual(len(r['tips']), 2, r['t'])
            for t in r['tips']:
                self.assertIsNotNone(tips.tip(t))


class RecipeDataTest(unittest.TestCase):
    def test_ids_are_unique(self):
        ids = [r['id'] for r in recommendations.load_recipes()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_dataset_image_paths_take_precedence(self):
        with open(recommendations.CSV_PATH, encoding='utf-8-sig', newline='') as source:
            rows = list(csv.DictReader(source))
        recipes = recommendations.load_recipes(force_reload=True)
        self.assertEqual(len(recipes), len(rows))
        for row, recipe in zip(rows, recipes):
            image_name = os.path.basename((row.get('Image_path') or '').replace('\\', '/'))
            if image_name and os.path.isfile(os.path.join(recommendations.IMAGE_DIR, image_name)):
                self.assertTrue(recipe['img'].endswith(quote(image_name)), row['Recipe Title'])

    def test_new_fields_present(self):
        for r in recommendations.load_recipes():
            self.assertIn(r['df']['l'], difficulty.LEVELS)
            if r['nu']:
                self.assertGreater(r['nu']['k'], 0)
                self.assertGreaterEqual(r['nu']['cov'], nutrition.MIN_COVERAGE)

    def test_most_recipes_have_nutrition(self):
        recs = recommendations.load_recipes()
        covered = sum(1 for r in recs if r['nu'])
        self.assertGreater(covered / len(recs), 0.75)


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database = database.DATABASE
        database.DATABASE = os.path.join(self.temp_dir.name, 'test.db')
        database.init_db()
        app.config['TESTING'] = True
        self.client = app.test_client()

    def tearDown(self):
        database.DATABASE = self.original_database
        self.temp_dir.cleanup()

    def signup_and_login(self, email='chef@example.com', name='Wanjiku Kamau', pw='secret1'):
        r = self.client.post('/sign-up', json={'name': name, 'email': email, 'password': pw})
        self.assertEqual(r.status_code, 200)
        r = self.client.post('/sign-in', json={'email': email, 'password': pw})
        self.assertEqual(r.status_code, 200)


class ProfileTest(AppTestCase):
    def test_signup_stores_name(self):
        self.signup_and_login()
        self.assertEqual(database.get_user_profile(1)['display_name'], 'Wanjiku Kamau')
        self.assertEqual(database.get_user_profile(1)['initials'], 'WK')

    def test_profile_requires_login(self):
        self.assertEqual(self.client.get('/profile').status_code, 302)
        self.assertEqual(self.client.post('/profile', json={'display_name': 'x'}).status_code, 401)
        self.assertEqual(self.client.post('/profile/password', json={}).status_code, 401)

    def test_profile_page_renders_and_escapes(self):
        self.signup_and_login(name='<script>alert(1)</script>')
        html = self.client.get('/profile').get_data(as_text=True)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_save_profile(self):
        self.signup_and_login()
        r = self.client.post('/profile', json={'display_name': 'Chef Wanjiku', 'bio': 'Ugali fan', 'avatar_emoji': '🥘',
                                               'avatar_color': 'gold', 'cooking_level': 'beginner', 'calorie_goal': 2100})
        self.assertEqual(r.status_code, 200)
        p = database.get_user_profile(1)
        self.assertEqual((p['display_name'], p['cooking_level'], p['calorie_goal'], p['avatar_emoji']),
                         ('Chef Wanjiku', 'beginner', 2100, '🥘'))
        # shows up on the dashboard
        self.assertIn('Karibu, Chef Wanjiku.', self.client.get('/dashboard').get_data(as_text=True))

    def test_validation(self):
        self.signup_and_login()
        for bad in ({'display_name': ''}, {'display_name': 'x', 'avatar_emoji': '💣'}, {'display_name': 'x', 'cooking_level': 'wizard'},
                    {'display_name': 'x', 'calorie_goal': 99999}, {'display_name': 'x' * 41}):
            self.assertEqual(self.client.post('/profile', json=bad).status_code, 400, bad)

    def test_form_posts_are_rejected(self):
        """Only JSON is accepted, so a cross-site HTML form cannot change the profile."""
        self.signup_and_login()
        r = self.client.post('/profile', data={'display_name': 'Hacked'})
        self.assertEqual(r.status_code, 415)
        self.assertNotEqual(database.get_user_profile(1)['display_name'], 'Hacked')

    def test_change_password(self):
        self.signup_and_login()
        self.assertEqual(self.client.post('/profile/password', json={'current_password': 'wrong', 'new_password': 'newpass1'}).status_code, 403)
        self.assertEqual(self.client.post('/profile/password', json={'current_password': 'secret1', 'new_password': 'abc'}).status_code, 400)
        self.assertEqual(self.client.post('/profile/password', json={'current_password': 'secret1', 'new_password': 'secret1'}).status_code, 400)
        self.assertEqual(self.client.post('/profile/password', json={'current_password': 'secret1', 'new_password': 'newpass1'}).status_code, 200)
        self.client.get('/logout')
        self.assertEqual(self.client.post('/sign-in', json={'email': 'chef@example.com', 'password': 'secret1'}).status_code, 401)
        self.assertEqual(self.client.post('/sign-in', json={'email': 'chef@example.com', 'password': 'newpass1'}).status_code, 200)

    def test_migration_keeps_existing_users(self):
        path = os.path.join(self.temp_dir.name, 'old.db')
        con = sqlite3.connect(path)
        con.execute('CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        con.execute("INSERT INTO users (email, password_hash) VALUES ('old@example.com', 'x')")
        con.commit()
        con.close()
        database.DATABASE = path
        database.init_db()
        database.init_db()  # idempotent
        p = database.get_user_profile(1)
        self.assertEqual(p['display_name'], 'old')
        self.assertEqual(p['email'], 'old@example.com')

    def test_delete_account_still_works(self):
        self.signup_and_login()
        self.assertEqual(self.client.post('/account/delete').status_code, 200)
        self.assertIsNone(database.get_user_profile(1))


class SharingAndPagesTest(AppTestCase):
    def test_recipe_page_has_new_data(self):
        html = self.client.get('/recipes/').get_data(as_text=True)
        self.assertEqual(self.client.get('/recipes/').status_code, 200)
        self.assertIn('const TIPS =', html)
        self.assertIn('"df":', html)
        # embedded JSON cannot close the script tag early
        self.assertNotIn('</script><', html.split('const TIPS =')[0].split('let RX =')[1])

    def test_permalink_has_open_graph_tags(self):
        r = self.client.get('/recipes/recipe/1')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('<meta property="og:title" content="Chapati | Perfect Palate">', html)
        self.assertIn('og:image', html)
        self.assertIn('twitter:card', html)
        self.assertRegex(html, r'og:url" content="http://localhost/recipes/recipe/1"')
        self.assertIn('const OPEN_RECIPE = 1;', html)

    def test_permalink_uses_public_base_url(self):
        original = app.config['PUBLIC_BASE_URL']
        app.config['PUBLIC_BASE_URL'] = 'https://palate.example'
        try:
            html = self.client.get('/recipes/recipe/1').get_data(as_text=True)
        finally:
            app.config['PUBLIC_BASE_URL'] = original
        self.assertIn('og:url" content="https://palate.example/recipes/recipe/1"', html)

    def test_permalink_404_and_public(self):
        self.assertEqual(self.client.get('/recipes/recipe/999999').status_code, 404)
        self.assertEqual(self.client.get('/recipes/recipe/1').status_code, 200)  # no login needed

    def test_every_recipe_permalink_renders(self):
        for r in recommendations.load_recipes():
            self.assertEqual(self.client.get(f"/recipes/recipe/{r['id']}").status_code, 200, r['t'])

    def test_tips_page(self):
        r = self.client.get('/recipes/tips')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        for t in tips.TIPS:
            self.assertIn(f'id="{t["id"]}"', html)

    def test_signed_in_pages_still_render(self):
        self.signup_and_login()
        for url in ('/dashboard', '/preferences', '/profile', '/recipes/', '/recipes/tips', '/planner/', '/planner/favorites', '/planner/shopping-list', '/sign-in'):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_sign_in_page_has_real_form_semantics(self):
        html = self.client.get('/sign-in').get_data(as_text=True)
        self.assertIn('<form class="auth-form mobile-active" id="fSI"', html)
        self.assertRegex(html, r'<label for="siEmail">')
        self.assertIn('class="sr-only"', html)

    def test_no_hardcoded_recipe_count_or_head_headings(self):
        from recommendations import load_recipes
        total = len(load_recipes())
        self.assertIn(f'{total} curated recipes', self.client.get('/sign-in').get_data(as_text=True))
        self.signup_and_login()
        dash = self.client.get('/dashboard').get_data(as_text=True)
        self.assertIn(f'{total} recipes are waiting', dash)
        self.assertNotIn('196', dash.replace('rgba(244,196,48', ''))
        prefs = self.client.get('/preferences').get_data(as_text=True)
        self.assertIn(f'TOTAL_RECIPES={total}', prefs)
        self.assertNotIn('>196<', prefs)
        import re
        for url in ('/dashboard', '/preferences', '/planner/', '/planner/favorites', '/planner/shopping-list'):
            html = self.client.get(url).get_data(as_text=True)
            head = html.split('</head>')[0]
            self.assertNotIn('<h2', head, url)

    def test_nutrition_panel_has_servings_stepper(self):
        html = self.client.get('/recipes/').get_data(as_text=True)
        self.assertIn('id="svUp"', html)
        self.assertIn('is a guess based on its category', html)

    def test_images_are_resized_and_cached(self):
        from recommendations import load_recipes
        r = next(x for x in load_recipes() if x['img'])
        full = self.client.get(r['img'])
        small = self.client.get(r['img'] + '?w=480')
        self.assertEqual(small.status_code, 200)
        self.assertEqual(small.mimetype, 'image/webp')
        self.assertLessEqual(len(small.data), len(full.data))
        self.assertIn('max-age', small.headers.get('Cache-Control', ''))
        # sizes outside the whitelist fall back to the original rather than filling the cache
        self.assertEqual(self.client.get(r['img'] + '?w=7').mimetype, full.mimetype)

    def test_homepage_does_not_inline_frames(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertLess(len(html), 100_000)
        self.assertIn('/static/frames/f00.webp', html)
        self.assertNotIn('base64,', html)

    def test_shared_navbar_on_every_signed_in_page(self):
        self.signup_and_login()
        expect = {'/dashboard': 'Dashboard', '/recipes/': 'Recipes', '/planner/': 'Meal Plan',
                  '/planner/favorites': 'Favourites', '/planner/shopping-list': 'Shopping', '/recipes/tips': 'Tips'}
        for url, label in expect.items():
            html = self.client.get(url).get_data(as_text=True)
            self.assertEqual(html.count('id="pn"'), 1, url)
            self.assertIn('id="pnBurger"', html, url)                     # hamburger for small screens
            self.assertIn('href="/profile"', html, url)                   # profile reachable from every page
            self.assertRegex(html, r'aria-current="page">' + label, url)  # current page marked
        for url in ('/preferences', '/profile'):
            html = self.client.get(url).get_data(as_text=True)
            self.assertIn('id="pnChip"', html, url)

    def test_navbar_when_signed_out(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('id="pnBurger"', html)
        self.assertIn('pn-overlay', html)
        self.assertNotIn('id="pnChip"', html)

    def test_homepage_numbers_come_from_the_data(self):
        from recommendations import load_recipes
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn(f'{len(load_recipes())} recipes', html)
        self.assertNotIn('500+', html)
        self.assertNotIn('152', html)
        self.assertNotIn('Steps guided per recipe', html)

    def test_homepage_buttons_have_no_underline_and_text_is_readable(self):
        import re
        html = self.client.get('/').get_data(as_text=True)
        for cls in ('.btn-gold', '.btn-outline'):
            rule = re.search(re.escape(cls) + r' \{[^}]*\}', html).group(0)
            self.assertIn('text-decoration: none', rule, cls)
        self.assertIn('.phase::before', html)                 # shade behind the hero text
        self.assertIn('min(520px, calc(100vw - 48px))', html)  # intro block can't overflow a phone

    def test_recipes_page_has_back_to_top(self):
        html = self.client.get('/recipes/').get_data(as_text=True)
        self.assertIn('id="ppTop"', html)
        self.assertIn('aria-label="Back to top"', html)

    def test_footer_on_every_page_with_real_content(self):
        from datetime import datetime
        from recommendations import load_recipes
        total = len(load_recipes())
        for url in ('/', '/recipes/tips', '/recipes/'):
            html = self.client.get(url).get_data(as_text=True)
            self.assertEqual(html.count('id="ppFooter"'), 1, url)
            self.assertIn(f'{total} Kenyan and East African recipes', html, url)
            self.assertIn(f'© {datetime.now().year} Perfect Palate', html, url)
            self.assertIn('not a guarantee', html, url)        # estimates / allergy disclaimer
            self.assertIn('id="pfShare"', html, url)
            self.assertIn('id="pfTop"', html, url)
        self.signup_and_login()
        for url in ('/dashboard', '/profile', '/preferences', '/planner/', '/planner/favorites', '/planner/shopping-list'):
            html = self.client.get(url).get_data(as_text=True)
            self.assertEqual(html.count('id="ppFooter"'), 1, url)
            self.assertIn('Your kitchen', html, url)           # signed-in column
        self.assertNotIn('Get started', self.client.get('/dashboard').get_data(as_text=True).split('id="ppFooter"')[1])

    def test_footer_signed_out_offers_sign_in(self):
        html = self.client.get('/recipes/tips').get_data(as_text=True).split('id="ppFooter"')[1]
        self.assertIn('Get started', html)
        self.assertIn('Sign in or create an account', html)
        self.assertNotIn('Your kitchen', html)


if __name__ == '__main__':
    unittest.main()
