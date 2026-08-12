# NOCIX VPS Panel Design

## Goal

Deploy the NOCIX stock monitor and automatic checkout workflow on a Debian VPS
with a React control panel, FastAPI backend, SQLite persistence, multiple
monitoring tasks, API-key authentication, and Telegram notifications.

The checkout flow uses an existing NOCIX account whose PayPal payment method is
already saved in the NOCIX account. The panel must not accept, store, or display
credit-card fields.

## Scope

### Included

- Debian VPS deployment with Docker Compose.
- FastAPI backend serving JSON APIs and the built React application.
- React/Vite/TypeScript frontend inspired by the `ovh-main` panel structure.
- Multiple independent NOCIX monitoring tasks.
- Per-task product ID, stock URL, cart URL, target price, interval, OS preference,
  existing NOCIX account credentials, and PayPal payment method.
- Start, pause, resume, stop, check-now, edit, and delete task actions.
- SQLite persistence for task state, configuration, order history, and logs.
- Restart recovery for tasks that were running before a VPS restart.
- API-key authentication for the panel and protected API routes.
- Telegram notifications for stock recovery, order success, order failure, and
  worker errors.
- Automatic checkout after stock recovery and target-price validation.
- Redacted logs with no NOCIX password or PayPal/session secret output.
- Selenium Firefox as an internal browser service; WebDriver and VNC ports must
  not be exposed publicly.

### Excluded

- Credit-card entry or storage in the panel, database, or task payloads.
- PayPal login automation or PayPal credentials.
- OVH account/server-management features.
- Multi-user roles and permissions.
- Public WebDriver or VNC access.
- Email notifications.

## Architecture

```text
Browser
  -> VPS_IP:8000
  -> FastAPI API + built React assets
  -> SQLite and TaskManager
  -> isolated Selenium Firefox sessions
  -> NOCIX stock and checkout pages
```

The existing `nocix_fucker.Client` remains the browser-facing checkout
implementation, but the direct CLI entrypoint is replaced by a worker adapter.
The adapter owns task lifecycle, state transitions, retries, logging, order
history, and notifications. Each task receives its own Selenium session so an
account or cart cannot be shared accidentally between tasks.

## Payment Model

The only supported automatic checkout payment method in the panel is `paypal`.
The worker uses the existing-customer path and selects the PayPal option exposed
by the NOCIX checkout page. It does not open PayPal directly and does not store
PayPal credentials. If the NOCIX page requires an additional PayPal redirect or
manual authorization despite the saved account method, the worker records a
failed or blocked checkout with the page URL and sends a Telegram notification;
it must not attempt to collect PayPal credentials.

Task configuration requires:

```text
new_customer = false
payment_method = paypal
email = existing NOCIX account email
password = existing NOCIX account password
```

Credit-card fields are rejected by API validation and are not represented in the
frontend task form or database model.

## Database

SQLite stores the following logical records:

### tasks

- `id`
- `goods_id`
- `stock_url`
- `cart_url`
- `target_price`
- `wait_interval`
- `operating_system`
- `email`
- encrypted `password`
- customer profile fields needed by NOCIX checkout
- `payment_method` fixed to `paypal`
- `auto_submit` fixed true for this confirmed workflow
- `status`
- `last_stock_status`
- `last_checked_at`
- `last_error`
- `created_at`
- `updated_at`

### orders

- task ID
- goods ID
- target and observed price
- status: `success`, `failed`, or `unknown` for an indeterminate submission
- error message without secrets
- timestamps

### logs

- timestamp
- level
- task ID when available
- message after redaction

The encryption key is supplied by `DATA_ENCRYPTION_KEY` on the VPS and never
returned by the API. The API returns only masked values such as `configured: true`
for credentials.

## Task State Machine

```text
stopped -> running -> checking -> ordering -> success
                         |             |
                         v             v
                       failed       failed

running <-> paused
```

- `running`: task is eligible for periodic checks.
- `checking`: Selenium is checking the stock page.
- `ordering`: stock was detected and checkout is in progress.
- `success`: order submitted; worker exits and the task stops.
- `failed`: the current attempt ended with an error; the task stops unless the
  user explicitly starts it again.
