# AI Customer Support Assistant

## Current step
A working Django foundation with a home page, authenticated staff workspace,
Django administration, and a database health API. AI chat, documents, and tickets
are not implemented yet. This README will grow with the working features.

## Problem and proposed solution
Small online stores receive repeated policy questions and requests that need
human follow-up. The completed application will answer from approved store
documents with RAG and citations, then create a support ticket only after the
customer confirms the details. Customers will use session-based chat; staff
will authenticate to manage documents, conversations, and tickets.

## Technologies
Python 3.12, Django 5.2, Django REST Framework, Django templates, and CSS.
SQLite is used only for the initial local foundation. PostgreSQL with pgvector
is the specified target before document indexing and final evaluation.
No Docker, queue, or separate frontend is needed for this version.

## Run on macOS or Linux
Install Python 3.12 first. Extract the project and open a terminal in this folder.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Paste the generated key after `SECRET_KEY=` in `.env`. Then run:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Choose your own username and password when prompted. No accounts or credentials
are bundled. Open http://127.0.0.1:8000/ and use **Staff workspace** to sign in.
You should see the home page, your staff workspace, and Django administration.
Stop the server with Ctrl+C.

## Environment variables
- `DEBUG`: `True` for local development; defaults to `True`.
- `SECRET_KEY`: Django signing key. Set it for stable sessions. If omitted in
  debug mode, a temporary key is generated at startup; production mode requires it.
- `ALLOWED_HOSTS`: comma-separated allowed hostnames.
- `DATABASE_URL`: optional for this first step; blank uses local SQLite.
  Later use a PostgreSQL URL as illustrated in `.env.example`. The PostgreSQL
  database and role must already exist. Setting a URL does not transfer SQLite data.

Never commit `.env` or real credentials. `.env.example` is safe to commit.
This project is configured for local development, not production hosting.

## Project structure
- `config/`: settings, root URLs, and WSGI entry point.
- `support/views/`: separate page and API views.
- `support/services/`: database health logic, separate from the API view.
- `support/tests/`: application and staff permission checks.
- `templates/`: shared layout, home, and staff workspace.
- `static/`: application stylesheet.

Add each major domain model in a separate file under `support/models/` when its
feature is implemented. Django authentication currently supplies the user model.

## API and verification
`GET /api/health/` is public and returns:

```json
{"status": "ok", "database": "connected"}
```

It executes a small database query. An unavailable database returns HTTP 503.
Other APIs will use explicit session and staff permissions as they are added.
The staff workspace redirects anonymous users and ordinary non-staff users to
staff login. Login and logout use Django authentication and CSRF protection.

```bash
python manage.py check
python manage.py test
```

## Next steps
1. Add staff document upload and document processing status.
2. Add PostgreSQL/pgvector indexing, session chat, RAG answers, and citations.
3. Add confirmed support tickets and staff management.
4. Run the specified evaluation: fixed quality cases, baseline comparison,
   response latency, and local backend memory measurements.
5. Complete this README, evaluation document, and presentation, then submit GitHub.

The final evaluation will use 25 answerable questions, 10 unsupported questions,
10 escalation workflows, and 5 multi-turn conversations, with separate development
examples. Results will be measured after the main features work.
