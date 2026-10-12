# AI Customer Support Assistant

A Django application for a fictional online store. Customers ask questions
about store policies and products through guest or account-based chat. The
assistant retrieves relevant document passages and answers with supporting
sources. Registered customers can manage saved conversations across browsers
and devices. Customers can submit confirmed support tickets for staff review.

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
- Guest chat and tickets restricted to the current browser session.
- Customer registration, login, and POST-only logout using Django authentication.
- Account-owned conversations and tickets accessible after logging in again.
- Guest-history transfer on registration/login, preserving messages, citations,
  and existing tickets.
- Paginated My conversations list, conversation selection, and New conversation.
- Ownership checks for conversation selection and customer ticket access.
- Browser chat checks the selected conversation ID before sending a message.
- Staff ticket search, status filters, conversation review, and status updates.
- Document activation/deactivation and versioned replacement.
- The old document remains available until replacement indexing succeeds.
- Staff-only document deletion with explicit confirmation, removal of search
  data, and preservation of historical citation text.

A single assistant selects knowledge-search and support-ticket tools through
a bounded tool-calling loop. Tool selection allows up to three model turns
and two tool calls per chat request. Follow-up rewriting and grounded answer
generation are separate model calls outside that loop.

Ticket creation requires the customer to complete the support form, review
the saved draft, and explicitly confirm it. The backend verifies the draft
identifier, customer account or guest session ownership, and fields before
executing the ticket tool.
Chat messages cannot authorize ticket creation.

Live order tracking, payments, refund execution, OCR, notifications, and live
human chat handoff are outside the current scope.

## Users and access

| User | Available features |
| --- | --- |
| Guest | Chat and confirmed support tickets within the current browser session |
| Registered customer | Account-owned chat history, My conversations, New conversation, and their tickets |
| Staff | Customer features plus document management and staff ticket workflows |

Registration creates an ordinary customer account. It does not grant staff or
superuser permissions. Staff access requires an active Django user with
`is_staff=True`; the superuser created during setup has this access.

Guest access depends on session cookies. Clearing cookies or session expiry
can remove access to guest history and tickets. Registering or logging in
through the application's account pages transfers the current guest
conversation and its existing tickets to that account. Existing account
conversations remain separate and appear in My conversations.

Login and conversation switching clear unfinished support-ticket drafts.
Saved tickets are retained. Logging out ends the browser's authenticated
session without deleting account history.

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

Open http://127.0.0.1:8000/.

- Customers can use guest chat or choose Create account / Log in.
- Staff can use Log in with their existing staff credentials; the default
  destination after login is the staff workspace.
- `/admin/` remains available for Django administration. Unauthenticated
  staff-workspace requests currently redirect to the admin login page.
- For guest-history transfer, use `/accounts/login/` or `/accounts/signup/`;
  that transfer is implemented in the application account views.

When updating an existing installation, apply `python manage.py migrate`.
The account-ownership migration preserves existing conversations as guest
conversations until they are transferred through application registration/login.

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

## Customer accounts and saved conversations

1. Open Customer chat and optionally ask a question as a guest.
2. Choose Create account and enter a username and password. Django validates
   the password; email verification and password-reset flows are not implemented.
3. The current guest conversation, its citations, and existing tickets transfer
   to the account. A new account does not receive staff permissions.
4. Use New conversation to open an empty chat while retaining earlier chats.
5. Open My conversations to select an earlier conversation. List labels use the
   first customer message; empty chats are labeled New conversation.
6. Log out, then log in again or use another browser to access account history.
7. My tickets lists tickets across all conversations owned by the account.

A browser session stores its selected conversation. If no owned selection is
available, chat opens the account's most recently updated conversation, or
creates its first conversation. Separate browser sessions can select different
conversations. Tabs sharing a session share the selection; the browser chat
includes the loaded conversation ID with each question to detect an outdated
selection and reload without automatically resending.

## Document availability, replacement, and deletion

Use Deactivate document to exclude a Ready document from future retrieval
while retaining its file and indexing data. Activate document restores
availability when the document is eligible.

To update a Ready, active document, choose Upload replacement and process the
new version. The original remains available until replacement indexing
succeeds. Successful indexing activates the replacement and deactivates the
original together. A replaced original cannot be reactivated while a Ready
replacement references it.

To remove a document:

1. Open its detail page in the staff workspace.
2. Choose Delete document.
3. Review the title/version, tick the confirmation checkbox, and submit.

Deletion removes the database document, extracted text, chunks, and embeddings.
Existing conversations and citation snapshots remain; their chunk links become
null. Uploaded-file cleanup runs after the database transaction commits. If
file cleanup fails, the failure is logged and the document remains excluded
from retrieval.

