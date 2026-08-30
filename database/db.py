"""SQLite data-access layer for Spendwise-ish.

Exposes get_db(), init_db(), and seed_db(). No other module should
open a sqlite3 connection or write SQL directly — all DB access
funnels through this file.
"""

import os
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

# Anchor to the project root (parent of database/), not the process cwd,
# so `python app.py` finds/creates the DB the same way regardless of
# where it's invoked from.
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "expense_tracker.db",
)

CATEGORIES = [
    "Food", "Transport", "Bills", "Health",
    "Entertainment", "Shopping", "Other",
]


def get_db():
    """Open a new SQLite connection with row access and FK enforcement."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they don't already exist. Safe to call repeatedly."""
    conn = get_db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_db():
    """Insert one demo user + 8 sample expenses, once only."""
    conn = get_db()
    try:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None:
            return

        password_hash = generate_password_hash("demo123")
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendwise-ish.com", password_hash),
        )
        user_id = cursor.lastrowid

        today = date.today()
        month_start = today.replace(day=1)

        def day_n(n):
            d = month_start + timedelta(days=n)
            if d > today:
                d = today
            return d.strftime("%Y-%m-%d")

        sample_expenses = [
            (45.50, "Food", day_n(1), "Groceries"),
            (12.00, "Transport", day_n(3), "Bus pass top-up"),
            (89.99, "Bills", day_n(4), "Electricity bill"),
            (25.00, "Health", day_n(6), "Pharmacy"),
            (15.75, "Entertainment", day_n(8), "Movie tickets"),
            (60.20, "Shopping", day_n(10), "New shoes"),
            (9.50, "Other", day_n(12), "Miscellaneous"),
            (32.40, "Food", day_n(15), "Dinner out"),
        ]

        conn.executemany(
            """
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            [(user_id, *row) for row in sample_expenses],
        )
        conn.commit()
    finally:
        conn.close()


def create_user(name, email, password):
    """Insert a new user with a hashed password. Returns the new user's id.

    Raises sqlite3.IntegrityError if the email is already taken.
    """
    conn = get_db()
    try:
        password_hash = generate_password_hash(password)
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_user_by_email(email):
    """Look up a user by email address.

    Returns a sqlite3.Row with the user's columns (including id and
    password_hash) if found, or None if no user has that email.
    """
    conn = get_db()
    try:
        cursor = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        )
        return cursor.fetchone()
    finally:
        conn.close()
