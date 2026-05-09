# FOXJP Hermes Web UI Official Systemd Migration Plan

Created: 2026-04-30
Target host: `foxjp`
Status: executed on 2026-04-30 17:45-17:52 UTC

## Execution Result

- Migration backup: `/root/backup/hermes-webui-official-systemd-20260430174533`
- `hermes-webui.service` now runs the official npm package entry:
  `/opt/node-webui/current/lib/node_modules/hermes-web-ui/dist/server/index.js`
- `/root/hermes-webui` source deployment was archived in the migration backup and removed from the active filesystem.
- Built-in update endpoint was tested successfully; systemd restarted Web UI after the official updater exited.
- `hermes-webui-session-sync.timer` remains enabled for external `weixin` and `cron` conversation sync.
- Verified Web UI API session sources after migration: `cron`, `api_server`, and `weixin`.

## Goal

Migrate Hermes Web UI on `foxjp` back to an almost-official deployment while keeping systemd persistence, current data, and external conversation visibility.

Target shape:

- Run the official npm package `hermes-web-ui` instead of the local source tree `/root/hermes-webui`.
- Keep systemd as the process supervisor for boot persistence and crash recovery.
- Let the Web UI built-in update button install the latest official npm package.
- Keep `/root/.hermes-web-ui` unchanged so token, credentials, SQLite DB, uploads, and logs survive.
- Keep `hermes-webui-session-sync.timer` for now so `weixin` and `cron` conversation groups continue to appear.
- Remove or archive redundant old Web UI source/build directories after verification.

## Current Assumptions

- Security group no longer exposes `8648/tcp` to the public internet.
- Nginx still proxies `hermes.222046.xyz` to `127.0.0.1:8648`.
- Official Hermes Web UI `0.5.3` only imports Hermes sessions when the local Web UI DB is empty. It does not yet replace the continuous sync timer.
- `/root/.hermes-web-ui/hermes-web-ui.db` is the production Web UI DB.
- `/root/.hermes/state.db` is the Hermes state DB.
- `/opt/node-webui/current/bin/node` is Node `>=23`; currently expected to be Node 24.x.

## Design Decision

Do not run `hermes-web-ui start` under systemd.

Reason: the official CLI `start` command daemonizes itself and writes its own PID file. If systemd also supervises it, process ownership becomes ambiguous.

Instead, systemd should run the official package server entry directly:

```bash
/opt/node-webui/current/bin/node /opt/node-webui/current/lib/node_modules/hermes-web-ui/dist/server/index.js
```

This keeps systemd as the only supervisor.

The built-in update button can still work because official `/api/hermes/update` does:

```bash
npm install -g hermes-web-ui@latest
hermes-web-ui restart --port 8648
process.exit(0)
```

In this systemd model, the CLI restart may not own a PID file, but the important part is that the current server process exits after npm update. systemd then restarts the same server entry path, now pointing to the updated npm package.

## Do Not Touch

- `/root/.hermes-web-ui/`
- `/root/.hermes/state.db`
- `/root/.hermes/config.yaml`
- `/root/.hermes/scripts/sync_hermes_sessions_to_webui.py`
- `/etc/systemd/system/hermes-webui-session-sync.service`
- `/etc/systemd/system/hermes-webui-session-sync.timer`
- Nginx vhost files unless verification shows the proxy target is wrong

## Preflight Inventory

Run on `foxjp`:

```bash
date -u
systemctl is-active hermes-webui hermes-gateway hermes-webui-session-sync.timer
systemctl is-enabled hermes-webui hermes-gateway hermes-webui-session-sync.timer
systemctl cat hermes-webui --no-pager
systemctl cat hermes-webui-session-sync.timer --no-pager
ss -ltnp | grep -E ':(8648|8642|80|443)\s'
nginx -t
/opt/node-webui/current/bin/node -v
/opt/node-webui/current/bin/npm list -g --depth=0 | grep hermes-web-ui || true
```

Check current Web UI health:

```bash
curl -fsS http://127.0.0.1:8648/health
```

Check Web UI DB source counts:

