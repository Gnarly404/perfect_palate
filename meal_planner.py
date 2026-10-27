"""
Perfect Palate - Meal Planner & Favourites Blueprint
Meal plan creation, management, and favorite recipes
"""
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from database import get_db_connection
from datetime import datetime, timedelta

meal_planner_bp = Blueprint('meal_planner', __name__, url_prefix='/planner')

@meal_planner_bp.route('/')
def meal_planner():
    """7-day meal planner view"""
    if 'user_id' not in session:
        return redirect(url_for('sign_in'))
    
    # TODO: Load user's meal plan from database
    return render_template('meal_planner.html')

@meal_planner_bp.route('/create', methods=['POST'])
def create_meal_plan():
    """Create a new meal plan"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    week_start = request.json.get('week_start_date')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO meal_plans (user_id, week_start_date)
        VALUES (?, ?)
    ''', (user_id, week_start))
    
    conn.commit()
    plan_id = cursor.lastrowid
    conn.close()
    
    return jsonify({'id': plan_id})

@meal_planner_bp.route('/add-meal', methods=['POST'])
def add_meal_to_plan():
    """Add recipe to meal plan"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    meal_plan_id = data.get('meal_plan_id')
    day_of_week = data.get('day_of_week')
    meal_type = data.get('meal_type')  # breakfast, lunch, dinner, snack
    recipe_id = data.get('recipe_id')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO meal_plan_items (meal_plan_id, day_of_week, meal_type, recipe_id)
        VALUES (?, ?, ?, ?)
    ''', (meal_plan_id, day_of_week, meal_type, recipe_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success'})

@meal_planner_bp.route('/shopping-list')
def shopping_list():
    """Generate shopping list from meal plan"""
    if 'user_id' not in session:
        return redirect(url_for('sign_in'))
    
    # TODO: Parse meal plan and generate categorized shopping list
    return render_template('shopping_list.html')

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
