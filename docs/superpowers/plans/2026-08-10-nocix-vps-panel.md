# NOCIX VPS Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Debian-ready FastAPI + React/Vite control panel that manages multiple NOCIX PayPal checkout workers with SQLite persistence, API-key authentication, Telegram notifications, and internal Selenium Firefox.

**Architecture:** Keep the existing `nocix_fucker.Client` as the browser automation boundary and move orchestration into a FastAPI application. The API owns SQLite-backed task state and starts one asyncio/thread worker per task; each worker creates an isolated Selenium session, monitors the NOCIX out-of-stock page, opens the cart when available, validates price, selects the NOCIX-saved PayPal method, submits the order, records history, and notifies Telegram. The React frontend is built separately and served by FastAPI from static assets in production.

**Tech Stack:** Python 3.10+, FastAPI, Uvicorn, SQLAlchemy 2, SQLite, Fernet-compatible `cryptography`, Pydantic, Selenium 4, React 18, Vite, TypeScript, TanStack Query, Tailwind CSS, Docker Compose, Selenium standalone Firefox.

---

## File Map

### Backend files

- Create: `backend/app/main.py` - FastAPI startup, static frontend serving, router registration, and shutdown.
- Create: `backend/app/config.py` - environment configuration and required-secret validation.
- Create: `backend/app/db.py` - SQLite engine, session factory, and table initialization.
- Create: `backend/app/models.py` - task, order, log, and settings tables.
- Create: `backend/app/schemas.py` - request/response models; PayPal-only validation.
- Create: `backend/app/security.py` - API-key middleware and Fernet encryption helpers.
- Create: `backend/app/redaction.py` - log and response redaction.
- Create: `backend/app/repositories.py` - database CRUD and atomic task state updates.
- Create: `backend/app/manager.py` - task lifecycle and one-worker-per-task coordination.
- Create: `backend/app/worker.py` - monitor/check/checkout workflow adapter.
- Create: `backend/app/telegram.py` - Telegram Bot API notifications.
- Create: `backend/app/routers/tasks.py` - task CRUD and lifecycle endpoints.
- Create: `backend/app/routers/stats.py` - dashboard counters and health data.
- Create: `backend/app/routers/orders.py` - order history endpoints.
- Create: `backend/app/routers/logs.py` - filtered log endpoints.
- Create: `backend/app/routers/settings.py` - Telegram and runtime settings endpoints.
- Create: `backend/requirements.txt` - pinned runtime dependencies.
- Create: `backend/Dockerfile` - API image with backend and built frontend assets.

### Frontend files

- Create: `frontend/package.json` - React/Vite dependencies and build scripts.
- Create: `frontend/vite.config.ts` - development proxy to FastAPI.
- Create: `frontend/src/main.tsx` - React entrypoint and query provider.
- Create: `frontend/src/lib/api.ts` - API client with `X-API-Key` header.
- Create: `frontend/src/lib/types.ts` - API types matching backend schemas.
- Create: `frontend/src/hooks/use-tasks.ts` - task queries and lifecycle mutations.
- Create: `frontend/src/hooks/use-dashboard.ts` - stats polling.
- Create: `frontend/src/hooks/use-logs.ts` - log query and clear mutation.
- Create: `frontend/src/hooks/use-orders.ts` - order history query.
- Create: `frontend/src/components/AuthGate.tsx` - API-key gate backed by session storage.
- Create: `frontend/src/components/Layout.tsx` - sidebar, top bar, and route outlet.
- Create: `frontend/src/components/StatusDot.tsx` - status indicator.
- Create: `frontend/src/components/TaskCard.tsx` - task status and controls.
- Create: `frontend/src/components/TaskForm.tsx` - PayPal-only task form with no card fields.
- Create: `frontend/src/pages/Dashboard.tsx` - dashboard metrics and recent errors.
- Create: `frontend/src/pages/Tasks.tsx` - multi-task list, add/edit dialog, and history.
- Create: `frontend/src/pages/Orders.tsx` - order results table.
- Create: `frontend/src/pages/Logs.tsx` - searchable logs.
- Create: `frontend/src/pages/Settings.tsx` - Telegram and service status.
- Create: `frontend/src/styles.css` - visual system inspired by `ovh-main`.

### Deployment and tests

