"""
Perfect Palate - Meal Planner & Favourites Blueprint
Meal plan creation, management, and favorite recipes
"""
import re
from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for

from database import get_db_connection

meal_planner_bp = Blueprint('meal_planner', __name__, url_prefix='/planner')
WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
MEAL_TYPES = ('breakfast', 'lunch', 'dinner', 'snack')


def _week_start(value=None):
    if value:
        try:
            selected = date.fromisoformat(value)
        except (TypeError, ValueError):
            return None
        if selected.weekday() != 0:
            return None
        return selected.isoformat()
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


def _ensure_plan(user_id, week_start):
    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute(
            'SELECT id FROM meal_plans WHERE user_id = ? AND week_start_date = ? ORDER BY id LIMIT 1',
            (user_id, week_start),
        ).fetchone()
        if row:
            plan_id = row['id']
        else:
            cursor = conn.execute(
                'INSERT INTO meal_plans (user_id, week_start_date) VALUES (?, ?)',
                (user_id, week_start),
            )
            plan_id = cursor.lastrowid
        conn.commit()
        return plan_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _plan_items(plan_id):
    conn = get_db_connection()
    try:
        rows = conn.execute(
            '''
            SELECT day_of_week, meal_type, recipe_id
            FROM meal_plan_items
            WHERE meal_plan_id = ?
            ''',
            (plan_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

@meal_planner_bp.route('/')
def meal_planner():
    """7-day meal planner view"""
    if 'user_id' not in session:
        return redirect(url_for('sign_in'))

    week_start = _week_start(request.args.get('week_start_date'))
    if not week_start:
        return jsonify({'error': 'week_start_date must be a Monday in YYYY-MM-DD format.'}), 400

    from recommendations import load_recipes

    recipes = load_recipes()
    recipe_data = [{
        'id': recipe['id'],
        't': recipe['t'],
        'c': recipe['c'],
        'em': recipe['em'],
        'tm': int(re.search(r'\d+', recipe['tm']).group()),
        'g': recipe['g'],
        'img': recipe['img'],
        'ing': recipe['ing'],
    } for recipe in recipes]
    plan_id = _ensure_plan(session['user_id'], week_start)
    return render_template(
        'meal_planner.html',
        recipes=recipe_data,
        plan_items=_plan_items(plan_id),
        plan_id=plan_id,
        week_start=week_start,
    )

@meal_planner_bp.route('/create', methods=['POST'])
def create_meal_plan():
    """Create or retrieve the current user's plan for a week."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    week_start = _week_start(data.get('week_start_date'))
    if not week_start:
        return jsonify({'error': 'week_start_date must be a Monday in YYYY-MM-DD format.'}), 400
    plan_id = _ensure_plan(session['user_id'], week_start)
    return jsonify({'id': plan_id, 'week_start_date': week_start, 'items': _plan_items(plan_id)})

@meal_planner_bp.route('/add-meal', methods=['POST'])
def add_meal_to_plan():
    """Add recipe to meal plan"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    meal_plan_id = data.get('meal_plan_id')
    day_of_week = data.get('day_of_week')
    meal_type = data.get('meal_type')
    recipe_id = data.get('recipe_id')
    try:
        meal_plan_id = int(meal_plan_id)
        recipe_id = str(int(recipe_id))
    except (TypeError, ValueError):
        return jsonify({'error': 'A valid meal plan and recipe are required.'}), 400
    if day_of_week not in WEEKDAYS or meal_type not in MEAL_TYPES:
        return jsonify({'error': 'Invalid day or meal type.'}), 400

    from recommendations import load_recipes

    if not any(str(recipe['id']) == recipe_id for recipe in load_recipes()):
        return jsonify({'error': 'Recipe not found.'}), 404

    conn = get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        owned_plan = conn.execute(
            'SELECT id FROM meal_plans WHERE id = ? AND user_id = ?',
            (meal_plan_id, session['user_id']),
        ).fetchone()
        if not owned_plan:
            conn.rollback()
            return jsonify({'error': 'Meal plan not found.'}), 404
        conn.execute(
            'DELETE FROM meal_plan_items WHERE meal_plan_id = ? AND day_of_week = ? AND meal_type = ?',
            (meal_plan_id, day_of_week, meal_type),
        )
        conn.execute(
            '''
            INSERT INTO meal_plan_items (meal_plan_id, day_of_week, meal_type, recipe_id)
            VALUES (?, ?, ?, ?)
            ''',
            (meal_plan_id, day_of_week, meal_type, recipe_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return jsonify({'status': 'success'})


@meal_planner_bp.route('/remove-meal', methods=['POST'])
def remove_meal_from_plan():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON object is required.'}), 400
    try:
        meal_plan_id = int(data.get('meal_plan_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'A valid meal plan is required.'}), 400
    day_of_week = data.get('day_of_week')
    meal_type = data.get('meal_type')
    if day_of_week not in WEEKDAYS or meal_type not in MEAL_TYPES:
        return jsonify({'error': 'Invalid day or meal type.'}), 400

    conn = get_db_connection()
    try:
        cursor = conn.execute(
            '''
            DELETE FROM meal_plan_items
            WHERE meal_plan_id = ? AND day_of_week = ? AND meal_type = ?
              AND meal_plan_id IN (SELECT id FROM meal_plans WHERE user_id = ?)
            ''',
            (meal_plan_id, day_of_week, meal_type, session['user_id']),
        )
        conn.commit()
        if not cursor.rowcount:
            return jsonify({'error': 'Meal plan or item not found.'}), 404
    finally:
        conn.close()
    return jsonify({'status': 'success'})

@meal_planner_bp.route('/shopping-list')
def shopping_list():
    """Generate a categorized shopping list from this week's planned recipes."""
    if 'user_id' not in session:
        return redirect(url_for('sign_in'))

    from recommendations import load_recipes

    week_start = _week_start(request.args.get('week_start_date'))
    if not week_start:
        return jsonify({'error': 'week_start_date must be a Monday in YYYY-MM-DD format.'}), 400
    plan_id = _ensure_plan(session['user_id'], week_start)
    recipes_by_id = {str(recipe['id']): recipe for recipe in load_recipes()}
    aggregated = {}
    for item in _plan_items(plan_id):
        recipe = recipes_by_id.get(str(item['recipe_id']))
        if not recipe:
            continue
        for ingredient in re.split(r',\s*(?=[A-Za-z])', recipe['ing']):
            ingredient = ingredient.strip()
            if not ingredient:
                continue
            match = re.match(r'^(.*?)\s*\((.*?)\)\s*$', ingredient)
            name = (match.group(1) if match else ingredient).strip()
            quantity = match.group(2).strip() if match else ''
            normalized = name.casefold()
            entry = aggregated.setdefault(normalized, {
                'name': name,
                'quantities': [],
                'sources': [],
                'category': _ingredient_category(name),
            })
            if quantity and quantity not in entry['quantities']:
                entry['quantities'].append(quantity)
            if recipe['t'] not in entry['sources']:
                entry['sources'].append(recipe['t'])

    items = [{
        'id': index + 1,
        'name': entry['name'],
        'qty': ', '.join(entry['quantities']),
        'src': ', '.join(entry['sources']),
        'cat': entry['category'],
        'done': False,
    } for index, entry in enumerate(aggregated.values())]
    return render_template('shopping_list.html', items=items)


def _ingredient_category(name):
    value = name.casefold()
    if re.search(r'\b(milk|cream|butter|cheese|yogh?urt|ghee)\b', value):
        return 'dairy'
    if re.search(r'\b(beef|chicken|meat|fish|pork|lamb|goat|prawn|shrimp|egg)\b', value):
        return 'protein'
    if re.search(r'\b(tomato|onion|garlic|ginger|potato|carrot|coriander|cilantro|spinach|kale|cabbage|pepper|chili|chilli|lime|lemon|avocado|banana|mango|vegetable)\b', value):
        return 'produce'
    return 'pantry'

# Favorites management
@meal_planner_bp.route('/favorites')
def favorites():
    """View favorite recipes"""
    if 'user_id' not in session:
        return redirect(url_for('sign_in'))

    import json
    from recommendations import load_recipes

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT recipe_id, added_at FROM favorites WHERE user_id = ? ORDER BY added_at DESC
    ''', (user_id,))
    favorite_rows = cursor.fetchall()
    conn.close()

    added_at_by_id = {}
    for row in favorite_rows:
        rid = row['recipe_id']
        if rid.isdigit():
            added_at_by_id[int(rid)] = row['added_at']

    recipes = load_recipes()
    favorite_recipes = []
    for r in recipes:
        if r['id'] not in added_at_by_id:
            continue
        favorite_recipes.append({
            'id': r['id'],
            't': r['t'],
            'c': r['c'],
            'd': r['d'],
            'ing': r['ing'],
            'st': r['st'],
            'tags': r['tg'],
            'tm': int(r['tm'].split()[0]) if r['tm'].split()[0].isdigit() else 30,
            'sv': r['sv'],
            'g': r['g'],
            'em': r['em'],
            'img': r['img'],
            'w': False,
            'added': _time_ago(added_at_by_id[r['id']]),
        })

    return render_template('favorites.html', favorites=favorite_recipes, favorites_json=json.dumps(favorite_recipes))

def _time_ago(timestamp_str):
    """Turn a SQLite CURRENT_TIMESTAMP string into a friendly relative label."""
    if not timestamp_str:
        return 'recently'
    try:
        added = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return 'recently'

    delta = datetime.utcnow() - added
    days = delta.days
    if days <= 0:
        return 'today'
    if days == 1:
        return 'yesterday'
    if days < 7:
        return f'{days} days ago'
    weeks = days // 7
    if weeks == 1:
        return '1 week ago'
    if weeks < 5:
        return f'{weeks} weeks ago'
    months = days // 30
    return f'{months} month{"s" if months != 1 else ""} ago'

@meal_planner_bp.route('/favorite/<recipe_id>', methods=['POST'])
def add_favorite(recipe_id):
    """Add recipe to favorites"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR IGNORE INTO favorites (user_id, recipe_id)
        VALUES (?, ?)
    ''', (user_id, recipe_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'added'})

@meal_planner_bp.route('/favorite/<recipe_id>', methods=['DELETE'])
def remove_favorite(recipe_id):
    """Remove recipe from favorites"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM favorites WHERE user_id = ? AND recipe_id = ?
    ''', (user_id, recipe_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'removed'})
