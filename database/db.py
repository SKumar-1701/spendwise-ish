"""SQLite data-access layer for Spendwise-ish.

Exposes get_db(), init_db(), and seed_db(). No other module should
open a sqlite3 connection or write SQL directly — all DB access
funnels through this file.
"""

import os
import sqlite3
from datetime import date, datetime, timedelta

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


def insert_expense(user_id, amount, category, date, description):
    """Insert a new expense for a user. Returns the new expense's id.

    Caller is responsible for validating amount/category/date and for
    normalizing a blank description to None before calling.
    """
    conn = get_db()
    try:
        cursor = conn.execute(
            """
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, amount, category, date, description),
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


def get_user_by_id(user_id):
    """Look up a user by id.

    Returns a sqlite3.Row with the user's columns (including
    created_at) if found, or None if no user has that id.
    """
    conn = get_db()
    try:
        cursor = conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        )
        return cursor.fetchone()
    finally:
        conn.close()


def format_member_since(created_at):
    """Format a users.created_at timestamp as 'Month YYYY' (e.g. 'January 2026')."""
    return datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%B %Y")


def get_summary_stats(user_id, date_from=None, date_to=None):
    """Compute summary statistics for a user's expenses.

    If date_from and date_to are both given (YYYY-MM-DD strings), only
    expenses in that inclusive range are counted; omitting either
    preserves the original all-time behavior.

    Returns a dict with total_spent (float), transaction_count (int),
    and top_category (str), or zeroed-out defaults if the user has no
    expenses.
    """
    conn = get_db()
    try:
        if date_from and date_to:
            params = (user_id, date_from, date_to)
            totals_row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total_spent, "
                "COUNT(*) AS transaction_count FROM expenses "
                "WHERE user_id = ? AND date BETWEEN ? AND ?",
                params,
            ).fetchone()
            top_category_row = conn.execute(
                "SELECT category, SUM(amount) AS category_total FROM expenses "
                "WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY category "
                "ORDER BY category_total DESC LIMIT 1",
                params,
            ).fetchone()
        else:
            params = (user_id,)
            totals_row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total_spent, "
                "COUNT(*) AS transaction_count FROM expenses WHERE user_id = ?",
                params,
            ).fetchone()
            top_category_row = conn.execute(
                "SELECT category, SUM(amount) AS category_total FROM expenses "
                "WHERE user_id = ? GROUP BY category "
                "ORDER BY category_total DESC LIMIT 1",
                params,
            ).fetchone()

        top_category = top_category_row["category"] if top_category_row else "—"

        return {
            "total_spent": float(totals_row["total_spent"]),
            "transaction_count": int(totals_row["transaction_count"]),
            "top_category": top_category,
        }
    finally:
        conn.close()


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    """Look up a user's most recent expenses, newest first.

    If date_from and date_to are both given (YYYY-MM-DD strings), only
    expenses in that inclusive range are returned; omitting either
    preserves the original all-time behavior.

    Returns a list of sqlite3.Row objects (id, user_id, amount, category,
    date, description, created_at) — an empty list if the user has no
    expenses.
    """
    conn = get_db()
    try:
        if date_from and date_to:
            cursor = conn.execute(
                """
                SELECT id, user_id, amount, category, date, description, created_at
                FROM expenses
                WHERE user_id = ? AND date BETWEEN ? AND ?
                ORDER BY date DESC
                LIMIT ?
                """,
                (user_id, date_from, date_to, limit),
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, user_id, amount, category, date, description, created_at
                FROM expenses
                WHERE user_id = ?
                ORDER BY date DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
        return cursor.fetchall()
    finally:
        conn.close()


def get_category_breakdown(user_id, date_from=None, date_to=None):
    """Compute per-category spending totals and percentages for a user.

    If date_from and date_to are both given (YYYY-MM-DD strings), only
    expenses in that inclusive range are counted; omitting either
    preserves the original all-time behavior.

    Returns a list of dicts, one per category with at least one expense,
    ordered by summed amount descending:
      [{"name": <category str>, "amount": <float total>, "pct": <int>}, ...]
    The "pct" values are integers that sum to exactly 100 across the list
    (rounding drift is absorbed into the largest category). Returns an
    empty list if the user has no expenses.
    """
    conn = get_db()
    try:
        if date_from and date_to:
            rows = conn.execute(
                "SELECT category, SUM(amount) AS category_total FROM expenses "
                "WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY category "
                "ORDER BY category_total DESC",
                (user_id, date_from, date_to),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT category, SUM(amount) AS category_total FROM expenses "
                "WHERE user_id = ? GROUP BY category "
                "ORDER BY category_total DESC",
                (user_id,),
            ).fetchall()

        if not rows:
            return []

        grand_total = sum(row["category_total"] for row in rows)

        breakdown = [
            {
                "name": row["category"],
                "amount": float(row["category_total"]),
                "pct": round(row["category_total"] / grand_total * 100),
            }
            for row in rows
        ]

        pct_sum = sum(item["pct"] for item in breakdown)
        if pct_sum != 100:
            largest = max(breakdown, key=lambda item: item["amount"])
            largest["pct"] += 100 - pct_sum

        return breakdown
    finally:
        conn.close()


def get_expense_by_id(expense_id, user_id):
    """Look up a single expense by id, scoped to its owning user.

    Returns a sqlite3.Row with the expense's columns if it exists and
    belongs to user_id, or None otherwise. Scoping ownership in the query
    itself means a nonexistent id and another user's id are indistinguishable
    to the caller.
    """
    conn = get_db()
    try:
        cursor = conn.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        return cursor.fetchone()
    finally:
        conn.close()


def update_expense(expense_id, user_id, amount, category, date, description):
    """Update an existing expense, scoped to its owning user.

    Caller is responsible for validating amount/category/date and for
    normalizing a blank description to None before calling. The user_id
    condition is a second ownership guard in addition to the caller having
    already checked get_expense_by_id.
    """
    conn = get_db()
    try:
        conn.execute(
            """
            UPDATE expenses
            SET amount = ?, category = ?, date = ?, description = ?
            WHERE id = ? AND user_id = ?
            """,
            (amount, category, date, description, expense_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_expense(expense_id, user_id):
    """Delete an expense, scoped to its owning user.

    The user_id condition is a second ownership guard in addition to the
    caller having already checked get_expense_by_id. Deleting a nonexistent
    id or another user's id is a silent no-op (0 rows affected).
    """
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()
