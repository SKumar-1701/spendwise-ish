"""Tests for the /profile backend routes (see .claude/specs/05-profile-page-backend-routes.md)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import database.db as db


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    return db


def _add_expense(user_id, amount, category, date, description=None):
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
        )
        conn.commit()
    finally:
        conn.close()


class TestGetUserById:
    def test_valid_id_returns_user(self, isolated_db):
        user_id = isolated_db.create_user("Jane Doe", "jane@example.com", "pw123456")
        user = isolated_db.get_user_by_id(user_id)
        assert user["name"] == "Jane Doe"
        assert user["email"] == "jane@example.com"

    def test_nonexistent_id_returns_none(self, isolated_db):
        assert isolated_db.get_user_by_id(9999) is None


class TestGetSummaryStats:
    def test_user_with_expenses(self, isolated_db):
        user_id = isolated_db.create_user("Alice", "alice@example.com", "pw123456")
        _add_expense(user_id, 10.0, "Food", "2026-08-01")
        _add_expense(user_id, 20.0, "Bills", "2026-08-02")
        stats = isolated_db.get_summary_stats(user_id)
        assert stats["total_spent"] == 30.0
        assert stats["transaction_count"] == 2
        assert stats["top_category"] == "Bills"

    def test_user_with_no_expenses(self, isolated_db):
        user_id = isolated_db.create_user("Bob", "bob@example.com", "pw123456")
        stats = isolated_db.get_summary_stats(user_id)
        assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}


class TestGetRecentTransactions:
    def test_user_with_expenses_newest_first(self, isolated_db):
        user_id = isolated_db.create_user("Carl", "carl@example.com", "pw123456")
        _add_expense(user_id, 5.0, "Food", "2026-08-01", "Coffee")
        _add_expense(user_id, 15.0, "Bills", "2026-08-05", "Electric")
        txns = isolated_db.get_recent_transactions(user_id)
        assert [t["date"] for t in txns] == ["2026-08-05", "2026-08-01"]
        assert set(txns[0].keys()) >= {"date", "description", "category", "amount"}

    def test_user_with_no_expenses_returns_empty_list(self, isolated_db):
        user_id = isolated_db.create_user("Dana", "dana@example.com", "pw123456")
        assert isolated_db.get_recent_transactions(user_id) == []


class TestGetCategoryBreakdown:
    def test_user_with_expenses_percentages_sum_to_100(self, isolated_db):
        user_id = isolated_db.create_user("Eve", "eve@example.com", "pw123456")
        _add_expense(user_id, 33.33, "Food", "2026-08-01")
        _add_expense(user_id, 33.33, "Bills", "2026-08-02")
        _add_expense(user_id, 33.34, "Transport", "2026-08-03")
        breakdown = isolated_db.get_category_breakdown(user_id)
        assert sum(item["pct"] for item in breakdown) == 100
        amounts = [item["amount"] for item in breakdown]
        assert amounts == sorted(amounts, reverse=True)

    def test_user_with_no_expenses_returns_empty_list(self, isolated_db):
        user_id = isolated_db.create_user("Frank", "frank@example.com", "pw123456")
        assert isolated_db.get_category_breakdown(user_id) == []


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test_app.db"))
    sys.modules.pop("app", None)
    import app as app_module

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


class TestProfileRoute:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_authenticated_seed_user_profile(self, client):
        resp = client.post(
            "/login",
            data={"email": "demo@spendwise-ish.com", "password": "demo123"},
        )
        assert resp.status_code == 302

        resp = client.get("/profile")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)

        assert "Demo User" in body
        assert "demo@spendwise-ish.com" in body
        assert "₹" in body
        assert "₹290.34" in body  # sum of seeded demo expenses
        assert "Bills" in body  # top category

    def test_new_user_with_no_expenses_sees_empty_state(self, client):
        client.post(
            "/register",
            data={
                "name": "New Person",
                "email": "new@example.com",
                "password": "pw123456",
                "confirm_password": "pw123456",
            },
        )
        client.post("/login", data={"email": "new@example.com", "password": "pw123456"})

        resp = client.get("/profile")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "₹0.00" in body
