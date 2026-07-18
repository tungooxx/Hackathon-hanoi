# Deployment

Full Dockerized stack for DMX Advisor (backend `be1` + frontend `fe` + Postgres +
Elasticsearch + Qdrant), plus two ways to ship: **server-side auto-deploy** (polls
`origin/main`) and a **GitHub Actions** pipeline.

## Layout

| File | Purpose |
|------|---------|
| `docker-compose.prod.yml` | The production stack (5 services). |
| `deploy.sh` | Idempotent redeploy: sync → build → up → migrate → seed indexes. |
| `auto-deploy.sh` | Redeploys only when `origin/main` advanced. Run by the timer. |
| `systemd/dmx-deploy.{service,timer}` | Poll `origin/main` every 2 min and redeploy. |
| `.env.prod.example` | Template for `deploy/.env.prod` (compose interpolation). |
| `../be1/.env.production.example` | Template for `be1/.env` (backend runtime). |
| `../.github/workflows/deploy.yml` | Push-to-`main` deploy over SSH. |

Two gitignored secret files live on the server and **persist across deploys**
(git reset only touches tracked files):

- `be1/.env` — backend runtime config (LLM keys, JWT secrets, service URLs)
- `deploy/.env.prod` — `POSTGRES_PASSWORD`, public port, memory limits

The `POSTGRES_PASSWORD` in `deploy/.env.prod` **must match** the password inside
`DATABASE_URL` / `LANGGRAPH_DATABASE_URL` in `be1/.env`.

## First-time server setup

```bash
ssh my-assistant
cd ~/Hackathon-hanoi

# 1. Create the two secret files from the templates and fill in values
cp be1/.env.production.example be1/.env          # edit: keys, POSTGRES_PASSWORD, FRONTEND_ORIGINS
cp deploy/.env.prod.example  deploy/.env.prod    # edit: POSTGRES_PASSWORD (same value)
chmod 600 be1/.env deploy/.env.prod

# 2. First deploy
bash deploy/deploy.sh main
```

The SPA is then served on `http://<server-ip>/` and proxies `/auth`, `/chat`,
`/catalog`, `/health` to the backend.

## Continuous deployment (server-side, no repo admin needed)

```bash
sudo cp deploy/systemd/dmx-deploy.service /etc/systemd/system/
sudo cp deploy/systemd/dmx-deploy.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dmx-deploy.timer

systemctl list-timers dmx-deploy.timer      # verify schedule
journalctl -u dmx-deploy.service -f         # watch deploys
```

Every 2 minutes it fetches `origin/main`; if there is a new commit it runs
`deploy.sh`, otherwise it exits immediately.

## Continuous deployment (GitHub Actions)

`.github/workflows/deploy.yml` deploys on every push to `main`. The **repo owner**
must add these Actions secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|--------|-------|
| `SSH_HOST` | server IP |
| `SSH_USER` | `ubuntu` |
| `SSH_PRIVATE_KEY` | deploy private key contents |
| `SSH_PASSPHRASE` | key passphrase (omit if none) |
| `BE1_ENV` | full contents of `be1/.env` |
| `DEPLOY_ENV_PROD` | full contents of `deploy/.env.prod` |

Use either the systemd timer **or** GitHub Actions — running both just means the
second one finds nothing new to do.

## Common operations

```bash
CF="deploy/docker-compose.prod.yml"; EF="deploy/.env.prod"
docker compose -f $CF --env-file $EF ps          # status
docker compose -f $CF --env-file $EF logs -f backend
docker compose -f $CF --env-file $EF restart backend
docker compose -f $CF --env-file $EF down        # stop (keeps volumes/data)

# Re-seed the product search index manually
docker compose -f $CF --env-file $EF exec -T backend \
  python data_ingest/ingest_products.py --elasticsearch-url http://elasticsearch:9200 --recreate-index
```