```bash
python3 - <<'PY'
import sqlite3
con = sqlite3.connect('/root/.hermes-web-ui/hermes-web-ui.db')
cur = con.cursor()
print(cur.execute('select source,count(1) from sessions group by source order by source').fetchall())
print(cur.execute('select s.source,count(m.id) from sessions s left join messages m on m.session_id=s.id group by s.source order by s.source').fetchall())
con.close()
PY
```

Expected sources should include `api_server`, `cron`, and `weixin`.

## Required Backup

Create a timestamped backup directory:

```bash
ts="$(date -u +%Y%m%d%H%M%S)"
backup="/root/backup/hermes-webui-official-systemd-$ts"
mkdir -p "$backup"
```

Back up service and Nginx config:

```bash
systemctl cat hermes-webui --no-pager > "$backup/hermes-webui.service.current.txt"
systemctl cat hermes-webui-session-sync.service --no-pager > "$backup/hermes-webui-session-sync.service.current.txt"
systemctl cat hermes-webui-session-sync.timer --no-pager > "$backup/hermes-webui-session-sync.timer.current.txt"
nginx -T > "$backup/nginx.full.conf.txt" 2>&1
```

Back up Web UI data safely:

```bash
sqlite3 /root/.hermes-web-ui/hermes-web-ui.db ".backup '$backup/hermes-web-ui.db'"
cp -a /root/.hermes-web-ui/.token "$backup/.token"
cp -a /root/.hermes-web-ui/.credentials "$backup/.credentials" 2>/dev/null || true
rsync -a /root/.hermes-web-ui/upload/ "$backup/upload/" 2>/dev/null || true
```

Back up current source deployment and local patches:

```bash
if [ -d /root/hermes-webui/.git ]; then
  git -C /root/hermes-webui status --short > "$backup/hermes-webui.git-status.txt"
  git -C /root/hermes-webui rev-parse HEAD > "$backup/hermes-webui.git-head.txt"
  git -C /root/hermes-webui diff > "$backup/hermes-webui.local.patch"
fi
```

Optionally archive the full current source tree before removing it later:

```bash
tar -C /root -czf "$backup/hermes-webui-source.tgz" hermes-webui
```

## Migration Steps

1. Install or refresh the official npm package:

```bash
env PATH=/opt/node-webui/current/bin:$PATH \
  /opt/node-webui/current/bin/npm install -g hermes-web-ui@latest
```

2. Verify the official package exists:

```bash
/opt/node-webui/current/bin/hermes-web-ui --version
test -f /opt/node-webui/current/lib/node_modules/hermes-web-ui/dist/server/index.js
```

3. Replace `/etc/systemd/system/hermes-webui.service` with a systemd-supervised official-package service:

```ini
[Unit]
Description=Hermes Web UI
After=network-online.target hermes-gateway.service
Wants=network-online.target
Requires=hermes-gateway.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/root
Environment="HOME=/root"
Environment="USER=root"
Environment="LOGNAME=root"
Environment="NODE_ENV=production"
Environment="PATH=/opt/node-webui/current/bin:/root/.hermes/hermes-agent/venv/bin:/root/.hermes/node/bin:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PORT=8648"
Environment="UPSTREAM=http://127.0.0.1:8642"
ExecStart=/opt/node-webui/current/bin/node /opt/node-webui/current/lib/node_modules/hermes-web-ui/dist/server/index.js
Restart=always
RestartSec=10
KillSignal=SIGTERM
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Note: no `HOST=127.0.0.1` is set because official `0.5.3` does not support it. The server may listen on `0.0.0.0:8648`; rely on the VPS security group and local firewall posture to prevent public access to `8648/tcp`.

4. Reload and restart:

```bash
systemctl daemon-reload
systemctl enable hermes-webui
systemctl restart hermes-webui
```

5. Verify service state:

```bash
systemctl is-active hermes-webui
systemctl is-enabled hermes-webui
journalctl -u hermes-webui -n 80 --no-pager
curl -fsS http://127.0.0.1:8648/health
ss -ltnp | grep ':8648\s'
```

6. Verify Nginx proxy:

```bash
nginx -t
curl -fsS -H 'Host: hermes.222046.xyz' http://127.0.0.1/health
```

7. Verify external conversation sync still works:

```bash
systemctl is-active hermes-webui-session-sync.timer
journalctl -u hermes-webui-session-sync.service -n 20 --no-pager
```

Then re-check source counts in `/root/.hermes-web-ui/hermes-web-ui.db`.

## Optional Built-In Update Button Test

Only run this in a maintenance window. It will reinstall the latest npm package and restart Web UI.

```bash
token="$(cat /root/.hermes-web-ui/.token)"
curl -fsS -X POST \
  -H "Authorization: Bearer $token" \
  http://127.0.0.1:8648/api/hermes/update
