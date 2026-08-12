# NOCIX VPS Panel

FastAPI and React control panel for managing the existing NOCIX worker workflow.
The panel stores task passwords encrypted with Fernet, uses the NOCIX account's
saved PayPal method, and keeps Selenium Firefox on the private Docker network.
Credit-card fields and PayPal credentials are not accepted or stored.

## Debian Deployment

The commands below assume a fresh Debian VPS with SSH access and a user allowed
to run Docker. Install Docker Engine and the Compose plugin using Docker's
official Debian instructions, then verify:

```sh
docker --version
docker compose version
```

Copy the project to the VPS and create a private environment file:

```sh
cp .env.example .env
chmod 600 .env
```

Replace `API_KEY` with a strong random value. Generate one without storing it in
the shell history when possible, or use:

```sh
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Generate `DATA_ENCRYPTION_KEY` with a valid Fernet key:

```sh
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Put both generated values in `.env`. Keep the Fernet key backed up separately;
losing it makes encrypted task passwords unrecoverable. Do not add `.env` to
source control.

`HOST` and `LOG_LEVEL` are read by the API entrypoint. The provided production
deployment always listens on port `8000` inside and outside the container. The
container starts as root only long enough to create and chown the bind-mounted
data directory, then runs Uvicorn as UID `10001` (`appuser`). No host-side
ownership setup is required for a fresh `./data` directory.

Telegram credentials are not read from `.env`. Configure them only through the
authenticated panel settings so they are encrypted before storage.

Open only SSH and the API port in the VPS firewall. For UFW:

```sh
sudo ufw allow 22/tcp
sudo ufw allow 8000/tcp
sudo ufw enable
```

Validate the rendered Compose file before starting the stack:

```sh
docker compose config
```

Build and start the API and internal browser service:

```sh
docker compose up -d --build
curl http://127.0.0.1:8000/api/health
docker compose ps
```

The health endpoint should return `{"status":"ok"}`. Inspect service output with:

```sh
docker compose logs -f api
docker compose logs -f browser
```

The browser's WebDriver and VNC ports are intentionally not published. Do not
open or proxy ports `4444` or `5900` to the Internet.

## Updates And Backups

Pull the updated source and recreate the image without changing the persistent
SQLite volume:

```sh
docker compose up -d --build
```

Back up the SQLite database while the API is stopped so the copy is consistent:

```sh
mkdir -p backups
docker compose stop api
cp data/nocix.db "backups/nocix-$(date +%Y%m%d-%H%M%S).db"
docker compose start api
```

Back up `.env` and the Fernet key using a separate restricted mechanism. Restoring
the database requires the same `DATA_ENCRYPTION_KEY`.

On startup, `init_db()` checks the persistent SQLite database and applies
idempotent additive migrations tracked in the `schema_version` table. Existing
rows are preserved; current task lifecycle fields and order-history price/error
fields are added with safe defaults. Always stop the API and make a database
backup before upgrading. If an upgrade must be reversed, restore the backup
and use the matching application version. Keep the same Fernet key when
restoring a database.

## Security Notes

This deployment serves HTTP on port 8000. HTTP exposes the API key and panel
traffic to anyone able to observe the connection. Use a trusted network or an
SSH tunnel, or place a properly configured HTTPS reverse proxy in front of the
API before exposing it beyond a trusted network. The API key is not a substitute
for TLS.

The public endpoint is `GET /api/health`; other `/api/*` endpoints require the
`X-API-Key` header. The React single-page application is served by FastAPI, with
client-side routes falling back to `index.html`.

## Local Validation

```sh
npm --prefix frontend run build
python -m pytest -q
python -m compileall -q backend
docker compose config
```

The tests use fake workers and HTTP transports only. They do not start Selenium,
visit NOCIX, send Telegram messages, or submit checkout orders.

An ordinary pre-submit failure is terminal for the current attempt but can be
retried only through an explicit user `Start monitor` action. If submission was
initiated and its task/order outcome cannot be durably persisted, the worker
retains ownership and reports an indeterminate persistence failure; it is never
released as a retryable `stopped` or `failed` task and must not submit again.