- Modify: `pyproject.toml` - add backend runtime dependencies and test tooling.
- Modify: `docker-compose.yml` - replace the one-shot client with the FastAPI API service; keep Selenium internal-only.
- Modify: `.env.example` - add API key, encryption key, and worker defaults; remove Telegram credential variables and credit-card variables.
- Modify: `README.md` - Debian VPS deployment and panel usage.
- Create: `tests/test_api_config.py` - schema and authentication tests.
- Create: `tests/test_manager.py` - task lifecycle and duplicate-worker tests.
- Create: `tests/test_worker.py` - fake browser workflow tests.
- Create: `tests/test_redaction.py` - secret redaction tests.
- Create: `backend/static/.gitkeep` - target directory for the built frontend.

The current workspace is not a Git repository, so implementation checkpoints use test/build commands and file inspection instead of `git commit` commands.

## Task 1: Backend Skeleton and PayPal-Only Configuration

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/app/schemas.py`
- Create: `backend/app/security.py`
- Create: `tests/test_api_config.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add failing validation tests**

```python
def test_task_requires_existing_nocix_account_and_paypal():
    task = TaskCreate(
        goods_id="418",
        target_price=59,
        wait_interval=5,
        email="buyer@example.com",
        password="secret",
        new_customer=False,
        payment_method="paypal",
    )
    assert task.payment_method == "paypal"
    assert task.new_customer is False


def test_task_rejects_credit_card_fields():
    with pytest.raises(ValidationError):
        TaskCreate(
            goods_id="418",
            target_price=59,
            wait_interval=5,
            email="buyer@example.com",
            password="secret",
            new_customer=False,
            payment_method="paypal",
            cc_num="4111111111111111",
        )
```

- [ ] **Step 2: Run the focused tests and verify the expected missing-module failure**

Run: `python -m pytest tests/test_api_config.py -q`

Expected: FAIL because `backend.app.schemas` does not exist yet.

- [ ] **Step 3: Implement configuration and schemas**

`TaskCreate` must accept `goods_id`, optional URL overrides, positive `target_price`,
`wait_interval >= 2`, `operating_system` in `debian|ubuntu`, `email`, `password`,
`new_customer=False`, and `payment_method="paypal"`. Use Pydantic `extra="forbid"`
so credit-card fields and unknown secrets are rejected. `TaskResponse` must expose
`password_configured: bool`, never the password itself.

`Settings` must require non-empty `API_KEY` and `DATA_ENCRYPTION_KEY` in production,
with `BROWSER_DSN` defaulting to `http://browser:4444/wd/hub` and `HOST` defaulting
to `0.0.0.0`. The provided production Docker Compose deployment fixes the API port
at `8000`; `PORT` is not a user-configurable deployment setting.

Implement `require_api_key()` as a FastAPI dependency that compares the
`X-API-Key` header using `secrets.compare_digest`. Leave only `/api/health` public.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -m pytest tests/test_api_config.py -q`

Expected: all validation and API-key tests pass.

## Task 2: SQLite Persistence and Secret Encryption

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/app/repositories.py`
- Create: `backend/app/redaction.py`
- Create: `tests/test_redaction.py`

- [ ] **Step 1: Add failing persistence and redaction tests**

Test that a task can be inserted and read back with `password_configured=True`,
but the returned model has no plaintext password. Test that log messages containing
`password=`, `cc_num=`, `cc_ccv=`, `token=`, or `cookie=` are replaced before storage.

- [ ] **Step 2: Run the tests and verify they fail because persistence is absent**

Run: `python -m pytest tests/test_redaction.py -q`

Expected: FAIL with import or missing repository errors.

- [ ] **Step 3: Implement tables and repository methods**

Create SQLAlchemy tables for `tasks`, `orders`, `logs`, and `settings`. Store the
encrypted existing-account password in `tasks.password_ciphertext`. Add repository
methods:

```python
create_task(task: TaskCreate) -> TaskRecord
get_task(task_id: str) -> TaskRecord | None
list_tasks() -> list[TaskRecord]
update_task(task_id: str, patch: TaskUpdate) -> TaskRecord
delete_task(task_id: str) -> None
set_task_status(task_id: str, status: str, error: str | None = None) -> TaskRecord
create_order(task_id: str, status: str, observed_price: str | None, error: str | None)
list_orders() -> list[OrderRecord]
append_log(level: str, task_id: str | None, message: str) -> None
list_logs(task_id: str | None, level: str | None, limit: int) -> list[LogRecord]
```

