"""
Perfect Palate - Recommendations Blueprint
Recipe filtering, scoring, search, and image serving
"""
from flask import Blueprint, render_template, request, jsonify, send_file, redirect, url_for, session, abort, current_app
from database import get_db_connection
import csv
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

from nutrition import estimate_nutrition
from difficulty import rate_difficulty
from tips import tips_for_recipe, tip_payload, TIPS

recommendations_bp = Blueprint('recommendations', __name__, url_prefix='/recipes')

CSV_PATH = 'Dataset/Kenyan Recipes.csv'
IMAGE_DIR = 'Dataset/Recipe images'

# Visual styling per category (dataset has no colour/emoji data, so this
# is presentation-only; the recipe content itself is always real data).
CATEGORY_STYLE = {
    'Main Dish':   {'emoji': '🍚', 'gradient': 'linear-gradient(140deg,#2a4d63,#426e86)'},
    'Vegetarian':  {'emoji': '🫘', 'gradient': 'linear-gradient(140deg,#1e3028,#35564a)'},
    'Seafood':     {'emoji': '🐟', 'gradient': 'linear-gradient(140deg,#1a3545,#2a5560)'},
    'Dessert':     {'emoji': '🍰', 'gradient': 'linear-gradient(140deg,#4a2d3a,#7a4a5c)'},
    'Breakfast':   {'emoji': '🍳', 'gradient': 'linear-gradient(140deg,#4a3a1e,#8a6a2d)'},
    'Salad':       {'emoji': '🥗', 'gradient': 'linear-gradient(140deg,#1e3a2a,#2d6050)'},
    'Beverage':    {'emoji': '🥤', 'gradient': 'linear-gradient(140deg,#2a1e4a,#5c3a7a)'},
    'Bread':       {'emoji': '🍞', 'gradient': 'linear-gradient(140deg,#4a3220,#7a5535)'},
    'Soup':        {'emoji': '🍲', 'gradient': 'linear-gradient(140deg,#2a3a1e,#4a5c2d)'},
    'Appetizer':   {'emoji': '🥟', 'gradient': 'linear-gradient(140deg,#3a2a4a,#6a4a7a)'},
    'Snack':       {'emoji': '🍿', 'gradient': 'linear-gradient(140deg,#4a3a20,#8a6a35)'},
    'Meat':        {'emoji': '🍖', 'gradient': 'linear-gradient(140deg,#4a2020,#7a3a3a)'},
    'Pasta':       {'emoji': '🍝', 'gradient': 'linear-gradient(140deg,#3a2a1a,#6a4a2a)'},
    'Side Dish':   {'emoji': '🥘', 'gradient': 'linear-gradient(140deg,#2a3a3a,#4a6060)'},
    'Condiment':   {'emoji': '🫙', 'gradient': 'linear-gradient(140deg,#3a3020,#6a5535)'},
    'Staple':      {'emoji': '🌾', 'gradient': 'linear-gradient(140deg,#3a3520,#6a6035)'},
    'Baked Goods': {'emoji': '🧁', 'gradient': 'linear-gradient(140deg,#4a2d3a,#7a4a5c)'},
}
DEFAULT_STYLE = {'emoji': '🍽️', 'gradient': 'linear-gradient(140deg,#2a4d63,#426e86)'}

# Servings are not in the dataset; use a sane category-based default rather
# than inventing a precise number per recipe.
SERVINGS_BY_CATEGORY = {'Beverage': 2, 'Dessert': 6, 'Bread': 8, 'Baked Goods': 8, 'Condiment': 10}
DEFAULT_SERVINGS = 4

_image_index_cache = None
_recipes_cache = None


def _normalize(name):
    """Lowercase, strip anything that isn't a letter/number, for fuzzy filename matching."""
    return re.sub(r'[^a-z0-9]', '', name.lower())


def _build_image_index():
    """Map a normalized recipe title -> actual filename on disk, once."""
    global _image_index_cache
    if _image_index_cache is not None:
        return _image_index_cache

    index = {}
    if os.path.isdir(IMAGE_DIR):
        for fname in os.listdir(IMAGE_DIR):
            base, ext = os.path.splitext(fname)
            if ext.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
                index[_normalize(base)] = fname
    _image_index_cache = index
    return index


def _compact_nutrition(n):
    if not n:
        return None
    p = n['per_serving']
    return {'k': p['kcal'], 'p': p['protein'], 'c': p['carbs'], 'f': p['fat'], 'fi': p['fiber'],
            's': p['sugar'], 'na': p['sodium'], 'sv': n['servings'], 'cov': n['coverage'],
            'conf': n['confidence'], 'left': n['left_out'], 'notes': n['notes']}


