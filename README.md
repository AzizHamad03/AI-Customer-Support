# AI Customer Support Assistant

A Django application for a fictional online store. Customers ask questions
about store policies and products through a session-based chat. The assistant
retrieves relevant document passages and answers with supporting sources.
Customers can submit confirmed support tickets for issues requiring staff review.

## Problem statement

Small online stores receive repeated shipping, return, and product questions.
Customers wait for answers while staff spend time answering routine questions
and organizing requests that need follow-up.

## Proposed solution

Retrieval-Augmented Generation (RAG) supplies relevant store document passages
to a language model. Customers can inspect the evidence supporting an answer.
When information is inadequate, the assistant explains the limitation and
offers human support.

Staff manage the knowledge base, review ticket-linked conversations, and
update ticket statuses through an authenticated dashboard.

## Implemented features

- PDF/TXT upload, validation, text extraction, chunking, and indexing.
- PostgreSQL/pgvector retrieval from active, successfully indexed documents.
- English customer chat with bounded follow-up context.
- Persistent messages and citation evidence.
- Ticket validation, review, explicit confirmation, and duplicate prevention.
- Session-scoped customer chat history and ticket access.
- Staff ticket search, status filters, conversation review, and status updates.
- Document activation/deactivation and versioned replacement.
- The old document remains available until replacement indexing succeeds.

A single assistant selects knowledge-search and support-ticket tools through
a bounded tool-calling loop. Each chat request allows up to three model turns
and two tool calls.

Ticket creation requires the customer to complete the support form, review
the saved draft, and explicitly confirm it. The backend verifies the draft
identifier, browser session, and fields before executing the ticket tool.
Chat messages cannot authorize ticket creation.

Live order tracking, payments, refund execution, OCR, notifications, and live
human chat handoff are outside the current scope.

## Technologies

- Python 3.12
- Django and Django REST Framework
- PostgreSQL with the pgvector server extension
- LangChain OpenAI integration
- OpenAI chat and embedding APIs
- Pydantic and pypdf
- Django templates, HTML, CSS, and JavaScript

Python dependencies are pinned in requirements.txt. PostgreSQL and its vector
extension must be installed separately. There is no SQLite fallback.

## Installation

### 1. Install prerequisites

Install Git, Python 3.12, and PostgreSQL 15 or newer.

For macOS using Homebrew:

```bash
brew install python@3.12 postgresql@15
brew services start postgresql@15
export PATH="$(brew --prefix postgresql@15)/bin:$PATH"
```

Skip installation/startup commands for components already installed. If you
use a different PostgreSQL installation, use its tools and administrator
account rather than starting another server.

For Ubuntu 24.04:

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv git build-essential postgresql postgresql-server-dev-all
sudo service postgresql start
```

### 2. Install the vector server extension

Skip this step if vector is already installed for the running PostgreSQL server.
Installing the Python pgvector package does not install the server extension.

The pg_config executable must match the PostgreSQL server's major version.
Build in a separate directory outside the application:

```bash
git clone --branch v0.8.7 --depth 1 https://github.com/pgvector/pgvector.git pgvector-build
cd pgvector-build
pg_config --version
make PG_CONFIG="$(command -v pg_config)"
```

On a user-owned Homebrew installation:

```bash
make install PG_CONFIG="$(command -v pg_config)"
```

On Ubuntu:

```bash
sudo make install PG_CONFIG="$(command -v pg_config)"
```

Return to your working directory with `cd ..`.

macOS compilation requires the Xcode command-line tools. If missing, install
them with `xcode-select --install` before building.

See https://github.com/pgvector/pgvector#installation for other installation
methods and troubleshooting.

### 3. Create the database

Connect as your PostgreSQL administrator.

For Homebrew, this is normally:

```bash
psql -d postgres
```

For Ubuntu:

```bash
sudo -u postgres psql -d postgres
```

For a new setup, run in psql:

```sql
CREATE ROLE customer_support_user LOGIN CREATEDB;
\password customer_support_user
CREATE DATABASE customer_support OWNER customer_support_user;
\connect customer_support
CREATE EXTENSION IF NOT EXISTS vector;
SELECT extversion FROM pg_extension WHERE extname = 'vector';
SELECT '[1,2,3]'::vector;
\quit
```

Choose your own database password when prompted. Reuse existing roles and
databases instead of recreating them.

Enable vector as administrator before migrations. The application role does
not need to be a superuser. CREATEDB supports local test database creation.

### 4. Clone and install dependencies

```bash
git clone YOUR_REPOSITORY_URL ai-customer-support
cd ai-customer-support
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

For a ZIP download, extract it and enter the folder containing manage.py
instead of cloning.

### 5. Configure environment variables

For a new installation:

