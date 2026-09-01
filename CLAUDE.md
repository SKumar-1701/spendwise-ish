# CLAUDE.md

## Project Overview
Spendwise-ish is a lightweight personal expense tracker built with Flask and SQLite.

## Commands
```bash
# setup
source venv4/bin/activate
pip install -r requirements.txt

# run the dev server (http://localhost:5001)
python app.py

# Run all tests
pytest

# Run a specific test file
pytest tests/test_foo.py

# Run a specific test by name
pytest -k "test_name"
```
There is no lint/format tooling configured in this repo.

## Architecture

spendwise_ish/
├── app.py              # All routes — single file, no blueprints
├── database/
│   └── db.py           # SQLite helpers: get_db(), init_db(), seed_db()
├── templates/
│   ├── base.html       # Shared layout — all templates must extend this
│   └── *.html          # One template per page
├── static/
│   ├── css/
│   │   ├── style.css       # Global styles
│   │   └── landing.css     # Landing-page-only styles
│   └── js/
│       └── main.js         # Vanilla JS only
└── requirements.txt
Where things belong:

New routes → app.py only, no blueprints
DB logic → database/db.py only, never inline in routes
New pages → new .html file extending base.html
Page-specific styles → new .css file, not inline <style> tags

The product is branded "Spendwise-ish" (see `base.html` nav/footer).

## Code style
Python: PEP 8, snake_case for all variables and functions
Templates: Jinja2 with url_for() for every internal link — never hardcode URLs
Route functions: one responsibility only — fetch data, render template, done
DB queries: always use parameterized queries (? placeholders) — never f-strings in SQL
Error handling: use abort() for HTTP errors, not bare return "error string"

## Tech constraints
Flask only — no FastAPI, no Django, no other web frameworks
SQLite only — no PostgreSQL, no SQLAlchemy ORM, no external DB
Vanilla JS only — no React, no jQuery, no npm packages
No new pip packages — work within requirements.txt as-is unless explicitly told otherwise
Python 3.10+ assumed — f-strings and match statements are fine

## Subagent Policy
Always use a builtin explore subagent for codebase exploration before implementing any new feature
Always use a subagent to verify test results after any implementation
When asked to plan, delegate codebase research to a subagent before presenting the plan
always use a builtin plan subagent in plan mode

## Implemented vs Stub routes
Route | Status
GET /	Implemented — renders landing.html
GET /register	Implemented — renders register.html
GET /login	Implemented — renders login.html
GET /logout	Implemented — clears session, redirects to landing
GET /profile	Implemented — renders profile.html (live DB data)
GET, POST /expenses/add	Implemented — Step 7
GET, POST /expenses/<id>/edit	Implemented — Step 8
GET /expenses/<id>/delete	Stub — Step 9

Do not implement a stub route unless the active task explicitly targets that step.

## Warnings and things to avoid
Never use raw string returns for stub routes once a step is implemented — always render a template
Never hardcode URLs in templates — always use url_for()
Never put DB logic in route functions — it belongs in database/db.py
Never install new packages mid-feature without flagging it — keep requirements.txt in sync
Never use JS frameworks — the frontend is intentionally vanilla
database/db.py is currently empty — do not assume helpers exist until the step that implements them
FK enforcement is manual — SQLite foreign keys are off by default; get_db() must run PRAGMA foreign_keys = ON on every connection
The app runs on port 5001, not the Flask default 5000 — don't change this

