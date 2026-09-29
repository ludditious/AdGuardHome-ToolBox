# AdGuard Home ToolBox

**AdGuard Home ToolBox** syncs AdGuard Home configuration from one **source** instance to many **targets**, on your LAN or over the internet, using the official HTTP API (`/control/...`).

AdGuard Home has no single "export everything and clone to another host" workflow. This project pushes filtering, lists, custom rules, DNS options, rewrites, clients, blocked services, and related settings from a golden source to edge nodes, lab copies, or remote installs.

The project includes:

- **Docker web app** (recommended): browser UI, cron scheduling, backups, account settings
- **CLI** (optional): `python -m agsync` with YAML config for scripts and automation

| | |
|--|--|
| **GitHub** | [ludditious/AdGuardHome-ToolBox](https://github.com/ludditious/AdGuardHome-ToolBox) |
| **Container image** | `ghcr.io/ludditious/adguardhome-toolbox:latest` |
| **Package page** | [pkgs/container/adguardhome-toolbox](https://github.com/ludditious/AdGuardHome-ToolBox/pkgs/container/adguardhome-toolbox) |

CI publishes the image on every push to `main` (see [web/README.md](web/README.md)).

---

## Docker web app features

### Sync

| Area | What you can do |
|------|------------------|
| **Dashboard** | Run **Sync now**; see recent run results |
| **Source** | One enabled source: **IPv4 + admin port** (`http://` is assumed), username/password, **Test connection** |
| **Targets** | Named targets with the same addressing; enable/disable per server; test each |
| **Options** | Grouped toggles for each sync area (see table below); TLS verify; refresh lists after sync; **dry run** |
| **Schedule** | Built-in **cron** (checks every minute, UTC): interval in minutes or hours, days Sun–Sat; automatic sync when due |
| **Log** | Per-run log with **per-target** sections; failed targets show AdGuard API messages (HTTP status and body), not generic errors |

**Sync behavior notes:**

- **DNS** payloads are sanitized for targets (private PTR handling, domain-specific upstream lines, no DHCP or listen ports) so remote/cloud nodes are less likely to reject config.
- **Blocked services**: only service IDs that exist on the **target’s** catalog are applied; others are **skipped** and logged (handles older AdGuard Home or missing apps like a source-only service name).
- **Persistent clients**: source snapshots normalize `/clients` JSON so mixed AdGuard Home versions parse consistently.
- A failure on one target does not stop other targets in the same run.

### Backup and restore

| Area | What you can do |
|------|------------------|
| **AdGuard Home (source)** | **Manual backups** of source settings (no AdGuard login secrets); **automated daily backups** when enabled in Settings; **separate lists** with **Previous / Next** paging (10 per page) |
| **Retention** | Automated backups expire after 1 day through 120 days (Settings); **manual backups are never auto-deleted** |
| **Actions** | Download JSON, restore to source (respects current Options toggles), delete, restore from upload |
| **ToolBox configuration** | Backup/restore source, targets, **all sync option toggles**, schedule, update-check preference, and container encryption keys (recover saved AdGuard passwords after a new volume; not your ToolBox login) |

**Backup formats:** AdGuard snapshots use `adguardhome-toolbox-backup` (v2, no runtime server status). ToolBox config uses `adguardhome-toolbox-config` (v3).

### Settings and account

| Area | What you can do |
|------|------------------|
| **Password** | Change ToolBox login password |
| **Password recovery** | Three security questions for **Forgot password**; answers **encrypted at rest** and shown on Settings for review |
| **Automated source backup** | Enable daily cron backup of the source; retention dropdown |
| **Updates** | Optional sign-in check against GitHub `version.txt`; **Update** in the nav when a newer image exists |

### UI and ops

- **Light / dark** theme (browser localStorage)
- **About / login footer**: **Version** `YYYY.MM.DD-<build>` and **Revised** `YYYY-MM-DD-<build>` from the image `version.txt`
- **Self-contained container**: `SECRET_KEY` and `CRON_SECRET` under `/data`; SQLite on the volume
- **Health**: `GET /health`

Default ToolBox login is documented on the sign-in page until you change the password.

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

Open port **8080** (or your mapped port). Back up the **`/data`** volume.

---

## Sync options (Options page)

Each row can be turned off independently.

| Toggle | What it copies |
|--------|----------------|
| Filtering enabled + list update interval | `/filtering/config` |
| Block list subscriptions | block list URLs, names, enabled state |
| Allow list subscriptions | allow list (whitelist) subscriptions |
| Custom filtering rules | block and allow user rules |
| DNS settings | `/dns_config` (sanitized) |
| DNS rewrites | full replace on target |
| Persistent clients | replace persistent clients |
| Blocked services | selected IDs + schedule (target-aware) |
| Parental controls | enable/disable |
| Safe browsing | enable/disable |
| Safe search | enable/disable and settings when on |
| Refresh lists after sync | post-sync filter refresh (not a data copy) |
| Dry run | log only, no target changes |

**Not synced:** runtime server status, listen/web ports, TLS/DoH/DoT, DHCP, stats/history, AdGuard admin passwords.

---

## CLI (YAML config, optional)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.yaml config.yaml
python -m agsync -c config.yaml
```

`config.example.yaml` lists the same option keys as the web UI. Dry run, export-only, and single-target flags are supported.

---

## Requirements

- Python **3.10+** (CLI); **3.12** in the official Docker image
- AdGuard Home **v0.107+** on source and targets (newer targets may support fewer blocked-service IDs)
- Network path to each AdGuard Home **admin UI** port

---

## Security notes

- Protect `config.yaml` and the Docker **`/data`** volume (database, secrets, backups).
- Prefer HTTPS on AdGuard Home in production; enable **Verify TLS** when certificates are valid.
- Backup files contain sensitive configuration. Store them privately.

---

## Similar projects

- [adguardhome-sync](https://github.com/bakito/adguardhome-sync) (Go): mature Docker-oriented sync; this repo is a Python stack with web UI, backups, and granular options.

---

*Revised: 2026-09-29*
