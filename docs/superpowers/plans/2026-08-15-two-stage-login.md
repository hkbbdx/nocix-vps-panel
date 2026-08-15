# NOCIX Two-Stage Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add NOCIX two-stage existing-account login with manual email-code entry from the panel while preserving the current Selenium session and automatic PayPal checkout.

**Architecture:** The checkout worker keeps ownership of one Selenium session and exposes a thread-safe in-memory verification state. After the first and second credential submissions, it detects the email-code page, persists only the public task state `waiting_for_email_code`, and waits on an in-memory event. Protected API endpoints submit or cancel a code without storing it. The frontend renders a bilingual code-entry control on the task card; all code and errors are cleared from memory after each attempt and never enter SQLite, logs, Telegram, or browser storage.

**Tech Stack:** Python 3.10+, Selenium 4, FastAPI, SQLAlchemy/SQLite, Pydantic, React/Vite/TypeScript, TanStack Query, existing Fernet task-password storage.

---

## File Map

- Modify: `nocix_fucker/client.py` - two login submissions, page detection, code field fill and login continuation.
- Modify: `backend/app/worker.py` - verification state machine, in-memory code event, timeout/cancel cleanup, no-order-failure semantics.
- Modify: `backend/app/manager.py` - expose code submission/state/cancel and guard task ownership.
- Modify: `backend/app/repositories.py` - persist public login state/error only; never code.
- Modify: `backend/app/models.py` - add public login-state fields if the current task status column is insufficient.
- Modify: `backend/app/db.py` - additive migration for any new public login fields.
- Modify: `backend/app/schemas.py` - code request/response validation with no secret fields.
- Create: `backend/app/routers/login.py` - authenticated login-state, code-submit and cancel endpoints.
- Modify: `backend/app/main.py` - include login router and wire manager state.
- Modify: `frontend/src/lib/types.ts` - login state and API response types.
- Modify: `frontend/src/lib/api.ts` - login-state, code-submit and cancel calls.
- Modify: `frontend/src/hooks/use-tasks.ts` - login-state polling/mutations and cache invalidation.
- Modify: `frontend/src/components/TaskCard.tsx` - waiting-code panel and action locking.
- Create: `frontend/src/components/EmailCodeDialog.tsx` - accessible bilingual code form.
- Modify: `frontend/src/i18n.tsx` - Chinese/English login-state and code-entry translations.
- Modify: `frontend/src/styles.css` - waiting-code status and dialog styling.
- Create/modify: `tests/test_login_flow.py` - worker/client/API security tests.
- Create/modify: `frontend/src/__tests__/EmailCodeDialog.test.tsx` - UI and storage tests.
- Modify: `README.md` - document two-stage login and manual code entry.

## Task 1: Client Login State and Page Detection

**Files:**
- Modify: `nocix_fucker/client.py`
- Create: `tests/test_login_flow.py`

- [ ] **Step 1: Write failing client tests**

Cover these fake-driver behaviors:

```python
def test_existing_login_submits_credentials_twice(): ...
def test_second_login_detects_email_code_page(): ...
def test_login_without_code_page_continues(): ...
def test_email_code_fills_code_and_submits(): ...
def test_code_error_does_not_log_or_return_code(): ...
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m pytest tests/test_login_flow.py -q`

Expected: FAIL because the two-stage client methods do not exist.

- [ ] **Step 3: Implement explicit client methods**

Add methods with injectable selectors/fake-driver coverage:

```python
login_existing_customer(email: str, password: str) -> bool
is_email_code_required() -> bool
submit_email_code(code: str) -> bool
```

`login_existing_customer` must submit the same email/password form twice, using
the page’s current visible form after the first submission. It must detect the
code page by visible code input and stable page markers, not by blind timing.
`submit_email_code` must clear the input after a failed attempt where supported,
return only success/failure, and never include the code in exception strings or
Loguru output. Existing direct form-filling helpers remain reusable.

- [ ] **Step 4: Run client tests**

Run: `python -m pytest tests/test_login_flow.py -q`

Expected: PASS for both-code-required and no-code page paths.

## Task 2: In-Memory Verification Coordinator

**Files:**
- Modify: `backend/app/worker.py`
- Modify: `backend/app/manager.py`
- Modify: `backend/app/repositories.py`
- Modify: `backend/app/models.py` and `backend/app/db.py` only if required
- Extend: `tests/test_login_flow.py`

- [ ] **Step 1: Write failing worker tests**

```python
def test_worker_enters_waiting_for_email_code_and_keeps_client(): ...
def test_code_submission_wakes_same_worker_session(): ...
def test_wrong_code_stays_waiting_and_clears_code(): ...
def test_cancel_code_wait_fails_without_order_record(): ...
def test_code_timeout_clears_memory_and_fails_without_order_record(): ...
def test_code_never_reaches_repository_logs_or_telegram(): ...
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_login_flow.py -q`

Expected: FAIL because worker verification coordination is absent.

- [ ] **Step 3: Implement thread-safe in-memory state**

Each active worker gets a `VerificationState` containing a lock, `threading.Event`,
pending flag, deadline, last safe error, and a private code slot. The manager keeps
the state only while the worker is owned. Public repository/task state is limited
to `waiting_for_email_code` and a redacted `last_error`.

Implement:

```python
get_login_state(task_id: str) -> LoginState
submit_email_code(task_id: str, code: str) -> LoginActionResult
cancel_login(task_id: str) -> LoginActionResult
```

