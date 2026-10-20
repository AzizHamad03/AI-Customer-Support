# AI Customer Support Assistant

A Django application for a fictional online store. Customers ask questions
about store policies and products through guest or account-based chat. The
assistant retrieves relevant document passages and answers with supporting
sources. Registered customers can manage saved conversations across browsers
and devices. Customers can submit confirmed support tickets for staff review.

Staff upload knowledge documents and queue processing from the browser.
A background worker extracts text, prepares chunks, and generates embeddings.
One local startup command launches both the website and worker.

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
- Persistent PostgreSQL-backed background document processing.
- Queued, Processing, Succeeded, and Failed processing-job states.
- Retry support and duplicate-job prevention.
- Automatic document-page refresh while processing is queued or running.
- Embedding requests outside indexing transactions.
- Document and chunk revalidation before embeddings are saved.
- Expiring job leases and attempt tokens to prevent superseded workers
  from publishing results.
- One-command local startup for the website and document worker.
- PostgreSQL/pgvector retrieval from active, successfully indexed documents.
- Configurable cosine-distance filtering to exclude weak retrieval matches.
- English customer chat with bounded follow-up context.
- Persistent messages and citation evidence.
- Ticket validation, review, explicit confirmation, and duplicate prevention.
- Ticket draft validation and confirmation handled by the ticket service,
  independently of the AI tools.
- Chat sending limits: 10 requests per minute per guest IP and 30 per minute
  per registered account.
- Conversation history remains readable after the chat sending limit is reached.
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
- Separate development and evaluation datasets for retrieval.
- An evaluation runner that records evidence coverage, retrieved passages,
  distances, timings, errors, and configuration fingerprints.

A single assistant selects the knowledge-search tool through a bounded
tool-calling loop. Tool selection allows up to three model turns and two
tool calls per chat request. Follow-up rewriting and grounded answer
generation are separate model calls outside that loop.

The tool-selection, question-rewriting, and grounded-answer prompts are
stored in `support/ai/prompts/` and loaded through a shared helper.
Store policy facts come from retrieved documents rather than hardcoded
policy examples in the prompts.

Ticket creation requires the customer to complete the support form, review
the saved draft, and explicitly confirm it. The confirmation view calls the
ticket service directly. The service validates the saved draft identifier,
explicit confirmation, account or guest-session ownership, and saved fields
before creating a ticket.

Ticket saving is transactional. Repeated confirmation of the same draft
returns the existing ticket rather than creating a duplicate.
The AI agent has no ticket-creation tool, and chat messages cannot authorize
ticket creation.

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

Python dependencies are pinned in `requirements.txt`. PostgreSQL and its vector
extension must be installed separately. There is no SQLite fallback.

Document jobs use the existing PostgreSQL database. Redis and a separate
message broker are not required.

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

The `pg_config` executable must match the PostgreSQL server's major version.
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