- An explicit user start from `failed` is the only supported retry. It is not an
  automatic retry and does not apply to a submission whose outcome is unknown.
- `paused`: no browser work is performed until resumed.
- `submitted_pending_confirmation`: submission was initiated but the final
  outcome requires manual confirmation; it is terminal and cannot be retried.
- `unknown`: the submission outcome cannot be determined; it is terminal and
  cannot be retried.
- If `submit_order()` was called but the task and order outcome cannot be
  persisted, the worker retains in-process ownership and reports a redacted,
  loud persistence failure. It must not be released as `stopped` or `failed`,
  and no retry or second submission is allowed.

Only one worker may own a task at a time. Starting an already-running task is
idempotent. A successful order cannot be retried automatically by the same task.
Indeterminate submission states are immutable lifecycle terminals: start, check,
pause, resume, stop, and update are rejected. Deletion remains an explicit
destructive action that removes the task and its history.

## API

All `/api/*` endpoints require `X-API-Key`, except `/api/health`.

```text
GET    /api/health
GET    /api/stats

GET    /api/tasks
POST   /api/tasks
GET    /api/tasks/{id}
PUT    /api/tasks/{id}
DELETE /api/tasks/{id}

POST   /api/tasks/{id}/start
POST   /api/tasks/{id}/pause
POST   /api/tasks/{id}/resume
POST   /api/tasks/{id}/stop
POST   /api/tasks/{id}/check

GET    /api/tasks/{id}/history
GET    /api/orders
DELETE /api/orders

GET    /api/logs
DELETE /api/logs

GET    /api/settings
PUT    /api/settings
POST   /api/telegram/test
```

API validation rejects:

- missing or invalid product ID;
- non-positive target price;
- intervals below the configured minimum;
- `new_customer=true`;
- payment methods other than `paypal`;
- missing existing-account email or password;
- credit-card keys in task payloads.

## Frontend

The frontend follows the useful interaction patterns from `ovh-main` without
copying OVH-specific screens:

- AuthGate for API-key entry.
- Dashboard cards for worker count, stock state, success count, and errors.
- Task cards with status dot, price, interval, last check, and action buttons.
- Add/edit task dialog with existing-account and PayPal-only checkout fields.
- Expandable per-task history.
- Orders page with success/failure records.
- Logs page with refresh, task filter, level filter, and clear action.
- Settings page for Telegram, API status, browser status, and credential status.

The frontend polls lightweight status endpoints at a bounded interval and never
polls or displays raw secrets.

## Notifications

Telegram settings are stored encrypted. Notifications include:

- task started or stopped;
- product became available;
- price mismatch;
- checkout started;
- checkout succeeded;
- checkout failed or was blocked by an unexpected PayPal redirect;
- Selenium or network failure.

Messages include task ID and product ID but exclude password, session cookies,
PayPal tokens, and payment data.

## Deployment

Docker Compose runs:

```text
api       FastAPI + built React assets, fixed at 0.0.0.0:8000 in the provided Compose deployment
browser   selenium/standalone-firefox, internal-only network access
```

Only TCP `22` and `8000` need to be opened in the Debian VPS firewall. Ports
`4444` and `5900` are not published. Production configuration is provided with
`.env`; it is excluded from version control. Required environment variables:

```env
API_KEY=
DATA_ENCRYPTION_KEY=
BROWSER_DSN=http://browser:4444/wd/hub
```

Configure Telegram credentials through the authenticated panel. The credentials
are stored encrypted in SQLite and are not required in `.env`.

The panel is intentionally HTTP-only because the user selected IP plus port and
does not want credit-card data in the panel. The API key still protects access,
but deployment documentation must state that HTTP is vulnerable to interception
and should be used only with a trusted network or SSH tunnel.

## Testing

- Unit tests for PayPal-only configuration validation.
- Unit tests proving credit-card fields are rejected and never serialized.
- Unit tests for stock-page detection and price matching.
- Unit tests for task state transitions and duplicate-worker prevention.
- API tests for API-key enforcement and task lifecycle endpoints.
- Worker tests with a fake browser client covering out-of-stock, stock recovery,
  price mismatch, PayPal selection, success, and failure.
- Frontend build and type-check.
- Docker Compose configuration validation.
- No test may submit an actual NOCIX order or use production credentials.