Use Fernet encryption with the configured key. Encrypt before insertion and decrypt
only inside `worker.py`; never put decrypted credentials in an API response.

- [ ] **Step 4: Run tests and inspect stored values**

Run: `python -m pytest tests/test_redaction.py -q`

Expected: PASS; the SQLite row contains ciphertext and redacted log text.

## Task 3: Worker Adapter for Existing Selenium Checkout

**Files:**
- Modify: `nocix_fucker/types.py`
- Modify: `nocix_fucker/client.py`
- Create: `backend/app/worker.py`
- Create: `tests/test_worker.py`

- [ ] **Step 1: Define a fake browser contract and write failing worker tests**

The fake client must record calls to `check_stock`, `open_cart`,
`select_operating_system`, `match_price`, `fill_in_customer_info`,
`fill_in_payment_info`, `click_next_step_button`, and `submit_order`.

Cover these cases:

```python
def test_worker_waits_when_out_of_stock(): ...
def test_worker_starts_checkout_when_stock_returns(): ...
def test_worker_stops_on_price_mismatch_without_filling_credentials(): ...
def test_worker_uses_existing_customer_paypal_flow(): ...
def test_worker_records_submit_error(): ...
```

- [ ] **Step 2: Run worker tests and verify the expected missing-worker failure**

Run: `python -m pytest tests/test_worker.py -q`

Expected: FAIL because `backend.app.worker` does not exist.

- [ ] **Step 3: Adapt the existing client for PayPal**

Add `PaymentMethod.PAYPAL = "paypal"` and remove credit-card usage from the
panel-facing flow. In `Client.fill_in_payment_info`, select the NOCIX page option
whose value is `paypal`, then accept terms. Do not navigate to PayPal or handle
PayPal credentials. Keep Bitcoin support only if the CLI compatibility path still
needs it, but reject Bitcoin in the panel schema.

The worker must:

1. Set task status to `checking`.
2. Call `check_stock(goods_id)` at `wait_interval` until stock is available or a
   stop/pause event is set.
3. Set status to `ordering` and call `open_cart(goods_id)`.
4. Select the configured OS, falling back from Debian to Ubuntu only when needed.
5. Stop and record an order failure on price mismatch.
6. Call existing-customer `fill_in_customer_info` with the decrypted NOCIX password.
7. Call `fill_in_payment_info(payment_method=PAYPAL, ...)` without card fields.
8. Submit the order once, record success or alert text, and send Telegram events.
9. Always quit the Selenium session in a `finally` block.

Use an injectable `client_factory` and `sleep` function so tests never start a
browser or wait in real time.

- [ ] **Step 4: Run worker tests and verify they pass**

Run: `python -m pytest tests/test_worker.py -q`

Expected: PASS with no network calls and no plaintext secret in test logs.

## Task 4: Task Manager, Recovery, and API Routers

**Files:**
- Create: `backend/app/manager.py`
- Create: `backend/app/routers/tasks.py`
- Create: `backend/app/routers/stats.py`
- Create: `backend/app/routers/orders.py`
- Create: `backend/app/routers/logs.py`
- Create: `backend/app/routers/settings.py`
- Create: `backend/app/main.py`
- Modify: `tests/test_api_config.py`
- Create: `tests/test_manager.py`

- [ ] **Step 1: Write failing manager and API lifecycle tests**

Cover:

```python
def test_starting_same_task_twice_creates_one_worker(): ...
def test_pause_sets_event_and_worker_does_not_check_again(): ...
def test_successful_task_is_not_restarted_during_recovery(): ...
def test_api_requires_x_api_key_for_task_routes(): ...
def test_start_pause_resume_stop_endpoints_update_status(): ...
```

- [ ] **Step 2: Run tests and verify failure before implementation**

Run: `python -m pytest tests/test_manager.py tests/test_api_config.py -q`

Expected: FAIL because `TaskManager` and FastAPI routers are not implemented.

- [ ] **Step 3: Implement TaskManager**

Keep `self._workers: dict[str, WorkerHandle]` guarded by an asyncio lock. Each
`WorkerHandle` contains a task object, a stop event, and a pause event. `start()`
must return the existing handle when already running. `pause()` and `resume()`
must update SQLite status before changing events. `stop()` must set the stop event,
await worker completion with a bounded timeout, and set `stopped`.

