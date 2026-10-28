"""
Perfect Palate - Database Initialization and Connection
SQLite database setup and helper functions
"""
import sqlite3
import os
from datetime import datetime, timedelta

DATABASE = 'instance/perfect_palate.db'

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_user_preferences(user_id):
    """Return a user's saved preferences as a dict of lists, or None if never saved."""
    import json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT health_conditions, allergies, dietary_restrictions FROM preferences WHERE user_id = ?',
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        'health_conditions': json.loads(row['health_conditions'] or '[]'),
        'allergies': json.loads(row['allergies'] or '[]'),
        'dietary_restrictions': json.loads(row['dietary_restrictions'] or '[]'),
    }

# --------------------------------------------------------------------------- #
# Profile customisation
# --------------------------------------------------------------------------- #
AVATAR_EMOJIS = ['🍳', '🥘', '🍲', '🍛', '🥗', '🍞', '🌶️', '🥭', '🍋', '🥥', '🫘', '🌽', '🐟', '🍰', '☕', '🔥']
AVATAR_COLORS = {
    'blue': '#426e86', 'gold': '#b8941f', 'green': '#2d6a4f', 'plum': '#6a4a7a',
    'rust': '#9c4a2e', 'teal': '#2a6a6a', 'rose': '#a04a62', 'slate': '#4a5560',
}
COOKING_LEVELS = ('beginner', 'intermediate', 'advanced')
PROFILE_DEFAULTS = {
    'display_name': '', 'bio': '', 'avatar_emoji': '🍳', 'avatar_color': 'blue',
    'cooking_level': '', 'calorie_goal': None,
}


class ProfileError(ValueError):
    """Raised when submitted profile data is not acceptable. The message is safe to show the user."""


def _clean_text(value, max_len, label, required=False):
    value = ''.join(ch for ch in str(value or '') if ch.isprintable() or ch in '\n')
    value = ' '.join(value.split()) if max_len <= 60 else value.strip()
    if required and not value:
        raise ProfileError(f'{label} is required.')
    if len(value) > max_len:
        raise ProfileError(f'{label} must be {max_len} characters or fewer.')
    return value


def validate_profile(data):
    """Validate and normalise profile fields. Raises ProfileError on bad input."""
    out = {}
    out['display_name'] = _clean_text(data.get('display_name'), 40, 'Display name', required=True)
    out['bio'] = _clean_text(data.get('bio'), 200, 'Bio')

    emoji = data.get('avatar_emoji') or PROFILE_DEFAULTS['avatar_emoji']
    if emoji not in AVATAR_EMOJIS:
        raise ProfileError('Please pick an avatar from the list.')
    out['avatar_emoji'] = emoji

    color = data.get('avatar_color') or PROFILE_DEFAULTS['avatar_color']
    if color not in AVATAR_COLORS:
        raise ProfileError('Please pick an avatar colour from the list.')
    out['avatar_color'] = color

    level = (data.get('cooking_level') or '').strip().lower()
    if level and level not in COOKING_LEVELS:
        raise ProfileError('Cooking level must be beginner, intermediate or advanced.')
    out['cooking_level'] = level

    goal = data.get('calorie_goal')
    if goal in (None, '', 'null'):
        out['calorie_goal'] = None
    else:
        try:
            goal = int(str(goal).strip())
        except (TypeError, ValueError):
            raise ProfileError('Daily calorie goal must be a whole number.')
        if not 1000 <= goal <= 5000:
            raise ProfileError('Daily calorie goal must be between 1000 and 5000.')
        out['calorie_goal'] = goal
    return out


