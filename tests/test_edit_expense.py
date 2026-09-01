"""Tests for the "Edit Expense" feature (see .claude/specs/08-edit-expense.md).

Covers:
- Unit tests on database/db.py's get_expense_by_id and update_expense helpers.
- Route tests on GET/POST /expenses/<id>/edit, using the seeded demo user
  (demo@spendwise-ish.com / demo123).

Follows the isolated_db / client / logged_in_client fixture conventions
established in tests/test_add_expense.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import database.db as db


# --------------------------------------------------------------------- #
# Fixtures (mirrors tests/test_add_expense.py)
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


def _fetch_expense_by_id(expense_id):
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# --------------------------------------------------------------------- #
# Unit tests: database/db.py get_expense_by_id
# --------------------------------------------------------------------- #

class TestGetExpenseById:
    def test_found_and_owned_returns_row(self, isolated_db):
        user_id = isolated_db.create_user("Alice", "alice@example.com", "pw123456")
        isolated_db.insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")
        expense_id = _fetch_expenses(user_id)[0]["id"]

        row = isolated_db.get_expense_by_id(expense_id, user_id)

        assert row is not None, "expected the owned expense to be returned"
        assert row["id"] == expense_id
        assert row["user_id"] == user_id
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_wrong_user_id_returns_none(self, isolated_db):
        owner_id = isolated_db.create_user("Alice", "alice@example.com", "pw123456")
        other_id = isolated_db.create_user("Bob", "bob@example.com", "pw123456")
        isolated_db.insert_expense(owner_id, 50.0, "Food", "2026-03-20", "Lunch")
        expense_id = _fetch_expenses(owner_id)[0]["id"]

        row = isolated_db.get_expense_by_id(expense_id, other_id)

        assert row is None, "expected None when expense belongs to a different user"

    def test_nonexistent_id_returns_none(self, isolated_db):
        user_id = isolated_db.create_user("Alice", "alice@example.com", "pw123456")

        row = isolated_db.get_expense_by_id(999999, user_id)

        assert row is None, "expected None for a non-existent expense id"


# --------------------------------------------------------------------- #
# Unit tests: database/db.py update_expense
# --------------------------------------------------------------------- #

class TestUpdateExpense:
    def test_valid_update_changes_row(self, isolated_db):
        user_id = isolated_db.create_user("Alice", "alice@example.com", "pw123456")
        isolated_db.insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")
        expense_id = _fetch_expenses(user_id)[0]["id"]

        isolated_db.update_expense(
            expense_id, user_id, 99.0, "Bills", "2026-04-15", "Rent"
        )

        row = _fetch_expense_by_id(expense_id)
        assert row["amount"] == 99.0
        assert row["category"] == "Bills"
        assert row["date"] == "2026-04-15"
        assert row["description"] == "Rent"

    def test_wrong_user_id_leaves_row_unchanged(self, isolated_db):
        owner_id = isolated_db.create_user("Alice", "alice@example.com", "pw123456")
        other_id = isolated_db.create_user("Bob", "bob@example.com", "pw123456")
        isolated_db.insert_expense(owner_id, 50.0, "Food", "2026-03-20", "Lunch")
        expense_id = _fetch_expenses(owner_id)[0]["id"]

        # Should not raise, and should affect 0 rows.
        isolated_db.update_expense(
            expense_id, other_id, 99.0, "Bills", "2026-04-15", "Rent"
        )

        row = _fetch_expense_by_id(expense_id)
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"


# --------------------------------------------------------------------- #
# Route tests: GET /expenses/<id>/edit
# --------------------------------------------------------------------- #

class TestGetEditExpense:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/expenses/1/edit")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_authenticated_owner_sees_prefilled_form(self, logged_in_client):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")
        db.insert_expense(user_id, 42.5, "Health", "2026-02-14", "Checkup")
        expense = [
            r for r in _fetch_expenses(user_id) if r["description"] == "Checkup"
        ][0]

        resp = logged_in_client.get(f"/expenses/{expense['id']}/edit")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)

        assert "<form" in body
        assert 'method="POST"' in body or 'method="post"' in body
        assert "42.5" in body, "expected the amount to be pre-filled"
        assert "2026-02-14" in body, "expected the date to be pre-filled"
        assert "Checkup" in body, "expected the description to be pre-filled"

        assert "<select" in body
        assert (
            f'value="Health" selected' in body
            or 'selected value="Health"' in body
            or ('>Health<' in body and 'selected' in body)
        ), "expected the Health category option to be pre-selected"

    def test_other_users_expense_returns_404(self, logged_in_client):
        other_id = db.create_user("Carol", "carol@example.com", "pw123456")
        db.insert_expense(other_id, 10.0, "Shopping", "2026-01-01", "Shoes")
        other_expense_id = _fetch_expenses(other_id)[0]["id"]

        resp = logged_in_client.get(f"/expenses/{other_expense_id}/edit")
        assert resp.status_code == 404

    def test_nonexistent_id_returns_404(self, logged_in_client):
        resp = logged_in_client.get("/expenses/999999/edit")
        assert resp.status_code == 404


# --------------------------------------------------------------------- #
# Route tests: POST /expenses/<id>/edit
# --------------------------------------------------------------------- #

class TestPostEditExpense:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.post(
            "/expenses/1/edit",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_valid_data_redirects_to_profile_and_updates_row(self, logged_in_client):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")
        db.insert_expense(user_id, 20.0, "Food", "2026-01-05", "Snacks")
        expense_id = [
            r for r in _fetch_expenses(user_id) if r["description"] == "Snacks"
        ][0]["id"]

        resp = logged_in_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "75.25",
                "category": "Bills",
                "date": "2026-06-10",
                "description": "Electricity",
            },
        )
        assert resp.status_code == 302
        assert "/profile" in resp.headers["Location"]

        row = _fetch_expense_by_id(expense_id)
        assert row["amount"] == 75.25
        assert row["category"] == "Bills"
        assert row["date"] == "2026-06-10"
        assert row["description"] == "Electricity"

    def test_other_users_expense_returns_404_and_db_unchanged(self, logged_in_client):
        other_id = db.create_user("Dave", "dave@example.com", "pw123456")
        db.insert_expense(other_id, 10.0, "Shopping", "2026-01-01", "Shoes")
        other_expense_id = _fetch_expenses(other_id)[0]["id"]

        resp = logged_in_client.post(
            f"/expenses/{other_expense_id}/edit",
            data={
                "amount": "999.0",
                "category": "Other",
                "date": "2026-12-25",
                "description": "Hacked",
            },
        )
        assert resp.status_code == 404

        row = _fetch_expense_by_id(other_expense_id)
        assert row["amount"] == 10.0
        assert row["category"] == "Shopping"
        assert row["date"] == "2026-01-01"
        assert row["description"] == "Shoes"

    def test_missing_amount_rerenders_form_with_error(self, logged_in_client):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")
        db.insert_expense(user_id, 20.0, "Food", "2026-01-05", "Snacks")
        expense_id = [
            r for r in _fetch_expenses(user_id) if r["description"] == "Snacks"
        ][0]["id"]

        resp = logged_in_client.post(
            f"/expenses/{expense_id}/edit",
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

        row = _fetch_expense_by_id(expense_id)
        assert row["amount"] == 20.0, "DB row should remain unchanged"

    def test_zero_amount_rerenders_form_with_error(self, logged_in_client):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")
        db.insert_expense(user_id, 20.0, "Food", "2026-01-05", "Snacks")
        expense_id = [
            r for r in _fetch_expenses(user_id) if r["description"] == "Snacks"
        ][0]["id"]

        resp = logged_in_client.post(
            f"/expenses/{expense_id}/edit",
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

        row = _fetch_expense_by_id(expense_id)
        assert row["amount"] == 20.0, "DB row should remain unchanged"

    def test_non_numeric_amount_rerenders_form_with_error(self, logged_in_client):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")
        db.insert_expense(user_id, 20.0, "Food", "2026-01-05", "Snacks")
        expense_id = [
            r for r in _fetch_expenses(user_id) if r["description"] == "Snacks"
        ][0]["id"]

        resp = logged_in_client.post(
            f"/expenses/{expense_id}/edit",
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

        row = _fetch_expense_by_id(expense_id)
        assert row["amount"] == 20.0, "DB row should remain unchanged"

    def test_invalid_category_rerenders_form_with_error(self, logged_in_client):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")
        db.insert_expense(user_id, 20.0, "Food", "2026-01-05", "Snacks")
        expense_id = [
            r for r in _fetch_expenses(user_id) if r["description"] == "Snacks"
        ][0]["id"]

        resp = logged_in_client.post(
            f"/expenses/{expense_id}/edit",
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

        row = _fetch_expense_by_id(expense_id)
        assert row["category"] == "Food", "DB row should remain unchanged"

    def test_invalid_date_rerenders_form_with_error(self, logged_in_client):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")
        db.insert_expense(user_id, 20.0, "Food", "2026-01-05", "Snacks")
        expense_id = [
            r for r in _fetch_expenses(user_id) if r["description"] == "Snacks"
        ][0]["id"]

        resp = logged_in_client.post(
            f"/expenses/{expense_id}/edit",
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

        row = _fetch_expense_by_id(expense_id)
        assert row["date"] == "2026-01-05", "DB row should remain unchanged"

    def test_no_description_is_optional_and_stores_null(self, logged_in_client):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")
        db.insert_expense(user_id, 20.0, "Food", "2026-01-05", "Snacks")
        expense_id = [
            r for r in _fetch_expenses(user_id) if r["description"] == "Snacks"
        ][0]["id"]

        resp = logged_in_client.post(
            f"/expenses/{expense_id}/edit",
            data={
                "amount": "15.0",
                "category": "Transport",
                "date": "2026-05-01",
            },
        )
        assert resp.status_code == 302
        assert "/profile" in resp.headers["Location"]

        row = _fetch_expense_by_id(expense_id)
        assert row["amount"] == 15.0
        assert row["category"] == "Transport"
        assert row["date"] == "2026-05-01"
        assert row["description"] is None
