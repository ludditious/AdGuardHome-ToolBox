# AdGuard Home ToolBox (1 → many)

Copies **settings, block lists, custom rules, DNS options, rewrites, clients, and blocked services** from one **source** AdGuard Home instance to **many targets** using the official HTTP API (`/control/...`).

Includes a **Windows desktop GUI**, a **Dockerized multi-user web app** (`web/`), and an optional **standalone `.exe`** build.

## What AdGuard Home is

[AdGuard Home](https://github.com/AdguardTeam/AdGuardHome) is a network-wide DNS sinkhole (like Pi-hole): block lists, custom filtering rules, upstream DNS, rewrites, per-client settings, optional DHCP, etc.

There is still **no full “export everything” button** in the UI for cloning to another host; this tool fills that gap via the API.

## Requirements

- Python 3.10+
- Source and targets reachable from the machine running the sync
- Same admin credentials pattern (each host can have its own user/password in config)
- AdGuard Home v0.107+ (typical current installs)

## Setup

```powershell
cd AdGuardHome-ToolBox
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.yaml config.yaml
# Edit config.yaml
```

## Web app (Docker, Linux)

See **[web/README.md](web/README.md)** — multi-user UI, Sun–Sat schedule + interval, cron-driven sync, activity log.

```bash
docker compose -f web/docker-compose.yml up -d --build
```

No `.env` required — secrets are created automatically on first start (stored in the Docker volume).

**GitHub image:** push to `main` triggers [GHCR publish](.github/workflows/docker-publish.yml). See [web/README.md](web/README.md) for `docker pull` / public package settings.

## Windows GUI (recommended)

```powershell
cd AdGuardHome-ToolBox
pip install -r requirements.txt
python run_app.py
```

Or double-click **`Launch GUI.bat`** (uses `pythonw` so no console window).

Settings are stored in **`%LOCALAPPDATA%\AGHomeSync\settings.json`** (passwords in plain text — restrict PC access or encrypt the folder if needed).

Tabs:

- **Source** — URL, username, password, enabled, test connection  
- **Targets** — add / edit / delete, enable/disable per server  
- **Options** — what to sync, dry run, TLS verify  
- **Schedule** — every N **minutes** or **hours**, **daily** at a time, or **weekly**; creates/removes a Windows task named `AGHomeSync`  
- **Sync** — save and run now  
- **Log** — history of each sync and connection test, with **Clear log**  

Activity is stored in **`%LOCALAPPDATA%\AGHomeSync\activity.log`**.

### Standalone `.exe`

```powershell
.\build_exe.ps1
```

Run **`dist\AGHomeSync.exe`**. Copy it anywhere; settings still use `%LOCALAPPDATA%\AGHomeSync`. If task creation fails with “access denied”, run the app once as Administrator to register the schedule.

## CLI usage

Dry run (log actions only):

```yaml
options:
  dry_run: true
```

Sync all targets:

```powershell
python -m agsync -c config.yaml
```

Export source snapshot for inspection:

```powershell
python -m agsync -c config.yaml --export-only snapshot.json
```

Sync one target by name:

```powershell
python -m agsync -c config.yaml --target basement
```

## What is synced

| Area | API |
|------|-----|
| Filtering on/off + update interval | `/filtering/config` |
| Block/allow list subscriptions | add/remove/set URL |
| Custom rules | `/filtering/set_rules` |
| DNS upstreams, blocking mode, cache, etc. | `/dns_config` |
| DNS rewrites | replace via `/rewrite/*` |
| Persistent clients | replace via `/clients/*` |
| Blocked services | `/blocked_services/set` |
| Parental / safe browsing / safe search | enable + settings |

## Not synced (by design)

These are usually **per machine** — change manually on each host if needed:

- Listen address / web port (`bind_host`, `port`)
- TLS certificates and DoH/DoT hostnames
- DHCP interface binding
- Query log / stats history
- Admin password (unless you change it yourself on each node)

## Scheduling

Use the GUI **Schedule** tab on Windows, or cron on Linux with `python -m agsync -c config.yaml`.

## Similar projects

- [adguardhome-sync](https://github.com/bakito/adguardhome-sync) (Go, Docker) — production-grade; this repo is a simple, editable Python alternative.

## Security

- Store `config.yaml` outside git; it contains passwords.
- Prefer HTTPS on AdGuard Home admin UI in production; set `verify_tls: true` when using valid certs.

---

*Revised: 2026-09-21*
