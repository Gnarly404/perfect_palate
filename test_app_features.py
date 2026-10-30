import bcrypt
import html
import json
import os
import random
import re
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

import database
import recommendations
from app import app
from werkzeug.security import generate_password_hash
from test_support import CsrfTestClient

app.test_client_class = CsrfTestClient


class ApplicationFeaturesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database = database.DATABASE
        database.DATABASE = os.path.join(self.temp_dir.name, 'test.db')
        database.init_db()
        self.client = app.test_client()
        conn = database.get_db_connection()
        cursor = conn.execute(
            'INSERT INTO users (email, password_hash) VALUES (?, ?)',
            ('cook@example.com', bcrypt.hashpw(b'password123', bcrypt.gensalt()).decode('ascii')),
        )
        self.user_id = cursor.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        database.DATABASE = self.original_database
        self.temp_dir.cleanup()

    def sign_in_session(self, user_id=None):
        with self.client.session_transaction() as session:
            session['user_id'] = user_id or self.user_id

    def test_registration_uses_bcrypt_and_login_upgrades_legacy_hash(self):
        response = self.client.post('/sign-up', json={
            'name': 'New Cook',
            'email': 'new@example.com',
            'password': 'password456',
        })
        self.assertEqual(response.status_code, 200)
        conn = database.get_db_connection()
        password_hash = conn.execute(
            'SELECT password_hash FROM users WHERE email = ?',
            ('new@example.com',),
        ).fetchone()['password_hash']
        conn.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (generate_password_hash('password123'), self.user_id),
        )
        conn.commit()
        conn.close()
        self.assertTrue(password_hash.startswith('$2'))
        self.assertTrue(bcrypt.checkpw(b'password456', password_hash.encode('ascii')))

        response = self.client.post('/sign-in', json={
            'email': 'cook@example.com',
            'password': 'password123',
        })
        self.assertEqual(response.status_code, 200)
        conn = database.get_db_connection()
        migrated_hash = conn.execute(
            'SELECT password_hash FROM users WHERE id = ?',
            (self.user_id,),
        ).fetchone()['password_hash']
        conn.close()
        self.assertTrue(migrated_hash.startswith('$2'))
        self.assertTrue(bcrypt.checkpw(b'password123', migrated_hash.encode('ascii')))

    def test_deleted_account_invalidates_existing_session(self):
        self.sign_in_session()
        conn = database.get_db_connection()
        conn.execute('DELETE FROM users WHERE id = ?', (self.user_id,))
        conn.commit()
        conn.close()

        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn('user_id', session)

    def test_meal_plan_persists_and_generates_categorized_shopping_list(self):
        self.sign_in_session()
        plan_response = self.client.post(
            '/planner/create',
            json={'week_start_date': '2026-10-26'},
        )
        self.assertEqual(plan_response.status_code, 200)
        plan_id = plan_response.json['id']
        add_response = self.client.post('/planner/add-meal', json={
            'meal_plan_id': plan_id,
            'day_of_week': 'Mon',
            'meal_type': 'breakfast',
            'recipe_id': 1,
        })
        self.assertEqual(add_response.status_code, 200)
        produce_response = self.client.post('/planner/add-meal', json={
            'meal_plan_id': plan_id,
            'day_of_week': 'Tue',
            'meal_type': 'lunch',
            'recipe_id': 4,
        })
        self.assertEqual(produce_response.status_code, 200)

        same_plan = self.client.post(
            '/planner/create',
            json={'week_start_date': '2026-10-26'},
        )
        self.assertEqual(same_plan.json['id'], plan_id)
        self.assertEqual(len(same_plan.json['items']), 2)

        shopping_response = self.client.get(
            '/planner/shopping-list?week_start_date=2026-10-26',
        )
        self.assertEqual(shopping_response.status_code, 200)
        shopping_page = shopping_response.get_data(as_text=True)
        self.assertIn('All-Purpose Flour', shopping_page)
        items_match = re.search(
            r'<script id="shoppingListData" type="application/json">(.*?)</script>',
            shopping_page,
            re.S,
        )
        self.assertIsNotNone(items_match)
        generated_items = json.loads(items_match.group(1))['items']
        self.assertIn('All-Purpose Flour', [item['name'] for item in generated_items])
        self.assertIn('Water', [item['name'] for item in generated_items])
        self.assertIn('produce', [item['cat'] for item in generated_items])
        self.assertIn('function toggleItem(id)', shopping_page)
        self.assertIn('navigator.share', shopping_page)
        self.assertNotIn('gsap.', shopping_page)

    def test_clear_shopping_list_keeps_meal_plan_and_persists_for_week(self):
        self.sign_in_session()
        week_start = '2026-10-26'
        plan_id = self.client.post('/planner/create', json={
            'week_start_date': week_start,
        }).json['id']
        added = self.client.post('/planner/add-meal', json={
            'meal_plan_id': plan_id,
            'day_of_week': 'Mon',
            'meal_type': 'breakfast',
            'recipe_id': 1,
        })
        self.assertEqual(added.status_code, 200)

        page = self.client.get(
            f'/planner/shopping-list?week_start_date={week_start}',
        ).get_data(as_text=True)
        self.assertIn('All-Purpose Flour', page)
        self.assertIn('id="clearAllBtn"', page)
        self.assertIn('function clearAll()', page)

        cleared = self.client.post('/planner/shopping-list/clear', json={
            'week_start_date': week_start,
        })
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json['status'], 'success')

        refreshed_page = self.client.get(
            f'/planner/shopping-list?week_start_date={week_start}',
        ).get_data(as_text=True)
        items_match = re.search(
            r'<script id="shoppingListData" type="application/json">(.*?)</script>',
            refreshed_page,
            re.S,
        )
        self.assertIsNotNone(items_match)
        self.assertEqual(json.loads(items_match.group(1))['items'], [])

        unchanged_plan = self.client.post('/planner/create', json={
            'week_start_date': week_start,
        })
        self.assertEqual(len(unchanged_plan.json['items']), 1)

        added_after_clear = self.client.post('/planner/add-meal', json={
            'meal_plan_id': plan_id,
            'day_of_week': 'Tue',
            'meal_type': 'lunch',
            'recipe_id': 4,
        })
        self.assertEqual(added_after_clear.status_code, 200)
        regenerated_page = self.client.get(
            f'/planner/shopping-list?week_start_date={week_start}',
        ).get_data(as_text=True)
        self.assertIn('All-Purpose Flour', regenerated_page)
        self.assertIn('Sukuma Wiki', regenerated_page)

    def test_dragging_meals_moves_to_empty_slots_and_swaps_occupied_slots(self):
        self.sign_in_session()
        planner_page = self.client.get('/planner/').get_data(as_text=True)
        self.assertIn('draggable="true"', planner_page)
        self.assertIn("plannerBody.addEventListener('drop'", planner_page)
        self.assertIn('/planner/move-meal', planner_page)

        plan_id = self.client.post('/planner/create', json={
            'week_start_date': '2026-10-26',
        }).json['id']
        for day, meal, recipe_id in (
            ('Mon', 'breakfast', 1),
            ('Tue', 'lunch', 4),
        ):
            response = self.client.post('/planner/add-meal', json={
                'meal_plan_id': plan_id,
                'day_of_week': day,
                'meal_type': meal,
                'recipe_id': recipe_id,
            })
            self.assertEqual(response.status_code, 200)

        moved = self.client.post('/planner/move-meal', json={
            'meal_plan_id': plan_id,
            'source_day': 'Mon',
            'source_meal': 'breakfast',
            'target_day': 'Wed',
            'target_meal': 'dinner',
        })
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(len(moved.json['items']), 2)
        self.assertIn({
            'day_of_week': 'Wed',
            'meal_type': 'dinner',
            'recipe_id': '1',
        }, moved.json['items'])

        swapped = self.client.post('/planner/move-meal', json={
            'meal_plan_id': plan_id,
            'source_day': 'Wed',
            'source_meal': 'dinner',
            'target_day': 'Tue',
            'target_meal': 'lunch',
        })
        self.assertEqual(swapped.status_code, 200)
        self.assertEqual({
            (item['day_of_week'], item['meal_type']): item['recipe_id']
            for item in swapped.json['items']
        }, {
            ('Tue', 'lunch'): '1',
            ('Wed', 'dinner'): '4',
        })

    def test_favorite_add_to_meal_action_opens_picker_and_uses_meal_plan_api(self):
        self.sign_in_session()
        self.client.post('/planner/favorite/1')

        response = self.client.get('/planner/favorites')
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('openAddMeal(${r.id},this)', page)
        self.assertIn('addFavoriteToMealPlan()', page)
        self.assertIn('/planner/create', page)
        self.assertIn('/planner/add-meal', page)

    def test_meal_planner_recipe_picker_includes_recipe_images(self):
        self.sign_in_session()
        response = self.client.get('/planner/')
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        recipes_match = re.search(r"data-recipes='(.*?)'", page)
        self.assertIsNotNone(recipes_match)
        recipes = json.loads(html.unescape(recipes_match.group(1)))
        self.assertTrue(recipes)
        self.assertTrue(all('img' in recipe for recipe in recipes))
        self.assertIn("r.img?`background-image:url('${r.img}')", page)
        self.assertIn('id="recipeSearch"', page)
        self.assertIn('id="recipeCategory"', page)
        self.assertIn('id="recipeTime"', page)
        self.assertIn('function renderRecipeCards()', page)
        self.assertIn('selectedCell.scrollIntoView({behavior:\'smooth\',block:\'center\'})', page)

    def test_recipe_browse_and_meal_picker_shuffle_each_request(self):
        original_recipes = recommendations.load_recipes()
        with patch('recommendations.random.shuffle', side_effect=lambda recipes: recipes.reverse()):
            browse_page = self.client.get('/recipes/').get_data(as_text=True)
        browse_match = re.search(r'let RX = (\[.*?\]);', browse_page)
        self.assertIsNotNone(browse_match)
        browse_recipes = json.loads(browse_match.group(1))
        self.assertEqual(browse_recipes[0]['id'], original_recipes[-1]['id'])

        self.sign_in_session()
        with patch('meal_planner.random.shuffle', side_effect=lambda recipes: recipes.reverse()):
            planner_page = self.client.get('/planner/').get_data(as_text=True)
        planner_match = re.search(r"data-recipes='(.*?)'", planner_page)
        self.assertIsNotNone(planner_match)
        planner_recipes = json.loads(html.unescape(planner_match.group(1)))
        self.assertEqual(planner_recipes[0]['id'], original_recipes[-1]['id'])

    def test_personalized_recipes_shuffle_and_browser_can_toggle_scopes(self):
        self.sign_in_session()
        save_response = self.client.post('/preferences', json={
            'health_conditions': [],
            'allergies': [],
            'dietary_restrictions': ['Vegan'],
        })
        self.assertEqual(save_response.status_code, 200)

        source_recipes = recommendations.load_recipes()
        vegan_recipes = recommendations.filter_recipes_by_preferences(
            source_recipes,
            dietary_restrictions=['Vegan'],
        )
        self.assertTrue(vegan_recipes)
        with patch(
            'recommendations.random.shuffle',
            side_effect=lambda recipes: recipes.reverse(),
        ):
            response = self.client.get('/recipes/personalized')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['has_preferences'])
        self.assertEqual(
            [recipe['id'] for recipe in response.json['recipes']],
            [recipe['id'] for recipe in reversed(vegan_recipes)],
        )
        self.assertEqual(
            [recipe['id'] for recipe in recommendations.load_recipes()],
            [recipe['id'] for recipe in source_recipes],
        )

        page = self.client.get('/recipes/').get_data(as_text=True)
        self.assertIn('function togglePersonalization()', page)
        self.assertIn('Show personalised recipes', page)
        self.assertIn('function shuffleRecipes(recipes)', page)

    def test_preferences_page_has_one_save_button(self):
        self.sign_in_session()
        page = self.client.get('/preferences').get_data(as_text=True)
        save_buttons = re.findall(
            r'<button[^>]*class="btn-save"[^>]*>.*?Save Preferences.*?</button>',
            page,
            re.S,
        )
        self.assertEqual(len(save_buttons), 1)

    def test_multi_variation_recipe_is_grouped_in_detail_and_cook_views(self):
        response = self.client.get('/recipes/')
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('Lemon-rosemary chicken noodles', page)
        self.assertIn('Creamy coconut mushroom noodles', page)
        self.assertIn('Pea and minced beef noodles', page)
        self.assertIn('function parseInstructionSections(raw)', page)
        self.assertIn('pp-cook-ingredients', page)

    def test_dashboard_randomizes_featured_and_recommended_recipes(self):
        self.sign_in_session()
        with patch('random.choice', wraps=random.choice) as choose_recipe, \
                patch('random.sample', wraps=random.sample) as sample_recipes:
            response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        choose_recipe.assert_called_once()
        sample_recipes.assert_called_once()

    def test_dashboard_stats_use_only_signed_in_users_data(self):
        self.sign_in_session()
        conn = database.get_db_connection()
        other_user_id = conn.execute(
            'INSERT INTO users (email, password_hash) VALUES (?, ?)',
            ('other@example.com', 'test-hash'),
        ).lastrowid
        week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()

        conn.executemany(
            'INSERT INTO favorites (user_id, recipe_id) VALUES (?, ?)',
            [(self.user_id, '1'), (self.user_id, '2')]
            + [(other_user_id, str(recipe_id)) for recipe_id in range(3, 8)],
        )
        current_plan_id = conn.execute(
            'INSERT INTO meal_plans (user_id, week_start_date) VALUES (?, ?)',
            (self.user_id, week_start),
        ).lastrowid
        other_plan_id = conn.execute(
            'INSERT INTO meal_plans (user_id, week_start_date) VALUES (?, ?)',
            (other_user_id, week_start),
        ).lastrowid
        conn.executemany(
            'INSERT INTO meal_plan_items (meal_plan_id, day_of_week, meal_type, recipe_id) VALUES (?, ?, ?, ?)',
            [(current_plan_id, 'Mon', 'breakfast', '1'),
             (current_plan_id, 'Tue', 'lunch', '2')]
            + [(other_plan_id, 'Mon', 'breakfast', str(recipe_id)) for recipe_id in range(3, 7)],
        )
        conn.execute(
            'INSERT INTO recipe_reviews (user_id, recipe_id, rating, review) VALUES (?, ?, ?, ?)',
            (self.user_id, '1', 5, 'Great'),
        )
        conn.executemany(
            'INSERT INTO recipe_reviews (user_id, recipe_id, rating, review) VALUES (?, ?, ?, ?)',
            [(other_user_id, str(recipe_id), 4, 'Good') for recipe_id in range(2, 5)],
        )
        conn.execute(
            'INSERT INTO preferences (user_id, health_conditions, allergies, dietary_restrictions) VALUES (?, ?, ?, ?)',
            (self.user_id, '["Diabetes"]', '["Peanuts"]', '[]'),
        )
        conn.execute(
            'INSERT INTO preferences (user_id, health_conditions, allergies, dietary_restrictions) VALUES (?, ?, ?, ?)',
            (other_user_id, '["Diabetes","Blood Pressure"]', '["Peanuts"]', '["Vegan","Vegetarian"]'),
        )
        conn.commit()
        conn.close()

        page = self.client.get('/dashboard').get_data(as_text=True)
        expected = {'sv1': 2, 'sv2': 2, 'sv3': 1, 'sv4': 2}
        for element_id, count in expected.items():
            self.assertRegex(
                page,
                rf'id="{element_id}" data-count="{count}"',
            )
        self.assertIn('Reviews Written', page)
        self.assertIn('Preferences Active', page)
        self.assertNotIn('Recipes Cooked', page)

    def test_homepage_navigation_uses_shared_nav_layout(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('.pn-links{display:flex', page)
        self.assertNotRegex(page, re.compile(r'(?m)^\s*nav\s*\{'))

    def test_dashboard_todays_meal_plan_uses_current_day_plan(self):
        self.sign_in_session()
        plan_id = self.client.post('/planner/create', json={}).json['id']
        today = date.today().strftime('%a')
        tomorrow = (date.today() + timedelta(days=1)).strftime('%a')
        for day, meal_type, recipe_id in (
            (today, 'breakfast', 1),
            (tomorrow, 'lunch', 4),
        ):
            response = self.client.post('/planner/add-meal', json={
                'meal_plan_id': plan_id,
                'day_of_week': day,
                'meal_type': meal_type,
                'recipe_id': recipe_id,
            })
            self.assertEqual(response.status_code, 200)

        page = self.client.get('/dashboard').get_data(as_text=True)
        meal_section = re.search(
            r'<div class="meal-section" id="mealSec">(.*?)<div class="recent-section"',
            page,
            re.S,
        )
        self.assertIsNotNone(meal_section)
        self.assertIn('Chapati', meal_section.group(1))
        self.assertNotIn('Sukuma Wiki and Rice', meal_section.group(1))
        self.assertIn('No lunch planned — add one', meal_section.group(1))
        self.assertNotIn('Mkate wa Ufuta', meal_section.group(1))

    def test_recipe_reviews_are_validated_and_upsert_per_user(self):
        self.sign_in_session()
        response = self.client.post('/recipes/1/reviews', json={
            'rating': 5,
            'review': 'Great recipe.',
        })
        self.assertEqual(response.status_code, 200)
        response = self.client.post('/recipes/1/reviews', json={
            'rating': 4,
            'review': 'Updated review.',
        })
        self.assertEqual(response.status_code, 200)
        response = self.client.get('/recipes/1/reviews')
        self.assertEqual(response.json['count'], 1)
        self.assertEqual(response.json['average'], 4)
        self.assertEqual(response.json['my_review']['review'], 'Updated review.')

        invalid_response = self.client.post('/recipes/1/reviews', json={'rating': 6})
        self.assertEqual(invalid_response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
