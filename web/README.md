# AdGuard Home ToolBox, Web (Docker)

Browser UI to sync one **source** AdGuard Home to many **targets**. Uses the shared Python package in `../agsync`.

**Self-contained:** no `.env` required. First start generates `SECRET_KEY` and `CRON_SECRET` in `/data/app-secrets.env`.

Full feature list: [repository README](../README.md).

## Image and repo

| | |
|--|--|
| **GitHub** | [ludditious/AdGuardHome-ToolBox](https://github.com/ludditious/AdGuardHome-ToolBox) |
| **GHCR package** | `adguardhome-toolbox` |
| **Pull** | `ghcr.io/ludditious/adguardhome-toolbox:latest` |
| **Package UI** | [pkgs/container/adguardhome-toolbox](https://github.com/ludditious/AdGuardHome-ToolBox/pkgs/container/adguardhome-toolbox) |

[`.github/workflows/docker-publish.yml`](../.github/workflows/docker-publish.yml) builds and pushes on **`main`** or tag **`v*`**. Each build updates **`version.txt`** (example `2026.09.28-39`). The UI shows **Version** and **Revised** with the same build number. CI links the package to this repository after push.

Make the package **Public** in package settings for anonymous `docker pull`.

## Pull and run

```bash
docker pull ghcr.io/ludditious/adguardhome-toolbox:latest

docker run -d --name adguardhome-toolbox \
  -p 8080:8080 \
  -v adguardhome-toolbox-data:/data \
  --restart unless-stopped \
  ghcr.io/ludditious/adguardhome-toolbox:latest
```

Compose: `docker compose -f web/docker-compose.pull.yml up -d`

Open **http://localhost:8080** (or your mapped port). Configure **Source**, **Targets**, **Options**, **Schedule**, **Backup**.

Private package: `docker login ghcr.io` with a PAT that includes `read:packages`.

## Source / target addressing

Connections use **`http://IP:port`** to the AdGuard Home **admin UI** (not DNS port 53).

Optional container env (not stored in the app DB): `CUSTOM_DNS`, `AGH_SYNC_HOST_ALIASES`, `AGH_SYNC_DNS_FALLBACK`.

## Cron

`web/cron/crontab` runs every minute and POSTs to `/internal/cron/tick`. That runs **scheduled sync** and **automated source backups** (when enabled under Settings).

## Optional environment

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Override session + field encryption |
| `CRON_SECRET` | Override cron bearer token |
| `DATABASE_URL` | Default SQLite at `/data/aghomesync.db` |
| `PORT` | Default `8080` |

Back up **`/data`**.

## Build locally

From repository root:

```bash
docker compose -f web/docker-compose.yml up -d --build
```

Or: `docker build -t adguardhome-toolbox:latest .`

## Local dev

```bash
cd web
pip install -r requirements.txt
export PYTHONPATH=..
export SECRET_KEY=dev
export CRON_SECRET=dev
export DATABASE_URL=sqlite:///./dev.db
uvicorn app.main:app --reload --port 8080
```

---

*Revised: 2026-09-29*
