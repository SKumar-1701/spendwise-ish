"""Tests for the "Delete Expense" feature (Step 9).

Covers:
- Unit tests on database/db.py's delete_expense helper.
- Route tests on POST /expenses/<id>/delete, using the seeded demo user
  (demo@spendwise-ish.com / demo123).
- GET /expenses/<id>/delete has no handler and must return 405.

Follows the isolated_db / client / logged_in_client fixture conventions
established in tests/test_edit_expense.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import database.db as db


# --------------------------------------------------------------------- #
# Fixtures (mirrors tests/test_edit_expense.py)
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
# Unit tests: database/db.py delete_expense
# --------------------------------------------------------------------- #

class TestDeleteExpense:
    def test_owned_expense_is_deleted(self, isolated_db):
        user_id = isolated_db.create_user("Alice", "alice@example.com", "pw123456")
        isolated_db.insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")
        expense_id = _fetch_expenses(user_id)[0]["id"]

        isolated_db.delete_expense(expense_id, user_id)

        assert _fetch_expense_by_id(expense_id) is None, (
            "expected the owned expense row to be removed from the DB"
        )

    def test_nonexistent_id_is_silent_no_op(self, isolated_db):
        user_id = isolated_db.create_user("Alice", "alice@example.com", "pw123456")
        isolated_db.insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")
        existing_id = _fetch_expenses(user_id)[0]["id"]

        # Should not raise for a non-existent id.
        isolated_db.delete_expense(999999, user_id)

        # The existing, unrelated row must remain untouched.
        assert _fetch_expense_by_id(existing_id) is not None, (
            "deleting a non-existent id must not affect other rows"
        )

    def test_wrong_user_id_is_silent_no_op(self, isolated_db):
        owner_id = isolated_db.create_user("Alice", "alice@example.com", "pw123456")
        other_id = isolated_db.create_user("Bob", "bob@example.com", "pw123456")
        isolated_db.insert_expense(owner_id, 50.0, "Food", "2026-03-20", "Lunch")
        expense_id = _fetch_expenses(owner_id)[0]["id"]

        # Should not raise, and should affect 0 rows.
        isolated_db.delete_expense(expense_id, other_id)

        row = _fetch_expense_by_id(expense_id)
        assert row is not None, (
            "expected the expense to remain since it belongs to a different user"
        )
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_deleting_one_expense_does_not_affect_others(self, isolated_db):
        user_id = isolated_db.create_user("Alice", "alice@example.com", "pw123456")
        isolated_db.insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")
        isolated_db.insert_expense(user_id, 15.0, "Transport", "2026-04-01", "Bus")
        expenses = _fetch_expenses(user_id)
        to_delete = [e for e in expenses if e["description"] == "Lunch"][0]
        to_keep = [e for e in expenses if e["description"] == "Bus"][0]

        isolated_db.delete_expense(to_delete["id"], user_id)

        assert _fetch_expense_by_id(to_delete["id"]) is None
        remaining = _fetch_expense_by_id(to_keep["id"])
        assert remaining is not None, "unrelated expense should not be deleted"
        assert remaining["amount"] == 15.0
        assert remaining["description"] == "Bus"


# --------------------------------------------------------------------- #
# Route tests: POST /expenses/<id>/delete
# --------------------------------------------------------------------- #

class TestPostDeleteExpense:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.post("/expenses/1/delete")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_unauthenticated_flashes_login_message(self, client):
        resp = client.post("/expenses/1/delete", follow_redirects=True)
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Please log in to delete an expense." in body

    def test_authenticated_owner_deletes_and_redirects_to_profile(
        self, logged_in_client
    ):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")
        db.insert_expense(user_id, 20.0, "Food", "2026-01-05", "Snacks")
        expense_id = [
            r for r in _fetch_expenses(user_id) if r["description"] == "Snacks"
        ][0]["id"]

        resp = logged_in_client.post(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 302
        assert "/profile" in resp.headers["Location"]

        assert _fetch_expense_by_id(expense_id) is None, (
            "expected the expense row to be removed from the DB after deletion"
        )

    def test_authenticated_owner_flashes_success_message(self, logged_in_client):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")
        db.insert_expense(user_id, 20.0, "Food", "2026-01-05", "Snacks")
        expense_id = [
            r for r in _fetch_expenses(user_id) if r["description"] == "Snacks"
        ][0]["id"]

        resp = logged_in_client.post(
            f"/expenses/{expense_id}/delete", follow_redirects=True
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Expense deleted successfully." in body

    def test_nonexistent_id_returns_404(self, logged_in_client):
        resp = logged_in_client.post("/expenses/999999/delete")
        assert resp.status_code == 404

    def test_other_users_expense_returns_404_and_db_unchanged(
        self, logged_in_client
    ):
        other_id = db.create_user("Carol", "carol@example.com", "pw123456")
        db.insert_expense(other_id, 10.0, "Shopping", "2026-01-01", "Shoes")
        other_expense_id = _fetch_expenses(other_id)[0]["id"]

        resp = logged_in_client.post(f"/expenses/{other_expense_id}/delete")
        assert resp.status_code == 404

        row = _fetch_expense_by_id(other_expense_id)
        assert row is not None, "another user's expense must not be deleted"
        assert row["amount"] == 10.0
        assert row["category"] == "Shopping"
        assert row["date"] == "2026-01-01"
        assert row["description"] == "Shoes"


# --------------------------------------------------------------------- #
# Route tests: GET /expenses/<id>/delete (no GET handler)
# --------------------------------------------------------------------- #

class TestGetDeleteExpenseMethodNotAllowed:
    def test_get_unauthenticated_returns_405(self, client):
        resp = client.get("/expenses/1/delete")
        assert resp.status_code == 405

    def test_get_authenticated_returns_405(self, logged_in_client):
        user_id = _get_user_id_by_email("demo@spendwise-ish.com")
        db.insert_expense(user_id, 20.0, "Food", "2026-01-05", "Snacks")
        expense_id = [
            r for r in _fetch_expenses(user_id) if r["description"] == "Snacks"
        ][0]["id"]

        resp = logged_in_client.get(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 405

        # The expense must remain untouched since GET has no handler.
        assert _fetch_expense_by_id(expense_id) is not None
