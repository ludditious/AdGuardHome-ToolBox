# AdGuard Home ToolBox, Web (Docker)

Browser UI and API for syncing one **source** AdGuard Home to many **targets**. Uses the shared Python package in `../agsync` (same sync engine as the CLI).

**Self-contained:** no `.env` required. On first start the container generates `SECRET_KEY` and `CRON_SECRET` in `/data/app-secrets.env`.

For a full feature list (backups, schedule, settings, updates), see the [repository README](../README.md).

## Image and repo

| | |
|--|--|
| **GitHub** | [ludditious/AdGuardHome-ToolBox](https://github.com/ludditious/AdGuardHome-ToolBox) |
| **GHCR package** | `adguardhome-toolbox` |
| **Pull** | `ghcr.io/ludditious/adguardhome-toolbox:latest` |

CI: [`.github/workflows/docker-publish.yml`](../.github/workflows/docker-publish.yml) builds and pushes on push to **`main`** or tag **`v*`**. Each build writes **`version.txt`** (for example `2026.09.25-30`); the UI shows that as **Version** and **Revised** `YYYY-MM-DD-<build#>`.

Make the package **Public** under **Packages → adguardhome-toolbox → Package settings** if you want anonymous `docker pull`.

## Pull and run

```bash
docker pull ghcr.io/ludditious/adguardhome-toolbox:latest

docker run -d --name adguardhome-toolbox \
  -p 8080:8080 \
  -v adguardhome-toolbox-data:/data \
  --restart unless-stopped \
  ghcr.io/ludditious/adguardhome-toolbox:latest
```

Compose from this repo:

```bash
docker compose -f web/docker-compose.pull.yml up -d
```

Open **http://localhost:8080** (or your mapped port). Sign in, configure **Source** (IPv4 + port), **Targets**, **Options**, and **Schedule**.

If the package is private:

```bash
echo YOUR_GITHUB_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

## Source / target addressing

Connections use **`http://IP:port`** to the AdGuard Home **admin UI** (not DNS port 53). Hostnames are not required; use IPv4 and the port shown in AdGuard Home settings.

### DNS inside the container

Resolution uses the container resolver (`/etc/resolv.conf`). Optional environment (not stored in the app DB):

| Variable | Purpose |
|----------|---------|
| **`CUSTOM_DNS`** | Extra nameservers for the container |
| **`AGH_SYNC_HOST_ALIASES`** | `hostname:ip` pairs |
| **`AGH_SYNC_DNS_FALLBACK`** | Only if you set it explicitly |

Update checks can fall back to public DNS and then the source IP when reaching GitHub for `version.txt`.

## Cron

`web/cron/crontab` runs **`cron-tick.sh`** every minute, which POSTs to `/internal/cron/tick` with `CRON_SECRET`. That drives **scheduled sync** and **automated source backups** (when enabled under Settings).

## Optional environment

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Override session + field encryption key |
| `CRON_SECRET` | Override cron bearer token |
| `DATABASE_URL` | Default SQLite at `/data/aghomesync.db` |
| `PORT` | Default `8080` |

Back up the **`/data`** volume (database, secrets, backup records).

## Build locally

From the **repository root** (context must include `agsync/` and `version.txt`):

```bash
docker compose -f web/docker-compose.yml up -d --build
```

Or:

```bash
docker build -t adguardhome-toolbox:latest .
```

## Local dev (no Docker)

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

*Revised: 2026-09-26*