```bash
cp .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Edit .env and set SECRET_KEY, DB_PASSWORD, and OPENAI_API_KEY.
Keep the signing key stable across restarts.

If .env already exists, compare it with the example instead of overwriting
working credentials.

| Variable | Purpose |
| --- | --- |
| DEBUG | Local development mode; True for this demo |
| SECRET_KEY | Unique, stable Django signing key |
| ALLOWED_HOSTS | Allowed hostnames, separated by commas |
| DB_NAME | PostgreSQL database name |
| DB_USER | PostgreSQL role |
| DB_PASSWORD | Database role password |
| DB_HOST | Database host; defaults to localhost |
| DB_PORT | Database port; defaults to 5432 |
| OPENAI_API_KEY | Required for embeddings and live AI answers |
| CHAT_MODEL | Chat model; defaults to gpt-4.1-mini |

The embedding model is configured in config/settings.py as
text-embedding-3-small with 1536 dimensions. Changing the embedding model
requires compatible dimensions and reindexing.

DATABASE_URL is not used. Shell environment variables take precedence over
values loaded from .env.

Never commit real credentials, .env, private uploaded documents, or ticket data.

### 6. Migrate and run

```bash
python manage.py check
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/ and sign in through Staff workspace.

AI indexing and live answers require an API key with model access and available
API credit. A ChatGPT subscription is separate from API billing.

## Load sample documents

1. Open Staff workspace and sign in.
2. Open Manage documents, then Upload document.
3. Upload each file in sample_data/policies/ once.
4. Click **Process document** to extract text, prepare chunks, and generate
   embeddings. Confirm the document is Ready and available for chat.
   If indexing fails, use the same button to retry.
5. Open Customer chat and ask a sample question.
6. Expand the answer's source to inspect the supporting passage.

See sample_data/README.md for titles, categories, questions, and replacement
testing. Sample documents are not automatically loaded by migrations.

## Support-ticket demonstration

1. Report a damaged delivery in chat.
2. Click Request human support.
3. Enter fictional contact details, an issue description, and an optional
   order reference.
4. Review the details and explicitly confirm.
5. Check the saved reference and status under My tickets.
6. Open the ticket in the staff workspace and update its status.

Sending a chat message alone does not create a ticket.

## APIs

| Endpoint | Purpose |
| --- | --- |
| GET /api/health/ | Database connectivity; returns 503 if unavailable |
| GET /api/chat/ | Current session's messages and citations |
| POST /api/chat/ | Send a question as JSON |

Example POST body:

```json
{"content": "How much does shipping cost?"}
```

Chat requests use the browser session cookie. POST requests require a CSRF
token in the X-CSRFToken header, including for anonymous visitors.

Staff document and ticket operations currently use authenticated Django
pages/forms rather than separate REST APIs.

## Project structure

| Location | Responsibility |
| --- | --- |
| config/ | Settings, root URLs, WSGI |
| support/models/ | Separate domain models |
| support/views/ | Pages and API request handling |
| support/api/ | Serializer and session/CSRF authentication |
| support/services/ | Document, retrieval, chat, and ticket rules |
| support/ai/ | Embeddings, prompts, rewriting, structured answers |
| support/migrations/ | Database schema and vector migration |
| support/tests/ | Functional and permission checks |
| templates/ | Customer and staff pages |
| static/ | Stylesheet and browser chat code |
| sample_data/ | Public fictional demonstration documents |
| media/ | Runtime uploads, excluded from Git |

Data persists in PostgreSQL after restarting the application. Preserve the
database, uploaded files, and signing key.

Anonymous access depends on browser session cookies. Clearing cookies or
session expiry can remove that visitor's access to history and tickets.

## Automated checks

Prepare a separate test database once through the PostgreSQL administrator:

```sql
CREATE DATABASE test_customer_support OWNER customer_support_user;
\connect test_customer_support
CREATE EXTENSION IF NOT EXISTS vector;
\quit
```

If the test database exists, connect and ensure vector is enabled. Use
test_<DB_NAME> if your application database name differs.

Then run:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --keepdb
```

The --keepdb option retains the prepared test database and vector extension.
Run the full suite on PostgreSQL, not SQLite.

Existing tests mock AI requests. They do not require an API key or measure
live model quality, latency, or memory.

## Troubleshooting

| Problem | Check |
| --- | --- |
| Missing DB environment variable | .env exists beside manage.py and contains required fields |
| Database connection refused | PostgreSQL is running on the configured host/port |
| Authentication failed | DB_USER and DB_PASSWORD match the database role |
| vector.control missing | Server extension is installed for the running PostgreSQL version |
| Permission denied creating vector | Administrator enabled vector in the application/test database |
| No searchable documents | Documents are indexed, Ready, and Active |
| API error | Key, billing, model access, and network; restart after editing .env |
| Empty/scanned file fails | Use non-empty UTF-8 TXT or text-based PDF |

## Evaluation and remaining work

Performance evaluation is not yet completed.

The proposed evaluation includes 25 answerable questions, 10 unsupported
questions, 10 escalation workflows, and 5 multi-turn conversations, with
separate development examples.

The report will cover retrieval and answer quality, groundedness, ticket
success, latency, local backend memory, and a no-RAG comparison.

Remaining work includes controlled agent tools, broader failure-path tests,
the evaluation report, and the final presentation.