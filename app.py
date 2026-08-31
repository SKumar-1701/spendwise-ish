import sqlite3

from flask import Flask, render_template, request, flash, redirect, url_for, session
from werkzeug.security import check_password_hash

from database.db import (
    get_db,
    init_db,
    seed_db,
    create_user,
    get_user_by_email,
    get_user_by_id,
    format_member_since,
    get_recent_transactions,
    get_summary_stats,
    get_category_breakdown,
)

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not email or not password or not confirm_password:
        flash("All fields are required.", "error")
        return render_template("register.html")

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return render_template("register.html")

    try:
        create_user(name, email, password)
    except sqlite3.IntegrityError:
        flash("Email already registered.", "error")
        return render_template("register.html")

    flash("Account created successfully! Please sign in.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()

    if not email or not password:
        flash("Invalid email or password.", "error")
        return render_template("login.html")

    user = get_user_by_email(email)

    if user is None or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password.", "error")
        return render_template("login.html")

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    flash("Logged in successfully.", "success")
    return redirect(url_for("landing"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# --- Summary stats view-model helper (implemented by summary-stats subagent) ---
# Must return a list of 3 dicts matching profile.html's `stats` loop:
#   [{"label": "Total Spent", "value": "₹123.45"},
#    {"label": "Transactions", "value": "8"},
#    {"label": "Top Category", "value": "Bills"}]
# Calls database.db.get_summary_stats(user_id) and formats the result.
def _build_summary_stats(user_id):
    stats = get_summary_stats(user_id)
    return [
        {"label": "Total Spent", "value": f"₹{stats['total_spent']:.2f}"},
        {"label": "Transactions", "value": str(stats["transaction_count"])},
        {"label": "Top Category", "value": stats["top_category"]},
    ]


# --- Transaction history view-model helper (implemented by transaction-history subagent) ---
# Must return a list of dicts matching profile.html's `transactions` loop, newest-first:
#   [{"date": "2026-08-15", "description": "Dinner out", "category": "Food", "amount": "₹32.40"}, ...]
# Calls database.db.get_recent_transactions(user_id) and formats the result.
def _build_transactions(user_id):
    rows = get_recent_transactions(user_id)
    return [
        {
            "date": row["date"],
            "description": row["description"] or "",
            "category": row["category"],
            "amount": f"₹{row['amount']:.2f}",
        }
        for row in rows
    ]


# --- Category breakdown view-model helper (implemented by category-breakdown subagent) ---
# Must return a list of dicts matching profile.html's `categories` loop, ordered by amount desc:
#   [{"name": "Bills", "amount": "₹89.99", "percent": 31}, ...]  (percent ints summing to 100)
# Calls database.db.get_category_breakdown(user_id) and formats the result.
def _build_categories(user_id):
    breakdown = get_category_breakdown(user_id)
    return [
        {
            "name": item["name"],
            "amount": f"₹{item['amount']:.2f}",
            "percent": item["pct"],
        }
        for item in breakdown
    ]


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        flash("Please log in to view your profile.", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user_row = get_user_by_id(user_id)
    name_parts = user_row["name"].split()
    initials = "".join(part[0] for part in name_parts[:2]).upper()
    user = {
        "name": user_row["name"],
        "email": user_row["email"],
        "initials": initials,
        "member_since": format_member_since(user_row["created_at"]),
    }
    stats = _build_summary_stats(user_id)
    transactions = _build_transactions(user_id)
    categories = _build_categories(user_id)
    return render_template(
        "profile.html", user=user, stats=stats,
        transactions=transactions, categories=categories,
    )


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