A document referenced by any replacement version cannot be deleted. Delete
referencing versions first, or deactivate the document. Deleting a replacement
does not automatically reactivate its original. No conversation-deletion or
conversation-renaming interface is currently provided.

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
| GET /api/chat/ | Selected owned or guest conversation ID, messages, and citations |
| POST /api/chat/ | Send a question as JSON |

First call `GET /api/chat/` to obtain the selected `conversation_id`.
Include that ID in a question request, for example:

```json
{
  "content": "How much does shipping cost?",
  "conversation_id": 1
}
```

Replace `1` with the ID returned by GET. The ID is a selection check, not a way
to open an arbitrary conversation. The server verifies ownership when selecting
history. `conversation_id` is optional for API compatibility; the browser always
supplies it. A supplied ID must be an integer matching the selected conversation.

Chat responses include `conversation_id` and `messages`. A selection mismatch,
concurrent conversation change, or evidence change during a cited answer returns
409. AI/database availability failures return 503.

Chat requests use the browser session cookie. POST requests require a CSRF
token in the X-CSRFToken header, including for anonymous visitors.

Account, conversation-selection, and staff operations use Django pages/forms
rather than separate REST APIs. Relevant routes include:

| Route | Method | Purpose |
| --- | --- | --- |
| /accounts/signup/ | GET, POST | Customer registration |
| /accounts/login/ | GET, POST | Customer/staff login |
| /accounts/logout/ | POST | Logout |
| /conversations/ | GET | Registered customer's conversation list |
| /conversations/new/ | POST | Create and select an account-owned conversation |
| /conversations/<id>/open/ | POST | Select an owned conversation |
| /support/request/ | GET, POST | Prepare a support-ticket draft |
| /support/confirm/ | GET, POST | Review and confirm ticket creation |
| /support/tickets/ | GET | Customer's accessible tickets |
| /staff/ | GET | Staff dashboard |
| /staff/documents/<id>/delete/ | GET, POST | Staff deletion review and confirmation |

State-changing forms include CSRF tokens. Conversation routes require login;
staff routes require staff membership.

## Project structure

| Location | Responsibility |
| --- | --- |
| config/ | Settings, root URLs, WSGI |
| support/models/ | Separate domain models |
| support/views/ | Pages and API request handling |
| support/api/ | Serializer and session/CSRF authentication |
| support/services/ | Accounts, conversations, documents, retrieval, chat, and ticket rules |
| support/ai/ | Embeddings, bounded agent, controlled tools, rewriting, structured answers |
| support/migrations/ | Database schema and vector migration |
| support/tests/ | Functional and permission checks |
| templates/ | Customer and staff pages |
| static/ | Stylesheet and browser chat code |
| sample_data/ | Public fictional demonstration documents |
| media/ | Runtime uploads, excluded from Git |

Data persists in PostgreSQL after restarting the application. Preserve the
database, uploaded files, and signing key.

Registered history belongs to the account and can be accessed after logging
in again. Guest history remains dependent on the original browser session.

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

Tests cover document processing/replacement/deletion, citation preservation,
RAG failures, controlled tools, ticket validation and duplicate prevention,
concurrent ticket confirmation, registration/login, guest-history transfer,
account ownership, staff permissions, conversation selection, and stale-tab
requests.

AI requests are mocked. Tests do not require an API key and do not measure
live model quality, latency, or memory. Invalid-PDF and simulated AI-failure
logs can appear during successful failure-path tests; use the final test result
and traceback output to identify actual failures.

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
| Conversation changed / HTTP 409 | Review reloaded history before resending; another tab or request may have changed it |
| Login-related CSRF error in an old tab | Refresh the full page after logging in or out |
| Customer cannot access staff workspace | Expected; use an account with staff membership |
| Cannot delete a document | Check for referencing replacement versions |
| Earlier chat not currently visible | Open My conversations and select it; guests need their original session |

## Evaluation and remaining work

Performance evaluation is not yet completed.

The proposed evaluation includes 25 answerable questions, 10 unsupported
questions, 10 escalation workflows, and 5 multi-turn conversations, with
separate development examples.

The report will cover retrieval and answer quality, groundedness, ticket
success, latency, local backend memory, and a no-RAG comparison.

The fixed evaluation dataset, evaluation runner, measurement/scoring scripts,
and recorded evaluation results are not included in this version. Sample
questions are development/demo examples. Remaining deliverables include the
performance evaluation document and final presentation.

Possible later improvements include moving embedding API calls outside document
indexing transactions, adding an overall chat-request time budget, and using
measured evaluation results to tune retrieval. Current document indexing runs
synchronously, and long conversation histories are loaded in full.

The current scope is one demonstration store with English text chat. The
application does not yet include password recovery, email verification, or
production deployment configuration.