# AdGuard Home ToolBox — Web (Docker)

Multi-user web UI to sync one **source** AdGuard Home instance to many **targets**. Uses the shared Python package in `../agsync` (same sync engine as the Windows desktop app).

**Self-contained:** no `.env` file required. On first start the container generates `SECRET_KEY` and `CRON_SECRET` and stores them in the `/data` volume (`/data/app-secrets.env`).

## Publish the image on GitHub (one-time setup)

GitHub repo: **ludditious/AdGuardHome-ToolBox** (source + CI). GHCR package **`AdGuardHome-ToolBox`** (`ghcr.io/ludditious/adguardhome-toolbox`).

**`.github/workflows/docker-publish.yml`** builds and pushes that image on push to **`main`** or tag **`v*`**.

1. **Commit and push** the repo to GitHub (including the `web/` and `agsync/` folders and the workflow file).
2. Open **Actions** on GitHub and confirm **Publish Docker image** succeeds.
3. Open **Packages** → **`AdGuardHome-ToolBox`** → **Package settings** → **Public** if you want anonymous `docker pull`.

Image name (lowercase):

```text
ghcr.io/ludditious/adguardhome-toolbox:latest
```

## Pull and run (for you or anyone else)

No clone and no `.env` required:

```bash
docker pull ghcr.io/ludditious/adguardhome-toolbox:latest

docker run -d --name adguardhome-toolbox \
  -p 8080:8080 \
  -v adguardhome-toolbox-data:/data \
  --restart unless-stopped \
  ghcr.io/ludditious/adguardhome-toolbox:latest
```

### Hostnames / DNS

The app resolves hostnames with **system DNS** (`getaddrinfo` and `/etc/resolv.conf` in the container). It does **not** store DNS server addresses in the database.

If resolution fails inside Docker, configure the **container/host resolver**, or use optional env:

- **`CUSTOM_DNS`** — extra nameservers for the container (ops config, not saved in the app)
- **`AGH_SYNC_HOST_ALIASES`** — `hostname:ip` pairs to skip DNS for specific names
- **Connect using IP** on the Source form (optional)

Optional **`AGH_SYNC_DNS_FALLBACK`** only if you explicitly set it (public resolvers are never added by default).

Or with compose from this repo:

```bash
docker compose -f web/docker-compose.pull.yml up -d
```

Open **http://localhost:8080**, register, configure source/targets.

If the package is **private**, log in first:

```bash
echo YOUR_GITHUB_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

## Build locally (developers)

From the **repository root** (build context must include `agsync/`):

```bash
docker compose -f web/docker-compose.yml up -d --build
```

Or:

```bash
docker build -t adguardhome-toolbox:latest .
```

## Optional environment

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Override session + encryption key (otherwise auto-generated) |
| `CRON_SECRET` | Override cron token (otherwise auto-generated) |
| `ALLOW_REGISTRATION` | Legacy; registration is disabled (login only) |
| `DATABASE_URL` | Default SQLite at `/data/aghomesync.db` |

Back up the **`/data`** volume — it holds the database and generated secrets.

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

*Revised: 2026-09-21*