See the [pgvector installation guide](https://github.com/pgvector/pgvector#installation)
for other installation methods and troubleshooting.

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
not need to be a superuser. `CREATEDB` supports local test database creation.

### 4. Clone and install dependencies

```bash
git clone https://github.com/AzizHamad03/AI-Customer-Support.git ai-customer-support
cd ai-customer-support
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

For a ZIP download, extract it and enter the folder containing `manage.py`
instead of cloning.

### 5. Configure environment variables

For a new installation:

```bash
cp .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Edit `.env` and set `SECRET_KEY`, `DB_PASSWORD`, and `OPENAI_API_KEY`.
Keep the signing key stable across restarts.

`DEBUG` defaults to `False` when it is not explicitly configured.
The supplied `.env.example` sets `DEBUG=True` for local development.

When `DEBUG=False`, `SECRET_KEY` must be explicitly configured.
Disabling debug mode alone does not provide a complete production deployment
configuration.

If `.env` already exists, compare it with the example instead of overwriting
working credentials.

| Variable | Purpose |
| --- | --- |
| DEBUG | Defaults to False; set True in .env for local development |
| SECRET_KEY | Unique, stable Django signing key |
| ALLOWED_HOSTS | Allowed hostnames, separated by commas |
| DB_NAME | PostgreSQL database name |
| DB_USER | PostgreSQL role |
| DB_PASSWORD | Database role password |
| DB_HOST | Database host; defaults to localhost |
| DB_PORT | Database port; defaults to 5432 |
| OPENAI_API_KEY | Required for embeddings and live AI answers |
| CHAT_MODEL | Chat model; defaults to gpt-4.1-mini |
| RETRIEVAL_MAX_DISTANCE | Maximum accepted cosine distance; defaults to 0.80 |

`RETRIEVAL_MAX_DISTANCE` must be a number between 0 and 2, inclusive.
Lower values make retrieval stricter.

The embedding model is configured in `config/settings.py` as
`text-embedding-3-small` with 1536 dimensions. Changing the embedding model
requires compatible dimensions and reindexing.

`DOCUMENT_JOB_LEASE_SECONDS` is configured directly in `config/settings.py`
as `900` seconds. It is not read from an environment variable.

`DATABASE_URL` is not used. Shell environment variables take precedence over
values loaded from `.env`.

Never commit real credentials, `.env`, private uploaded documents, or ticket data.

### 6. Migrate and run

```bash
python manage.py check
python manage.py migrate
python manage.py createsuperuser
python manage.py runlocal
```

Skip `createsuperuser` if an appropriate staff account already exists.

`runlocal` starts both the web server and document worker from one terminal.
Keep it running while using the application. Press **Control+C** to stop both.

Open http://127.0.0.1:8000/.

- Customers can use guest chat or choose Create account / Log in.
- Staff can use Log in with their existing staff credentials; the default
  destination after login is the staff workspace.
- `/admin/` remains available for Django administration.
- Staff-workspace access redirects to the application's `/accounts/login/`
  page when the visitor does not meet the staff requirement.
- An already signed-in customer can view that login form without a redirect
  loop and sign in with an appropriate staff account.
- For guest-history transfer, use `/accounts/login/` or `/accounts/signup/`;
  that transfer is implemented in the application account views.

When updating an existing installation, apply `python manage.py migrate`
before starting the application. Existing Ready documents do not need
reindexing for the background-processing change.

The account-ownership migration preserves existing conversations as guest
conversations until they are transferred through application registration/login.

AI indexing and live answers require an API key with model access and available
API credit. A ChatGPT subscription is separate from API billing.

## Local development startup

With the virtual environment activated, start the complete local application:

```bash
python manage.py runlocal
```

To use a different web-server port:

```bash
python manage.py runlocal 127.0.0.1:8001
```

The launcher:

- Starts Django's development server and the document worker.
- Uses the active Python environment for both processes.
- Shows both processes' output in one terminal.
- Stops both when Control+C is pressed.
- Stops the remaining process if either process exits.

The web server retains Django's automatic code reloading.
The worker does not automatically reload its Python modules.
After editing worker or processing-service code, stop and restart `runlocal`.

Also restart after changing environment variables so both processes use
the updated configuration.

The launcher uses POSIX process groups and is intended for local development
on macOS or Linux. It is not a production process manager.

### Running the processes separately

For debugging or testing queue behavior, the processes can still be started
individually.

Web server:

```bash
python manage.py runserver
```

Document worker, in another terminal:

```bash
python manage.py process_document_jobs
```

Do not run these alongside `runlocal` unless intentionally managing additional
processes. Normal local use only requires `runlocal`.

## Load sample documents

1. Start the application with `python manage.py runlocal`.
2. Open Staff workspace and sign in.
3. Open Manage documents, then Upload document.
4. Upload each file in `sample_data/policies/` once.
5. Click **Process document** to queue extraction, chunk preparation,
   and embedding generation.
6. The detail page shows Queued, Processing, Succeeded, or Failed.
   Processing continues even if the page is closed.
7. Confirm the document is Ready and available for chat.
   If processing fails, use **Retry processing**.
8. Open Customer chat and ask a sample question.
9. Expand the answer's source to inspect the supporting passage.

Use these titles and categories:

| File | Document title | Category |
| --- | --- | --- |
| shipping_policy.txt | Demo Store Shipping Policy | Shipping |
| returns_policy.txt | Demo Store Returns Policy | Returns |
| product_catalog.txt | Demo Store Product Catalog | Products |
| support_policy.txt | Demo Store Support Policy | General |

Reuse existing matching documents rather than uploading duplicates.

See `sample_data/README.md` for sample questions and replacement testing.
Sample documents are not automatically loaded by migrations.

## Background document processing

Document processing uses a persistent PostgreSQL-backed queue.
The browser request only queues work and returns the document page.
The separate worker performs text extraction, chunk preparation, and indexing.

Staff only need to click **Process document**. They do not run terminal
commands for individual documents.

### Processing states

Processing jobs have their own state, separate from the document's
Pending, Extracted, Ready, or Failed status.

| Job state | Meaning |
| --- | --- |
| Queued | Saved and waiting for an available worker |
| Processing | A worker has claimed the job |
| Succeeded | The processing attempt completed successfully |
| Failed | The attempt failed; the detail page shows an error and retry option |

The detail page refreshes automatically while the job is queued or processing.
Small documents may finish between refreshes, so the visible state can change
directly from Queued to Succeeded.

A successful document must be Ready and active before retrieval can use it.

### Duplicate prevention and retries

Each document has one processing-job record.
Repeated submissions while it is queued or processing do not create another
job. Submitting an already Ready document does not start new processing.

Failed jobs can be queued again using **Retry processing**.
A retry reuses the job record and increases the attempt count when claimed.

After an embedding failure, retries retain extracted text and prepared chunks
when they are still available. Extraction failures are reprocessed on retry.

### Transaction and replacement safeguards

Indexing captures the document and chunk inputs in a short transaction,
then requests embeddings outside that transaction.

Before saving the result, it re-locks and checks:

- The document's indexing eligibility and replacement relationship.
- The document and chunk snapshot.
- The current processing-attempt token and lease.
- Whether another replacement has already completed indexing.

If the input state changed or the attempt lost ownership, its embeddings
are not published.

The original document remains active until replacement indexing succeeds.
Original deactivation and replacement activation commit together.

### Interrupted workers and leases

Queue records persist when the worker stops.
Queued work can be claimed when a worker starts again.

Each claimed attempt has a fixed 15-minute lease, configured by
`DOCUMENT_JOB_LEASE_SECONDS`. An interrupted job may remain Processing until
its existing lease expires. A running worker can then reclaim it with a new
attempt token.

An expired or superseded attempt cannot publish its embeddings.
Attempts that exceed the lease must be processed again.

Recovery may repeat an external embedding request. This is not an exactly-once
API-call guarantee. Ordinary processing failures are marked Failed and require
an explicit retry.

### Worker commands

Normal local startup includes the worker automatically:

```bash
python manage.py runlocal
```

To run only the worker:

```bash
python manage.py process_document_jobs
```

To process at most one available job and exit:

```bash
python manage.py process_document_jobs --once
```

The worker checks for available jobs every two seconds while idle.
The polling interval can be changed:

```bash
python manage.py process_document_jobs --poll-interval 3
```

If no worker is running, the website can still save queued jobs, but they
will not be processed until a worker is available.

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

To update a Ready, active document, choose Upload replacement and queue
processing for the new version. The original remains available until
replacement indexing succeeds.

Successful indexing activates the replacement and deactivates the original
together. A replaced original cannot be reactivated while a Ready replacement
references it.

To remove a document:

1. Open its detail page in the staff workspace.
2. Choose Delete document.
3. Review the title/version, tick the confirmation checkbox, and submit.

Deletion removes the database document, extracted text, chunks, embeddings,
and its processing-job record.

Existing conversations and citation snapshots remain; their chunk links become
null. Uploaded-file cleanup runs after the database transaction commits. If
file cleanup fails, the failure is logged and the document remains excluded
from retrieval.

Deleting a queued or processing document prevents its worker attempt from
publishing new indexing results.

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

## Chat rate limits

Only `POST /api/chat/` requests consume the chat sending allowance.

| Visitor | Limit | Identity |
| --- | --- | --- |
| Guest | 10 requests per minute | IP address |
| Registered user, including staff | 30 requests per minute | Account ID |

Guest browsers sharing an IP address share the guest allowance.
A registered account shares its allowance across browsers and devices.

For the current direct-server setup, DRF's `NUM_PROXIES` is set to `0`.
Guest throttling uses `REMOTE_ADDR` and ignores `X-Forwarded-For` when
identifying the client.

If the application is later deployed behind a reverse proxy, review the
proxy configuration and client-IP handling before changing `NUM_PROXIES`.

When the allowance is exhausted, the API returns HTTP 429 with a `detail`
message and a `Retry-After` header. Rejected requests do not reach the chat
service or trigger AI calls.

`GET /api/chat/` remains available for reading conversation history.
The browser displays the rate-limit message and preserves the typed question.

The allowance counts POST requests that reach throttling, including requests
that later fail validation or encounter an AI-service error.

The throttles use Django's cache. The default local-memory cache suits this
demonstration with one web-server process. Multiple web-server processes
require a shared cache for consistent counters.

DRF's built-in throttles can allow some additional requests under concurrent
load. They reduce excessive usage but do not enforce a strict spending cap.

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

Successful chat responses include `conversation_id` and `messages`.

| Status | Meaning |
| --- | --- |
| 400 | Invalid message or request data |
| 403 | Missing or invalid CSRF protection on a POST request |
| 409 | Selected conversation, conversation contents, or supporting evidence changed |
| 429 | Chat sending allowance exhausted |
| 503 | AI service or database temporarily unavailable |

Rate-limit responses include `detail` and a `Retry-After` header. Other chat
failures may return an `error` field, while serializer validation failures
identify the invalid field.

Chat requests use the browser session cookie. POST requests require a CSRF
token in the `X-CSRFToken` header, including for anonymous visitors.

Account, conversation-selection, document-processing, and staff operations use
Django pages/forms rather than separate REST APIs. Relevant routes include:

| Route | Method | Purpose |
| --- | --- | --- |
| `/accounts/signup/` | GET, POST | Customer registration |
| `/accounts/login/` | GET, POST | Customer/staff login |
| `/accounts/logout/` | POST | Logout |
| `/conversations/` | GET | Registered customer's conversation list |
| `/conversations/new/` | POST | Create and select an account-owned conversation |
| `/conversations/<id>/open/` | POST | Select an owned conversation |
| `/support/request/` | GET, POST | Prepare a support-ticket draft |
| `/support/confirm/` | GET, POST | Review and confirm ticket creation |
| `/support/tickets/` | GET | Customer's accessible tickets |
| `/support/tickets/<id>/` | GET | View an accessible customer ticket |
| `/staff/` | GET | Staff dashboard |
| `/staff/documents/<id>/process/` | POST | Queue document processing |
| `/staff/documents/<id>/chunks/` | POST | Legacy route that queues the unified processing workflow |
| `/staff/documents/<id>/index/` | POST | Legacy route that queues the unified processing workflow |
| `/staff/documents/<id>/delete/` | GET, POST | Staff deletion review and confirmation |
| `/staff/tickets/` | GET | Search and filter staff tickets |
| `/staff/tickets/<id>/` | GET, POST | Review a ticket and update its status |

State-changing forms include CSRF tokens. Conversation routes require login;
staff routes require staff membership.

Ticket request and confirmation pages accept GET and POST.
Customer ticket lists and details, and the staff ticket list, accept GET only.
The staff ticket detail accepts GET and POST.
Unsupported methods return HTTP 405 after applicable access checks.

Customer ticket lists and details use the same ownership-filtering service.
Registered customers see their account's tickets; guests see only tickets
belonging to their current session.

## Project structure

| Location | Responsibility |
| --- | --- |
| config/ | Settings, root URLs, WSGI |
| config/test_settings.py | Test configuration that prevents shared throttle counters between ordinary tests |
| support/models/ | Separate domain models |
| support/models/processing_job.py | Persistent document-job state, attempt tokens, counts, and leases |
| support/views/ | Pages and API request handling |
| support/api/ | Serializer, session/CSRF authentication, and chat throttles |
| support/services/ | Accounts, conversations, documents, background processing, retrieval, chat, tickets, and evaluation |
| support/services/processing_jobs.py | Queueing, claiming, lease checks, and job completion |
| support/services/document_worker.py | Execution of claimed document jobs |
| support/services/indexing.py | Embedding requests and validated atomic indexing publication |
| support/ai/ | Embeddings, bounded search agent, search tool, rewriting, structured answers, and prompt loader |
| support/ai/prompts/ | Markdown prompts for tool selection, question rewriting, and grounded answers |
| support/management/commands/ | Local startup, document worker, and retrieval evaluation commands |
| support/migrations/ | Database schema and vector migration |
| support/tests/ | Functional, permission, reliability, background-processing, throttling, retrieval, and scoring checks |
| templates/ | Customer and staff pages |
| static/ | Stylesheet and browser chat code |
| sample_data/ | Public fictional demonstration documents |
| evaluation/ | Development and evaluation datasets |
| evaluation/results/ | Timestamped retrieval evaluation reports |
| media/ | Runtime uploads, excluded from Git |

The prompt files are:

- `support/ai/prompts/tool_selection.md`
- `support/ai/prompts/rewrite_question.md`
- `support/ai/prompts/grounded_answer.md`

They are loaded by `support/ai/prompt_loader.py`.

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
`test_<DB_NAME>` if your application database name differs.

Then run:

```bash
python -m pip check
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --keepdb --settings=config.test_settings
```

The `--keepdb` option retains the prepared test database and vector extension.
Run the full suite on PostgreSQL, not SQLite.

Use `config.test_settings` for full-suite test runs. It uses a dummy cache so
unrelated tests do not share rate-limit counters. Dedicated throttle tests
override this with a working local-memory cache and verify the actual limits.

To run background-processing and document-workflow checks:

```bash
python manage.py test support.tests.test_background_documents support.tests.test_document_workflows --keepdb --settings=config.test_settings
```

To run the throttle and ticket-view checks:

```bash
python manage.py test support.tests.test_chat_throttling support.tests.test_ticket_view_rules --keepdb --settings=config.test_settings
```

To run retrieval filtering and evaluation-scoring checks:

```bash
python manage.py test support.tests.test_retrieval_threshold support.tests.test_retrieval_evaluation --keepdb --settings=config.test_settings
```

A separate running worker is not required for the automated test suite.
Worker tests invoke the processing services directly.

Do not use `config.test_settings` to run the website or local launcher.
Normal local startup is:

```bash
python manage.py runlocal
```

Tests cover document processing/replacement/deletion, citation preservation,
RAG failures, bounded agent tools, ticket draft validation, explicit
confirmation, duplicate prevention, concurrent ticket confirmation,
registration/login, guest-history transfer, account ownership, staff
permissions, conversation selection, and stale-tab requests.

Additional checks cover:

- Queueing document work without running embeddings in the web request.
- Repeated processing submissions creating only one job.
- Concurrent workers not claiming the same unexpired attempt.
- Embedding requests outside database transactions.
- Retrying failed embedding requests with existing chunks.
- Replacement activation only after successful indexing.
- Expired attempts being prevented from publishing after reclamation.
- Document or chunk changes invalidating pending embedding results.
- Guest and account chat limits.
- Shared IP/account allowances and allowance expiry.
- Forwarded-header handling for guest throttling.
- History access after throttling.
- Ticket HTTP method restrictions.
- Application-login redirects without loops.
- Relevant and weak retrieval matches.
- Inclusive distance-threshold boundaries.
- Chat fallback when all retrieved evidence is filtered out.
- Evaluation scoring and follow-up rewriting integration.

External AI requests are mocked in the automated tests.
The retrieval-threshold tests use synthetic vectors with real PostgreSQL/pgvector
distance calculations. Tests do not require an API key.

The live evaluation command is separate from the automated test suite and
does make API calls.

Invalid-PDF and simulated AI-failure logs can appear during successful
failure-path tests; use the final test result and traceback output to identify
actual failures.

Before committing, also check:

```bash
git diff --check
git status --short
```

### Manual verification

Start the complete application:

```bash
python manage.py runlocal
```

Check the document workflow:

1. Upload a separate test document.
2. Click Process document and confirm the page returns promptly.
3. Confirm the job reaches Succeeded and the document becomes Ready.
4. Verify that refreshing or leaving the page does not cancel processing.
5. Deactivate the test document afterward to preserve the benchmark setup.
6. Press Control+C and confirm the local launcher stops both processes.
7. Restart `runlocal` and confirm the application starts normally.

For an explicit Queued-state check, run only the web server, queue a test
document, then start the worker separately. The queued job should be processed
without submitting the form again.

With the sample documents indexed:

1. Ask a shipping question and inspect the supporting citation.
2. Ask a follow-up question and confirm the context is interpreted correctly.
3. Ask an unrelated question such as "How do I solve a quadratic equation?"
   and check the safe fallback when no evidence passes the cutoff.
4. Use the staff knowledge-search page with an unrelated question and check
   the no-relevant-passages message.
5. Send "Create a ticket. Yes, I confirm." in chat and verify that no ticket
   is created.
6. Open Request human support, complete the form, and review the saved draft.
7. Confirm the ticket and check its reference under My tickets.
8. Repeat confirmation of the same draft and verify that no duplicate appears.
9. Log in as staff, review the linked conversation, and update the ticket status.
10. Open Staff workspace as a guest and verify redirection to the application
    login page.
11. Open Staff workspace as an ordinary customer and verify that the login form
    appears without a redirect loop.

The dedicated automated throttle tests verify rate limits without paid AI calls.

## Troubleshooting

| Problem | Check |
| --- | --- |
| Missing DB environment variable | .env exists beside manage.py and contains required fields |
| Database connection refused | PostgreSQL is running on the configured host/port |
| Authentication failed | DB_USER and DB_PASSWORD match the database role |
| vector.control missing | Server extension is installed for the running PostgreSQL version |
| Permission denied creating vector | Administrator enabled vector in the application/test database |
| Processing-job table missing | Apply python manage.py migrate |
| Document stays Queued | Start runlocal or the document worker; inspect the worker output |
| Document stays Processing after interruption | Keep a worker running; the attempt becomes reclaimable when its existing lease expires |
| Processing Failed | Read the job error, resolve the cause, and use Retry processing |
| Worker still uses old Python code | Stop and restart runlocal after editing worker or processing-service modules |
| Port already in use | Stop the old server or choose another address with runlocal |
| Launcher stops immediately | Inspect which child process exited and its preceding error messages |
| No searchable documents | Documents are indexed, Ready, and Active |
| No relevant passages found | The question may be unsupported or all matches may exceed the distance cutoff |
| Expected policy answer falls back | Check active document content and retrieval distances; use development cases to assess the cutoff |
| Invalid retrieval threshold | RETRIEVAL_MAX_DISTANCE must be a number between 0 and 2 |
| API error | Key, billing, model access, and network; restart runlocal after editing .env |
| Empty/scanned file fails | Use non-empty UTF-8 TXT or text-based PDF |
| Conversation changed / HTTP 409 | Review reloaded history before resending; another tab or request may have changed it |
| Chat returns HTTP 429 | Wait for the Retry-After interval; guests sharing an IP share an allowance |
| Tests unexpectedly return HTTP 429 | Run the suite with --settings=config.test_settings |
| Application fails because SECRET_KEY is missing | Configure a stable SECRET_KEY; DEBUG defaults to False |
| Login-related CSRF error in an old tab | Refresh the full page after logging in or out |
| Customer cannot access staff workspace | Expected; use an account with staff membership |
| Cannot delete a document | Check for referencing replacement versions |
| Earlier chat not currently visible | Open My conversations and select it; guests need their original session |
| Evaluation rejects the knowledge base | Use exactly the four active, Ready, version-1 sample documents with the required titles and content |
| Evaluation reports errors | Inspect the saved per-case errors and resolve them before treating the run as complete |
| Evaluation corpus changed | Keep documents unchanged during the run and repeat it |

## Retrieval relevance filtering

Retrieval searches active, Ready documents with saved embeddings.
Only chunks with cosine distance less than or equal to
`RETRIEVAL_MAX_DISTANCE` are returned.

The default cutoff is `0.80`. It was selected using the development baseline:
the largest required first-match distance was approximately `0.651`, while
the smallest unsupported first-match distance was approximately `0.943`.
Their midpoint is approximately `0.797`, rounded to `0.80`.

Lower values make retrieval stricter. Cosine distance is not a probability
or an answer-confidence score.

When no passage passes the cutoff, the existing chat fallback is used
without grounded-answer generation. Retrieved passages still pass through
the existing answer-grounding and citation checks.

The cutoff is calibrated for the current demonstration documents and
embedding setup. Re-evaluate it when changing documents, chunking,
or embedding models.

Changing the cutoff does not require document reindexing.
Restart the application after changing its environment configuration.

## Evaluation and remaining work

A retrieval evaluation dataset and runner are included.

- Development set: 8 cases, comprising 4 answerable questions,
  2 unsupported questions, and 2 follow-ups.
- Evaluation set: 20 cases, comprising 12 answerable questions,
  4 unsupported questions, and 4 follow-ups.
- Labels identify acceptable source documents and required evidence phrases.
- Follow-up cases include reference standalone questions for manual inspection.

The dataset files are:

- `evaluation/retrieval_dev.json`
- `evaluation/retrieval_eval.json`

### Running the evaluation

The runner requires exactly four active, Ready, version-1 sample documents,
using the titles listed in `sample_data/README.md`. It checks their extracted
text against the files in `sample_data/policies/` before making AI calls.

Other Ready documents must be inactive for this benchmark.
Do not upload duplicate sample documents or use the version-2 shipping
replacement for these version-1 labels.

Wait for sample-document processing to finish before starting evaluation.
Do not process replacements or change document availability during a run.

Run the development evaluation with the current cutoff:

```bash
python manage.py evaluate_retrieval --split dev --label threshold_0_8
```

After reviewing development results, evaluate the fixed configuration:

```bash
python manage.py evaluate_retrieval --split eval --label threshold_0_8
```

These commands use the configured embedding API. Follow-up cases also use
the chat model to rewrite questions.

The evaluation runs directly against the indexed database. The web server
and document worker do not need to be running once the documents are Ready.

The `--label` argument names the run; it does not change retrieval behavior.
The actual cutoff comes from `RETRIEVAL_MAX_DISTANCE`.

Each run saves a new timestamped JSON report under `evaluation/results/`.
Reports contain:

- Original questions and expected evidence labels.
- Actual standalone questions used for retrieval.
- Retrieved passages, document versions, and cosine distances.
- Evidence coverage at the top 1, 3, and 5 matches.
- Unsupported-query retrieval counts.
- Rewriting, retrieval, and combined timings.
- Per-case errors.
- The configured retrieval cutoff.
- Model names and fingerprints of the dataset, knowledge base, embeddings,
  retrieval code, and rewriting prompt.

Knowledge-base changes during a run invalidate that report.
Resolve any recorded errors before using a report as a complete result.

Use development cases for tuning. Keep evaluation labels fixed and use the
evaluation set to assess changes after development decisions are made.

### Recorded retrieval results

The following runs were recorded on 20 October 2026.
The original baselines were collected before distance filtering was introduced.
The filtered runs used the fixed cutoff of `0.80`.

| Run | Cases completed | Required evidence in first match | Unsupported questions returning passages | Technical errors |
| --- | --- | --- | --- | --- |
| Development baseline | 8/8 | 6/6 | 2/2 | 0 |
| Development with cutoff 0.80 | 8/8 | 6/6 | 0/2 | 0 |
| Evaluation baseline | 20/20 | 16/16 | 4/4 | 0 |
| Evaluation with cutoff 0.80 | 20/20 | 16/16 | 0/4 | 0 |

The filtered evaluation retained all required first-match evidence and
returned no passages for the four unsupported questions.

The dataset and knowledge-base fingerprints matched between the corresponding
baseline and filtered runs. The knowledge base remained unchanged during
each run.

These reports were recorded before the background-processing change.

The report files are:

- `evaluation/results/dev_baseline_20261020T133429500504Z.json`
- `evaluation/results/eval_baseline_20261020T133513590862Z.json`
- `evaluation/results/dev_threshold_0_8_20261020T134848856794Z.json`
- `evaluation/results/eval_threshold_0_8_20261020T135146093948Z.json`

Keep the original baseline reports unchanged.
Naming a new run `baseline` does not disable the current filter.

### Evaluation limitations

This is a small retrieval benchmark over four short demonstration documents.
Evidence matching uses document titles and normalized text phrases.
A high top-5 score alone is not strong evidence of retrieval quality because
the knowledge base contains only four documents.

The recorded results demonstrate retrieval behavior on these cases.
They do not establish overall chatbot accuracy or general performance across
other stores and larger knowledge bases.

The unsupported questions are clearly outside the store's domain.
Harder unsupported questions that use store-related vocabulary are needed
to assess filtering more thoroughly.

Follow-up reference questions are retained for inspection. Retrieval uses
the actual model-generated rewrite rather than the reference wording.

The runner evaluates direct vector retrieval and follow-up rewriting.
It does not evaluate agent tool selection, generated-answer correctness,
groundedness, ticket workflows, or full end-to-end chat latency.
It does not create customer conversations, messages, or tickets.

Reported timings are observations from individual runs and are not sufficient
to establish a reliable speed improvement or regression.
They do not measure background document-processing performance.

### Remaining work

The broader proposed evaluation includes 25 answerable questions,
10 unsupported questions, 10 escalation workflows, and 5 multi-turn
conversations, with separate development examples.

The broader performance report will cover retrieval and answer quality,
groundedness, ticket success, latency, local backend memory, and a no-RAG
comparison. That evaluation, its performance report, and the final
presentation remain separate deliverables.

Possible later improvements include:

- Adding an overall chat-request time budget.
- Expanding development coverage to include harder unsupported questions
  that use store-related vocabulary.
- Recalibrating retrieval filtering as the knowledge base grows.
- Adding pagination or bounded loading for long conversation histories.

Document processing now runs through a background worker.
Long conversation histories are still loaded in full.

The current scope is one demonstration store with English text chat.
The application does not yet include password recovery, email verification,
or production deployment configuration.

A production deployment must manage the web application and document worker
as persistent services. The local runlocal launcher is for development.