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