def load_recipes(force_reload=False):
    """Load and normalize recipes from the Kenyan Recipes dataset."""
    global _recipes_cache
    if _recipes_cache is not None and not force_reload:
        return _recipes_cache

    recipes = []
    if not os.path.exists(CSV_PATH):
        _recipes_cache = recipes
        return recipes

    image_index = _build_image_index()

    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        all_rows = list(csv.DictReader(f))

    # The dataset reuses some Recipe IDs for different dishes (34 of them), which
    # would make favourites and share links ambiguous. The first row keeps its
    # ID, later rows that collide get fresh IDs above the dataset's maximum, in
    # file order, so the assignment is stable between runs.
    used = set()
    next_free = max([int(r['Recipe ID']) for r in all_rows if (r.get('Recipe ID') or '').strip().isdigit()] or [0]) + 1
    ids = []
    for i, row in enumerate(all_rows):
        raw = (row.get('Recipe ID') or '').strip()
        rid = int(raw) if raw.isdigit() else None
        if rid is None or rid in used:
            rid = next_free
            next_free += 1
        used.add(rid)
        ids.append(rid)

    for i, row in enumerate(all_rows):
        title = (row.get('Recipe Title') or '').strip()
        if not title:
            continue

        category = (row.get('Recipe Category') or 'Other').strip()
        ingredients_raw = (row.get('Recipe Ingredients Quantities') or '').strip()
        instructions_raw = (row.get('Recipe Instructions') or '').strip()
        description = (row.get('Description') or '').strip()

        style = CATEGORY_STYLE.get(category, DEFAULT_STYLE)

        # Dietary/health tags, derived directly from the dataset's own flag columns
        tags = []
        if row.get('Vegan', '').strip() == '#':
            tags.append('vg')
        if row.get('Vegetarian', '').strip() == '#':
            tags.append('veg')
        if row.get('Gluten-Free', '').strip() == '#':
            tags.append('gf')
        if row.get('Blood Pressure', '').strip() == '#':
            tags.append('bp')
        if row.get('Diabetes', '').strip() == '#':
            tags.append('dia')
        if re.search(r'\bchil?[il]?e?s?\b|pepper', ingredients_raw, re.I):
            tags.append('sp')

        # Duration isn't in the dataset; estimate roughly from step count
        # rather than fabricating a specific figure.
        step_count = len([s for s in re.split(r'\d+\.\s+', instructions_raw) if s.strip()])
        est_minutes = max(15, min(90, 10 + step_count * 6))
        est_servings = SERVINGS_BY_CATEGORY.get(category, DEFAULT_SERVINGS)

        image_file = image_index.get(_normalize(title))
        recipe_id = ids[i]

        difficulty = rate_difficulty(ingredients_raw, instructions_raw)
        nutrition = estimate_nutrition(ingredients_raw, est_servings, category)
        tip_ids = tips_for_recipe(title, category, ingredients_raw, instructions_raw)

        recipes.append({
            'id': recipe_id,
            't': title,
            'c': category,
            'd': description or f"A traditional Kenyan {category.lower()} dish.",
            'ing': ingredients_raw,
            'st': instructions_raw,
            'tg': tags,
            'tm': f'{est_minutes} min',
            'sv': est_servings,
            'g': style['gradient'],
            'em': style['emoji'],
            'img': f'/recipes/image/{quote(image_file)}' if image_file else None,
            'df': {'l': difficulty['level'], 'r': difficulty['rank'], 'why': difficulty['reasons']},
            'nu': _compact_nutrition(nutrition),
            'tips': tip_ids,
            'flags': {
                'blood_pressure': row.get('Blood Pressure', '').strip() == '#',
                'blood_sugar': row.get('Blood Sugar', '').strip() == '#',
                'high_cholesterol': row.get('High Cholesterol', '').strip() == '#',
                'diabetes': row.get('Diabetes', '').strip() == '#',
                'allergy_safe_meat': row.get('Allergies_Meat', '').strip() == '#',
                'allergy_safe_eggs': row.get('Allergies_Eggs', '').strip() == '#',
                'allergy_safe_fish': row.get('Allergies_Fish', '').strip() == '#',
                'allergy_safe_peanuts': row.get('Allergies_Peanuts', '').strip() == '#',
                'gluten_free': row.get('Gluten-Free', '').strip() == '#',
                'lactose_free': row.get('Lactose-Intolerant', '').strip() == '#',
                'vegan': row.get('Vegan', '').strip() == '#',
                'vegetarian': row.get('Vegetarian', '').strip() == '#',
            },
        })

    _recipes_cache = recipes
    return recipes


