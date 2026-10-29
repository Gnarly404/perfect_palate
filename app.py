"""
Perfect Palate - Main Flask Application
Routes, authentication, session management
"""
import pkgutil
import importlib.util
import os

# Compatibility shim: Python 3.14 removed `pkgutil.get_loader` which
# older versions of Flask still call. Add a thin replacement that
# returns the loader from `importlib.util.find_spec` when needed.
if not hasattr(pkgutil, 'get_loader'):
    def get_loader(name):
        try:
            spec = importlib.util.find_spec(name)
            return getattr(spec, 'loader', None) if spec is not None else None
        except Exception:
            return None
    pkgutil.get_loader = get_loader

import json
import html
import secrets
import smtplib
import ssl
import bcrypt
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_session import Session
from dotenv import load_dotenv
from werkzeug.security import check_password_hash
from urllib.parse import urljoin, urlsplit
from database import (init_db, get_db_connection, create_password_reset_token, get_valid_password_reset_token,
                      consume_password_reset_token, get_user_profile, update_user_profile, ProfileError,
                      AVATAR_EMOJIS, AVATAR_COLORS, COOKING_LEVELS)
from recommendations import recommendations_bp
from meal_planner import meal_planner_bp

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PUBLIC_BASE_URL'] = os.getenv('PUBLIC_BASE_URL', '').strip()
Session(app)

# Initialize database
init_db()


def hash_password(password):
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_user_password(password_hash, password):
    """Verify bcrypt hashes and transparently upgrade legacy Werkzeug hashes."""
    encoded_password = password.encode('utf-8')
    if password_hash.startswith('$2'):
        if len(encoded_password) > 72:
            return False, False
        try:
            return bcrypt.checkpw(encoded_password, password_hash.encode('ascii')), False
        except (ValueError, TypeError):
            return False, False

    if check_password_hash(password_hash, password):
        return True, len(encoded_password) <= 72
    return False, False


def password_error(password):
    if len(password) < 6:
        return 'Password must be at least 6 characters.'
    if len(password.encode('utf-8')) > 72:
        return 'Password must be no more than 72 UTF-8 bytes.'
    return None


@app.before_request
def validate_session_user():
    """Clear sessions whose account no longer exists."""
    user_id = session.get('user_id')
    if user_id is None:
        return
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        session.clear()
        return
    try:
        conn = get_db_connection()
        try:
            user = conn.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
        finally:
            conn.close()
    except Exception:
        app.logger.exception('Failed to validate the current session.')
        raise
    if user is None:
        session.clear()


# Register blueprints
app.register_blueprint(recommendations_bp)
app.register_blueprint(meal_planner_bp)


@app.context_processor
def inject_profile():
    """Expose the signed-in user's profile to templates as `me` (None when signed out)."""
    user_id = session.get('user_id')
    return {'me': get_user_profile(user_id) if user_id else None}


# Compress HTML/JSON/CSS/JS responses (the recipe list embedded in /recipes/ is ~600 KB of JSON).
try:
    from flask_compress import Compress
    Compress(app)
except ImportError:  # optional: the app still runs, just without compression
    pass


_steps_cache = {}


def _median_steps(recipes):
    """Typical number of method steps per recipe, measured from the data (cached per dataset size)."""
    key = len(recipes)
    if key not in _steps_cache:
        from statistics import median
        from difficulty import split_steps
        counts = [len(split_steps(r['st'])) for r in recipes]
        _steps_cache[key] = int(round(median(counts))) if counts else 0
    return _steps_cache[key]


@app.context_processor
def inject_recipe_total():
    """Real size of the recipe dataset, so pages never advertise a stale hardcoded count."""
    from recommendations import load_recipes
    recipes = load_recipes()
    return {'recipe_total': len(recipes), 'median_steps': _median_steps(recipes)}