```

Expected behavior:

- API returns success after `npm install -g hermes-web-ui@latest`.
- Current server exits.
- systemd restarts `hermes-webui.service`.
- `/health` returns the same or newer `webui_version`.

If this test fails but the service is healthy after systemd restart, inspect:

```bash
journalctl -u hermes-webui -n 120 --no-pager
/opt/node-webui/current/bin/npm list -g --depth=0 | grep hermes-web-ui
```

## Cleanup Plan

Do not delete anything before the new official-package service has run stably and source counts still include external sessions.

Immediate safe cleanup after successful migration:

- Remove stale `~/.hermes-web-ui/server.pid` only if it exists and does not point to a running official CLI daemon.
- Stop any extra `hermes-web-ui` daemon process not owned by systemd if found.

Archive first, then delete after a retention window:

- `/root/hermes-webui`
  - Current source deployment. Redundant after systemd runs official npm package.
  - Keep archived as `hermes-webui-source.tgz` in the migration backup before deleting.

- `/root/.hermes/webui`
  - Old Web UI directory if still present.

- `/root/.hermes/webui-new`
  - Previous temporary Web UI clone if still present.

- `/root/hermes-webui/packages/server/data/hermes-web-ui.db`
  - Stale development-path DB from the earlier source deployment.
  - Only exists inside the old source tree.

- Old backup directories under `/root/backup/hermes-webui-*`
  - Keep the newest official migration backup.
  - Delete older backup directories only after confirming login, uploads, Web UI chat, Weixin groups, cron groups, and update behavior are stable.

Keep these:

- `/root/.hermes-web-ui`
- `/root/.hermes/scripts/sync_hermes_sessions_to_webui.py`
- `/etc/systemd/system/hermes-webui-session-sync.service`
- `/etc/systemd/system/hermes-webui-session-sync.timer`
- `/opt/node-webui/current`
- Nginx site config for `hermes.222046.xyz`

## Rollback Plan

If the official-package systemd service fails:

1. Restore the previous systemd unit from the backup:

```bash
cp "$backup/hermes-webui.service.current.txt" "$backup/hermes-webui.service.current.raw.txt"
```

The `systemctl cat` output includes comments and may need manual extraction of only the unit body before writing back to:

```bash
/etc/systemd/system/hermes-webui.service
```

2. Restore or unpack `/root/hermes-webui` from `hermes-webui-source.tgz` if it was removed.

3. Rebuild the source deployment if needed:

```bash
cd /root/hermes-webui
env PATH=/opt/node-webui/current/bin:$PATH /opt/node-webui/current/bin/npm ci
env PATH=/opt/node-webui/current/bin:$PATH /opt/node-webui/current/bin/npm run build
systemctl daemon-reload
systemctl restart hermes-webui
```

4. Restore Web UI DB only if data corruption occurred:

```bash
systemctl stop hermes-webui
sqlite3 /root/.hermes-web-ui/hermes-web-ui.db ".restore '$backup/hermes-web-ui.db'"
systemctl start hermes-webui
```

## Future Timer Removal

Do not disable `hermes-webui-session-sync.timer` until official Hermes Web UI supports continuous external-channel session sync.

Validation before disabling:

- Send a new Weixin message.
- Confirm the Weixin conversation group appears in Web UI without the timer running.
- Confirm message details are visible, not only the session title.
- Confirm cron sessions still appear after a new cron run.

Only then:

```bash
systemctl disable --now hermes-webui-session-sync.timer
```

Keep the script and service file for a short rollback window, then clean them later.