@recommendations_bp.route('/')
def recommendations():
    """Recipe recommendations page"""
    recipes = load_recipes()
    return render_template('recommendations.html', recipes=recipes, recipes_json=_safe_json(recipes),
                           tips_json=_safe_json(tip_payload()), og=None, open_recipe=None)


def _safe_json(obj):
    """JSON for embedding inside a <script> tag: '<' is escaped so '</script>' cannot appear."""
    return json.dumps(obj).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def _public_base():
    configured = (current_app.config.get('PUBLIC_BASE_URL') or '').strip().rstrip('/')
    return configured or request.url_root.rstrip('/')


@recommendations_bp.route('/recipe/<int:recipe_id>')
def recipe_permalink(recipe_id):
    """Shareable link to one recipe: public, with Open Graph / Twitter card tags for link previews."""
    recipes = load_recipes()
    recipe = next((r for r in recipes if r['id'] == recipe_id), None)
    if not recipe:
        abort(404)

    base = _public_base()
    url = f"{base}{url_for('recommendations.recipe_permalink', recipe_id=recipe_id)}"
    image = f"{base}{recipe['img']}?w=960" if recipe['img'] else f"{base}{url_for('static', filename='images/Logo.png')}"
    desc = recipe['d']
    nu = recipe.get('nu')
    bits = [recipe['df']['l'], recipe['tm']]
    if nu:
        bits.append(f"about {nu['k']} kcal per serving")
    og = {'title': f"{recipe['t']} | Perfect Palate", 'description': f"{desc} ({', '.join(bits)})"[:300],
          'url': url, 'image': image}
    return render_template('recommendations.html', recipes=recipes, recipes_json=_safe_json(recipes),
                           tips_json=_safe_json(tip_payload()), og=og, open_recipe=recipe_id)


@recommendations_bp.route('/tips')
def cooking_tips():
    """Cooking tips and techniques library."""
    groups = [('safety', 'Food safety'), ('technique', 'Techniques'), ('kenyan', 'Kenyan kitchen'), ('flavour', 'Flavour')]
    grouped = [(label, [t for t in TIPS if t['kind'] == key]) for key, label in groups]
    return render_template('tips.html', groups=grouped)

@recommendations_bp.route('/search', methods=['GET'])
def search():
    """Search recipes by name or ingredients"""
    query = request.args.get('q', '').lower()
    recipes = load_recipes()

    filtered = [r for r in recipes if query in r['t'].lower() or query in r['ing'].lower()]
    return jsonify(filtered)


