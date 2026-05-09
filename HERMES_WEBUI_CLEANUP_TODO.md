# Hermes Web UI Cleanup TODO

Created: 2026-04-30
Target host: `foxjp`
Updated: 2026-05-01

## Current Good State

- `hermes-webui` is `active` and `enabled`.
- `hermes-gateway` is `active` and `enabled`.
- `hermes-webui-session-sync.timer` is `active` and `enabled`.
- Web UI now runs from the official npm package under systemd.
- Web UI listens on official default `0.0.0.0:8648`; VPS security group should keep `8648/tcp` closed to the public internet.
- Nginx proxies `hermes.222046.xyz` to `127.0.0.1:8648`.
- Web UI production DB is `/root/.hermes-web-ui/hermes-web-ui.db`.
- External Hermes sessions are mirrored from `/root/.hermes/state.db` into the Web UI DB every minute.
- `/root/hermes-webui` source deployment has been archived and removed.

## Cleanup Candidates

- `/root/hermes-webui/packages/server/data/hermes-web-ui.db`
  - Already removed together with `/root/hermes-webui`.

- `/root/backup/hermes-webui-20260430035209`
  - Main rollback backup from the reinstall/migration.
  - Contains old `webui-new`, Hermes data, config backups, and old Web UI state.
  - Size was about 2.5G when created.
  - Safe approach: keep for several days; if Web UI, Weixin groups, cron groups, uploads, and login token are stable, compress or remove.

- Smaller backups:
  - `/root/backup/hermes-webui-config-before-switch-20260430040003`
  - `/root/backup/hermes-webui-db-switch-20260430043419`
  - `/root/backup/hermes-webui-db-before-sync-20260430061011`
  - Safe approach: keep until the main rollback window closes, then prune together.

## Do Not Clean

- `/root/.hermes`
- `/root/.hermes-web-ui`
- `/root/.hermes/scripts/sync_hermes_sessions_to_webui.py`
- `/etc/systemd/system/hermes-webui.service`
- `/etc/systemd/system/hermes-webui-session-sync.service`
- `/etc/systemd/system/hermes-webui-session-sync.timer`
- `/opt/node-webui/current`

## Verification Before Cleanup

Run on `foxjp`:

```bash
systemctl is-active hermes-webui hermes-gateway hermes-webui-session-sync.timer
systemctl is-enabled hermes-webui hermes-gateway hermes-webui-session-sync.timer
curl -fsS http://127.0.0.1:8648/health
journalctl -u hermes-webui-session-sync.service -n 20 --no-pager
```

Check DB sources:

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

## Reminder

After 2026-05-03, review this document and decide whether to prune old Web UI backup directories after confirming official npm-package Web UI, built-in update, Weixin groups, cron groups, uploads, and login token are stable.
