"""Tests for the "Add Expense" feature (see .claude/specs/07-add-expense.md).

Covers:
- Unit tests on database/db.py's insert_expense helper.
- Route tests on GET/POST /expenses/add, using the seeded demo user
  (demo@spendwise-ish.com / demo123).

Follows the isolated_db / client / logged_in_client fixture conventions
established in tests/test_profile_date_filter.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import database.db as db


# --------------------------------------------------------------------- #
# Fixtures (mirrors tests/test_profile_date_filter.py)
# --------------------------------------------------------------------- #

@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    return db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test_app.db"))
    sys.modules.pop("app", None)
    import app as app_module

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture
def logged_in_client(client):
    """Log in as the seeded demo user (seed_db runs on first app import)."""
    resp = client.post(
        "/login",
        data={"email": "demo@spendwise-ish.com", "password": "demo123"},
    )
    assert resp.status_code == 302
    return client


CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


def _get_user_id_by_email(email):
    """Look up a user_id directly from the DB (no assumed helper beyond query)."""
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def _fetch_expenses(user_id):
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# --------------------------------------------------------------------- #
# Unit tests: database/db.py insert_expense
# --------------------------------------------------------------------- #

class TestInsertExpense:
    def test_valid_insert_is_queryable(self, isolated_db):
        user_id = isolated_db.create_user("Alice", "alice@example.com", "pw123456")

        isolated_db.insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")

        rows = _fetch_expenses(user_id)
        assert len(rows) == 1, "expected exactly one expense row after insert"
        row = rows[0]
        assert row["user_id"] == user_id
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_description_none_stores_null(self, isolated_db):
        user_id = isolated_db.create_user("Bob", "bob@example.com", "pw123456")

        isolated_db.insert_expense(user_id, 25.0, "Bills", "2026-04-01", None)

        rows = _fetch_expenses(user_id)
        assert len(rows) == 1
        assert rows[0]["description"] is None, "description should be stored as NULL"


# --------------------------------------------------------------------- #
# Route tests: GET /expenses/add
# --------------------------------------------------------------------- #

class TestGetAddExpense:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/expenses/add")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_authenticated_returns_form_with_all_categories(self, logged_in_client):
        resp = logged_in_client.get("/expenses/add")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)

        assert "<select" in body, "expected a <select> element for category"
        for category in CATEGORIES:
            assert category in body, f"expected category '{category}' in the select options"

        assert "<form" in body
        assert 'method="POST"' in body or 'method="post"' in body, (
            "expected the add-expense form to use POST"
        )


# --------------------------------------------------------------------- #
# Route tests: POST /expenses/add
# --------------------------------------------------------------------- #

class TestPostAddExpense:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_valid_data_redirects_to_profile_and_inserts_row(self, logged_in_client):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")
        before_count = len(_fetch_expenses(user_id))

        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 302
        assert "/profile" in resp.headers["Location"]

        rows = _fetch_expenses(user_id)
        assert len(rows) == before_count + 1

        new_rows = [
            r
            for r in rows
            if r["amount"] == 50.0
            and r["category"] == "Food"
            and r["date"] == "2026-03-20"
            and r["description"] == "Lunch"
        ]
        assert len(new_rows) == 1, "expected the newly submitted expense to exist in the DB"

    def test_missing_amount_rerenders_form_with_error(self, logged_in_client):
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "<form" in body, "expected the form to be re-rendered"
        assert any(
            keyword in body for keyword in ("error", "Error", "required", "Required")
        ), "expected an error message in the response body"

    def test_zero_amount_rerenders_form_with_error(self, logged_in_client):
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert any(
            keyword in body for keyword in ("error", "Error")
        ), "expected an error message in the response body"

    def test_non_numeric_amount_rerenders_form_with_error(self, logged_in_client):
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "not-a-number",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert any(
            keyword in body for keyword in ("error", "Error")
        ), "expected an error message in the response body"

    def test_invalid_category_rerenders_form_with_error(self, logged_in_client):
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "NotACategory",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert any(
            keyword in body for keyword in ("error", "Error")
        ), "expected an error message in the response body"

    def test_invalid_date_rerenders_form_with_error(self, logged_in_client):
        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "not-a-date",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert any(
            keyword in body for keyword in ("error", "Error")
        ), "expected an error message in the response body"

    def test_no_description_is_optional_and_inserts_null(self, logged_in_client):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")

        resp = logged_in_client.post(
            "/expenses/add",
            data={
                "amount": "15.0",
                "category": "Transport",
                "date": "2026-05-01",
            },
        )
        assert resp.status_code == 302
        assert "/profile" in resp.headers["Location"]

        rows = _fetch_expenses(user_id)
        matching = [
            r
            for r in rows
            if r["amount"] == 15.0
            and r["category"] == "Transport"
            and r["date"] == "2026-05-01"
        ]
        assert len(matching) == 1
        assert matching[0]["description"] is None
