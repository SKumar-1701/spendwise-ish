import sqlite3

from flask import Flask, render_template, request, flash, redirect, url_for, session
from werkzeug.security import check_password_hash

from database.db import get_db, init_db, seed_db, create_user, get_user_by_email

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


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/profile")
def profile():
    if not session.get("user_id"):
        flash("Please log in to view your profile.", "error")
        return redirect(url_for("login"))

    user = {
        "name": "Demo User",
        "email": "demo@spendwise-ish.com",
        "initials": "DU",
        "member_since": "January 2026",
    }
    stats = [
        {"label": "Total Spent", "value": "$290.34"},
        {"label": "Transactions", "value": "8"},
        {"label": "Top Category", "value": "Food"},
    ]
    transactions = [
        {"date": "2026-08-15", "description": "Dinner out", "category": "Food", "amount": "$32.40"},
        {"date": "2026-08-12", "description": "Miscellaneous", "category": "Other", "amount": "$9.50"},
        {"date": "2026-08-10", "description": "New shoes", "category": "Shopping", "amount": "$60.20"},
        {"date": "2026-08-08", "description": "Movie tickets", "category": "Entertainment", "amount": "$15.75"},
        {"date": "2026-08-06", "description": "Pharmacy", "category": "Health", "amount": "$25.00"},
        {"date": "2026-08-04", "description": "Electricity bill", "category": "Bills", "amount": "$89.99"},
        {"date": "2026-08-03", "description": "Bus pass top-up", "category": "Transport", "amount": "$12.00"},
        {"date": "2026-08-01", "description": "Groceries", "category": "Food", "amount": "$45.50"},
    ]
    categories = [
        {"name": "Bills", "amount": "$89.99", "percent": 31},
        {"name": "Food", "amount": "$77.90", "percent": 27},
        {"name": "Shopping", "amount": "$60.20", "percent": 21},
        {"name": "Health", "amount": "$25.00", "percent": 9},
        {"name": "Entertainment", "amount": "$15.75", "percent": 5},
        {"name": "Transport", "amount": "$12.00", "percent": 4},
        {"name": "Other", "amount": "$9.50", "percent": 3},
    ]
    return render_template(
        "profile.html", user=user, stats=stats,
        transactions=transactions, categories=categories,
    )


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