def get_user_profile(user_id):
    """Return the user's profile dict (with defaults filled in), or None if the user does not exist."""
    conn = get_db_connection()
    try:
        row = conn.execute(
            'SELECT email, display_name, bio, avatar_emoji, avatar_color, cooking_level, calorie_goal '
            'FROM users WHERE id = ?', (user_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    profile = dict(PROFILE_DEFAULTS)
    for key in profile:
        if row[key] not in (None, ''):
            profile[key] = row[key]
    profile['email'] = row['email']
    if not profile['display_name']:
        profile['display_name'] = row['email'].split('@')[0]
    profile['initials'] = initials_for(profile['display_name'])
    profile['avatar_hex'] = AVATAR_COLORS.get(profile['avatar_color'], AVATAR_COLORS['blue'])
    return profile


def initials_for(name):
    parts = [p for p in (name or '').replace('.', ' ').replace('_', ' ').split() if p]
    if not parts:
        return '?'
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def update_user_profile(user_id, data):
    """Validate and save profile fields. Returns the saved profile. Raises ProfileError."""
    clean = validate_profile(data)
    conn = get_db_connection()
    try:
        cur = conn.execute(
            'UPDATE users SET display_name = ?, bio = ?, avatar_emoji = ?, avatar_color = ?, '
            'cooking_level = ?, calorie_goal = ? WHERE id = ?',
            (clean['display_name'], clean['bio'], clean['avatar_emoji'], clean['avatar_color'],
             clean['cooking_level'], clean['calorie_goal'], user_id))
        conn.commit()
        if cur.rowcount == 0:
            raise ProfileError('Account could not be found.')
    finally:
        conn.close()
    return get_user_profile(user_id)


def _ensure_column(cursor, table, column, ddl):
    """Add a column to an existing table if it is not there yet (SQLite has no IF NOT EXISTS for columns)."""
    existing = {row[1] for row in cursor.execute(f'PRAGMA table_info({table})').fetchall()}
    if column not in existing:
        cursor.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')


def create_password_reset_token(user_id, token, expires_at):
    """Persist a password reset token for a user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM password_reset_tokens WHERE user_id = ?', (user_id,))
        cursor.execute(
            '''
            INSERT INTO password_reset_tokens (user_id, token, expires_at)
            VALUES (?, ?, ?)
            ''',
            (user_id, token, expires_at)
        )
        conn.commit()
    finally:
        conn.close()


def get_valid_password_reset_token(token):
    """Return a reset-token row if it hasn't expired or been consumed."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT prt.id, prt.user_id, prt.token, prt.expires_at, prt.used_at, u.email
        FROM password_reset_tokens prt
        JOIN users u ON u.id = prt.user_id
        WHERE prt.token = ? AND prt.used_at IS NULL
        ''',
        (token,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    expires_at = row['expires_at']
    if isinstance(expires_at, str):
        expires_at_dt = datetime.fromisoformat(expires_at)
    else:
        expires_at_dt = expires_at

    if expires_at_dt <= datetime.now():
        return None

    return row


def consume_password_reset_token(token):
    """Mark a token as used after a successful password update."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'UPDATE password_reset_tokens SET used_at = CURRENT_TIMESTAMP WHERE token = ?',
            (token,)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_user_account(user_id):
    """
    Permanently delete a user and every row that belongs to them.
    SQLite doesn't enforce FK cascades here, so each table is cleared
    explicitly, in dependency order, inside a single transaction.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            DELETE FROM meal_plan_items
            WHERE meal_plan_id IN (SELECT id FROM meal_plans WHERE user_id = ?)
        ''', (user_id,))
        cursor.execute('DELETE FROM meal_plans WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM favorites WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM preferences WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM password_reset_tokens WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return deleted

def init_db():
    """Initialize database with schema"""
    if not os.path.exists('instance'):
        os.makedirs('instance')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Password reset tokens
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # User Preferences table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            health_conditions TEXT,
            allergies TEXT,
            dietary_restrictions TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Favorites table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            recipe_id TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Meal Plan table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meal_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            week_start_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Meal Plan Items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meal_plan_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_plan_id INTEGER NOT NULL,
            day_of_week TEXT,
            meal_type TEXT,
            recipe_id TEXT,
            FOREIGN KEY (meal_plan_id) REFERENCES meal_plans(id)
        )
    ''')
    
    # Profile columns: added in place so existing databases keep their users.
    _ensure_column(cursor, 'users', 'display_name', "TEXT DEFAULT ''")
    _ensure_column(cursor, 'users', 'bio', "TEXT DEFAULT ''")
    _ensure_column(cursor, 'users', 'avatar_emoji', "TEXT DEFAULT ''")
    _ensure_column(cursor, 'users', 'avatar_color', "TEXT DEFAULT ''")
    _ensure_column(cursor, 'users', 'cooking_level', "TEXT DEFAULT ''")
    _ensure_column(cursor, 'users', 'calorie_goal', 'INTEGER')

    conn.commit()

    # Indexes on columns used in WHERE/JOIN clauses throughout the app.
    # users.email is already indexed implicitly via its UNIQUE constraint.
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_preferences_user_id ON preferences(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON favorites(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_user_recipe ON favorites(user_id, recipe_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_meal_plans_user_id ON meal_plans(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_meal_plan_items_plan_id ON meal_plan_items(meal_plan_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON password_reset_tokens(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token)')

    conn.commit()
    conn.close()