def send_password_reset_email(to_email, reset_link):
    """Deliver a password reset email through the configured SMTP server."""
    host = os.getenv('SMTP_HOST', '').strip()
    from_email = os.getenv('SMTP_FROM_EMAIL', '').strip()
    username = os.getenv('SMTP_USERNAME', '').strip()
    password = os.getenv('SMTP_PASSWORD', '')
    from_name = os.getenv('SMTP_FROM_NAME', 'Perfect Palate').strip()

    if not host or not from_email:
        raise RuntimeError('SMTP_HOST and SMTP_FROM_EMAIL must be configured.')
    if bool(username) != bool(password):
        raise RuntimeError('SMTP_USERNAME and SMTP_PASSWORD must both be configured.')

    def smtp_flag(name, default):
        value = os.getenv(name, default).strip().lower()
        if value in {'1', 'true', 'yes', 'on'}:
            return True
        if value in {'0', 'false', 'no', 'off'}:
            return False
        raise RuntimeError(f'{name} must be a boolean value.')

    use_ssl = smtp_flag('SMTP_USE_SSL', 'false')
    use_tls = smtp_flag('SMTP_USE_TLS', 'true')
    if use_ssl and use_tls:
        raise RuntimeError('Enable either SMTP_USE_SSL or SMTP_USE_TLS, not both.')

    try:
        port = int(os.getenv('SMTP_PORT', '587'))
    except ValueError as exc:
        raise RuntimeError('SMTP_PORT must be a valid port number.') from exc
    if not 1 <= port <= 65535:
        raise RuntimeError('SMTP_PORT must be between 1 and 65535.')

    message = EmailMessage()
    message['Subject'] = 'Reset your Perfect Palate password'
    message['From'] = formataddr((from_name, from_email))
    message['To'] = to_email
    message.set_content(
        'We received a request to reset your Perfect Palate password.\n\n'
        f'Use this link within one hour to choose a new password:\n{reset_link}\n\n'
        'If you did not request a password reset, you can ignore this email.'
    )
    message.add_alternative(
        '<p>We received a request to reset your Perfect Palate password.</p>'
        f'<p><a href="{html.escape(reset_link, quote=True)}">'
        'Reset your password</a>. This link expires in one hour.</p>'
        '<p>If you did not request a password reset, you can ignore this email.</p>',
        subtype='html',
    )

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    connection_options = {'timeout': 20}
    if use_ssl:
        connection_options['context'] = ssl.create_default_context()

    with smtp_class(host, port, **connection_options) as smtp:
        if use_tls:
            smtp.starttls(context=ssl.create_default_context())
        if username:
            smtp.login(username, password)
        refused = smtp.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Show the forgot-password form and trigger a reset link request."""
    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        email = (data.get('email') or '').strip().lower()

        if not email:
            return jsonify({'status': 'error', 'message': 'Email address is required.'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()

        if user:
            token = secrets.token_urlsafe(32)
            expires_at = (datetime.now() + timedelta(hours=1)).isoformat(timespec='seconds')
            create_password_reset_token(user['id'], token, expires_at)

            reset_path = url_for('reset_password_page', token=token)
            public_base_url = app.config['PUBLIC_BASE_URL']
            parsed_base_url = urlsplit(public_base_url)
            if (
                parsed_base_url.scheme not in {'http', 'https'}
                or not parsed_base_url.netloc
                or parsed_base_url.username
                or parsed_base_url.password
                or parsed_base_url.query
                or parsed_base_url.fragment
            ):
                consume_password_reset_token(token)
                app.logger.error('PUBLIC_BASE_URL must be a public HTTP or HTTPS origin.')
                return jsonify({
                    'status': 'error',
                    'message': 'Password reset is temporarily unavailable. Please try again later.'
                }), 503
            reset_link = urljoin(public_base_url.rstrip('/') + '/', reset_path.lstrip('/'))

            try:
                send_password_reset_email(email, reset_link)
            except (OSError, RuntimeError, smtplib.SMTPException, ValueError):
                consume_password_reset_token(token)
                app.logger.exception('Failed to deliver password reset email.')
                return jsonify({
                    'status': 'error',
                    'message': 'Password reset is temporarily unavailable. Please try again later.'
                }), 503

        return jsonify({
            'status': 'ok',
            'message': 'If an account exists for that email, we sent a reset link.'
        })

    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password_page(token):
    """Validate the token and allow a new password to be submitted."""
    token_row = get_valid_password_reset_token(token)

    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        password = data.get('password') or ''

        if not token_row:
            return jsonify({'status': 'error', 'message': 'This password reset link is invalid or has expired.'}), 400

        error = password_error(password)
        if error:
            return jsonify({'status': 'error', 'message': error}), 400

        password_hash = hash_password(password)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, token_row['user_id']))
        conn.commit()
        conn.close()

        consume_password_reset_token(token)

        return jsonify({'status': 'ok', 'message': 'Your password has been reset. You can now sign in.'})

    if not token_row:
        return render_template('reset_password.html', token=token, invalid=True, message='This password reset link is invalid or has expired.')

    return render_template('reset_password.html', token=token, invalid=False)

@app.route('/')
def homepage():
    """Landing page"""
    return render_template('homepage.html')

@app.route('/sign-in', methods=['GET', 'POST'])
def sign_in():
    """Authentication endpoint"""
    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''

        if not email or not password:
            return jsonify({'status': 'error', 'message': 'Email and password are required.'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, password_hash FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            return jsonify({'status': 'error', 'message': 'Invalid email or password.'}), 401
        valid_password, needs_rehash = check_user_password(user['password_hash'], password)
        if not valid_password:
            return jsonify({'status': 'error', 'message': 'Invalid email or password.'}), 401
        if needs_rehash:
            conn = get_db_connection()
            try:
                conn.execute(
                    'UPDATE users SET password_hash = ? WHERE id = ?',
                    (hash_password(password), user['id']),
                )
                conn.commit()
            finally:
                conn.close()

        session.clear()
        session['user_id'] = user['id']
        session['email'] = email
        return jsonify({'status': 'ok', 'redirect': url_for('dashboard')})

    return render_template('sign_in.html')

@app.route('/sign-up', methods=['POST'])
def sign_up():
    """Account creation endpoint"""
    data = request.get_json(silent=True) or request.form
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not name or not email or not password:
        return jsonify({'status': 'error', 'message': 'All fields are required.'}), 400
    error = password_error(password)
    if error:
        return jsonify({'status': 'error', 'message': error}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'status': 'error', 'message': 'An account with that email already exists.'}), 409

    password_hash = hash_password(password)
    cursor.execute('INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)', (email, password_hash, name[:40]))
    conn.commit()
    conn.close()

    # Don't auto-login -- the new account should sign in explicitly.
    return jsonify({'status': 'ok', 'redirect': url_for('sign_in')})

@app.route('/dashboard')
def dashboard():
    """User dashboard"""
    if 'user_id' not in session:
        return redirect(url_for('sign_in'))

    from recommendations import load_recipes, filter_recipes_by_preferences
    from database import get_user_preferences
    import random

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM favorites WHERE user_id = ?', (user_id,))
    favorites_count = cursor.fetchone()[0]

    today = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    cursor.execute('''
        SELECT COUNT(*) FROM meal_plan_items mpi
        JOIN meal_plans mp ON mpi.meal_plan_id = mp.id
        WHERE mp.user_id = ? AND mp.week_start_date = ?
    ''', (user_id, week_start))
    meals_planned = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM recipe_reviews WHERE user_id = ?', (user_id,))
    reviews_count = cursor.fetchone()[0]
    cursor.execute('''
        SELECT mpi.meal_type, mpi.recipe_id
        FROM meal_plan_items mpi
        JOIN meal_plans mp ON mpi.meal_plan_id = mp.id
        WHERE mp.user_id = ? AND mp.week_start_date = ? AND mpi.day_of_week = ?
    ''', (user_id, week_start, today.strftime('%a')))
    today_plan_items = cursor.fetchall()
    conn.close()

    recipes = load_recipes()
    total_recipes = len(recipes)
    recipes_by_id = {str(recipe['id']): recipe for recipe in recipes}
    planned_recipes = {
        row['meal_type']: recipes_by_id.get(str(row['recipe_id']))
        for row in today_plan_items
    }
    today_meals = [{
        'type': meal_type,
        'label': label,
        'icon': icon,
        'class': css_class,
        'recipe': planned_recipes.get(meal_type),
    } for meal_type, label, icon, css_class in (
        ('breakfast', 'Breakfast', 'fa-sun', 'ms-b'),
        ('lunch', 'Lunch', 'fa-cloud-sun', 'ms-l'),
        ('dinner', 'Dinner', 'fa-moon', 'ms-d'),
        ('snack', 'Snack', 'fa-cookie-bite', 'ms-l'),
    )]

    # If the user has saved preferences, only recommend recipes that are
    # safe for them; fall back to the full catalogue for everyone else.
    prefs = get_user_preferences(user_id)
    preferences_count = sum(
        len(prefs.get(key, []) or [])
        for key in ('health_conditions', 'allergies', 'dietary_restrictions')
    ) if prefs else 0
    if prefs:
        pool_recipes = filter_recipes_by_preferences(
            recipes,
            prefs.get('health_conditions', []),
            prefs.get('allergies', []),
            prefs.get('dietary_restrictions', []),
        ) or recipes
    else:
        pool_recipes = recipes

    featured_recipe = random.choice(pool_recipes) if pool_recipes else None
    rec_pool = [r for r in pool_recipes if not featured_recipe or r['id'] != featured_recipe['id']]
    recommended_recipes = random.sample(rec_pool, min(3, len(rec_pool)))

    return render_template(
        'dashboard.html',
        total_recipes=total_recipes,
        favorites_count=favorites_count,
        meals_planned=meals_planned,
        reviews_count=reviews_count,
        preferences_count=preferences_count,
        today_meals=today_meals,
        featured_recipe=featured_recipe,
        recommended_recipes=recommended_recipes,
        personalized=bool(prefs),
    )

@app.route('/preferences', methods=['GET', 'POST'])
def preferences():
    """User health/allergy/dietary preferences"""
    if 'user_id' not in session:
        return redirect(url_for('sign_in'))
    
    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        health_conditions = data.get('health_conditions', [])
        allergies = data.get('allergies', [])
        dietary_restrictions = data.get('dietary_restrictions', [])

        user_id = session['user_id']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM preferences WHERE user_id = ?', (user_id,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute('''
                UPDATE preferences
                SET health_conditions = ?, allergies = ?, dietary_restrictions = ?
                WHERE user_id = ?
            ''', (json.dumps(health_conditions), json.dumps(allergies), json.dumps(dietary_restrictions), user_id))
        else:
            cursor.execute('''
                INSERT INTO preferences (user_id, health_conditions, allergies, dietary_restrictions)
                VALUES (?, ?, ?, ?)
            ''', (user_id, json.dumps(health_conditions), json.dumps(allergies), json.dumps(dietary_restrictions)))

        conn.commit()
        conn.close()

        if request.is_json:
            return jsonify({'status': 'saved'})
        return redirect(url_for('dashboard'))

    return render_template('preferences.html')

def _require_json():
    """State-changing profile endpoints only accept JSON. A cross-site form post cannot send
    Content-Type: application/json without a CORS preflight, which blocks simple CSRF."""
    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Expected a JSON request.'}), 415
    return None


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    """View and edit the signed-in user's profile."""
    if 'user_id' not in session:
        if request.method == 'POST':
            return jsonify({'status': 'error', 'message': 'Not logged in.'}), 401
        return redirect(url_for('sign_in'))

    if request.method == 'POST':
        bad = _require_json()
        if bad:
            return bad
        data = request.get_json(silent=True) or {}
        try:
            saved = update_user_profile(session['user_id'], data)
        except ProfileError as exc:
            return jsonify({'status': 'error', 'message': str(exc)}), 400
        return jsonify({'status': 'ok', 'profile': saved})

    conn = get_db_connection()
    favorites_count = conn.execute('SELECT COUNT(*) FROM favorites WHERE user_id = ?', (session['user_id'],)).fetchone()[0]
    since = conn.execute('SELECT created_at FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    return render_template(
        'profile.html', avatar_emojis=AVATAR_EMOJIS, avatar_colors=AVATAR_COLORS,
        cooking_levels=COOKING_LEVELS, favorites_count=favorites_count,
        member_since=(since['created_at'] or '')[:10] if since else '')