On application startup, load persisted tasks. Convert persisted `running`,
`checking`, and `ordering` states to `stopped` before exposing the API, then start
only tasks explicitly marked `running_before_shutdown` if that field is added to
the model. Never automatically retry `success` or `failed` tasks.

- [ ] **Step 4: Implement API routes**

Use the exact endpoints from the specification. Return HTTP 404 for unknown task
IDs, HTTP 409 for conflicting lifecycle actions, and HTTP 422 for invalid PayPal
configuration. `GET /api/tasks` returns masked task records. `POST /api/tasks/{id}/check`
starts one immediate check only when no worker owns the task.

- [ ] **Step 5: Run API and manager tests**

Run: `python -m pytest tests/test_manager.py tests/test_api_config.py -q`

Expected: PASS; duplicate workers are prevented and every protected route rejects
missing or invalid API keys.

## Task 5: Telegram Notifications and Logging

**Files:**
- Create: `backend/app/telegram.py`
- Modify: `backend/app/worker.py`
- Modify: `backend/app/routers/settings.py`
- Create: `tests/test_telegram.py`

- [ ] **Step 1: Write failing notification tests**

Test that a stock recovery message contains task ID and goods ID but not password,
PayPal token, cookies, or payment data. Test that a failed Telegram request is
logged without stopping the checkout worker.

- [ ] **Step 2: Run the tests and verify missing notifier failure**

Run: `python -m pytest tests/test_telegram.py -q`

Expected: FAIL because `TelegramNotifier` is not implemented.

- [ ] **Step 3: Implement TelegramNotifier**

Use `httpx.AsyncClient` against Telegram `sendMessage`, with a timeout of 10
seconds. Read encrypted token/chat ID from settings. Notification errors are
non-fatal and append a redacted warning log. Add `POST /api/telegram/test` and
`GET /api/settings`; settings responses only report whether each value is
configured.

- [ ] **Step 4: Run notification tests**

Run: `python -m pytest tests/test_telegram.py -q`

Expected: PASS with HTTP calls mocked and no external Telegram request.

## Task 6: React/Vite Panel Inspired by `ovh-main`

**Files:**
- Create: all files listed under `frontend/` in the file map.
- Create: `frontend/src/__tests__/TaskForm.test.tsx`
- Create: `frontend/src/__tests__/AuthGate.test.tsx`

- [ ] **Step 1: Scaffold frontend and write failing UI tests**

The task form test must assert that it renders `Payment method: PayPal`, requires
existing-account email/password, and has no input whose name or label contains
`card`, `cvv`, `cc_num`, or `credit`. The AuthGate test must assert that no task
query runs before a valid API key is stored.

- [ ] **Step 2: Run frontend tests/build and verify initial failure**

Run: `cd frontend; npm install; npm test -- --run`

Expected: FAIL because the components and test script are not implemented.

- [ ] **Step 3: Implement the panel shell**

Use a compact dark control-console visual language based on `ovh-main`: fixed
sidebar on desktop, collapsible mobile navigation, status dots, cards, tabs, and
toast feedback. Routes are `/`, `/tasks`, `/orders`, `/logs`, and `/settings`.
Store only the API key in `sessionStorage`. The API client adds `X-API-Key` to
every request and clears it on HTTP 401.

- [ ] **Step 4: Implement task management UI**

`Tasks.tsx` must support multiple cards, add/edit dialog, expandable history, and
start/pause/resume/stop/check/delete actions. `TaskForm.tsx` must submit only
PayPal-compatible fields and display a clear warning that automatic submission
will use the PayPal payment method already saved in NOCIX.

- [ ] **Step 5: Implement dashboard, orders, logs, and settings pages**

Dashboard polls `/api/stats` every 15 seconds. Logs poll every 5 seconds while
the page is visible, cap the rendered list at 500 entries, and expose task/level
filters. Orders show success/failure and observed price. Settings show Telegram,
browser, and credit-card status without exposing any secret or card field; the
credit-card status must always read `not used by panel` for this PayPal-only build.

- [ ] **Step 6: Run frontend tests and build**

Run: `cd frontend; npm test -- --run; npm run build`

Expected: all UI tests pass and Vite outputs `dist/` without TypeScript errors.