@recommendations_bp.route('/<int:recipe_id>/reviews', methods=['GET', 'POST'])
def recipe_reviews(recipe_id):
    """Read community reviews or create/update the signed-in user's review."""
    recipe = next((r for r in load_recipes() if r['id'] == recipe_id), None)
    if not recipe:
        return jsonify({'error': 'Recipe not found.'}), 404

    if request.method == 'POST':
        user_id = session.get('user_id')
        if user_id is None:
            return jsonify({'error': 'Sign in to rate and review recipes.'}), 401
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'error': 'A JSON object is required.'}), 400
        rating = data.get('rating')
        review = data.get('review', '')
        if not isinstance(review, str):
            return jsonify({'error': 'Review must be plain text.'}), 400
        review = review.strip()
        if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
            return jsonify({'error': 'Rating must be a whole number from 1 to 5.'}), 400
        if len(review) > 1000:
            return jsonify({'error': 'Reviews must be 1,000 characters or fewer.'}), 400

        conn = get_db_connection()
        try:
            conn.execute(
                '''
                INSERT INTO recipe_reviews (user_id, recipe_id, rating, review)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, recipe_id) DO UPDATE SET
                    rating = excluded.rating,
                    review = excluded.review,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (user_id, str(recipe_id), rating, review),
            )
            conn.commit()
        finally:
            conn.close()

    conn = get_db_connection()
    try:
        summary = conn.execute(
            '''
            SELECT COUNT(*) AS count, AVG(rating) AS average
            FROM recipe_reviews
            WHERE recipe_id = ?
            ''',
            (str(recipe_id),),
        ).fetchone()
        rows = conn.execute(
            '''
            SELECT rating, review, created_at
            FROM recipe_reviews
            WHERE recipe_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 20
            ''',
            (str(recipe_id),),
        ).fetchall()
        own_review = None
        if session.get('user_id') is not None:
            own_review = conn.execute(
                '''
                SELECT rating, review FROM recipe_reviews
                WHERE recipe_id = ? AND user_id = ?
                ''',
                (str(recipe_id), session['user_id']),
            ).fetchone()
    finally:
        conn.close()

    return jsonify({
        'count': summary['count'],
        'average': round(summary['average'], 1) if summary['average'] is not None else None,
        'reviews': [{
            'rating': row['rating'],
            'review': row['review'],
            'created_at': row['created_at'],
        } for row in rows],
        'my_review': dict(own_review) if own_review else None,
        'authenticated': session.get('user_id') is not None,
    })

def filter_recipes_by_preferences(recipes, health_conditions=None, allergies=None, dietary_restrictions=None):
    """Return only the recipes that are safe for the given preferences."""
    health_conditions = set(health_conditions or [])
    allergies = set(allergies or [])
    dietary_restrictions = set(dietary_restrictions or [])

    if not health_conditions and not allergies and not dietary_restrictions:
        return list(recipes)

    def is_safe(r):
        flags = r['flags']
        if 'Blood Pressure' in health_conditions and not flags['blood_pressure']:
            return False
        if 'Diabetes' in health_conditions and not flags['diabetes']:
            return False
        if 'High Cholesterol' in health_conditions and not flags['high_cholesterol']:
            return False
        if 'Meat' in allergies and not flags['allergy_safe_meat']:
            return False
        if 'Eggs' in allergies and not flags['allergy_safe_eggs']:
            return False
        if 'Fish' in allergies and not flags['allergy_safe_fish']:
            return False
        if 'Peanuts' in allergies and not flags['allergy_safe_peanuts']:
            return False
        if 'Vegan' in dietary_restrictions and not flags['vegan']:
            return False
        if 'Vegetarian' in dietary_restrictions and not flags['vegetarian']:
            return False
        if 'Gluten-Free' in dietary_restrictions and not flags['gluten_free']:
            return False
        if 'Lactose-Intolerant' in dietary_restrictions and not flags['lactose_free']:
            return False
        return True

    return [r for r in recipes if is_safe(r)]


@recommendations_bp.route('/filter', methods=['POST'])
def filter_recipes():
    """Filter recipes by health/dietary preferences"""
    data = request.json or {}
    recipes = load_recipes()
    filtered = filter_recipes_by_preferences(
        recipes,
        data.get('health_conditions', []),
        data.get('allergies', []),
        data.get('dietary_restrictions', []),
    )
    return jsonify(filtered)

@recommendations_bp.route('/personalized')
def personalized_recipes():
    """Return recipes filtered by the logged-in user's saved preferences"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    from database import get_user_preferences
    prefs = get_user_preferences(session['user_id'])
    recipes = load_recipes()

    if not prefs:
        return jsonify({'has_preferences': False, 'recipes': recipes})

    filtered = filter_recipes_by_preferences(
        recipes,
        prefs.get('health_conditions', []),
        prefs.get('allergies', []),
        prefs.get('dietary_restrictions', []),
    )
    return jsonify({'has_preferences': True, 'recipes': filtered, 'preferences': prefs})

IMAGE_WIDTHS = (480, 960)   # whitelist so the cache can't be filled with arbitrary sizes
IMAGE_CACHE_SECONDS = 60 * 60 * 24 * 7


def _resized_image(image_path, width):
    """Return the path of a cached WebP copy of the image no wider than `width` (built once)."""
    cache_dir = os.path.join(current_app.instance_path, 'image_cache')
    os.makedirs(cache_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(image_path))[0]
    out = os.path.join(cache_dir, f'{stem}.{width}.webp')
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(image_path):
        from PIL import Image
        with Image.open(image_path) as im:
            im = im.convert('RGB')
            if im.width > width:
                im.thumbnail((width, width * 4))
            im.save(out + '.tmp', 'WEBP', quality=80, method=4)
        os.replace(out + '.tmp', out)
    return out


@recommendations_bp.route('/image/<path:filename>')
def get_recipe_image(filename):
    """Serve a recipe image from the dataset. ?w=480 or ?w=960 returns a smaller cached WebP."""
    safe_name = os.path.basename(filename)
    image_path = os.path.join(IMAGE_DIR, safe_name)

    if os.path.exists(image_path):
        width = request.args.get('w', type=int)
        if width in IMAGE_WIDTHS:
            try:
                return send_file(_resized_image(image_path, width), mimetype='image/webp', max_age=IMAGE_CACHE_SECONDS)
            except Exception:
                current_app.logger.exception('Could not resize %s; serving the original', safe_name)
        return send_file(image_path, max_age=IMAGE_CACHE_SECONDS)
    return send_file('static/images/icon.png', mimetype='image/png')

@recommendations_bp.route('/cook-mode/<int:recipe_id>')
def cook_mode(recipe_id):
    """Redirect into the in-page Cook Mode view for a given recipe"""
    recipes = load_recipes()
    recipe = next((r for r in recipes if r['id'] == recipe_id), None)

    if recipe:
        return redirect(url_for('recommendations.recommendations') + f'#cook-{recipe_id}')
    return redirect(url_for('recommendations.recommendations'))
