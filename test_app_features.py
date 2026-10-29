import bcrypt
import json
import os
import re
import tempfile
import unittest

import database
from app import app
from werkzeug.security import generate_password_hash


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
        items_match = re.search(r'let items=(.*);', shopping_page)
        self.assertIsNotNone(items_match)
        generated_items = json.loads(items_match.group(1))
        self.assertIn('All-Purpose Flour', [item['name'] for item in generated_items])
        self.assertIn('Water', [item['name'] for item in generated_items])
        self.assertIn('produce', [item['cat'] for item in generated_items])
        self.assertIn('function toggleItem(id)', shopping_page)
        self.assertIn('navigator.share', shopping_page)
        self.assertNotIn('gsap.', shopping_page)

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
        recipes_match = re.search(r'const RX=(\[.*?\]);', page)
        self.assertIsNotNone(recipes_match)
        recipes = json.loads(recipes_match.group(1))
        self.assertTrue(recipes)
        self.assertTrue(all('img' in recipe for recipe in recipes))
        self.assertIn("r.img?`background-image:url('${r.img}')", page)

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
