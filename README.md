# AdGuard Home ToolBox

**AdGuard Home ToolBox** syncs AdGuard Home configuration from one **source** instance to many **targets**—on your LAN or over the internet—using the official HTTP API (`/control/...`).

It fills the gap where AdGuard Home has no single “export everything and clone to another host” workflow: filtering, lists, custom rules, DNS options, rewrites, clients, blocked services, and related settings can be pushed from a golden source to edge nodes, lab copies, or remote installs.

The project includes:

- **Docker web app** (recommended for servers) — browser UI, cron scheduling, backups, settings
- **Windows desktop GUI** — same sync engine, local JSON settings, Windows Task Scheduler
- **CLI** — `python -m agsync` with YAML config for scripts and automation

**GitHub:** [ludditious/AdGuardHome-ToolBox](https://github.com/ludditious/AdGuardHome-ToolBox)  
**Container image:** `ghcr.io/ludditious/adguardhome-toolbox:latest`

---

## Docker web app — features

Run the published image or build from this repo ([web/README.md](web/README.md) for pull, compose, and GHCR details).

### Sync

| Area | What you can do |
|------|------------------|
| **Dashboard** | Run **Sync now**; see recent run results |
| **Source** | One enabled source: **IPv4 + admin port** (`http://` is assumed), username/password, **Test connection** |
| **Targets** | Named targets with the same addressing; enable/disable per server; test each |
| **Options** | Choose what to sync (DNS, lists, rules, rewrites, clients, blocked services, parental/safe search); TLS verify; refresh lists after sync; **dry run** |
| **Schedule** | Built-in **cron** (checks every minute, UTC): interval in minutes or hours, days Sun–Sat; automatic sync when due |
| **Log** | Sync history (manual, cron, etc.); clear log |

The sync engine applies sensible **DNS payload sanitization** when pushing to targets (e.g. skips private reverse-DNS upstreams and other read-only or environment-specific fields) so cloud or remote targets are less likely to reject config.

### Backup & restore

| Area | What you can do |
|------|------------------|
| **AdGuard Home (source)** | **Manual backups** of all source settings (no AdGuard login secrets in the file); **automated daily backups** when enabled in Settings; separate lists with **Previous / Next** paging |
| **Retention** | Automated backups roll off after the period you choose (1 day through 120 days); **manual backups are never deleted automatically** |
| **Actions** | Download JSON, restore to source, delete; restore from uploaded file |
| **ToolBox configuration** | Backup/restore app config (source, targets, sync options, schedule, encrypted secrets) so a new container volume can recover saved AdGuard passwords and layout |

### Settings & account

| Area | What you can do |
|------|------------------|
| **Password** | Change the ToolBox login password |
| **Password recovery** | Three security questions for **Forgot password**; answers stored **encrypted at rest** and visible on Settings for review |
| **Automated source backup** | Enable/disable daily automated AdGuard Home source backup; retention dropdown (1 day → 120 days) |
| **Updates** | Optional check on sign-in against GitHub `version.txt` for a newer Docker image; **Update** link in the nav when a newer build is available |

### UI & ops

- **Light / dark** theme (persisted in the browser)
- **About** — version and revised build id from the image; links to repo, package, and licensing
- **Self-contained container** — `SECRET_KEY` and `CRON_SECRET` generated on first start under `/data`; SQLite database on the volume
- **Health** — `GET /health` for probes

Default ToolBox login after first deploy is documented on the sign-in page until you change the password.

---

## Quick start (Docker)

```bash
docker pull ghcr.io/ludditious/adguardhome-toolbox:latest

docker run -d --name adguardhome-toolbox \
  -p 8080:8080 \
  -v adguardhome-toolbox-data:/data \
  --restart unless-stopped \
  ghcr.io/ludditious/adguardhome-toolbox:latest
```

Open the UI on port **8080** (or map another host port). Back up the **`/data`** volume.

---

## What is synced (API overview)

| Area | API (typical) |
|------|----------------|
| Filtering on/off + update interval | `/filtering/config` |
| Block/allow list subscriptions | add/remove/set URL |
| Custom rules | `/filtering/set_rules` |
| DNS upstreams, blocking mode, cache, etc. | `/dns_config` |
| DNS rewrites | replace via `/rewrite/*` |
| Persistent clients | replace via `/clients/*` |
| Blocked services | `/blocked_services/set` |
| Parental / safe browsing / safe search | enable + settings |

### Usually not synced (per host)

Listen address, web port, TLS/DoH/DoT, DHCP binding, query stats history, and AdGuard admin passwords (unless you set them on each node yourself).

---

## Windows desktop GUI

```powershell
cd AdGuardHome-ToolBox
pip install -r requirements.txt
python run_app.py
```

Or **`Launch GUI.bat`**. Settings: **`%LOCALAPPDATA%\AGHomeSync\settings.json`**.

Tabs: Source, Targets, Options, Schedule (Windows task `AGHomeSync`), Sync, Log.

### Standalone `.exe`

```powershell
.\build_exe.ps1
```

Run **`dist\AGHomeSync.exe`**.

---

## CLI (YAML config)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.yaml config.yaml
python -m agsync -c config.yaml
```

Dry run, export-only, and single-target flags are supported; see `config.example.yaml`.

---

## Requirements

- Python **3.10+** (local GUI/CLI); **3.12** in the official Docker image
- AdGuard Home **v0.107+** on source and targets
- Network path from the ToolBox host/container to each AdGuard Home **admin UI** port

---

## Security notes

- Protect `config.yaml` and the Docker **`/data`** volume (database, secrets, backups).
- Prefer HTTPS on AdGuard Home in production; enable **Verify TLS** in sync options when certificates are valid.
- ToolBox backup files contain sensitive configuration—store them privately.

---

## Similar projects

- [adguardhome-sync](https://github.com/bakito/adguardhome-sync) (Go) — mature Docker-oriented sync; this repo is a Python alternative you can extend (web UI, backups, scheduling).

---

*Revised: 2026-09-26*