Validate code format as 4-12 ASCII digits, then immediately move it into the
worker’s private slot and clear the request object. The worker consumes and clears
the slot before calling Selenium. A second submission replaces only a failed
attempt’s cleared slot. Stop, pause, timeout, worker exception, success, and
cleanup clear the event, slot, and state object.

Do not use SQLite, `sessionStorage`, `localStorage`, logs, Telegram, or task error
strings to transport the code. A missing in-memory worker returns 409 rather than
creating a new browser session.

- [ ] **Step 4: Run worker tests**

Run: `python -m pytest tests/test_login_flow.py -q`

Expected: PASS with the same fake client instance before and after code submission.

## Task 3: Authenticated Login API

**Files:**
- Create: `backend/app/routers/login.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`
- Extend: `tests/test_login_flow.py`

- [ ] **Step 1: Write failing API tests**

Cover:

```python
def test_login_state_requires_api_key(): ...
def test_login_state_returns_public_waiting_state(): ...
def test_email_code_rejects_non_digits_and_never_echoes_code(): ...
def test_email_code_returns_409_when_task_is_not_waiting(): ...
def test_cancel_login_is_idempotent_for_owned_waiting_task(): ...
```

- [ ] **Step 2: Run API tests and verify failure**

Run: `python -m pytest tests/test_login_flow.py -q`

Expected: FAIL because the login router and schemas are absent.

- [ ] **Step 3: Implement protected endpoints**

Add:

```text
GET  /api/tasks/{id}/login-state
POST /api/tasks/{id}/email-code
POST /api/tasks/{id}/login-cancel
```

All routes require `X-API-Key`. Return only task ID, public state, attempts,
remaining seconds, and safe error text. Never return `code`, password, credentials,
Selenium URLs, cookies, or raw exception data.

Use 404 for unknown tasks, 409 when no worker owns the verification state or task
is not waiting, and 422 for malformed code input. Map worker/client failures to
safe status responses without changing the task’s order-attempt semantics.

- [ ] **Step 4: Run API tests**

Run: `python -m pytest tests/test_login_flow.py -q`

Expected: PASS with auth and redaction assertions.

## Task 4: Bilingual Frontend Code Entry

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/hooks/use-tasks.ts`
- Create: `frontend/src/components/EmailCodeDialog.tsx`
- Modify: `frontend/src/components/TaskCard.tsx`
- Modify: `frontend/src/i18n.tsx`
- Modify: `frontend/src/styles.css`
- Create/modify: `frontend/src/__tests__/EmailCodeDialog.test.tsx`

- [ ] **Step 1: Write failing frontend tests**

Cover:

```tsx
it("shows a bilingual waiting-code form without persisting the code", ...)
it("submits digits and clears the input immediately", ...)
it("shows safe server errors without rendering the code", ...)
it("disables normal task actions while waiting for code", ...)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `npm --prefix frontend test -- --run src/__tests__/EmailCodeDialog.test.tsx`

Expected: FAIL because the dialog and API hooks are absent.

- [ ] **Step 3: Implement the dialog and task-card state**

Use `type="password"`, `inputMode="numeric"`, `autoComplete="one-time-code"`,
`maxLength=12`, `aria-label`, and `role="alert"` for safe errors. Store the code
only in component memory. Clear it on submit, success, failure, unmount, and cancel.
While waiting, hide/disable start, pause, resume, edit, delete, check, and normal
checkout actions except `Submit code` and `Cancel login`.

Add Chinese and English translations for all labels, status names, countdown,
validation, accepted, rejected, cancelled, and timeout messages. Preserve raw
backend error text only when it is already safe and never render the submitted code.

- [ ] **Step 4: Run frontend tests and build**

Run: `npm --prefix frontend test -- --run; npm --prefix frontend run build`

Expected: focused and existing frontend tests pass, production build succeeds.

## Task 5: Integration, Documentation, and Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-15-two-stage-login-design.md` only if implementation constraints require clarification.
- Extend: `tests/test_login_flow.py` and existing worker/API tests.

- [ ] **Step 1: Add end-to-end contract tests with fakes**

Assert the call order:

```text
open_cart -> first login(email,password) -> second login(email,password)
-> waiting_for_email_code -> API code -> submit_email_code
-> select OS -> match price -> customer/payment -> submit order
```

Assert the same fake client object is used throughout and no code/password appears
in repository rows, log records, Telegram event payloads, API JSON, or frontend
storage.

- [ ] **Step 2: Run complete verification**

Run:

```text
python -m pytest -q
python -m compileall -q backend nocix_fucker tests
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Expected: all Python/frontend tests pass and builds complete without TypeScript or
compile errors. No test may contact NOCIX, Telegram, an email provider, or submit a
real order.

- [ ] **Step 3: Document operation**

Add README instructions:

1. Start the monitor.
2. Wait until the task shows `waiting_for_email_code`.
3. Retrieve the code from the configured email inbox.
4. Enter the code in the task card.
5. Confirm the task returns to ordering.

Document that a VPS restart clears in-memory verification sessions; the user must
restart the task and complete login again. Do not suggest storing the code in `.env`
or SQLite.

- [ ] **Step 4: Review status and deployment impact**

Confirm migrations are additive, Docker ports remain unchanged, proxy/PayPal/
Telegram behavior remains intact, and only the authenticated panel can submit a
verification code.