@app.route('/profile/password', methods=['POST'])
def change_password():
    """Change password; requires the current one."""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in.'}), 401
    bad = _require_json()
    if bad:
        return bad
    data = request.get_json(silent=True) or {}
    current = data.get('current_password') or ''
    new = data.get('new_password') or ''
    new_error = password_error(new)
    if new_error:
        return jsonify({'status': 'error', 'message': new_error}), 400

    conn = get_db_connection()
    row = conn.execute('SELECT password_hash FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if not row or not check_user_password(row['password_hash'], current)[0]:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Your current password is not correct.'}), 403
    if check_user_password(row['password_hash'], new)[0]:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Choose a password different from your current one.'}), 400
    conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (hash_password(new), session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'message': 'Password updated.'})


@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return redirect(url_for('homepage'))

@app.route('/account/delete', methods=['POST'])
def delete_account():
    """Permanently delete the logged-in user's account and all associated data"""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in.'}), 401

    from database import delete_user_account

    user_id = session['user_id']
    deleted = delete_user_account(user_id)
    session.clear()

    if not deleted:
        return jsonify({'status': 'error', 'message': 'Account could not be found.'}), 404

    return jsonify({'status': 'ok', 'redirect': url_for('homepage')})

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
    port = int(os.getenv('PORT', 5000))
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