## Task 7: Serve the Built Frontend and Add Docker Deployment

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/static/.gitkeep`
- Create: `frontend/Dockerfile.build`
- Modify: `backend/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Add an integration test for static serving and health**

Use FastAPI `TestClient` to assert `GET /api/health` returns `200`, protected task
routes return `401` without `X-API-Key`, and `/` serves `index.html` when the
frontend build exists.

- [ ] **Step 2: Implement static serving and lifespan**

Mount `backend/static/assets` and serve the SPA fallback from `backend/static`.
Create the SQLite tables, `TaskManager`, and Telegram notifier in FastAPI lifespan;
call `manager.shutdown()` before application exit.

- [ ] **Step 3: Implement the production image build**

Use a multi-stage Dockerfile: Node 20 builds `frontend/dist`, Python 3.10 installs
`backend/requirements.txt`, copies the backend and frontend build to
`/app/backend/static`, and runs:

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 4: Replace Compose services**

Define `api` and `browser`. Publish only `8000:8000`; do not publish `4444` or
`5900`. Put both services on the default internal network. Add a health check for
`/api/health`, `depends_on` browser health, `restart: unless-stopped`, and a
volume for `/app/data`.

- [ ] **Step 5: Update environment template and Debian instructions**

`.env.example` must contain:

```env
API_KEY=replace-with-a-long-random-value
DATA_ENCRYPTION_KEY=replace-with-a-fernet-key
BROWSER_DSN=http://browser:4444/wd/hub
HOST=0.0.0.0
LOG_LEVEL=INFO
```

Configure Telegram credentials through the authenticated panel; store them
encrypted in SQLite rather than in `.env`. Remove `CC_NUM`, `CC_EXP_MONTH`,
`CC_EXP_YEAR`, and `CC_CCV`. Document Debian commands for Docker installation,
`.env` permissions, firewall ports `22` and `8000`, `docker compose up -d --build`,
health checking, and log inspection.

- [ ] **Step 6: Validate Compose and container build**

Run: `docker compose config`

Expected: valid Compose output with no published Selenium ports.

Run: `docker compose build`

Expected: API image builds successfully and includes the frontend `dist/` files.

## Task 8: Full Verification and Operational Hardening

**Files:**
- Modify: `README.md`
- Create: `tests/test_end_to_end_contract.py`

- [ ] **Step 1: Add contract tests for the confirmed workflow**

Assert that a valid task has `new_customer=False`, `payment_method="paypal"`,
`auto_submit=True`, and no credit-card keys. Assert the worker call order is:

```text
check_stock -> open_cart -> select_operating_system -> match_price
-> fill_in_customer_info -> fill_in_payment_info(paypal)
-> click_next_step_button -> submit_order
```

- [ ] **Step 2: Run the complete Python suite**

Run: `python -m pytest -q`

Expected: all Python tests pass without network, Selenium, Telegram, or NOCIX
checkout side effects.

- [ ] **Step 3: Run frontend checks**

Run: `cd frontend; npm test -- --run; npm run build`

Expected: tests pass and production assets build cleanly.

- [ ] **Step 4: Run deployment checks**

Run: `docker compose config; docker compose build`

Expected: Compose validation and image build complete successfully; only API port
8000 is published.

- [ ] **Step 5: Perform a safe VPS smoke test**

Start the stack with PayPal task configuration but leave the task `stopped`:

```text
docker compose up -d
curl http://127.0.0.1:8000/api/health
curl -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/api/tasks
```

Expected: health is `ok`, the task list is authenticated, and no Selenium worker
starts. Only after reviewing the panel configuration should the user manually
start a task; verification must not submit a real order.

## Acceptance Criteria

- The panel is reachable at `http://VPS_IP:8000` on Debian.
- API routes reject requests without the configured API key.
- Multiple tasks can run without sharing Selenium sessions.
- The task form offers PayPal only and has no credit-card fields.
- Existing NOCIX account credentials are encrypted at rest and never returned.
- Stock recovery triggers the existing-customer PayPal checkout path.
- A price mismatch stops before customer/payment form submission.
- Success and failure create order history records and Telegram notifications.
- VPS restart does not duplicate workers or retry completed orders.
- Selenium WebDriver and VNC ports are not published.
- Python tests, frontend tests/build, Compose validation, and Docker build pass.
