# Deploy at https://www.pristinebiopharma.in/bill

The billing application is configured for **https://www.pristinebiopharma.in/bill**. Its pages, JavaScript/CSS, login and invitation links use `/bill`; browser API requests and PDF downloads use `/bill/api/v1`. Nginx removes only the `/bill` prefix on API requests, keeping FastAPI's internal `/api/v1` routes and existing business behavior.

The existing public company website continues at `/`. The supplied Nginx file adds billing locations inside its existing HTTPS server block; it does not replace the company's website or TLS certificate configuration. A URL path cannot be pointed at a different server with DNS: the server/proxy already receiving `www.pristinebiopharma.in` must route `/bill` to this application. If the main website is hosted elsewhere, configure that host's reverse proxy or bring its existing website configuration onto the same VPS before changing DNS.

## 1. Prepare the VPS

Use a Linux VPS with Docker Engine, the Docker Compose plugin, Python 3 (only for the settings generator), and Nginx. Size CPU/RAM and PDF storage for the actual workload using the existing limits and capacity notes in the operations runbook.

Install Docker using its [official OS-specific instructions](https://docs.docker.com/engine/install/) if needed. Existing HTTPS for `www.pristinebiopharma.in` can be retained. The public HTTPS proxy must be able to reach this VPS. If a certificate is needed, use the [Certbot Nginx documentation](https://eff-certbot.readthedocs.io/en/stable/using.html#nginx).

Upload/clone this project's complete source onto the VPS, for example `/opt/pristine-billing`, including `deploy/.env.example`. Do not copy local development `.env` files over production settings. Docker builds install the locked dependencies; local `node_modules`, virtual environments and build output are not needed.

## 2. Generate private production settings once

From the project root on the VPS:

```bash
python3 deploy/create_env.py --output .env.production
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
```

The generator creates a mode-0600 settings file with independent random signing/encryption keys and a matching PostgreSQL password/URL. It does not print credentials or overwrite an existing file. Keep this file for future releases and back it up privately. Reusing an existing database requires its existing database credentials and signing/encryption keys; do not generate replacement settings for an established deployment.

The relevant public settings are already supplied:

```dotenv
FRONTEND_ORIGIN=https://www.pristinebiopharma.in
NEXT_PUBLIC_BASE_PATH=/bill
NEXT_PUBLIC_API_BASE_URL=/bill/api/v1
COOKIE_SECURE=true
```

`FRONTEND_ORIGIN` is the origin only, without `/bill`. The frontend base path and API URL are embedded at build time; changing either requires rebuilding the frontend image. Local development retains root routes when `NEXT_PUBLIC_BASE_PATH` is empty. Production Compose defaults to `/bill`; for an intentional root deployment, explicitly set `NEXT_PUBLIC_BASE_PATH=` and a matching API URL.

## 3. Build, migrate, start

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml up -d postgres redis
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm backend sh /app/scripts/release_migrate.sh
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
docker compose --env-file .env.production -f docker-compose.prod.yml ps
curl --fail http://127.0.0.1:8000/ready
curl --fail --output /dev/null http://127.0.0.1:3000/bill/login
```

Stop if a migration or readiness check fails. Migration execution is a release step, not an application startup action. Named volumes retain PostgreSQL data and PDFs across restarts. Keep them and the production settings when updating the application. Never use `docker compose down -v` on the live system.

The host ports are bound to `127.0.0.1:3000` and `127.0.0.1:8000` for the local Nginx proxy. PostgreSQL and Redis have no host port bindings. Services restart automatically after a server reboot when Docker is enabled. If either host port is already occupied, adjust `FRONTEND_PORT`/`BACKEND_PORT` in `.env.production` and the corresponding upstream ports in the Nginx snippet.

## 4. Add billing to the existing HTTPS server

Copy `deploy/nginx/bill.locations.conf` to `/etc/nginx/snippets/pristine-bill.conf`. Inside the existing `server { ... }` block that serves **www.pristinebiopharma.in on HTTPS**, add:

```nginx
include /etc/nginx/snippets/pristine-bill.conf;
```

Keep its current `location /`, `server_name`, certificate paths and website configuration. Then validate and reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Do not install the snippet as a standalone server configuration: it contains locations to include inside the current HTTPS server. `/bill` is proxied directly rather than redirected to `/bill/`, avoiding a redirect loop with Next.js canonical URLs. `/bill/_next/...` assets retain their prefix. API requests preserve bodies, query strings, Origin, CSRF headers and cookies, and allow time for PDF rendering. API responses are not cached. Canonical API redirects remain under `/bill`. Secure `__Host-` cookies intentionally retain `Path=/`; do not rewrite their cookie path.

The root website's current HTTPS redirect should continue to send users to the `www` hostname. Open the billing application on the configured `www` hostname consistently.

## 5. Verify the deployed address

```bash
curl --fail --output /dev/null https://www.pristinebiopharma.in/
curl --fail --output /dev/null https://www.pristinebiopharma.in/bill/login
curl --fail https://www.pristinebiopharma.in/bill/api/v1/auth/csrf
```

Open **https://www.pristinebiopharma.in/bill**, sign in, open each bill/register, preview a draft and download an existing confirmed PDF. Confirm invitations point to `/bill/login#invite=...` and navigation stays under `/bill`. Check that the existing company website still works at `/`. Set up the database/PDF backups in [the operations runbook](OPERATIONS_RUNBOOK.md) before entering live billing data.

The repository changes prepare deployment; they do not upload the application, change DNS or activate the Nginx configuration on a VPS. Docker image execution, live HTTPS and existing-data migration must be verified on the deployment server. Current unrelated backend test failures remain documented in [project status](PROJECT_STATUS.md).
