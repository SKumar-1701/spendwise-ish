"""Tests for the /profile date-range filter feature (see
.claude/specs/06-profile-date-filter.md).

Covers:
- Unit tests on database/db.py's get_summary_stats, get_recent_transactions,
  and get_category_breakdown with date_from/date_to filtering.
- Route tests on GET /profile with query-string date filters, using the
  seeded demo user (demo@spendwise-ish.com / demo123, 8 expenses totaling
  ₹290.34 in the current calendar month).

Follows the isolated_db / client fixture conventions established in
tests/test_backend_connection.py.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import database.db as db


# --------------------------------------------------------------------- #
# Fixtures (mirrors tests/test_backend_connection.py)
# --------------------------------------------------------------------- #

@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    return db


def _add_expense(user_id, amount, category, date_str, description=None):
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date_str, description),
        )
        conn.commit()
    finally:
        conn.close()


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


# --------------------------------------------------------------------- #
# Unit tests: database/db.py functions with date_from/date_to
# --------------------------------------------------------------------- #

class TestGetSummaryStatsDateFilter:
    def test_range_includes_all_expenses_matches_unfiltered(self, isolated_db):
        user_id = isolated_db.create_user("Alice", "alice@example.com", "pw123456")
        _add_expense(user_id, 10.0, "Food", "2026-08-01")
        _add_expense(user_id, 20.0, "Bills", "2026-08-15")

        unfiltered = isolated_db.get_summary_stats(user_id)
        filtered = isolated_db.get_summary_stats(
            user_id, date_from="2026-08-01", date_to="2026-08-31"
        )
        assert filtered == unfiltered

    def test_range_excludes_all_expenses_returns_zeroed_defaults(self, isolated_db):
        user_id = isolated_db.create_user("Bob", "bob@example.com", "pw123456")
        _add_expense(user_id, 10.0, "Food", "2026-08-01")

        filtered = isolated_db.get_summary_stats(
            user_id, date_from="2020-01-01", date_to="2020-01-31"
        )
        assert filtered == {
            "total_spent": 0,
            "transaction_count": 0,
            "top_category": "—",
        }

    def test_range_covers_some_expenses_partial_result(self, isolated_db):
        user_id = isolated_db.create_user("Carl", "carl@example.com", "pw123456")
        _add_expense(user_id, 10.0, "Food", "2026-08-01")
        _add_expense(user_id, 20.0, "Bills", "2026-08-15")
        _add_expense(user_id, 30.0, "Transport", "2026-09-01")

        filtered = isolated_db.get_summary_stats(
            user_id, date_from="2026-08-01", date_to="2026-08-31"
        )
        assert filtered["total_spent"] == 30.0
        assert filtered["transaction_count"] == 2
        assert filtered["top_category"] == "Bills"

    def test_missing_or_partial_dates_behaves_as_all_time(self, isolated_db):
        user_id = isolated_db.create_user("Dana", "dana@example.com", "pw123456")
        _add_expense(user_id, 10.0, "Food", "2026-08-01")
        _add_expense(user_id, 20.0, "Bills", "2026-08-15")

        unfiltered = isolated_db.get_summary_stats(user_id)
        only_from = isolated_db.get_summary_stats(user_id, date_from="2026-08-01")
        only_to = isolated_db.get_summary_stats(user_id, date_to="2026-08-31")
        no_args = isolated_db.get_summary_stats(user_id, date_from=None, date_to=None)

        assert only_from == unfiltered
        assert only_to == unfiltered
        assert no_args == unfiltered


class TestGetRecentTransactionsDateFilter:
    def test_range_includes_all_expenses_matches_unfiltered(self, isolated_db):
        user_id = isolated_db.create_user("Eve", "eve@example.com", "pw123456")
        _add_expense(user_id, 5.0, "Food", "2026-08-01", "Coffee")
        _add_expense(user_id, 15.0, "Bills", "2026-08-05", "Electric")

        unfiltered = isolated_db.get_recent_transactions(user_id)
        filtered = isolated_db.get_recent_transactions(
            user_id, date_from="2026-08-01", date_to="2026-08-31"
        )
        assert [dict(t) for t in filtered] == [dict(t) for t in unfiltered]

    def test_range_excludes_all_expenses_returns_empty_list(self, isolated_db):
        user_id = isolated_db.create_user("Frank", "frank@example.com", "pw123456")
        _add_expense(user_id, 5.0, "Food", "2026-08-01")

        filtered = isolated_db.get_recent_transactions(
            user_id, date_from="2020-01-01", date_to="2020-01-31"
        )
        assert filtered == []

    def test_range_covers_some_expenses_partial_result(self, isolated_db):
        user_id = isolated_db.create_user("Grace", "grace@example.com", "pw123456")
        _add_expense(user_id, 5.0, "Food", "2026-08-01", "Coffee")
        _add_expense(user_id, 15.0, "Bills", "2026-08-05", "Electric")
        _add_expense(user_id, 25.0, "Transport", "2026-09-10", "Taxi")

        filtered = isolated_db.get_recent_transactions(
            user_id, date_from="2026-08-01", date_to="2026-08-31"
        )
        assert [t["date"] for t in filtered] == ["2026-08-05", "2026-08-01"]

    def test_missing_or_partial_dates_behaves_as_all_time(self, isolated_db):
        user_id = isolated_db.create_user("Henry", "henry@example.com", "pw123456")
        _add_expense(user_id, 5.0, "Food", "2026-08-01")
        _add_expense(user_id, 15.0, "Bills", "2026-08-05")

        unfiltered = [dict(t) for t in isolated_db.get_recent_transactions(user_id)]
        only_from = [
            dict(t) for t in isolated_db.get_recent_transactions(user_id, date_from="2026-08-01")
        ]
        only_to = [
            dict(t) for t in isolated_db.get_recent_transactions(user_id, date_to="2026-08-31")
        ]
        no_args = [
            dict(t)
            for t in isolated_db.get_recent_transactions(user_id, date_from=None, date_to=None)
        ]

        assert only_from == unfiltered
        assert only_to == unfiltered
        assert no_args == unfiltered

    def test_limit_still_respected_with_date_filter(self, isolated_db):
        user_id = isolated_db.create_user("Ivy", "ivy@example.com", "pw123456")
        for day in range(1, 6):
            _add_expense(user_id, 1.0, "Food", f"2026-08-0{day}")

        filtered = isolated_db.get_recent_transactions(
            user_id, limit=2, date_from="2026-08-01", date_to="2026-08-31"
        )
        assert len(filtered) == 2


class TestGetCategoryBreakdownDateFilter:
    def test_range_includes_all_expenses_matches_unfiltered(self, isolated_db):
        user_id = isolated_db.create_user("Jack", "jack@example.com", "pw123456")
        _add_expense(user_id, 33.33, "Food", "2026-08-01")
        _add_expense(user_id, 33.33, "Bills", "2026-08-02")
        _add_expense(user_id, 33.34, "Transport", "2026-08-03")

        unfiltered = isolated_db.get_category_breakdown(user_id)
        filtered = isolated_db.get_category_breakdown(
            user_id, date_from="2026-08-01", date_to="2026-08-31"
        )
        assert filtered == unfiltered

    def test_range_excludes_all_expenses_returns_empty_list(self, isolated_db):
        user_id = isolated_db.create_user("Kim", "kim@example.com", "pw123456")
        _add_expense(user_id, 10.0, "Food", "2026-08-01")

        filtered = isolated_db.get_category_breakdown(
            user_id, date_from="2020-01-01", date_to="2020-01-31"
        )
        assert filtered == []

    def test_range_covers_some_expenses_partial_result(self, isolated_db):
        user_id = isolated_db.create_user("Liam", "liam@example.com", "pw123456")
        _add_expense(user_id, 10.0, "Food", "2026-08-01")
        _add_expense(user_id, 20.0, "Bills", "2026-08-02")
        _add_expense(user_id, 999.0, "Transport", "2026-09-01")

        filtered = isolated_db.get_category_breakdown(
            user_id, date_from="2026-08-01", date_to="2026-08-31"
        )
        names = {item["name"] for item in filtered}
        assert names == {"Food", "Bills"}
        assert sum(item["pct"] for item in filtered) == 100

    def test_missing_or_partial_dates_behaves_as_all_time(self, isolated_db):
        user_id = isolated_db.create_user("Mona", "mona@example.com", "pw123456")
        _add_expense(user_id, 10.0, "Food", "2026-08-01")
        _add_expense(user_id, 20.0, "Bills", "2026-08-02")

        unfiltered = isolated_db.get_category_breakdown(user_id)
        only_from = isolated_db.get_category_breakdown(user_id, date_from="2026-08-01")
        only_to = isolated_db.get_category_breakdown(user_id, date_to="2026-08-31")
        no_args = isolated_db.get_category_breakdown(user_id, date_from=None, date_to=None)

        assert only_from == unfiltered
        assert only_to == unfiltered
        assert no_args == unfiltered


# --------------------------------------------------------------------- #
# Route tests: GET /profile with query-string date filters
# --------------------------------------------------------------------- #

class TestProfileRouteDateFilter:
    def test_no_query_params_same_totals_as_before(self, logged_in_client):
        resp = logged_in_client.get("/profile")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "₹290.34" in body, "unfiltered total should be unchanged by this feature"
        assert "Bills" in body

    def test_range_covering_current_month_matches_seed_totals(self, logged_in_client):
        today = date.today()
        month_start = today.replace(day=1).strftime("%Y-%m-%d")
        today_str = today.strftime("%Y-%m-%d")

        resp = logged_in_client.get(
            f"/profile?date_from={month_start}&date_to={today_str}"
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "₹290.34" in body, "all 8 seed expenses fall within the current month"
        assert "8" in body  # transaction count somewhere in the stats card

    def test_range_matching_zero_expenses_shows_empty_state(self, logged_in_client):
        resp = logged_in_client.get(
            "/profile?date_from=2000-01-01&date_to=2000-01-31"
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "₹0.00" in body
        assert "Internal Server Error" not in body

    def test_inverted_range_shows_flash_error_and_falls_back_to_unfiltered(
        self, logged_in_client
    ):
        today = date.today()
        after = (today + timedelta(days=10)).strftime("%Y-%m-%d")
        before = today.strftime("%Y-%m-%d")

        resp = logged_in_client.get(f"/profile?date_from={after}&date_to={before}")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Start date must be before end date." in body
        assert "₹290.34" in body, "should fall back to unfiltered totals"

    def test_malformed_date_silently_falls_back_no_crash_no_flash(self, logged_in_client):
        resp = logged_in_client.get("/profile?date_from=not-a-date&date_to=2026-08-01")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "₹290.34" in body, "should fall back to unfiltered totals"
        assert "Start date must be before end date." not in body

    def test_only_one_param_provided_falls_back_to_unfiltered(self, logged_in_client):
        today_str = date.today().strftime("%Y-%m-%d")
        resp = logged_in_client.get(f"/profile?date_from={today_str}")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "₹290.34" in body

    def test_this_month_preset_link_present_and_marked_active_when_selected(
        self, logged_in_client
    ):
        today = date.today()
        month_start = today.replace(day=1).strftime("%Y-%m-%d")
        today_str = today.strftime("%Y-%m-%d")

        resp = logged_in_client.get(
            f"/profile?date_from={month_start}&date_to={today_str}"
        )
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # Robust check: the preset link exists with the expected query params,
        # without pinning down exact surrounding HTML/attribute ordering.
        assert f"date_from={month_start}" in body
        assert f"date_to={today_str}" in body
        assert "This Month" in body
        assert "is-active" in body, "the active preset should carry a highlight class"

    def test_unauthenticated_request_redirects_to_login(self, client):
        resp = client.get("/profile?date_from=2026-08-01&date_to=2026-08-31")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
