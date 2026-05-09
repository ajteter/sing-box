# FOXJP Security Group Policy

Created: 2026-05-08
Target host: `foxjp`

This document records the intended public security group posture for `foxjp`
based on the services that were running during the migration review.

## Baseline Principle

Only the edge entry points should be reachable from the public internet.
Application management ports must stay private and be reached through
`127.0.0.1`, Nginx reverse proxy, SSH tunnel, or a dedicated private network.

## Publicly Allowed Ports

Keep these open only while the corresponding service is still hosted on
`foxjp`.

| Port | Protocol | Purpose | Notes |
| --- | --- | --- | --- |
| `22` | TCP | SSH administration | Prefer limiting source IPs to trusted operator IPs when possible. |
| `80` | TCP | Nginx HTTP entry | Serves/reverse-proxies `hermes.222046.xyz`, `manifest.222046.xyz`, historical `a2a.222046.xyz`, and `sub.222046.xyz`. |
| `40000` | TCP | sing-box VLESS Reality | Required only while `foxjp` remains the sing-box public ingress. |
| `40001` | UDP | sing-box Hysteria2 | Required only while `foxjp` remains the sing-box public ingress. |
| `40002` | UDP | sing-box TUIC | Required only while `foxjp` remains the sing-box public ingress. |

## Publicly Closed Ports

These must not be reachable directly from the public internet.

| Port | Protocol | Service | Expected access path |
| --- | --- | --- | --- |
| `8648` | TCP | Hermes Web UI | Nginx `hermes.222046.xyz` -> `127.0.0.1:8648`. The Web UI may listen on `0.0.0.0`, so the VPS security group must block this port. |
| `8642` | TCP | Hermes gateway | Localhost/internal only. |
| `2099` | TCP | Manifest | Nginx `manifest.222046.xyz` -> `127.0.0.1:2099`. |
| `3000` | TCP | AIClient-2-API Web UI | Nginx `a2a.222046.xyz` -> `127.0.0.1:3000`; no longer needed after a2a retirement. |
| `8085` | TCP | Gemini OAuth callback | Localhost/SSH tunnel only. |
| `8086` | TCP | Antigravity OAuth callback | Localhost/SSH tunnel only. |
| `1455` | TCP | Codex OAuth callback | Localhost/SSH tunnel only. |
| `19876-19880` | TCP | Kiro OAuth callback | Localhost/SSH tunnel only. |
| `5432` | TCP | Postgres | Docker/internal only. Never public. |

Docker bridge/internal network ports should not be exposed directly.

## Current Service Mapping At Review Time

| Domain | Public entry | Internal target | Status |
| --- | --- | --- | --- |
| `hermes.222046.xyz` | `80/tcp` via Nginx | `127.0.0.1:8648` | Migrating to `homerp4`; keep only until cutover. |
| `manifest.222046.xyz` | `80/tcp` via Nginx | `127.0.0.1:2099` | Migrating to `homerp4`; keep only until cutover. |
| `a2a.222046.xyz` | `80/tcp` via Nginx | `127.0.0.1:3000` | No longer needed. Can be retired. |
| `sub.222046.xyz` | `80/tcp` via Nginx | `/var/www/sub` | To remain on `foxjp` if sing-box remains there. |

## Retirement Sequence

Use this order when reducing the foxjp attack surface.

1. Retire AIClient-2-API / `a2a`.
   - Remove or disable the `a2a.222046.xyz` Nginx vhost.
   - Ensure `3000`, `8085`, `8086`, `1455`, and `19876-19880` remain closed publicly.

2. Cut over Manifest.
   - After `homerp4` Manifest is confirmed healthy, remove or disable the `manifest.222046.xyz` Nginx vhost on `foxjp`.
   - Keep `2099/tcp` closed publicly throughout.

3. Cut over Hermes and Hermes Web UI.
   - After Hermes data and Web UI conversation state are restored elsewhere, remove or disable `hermes.222046.xyz` on `foxjp`.
   - Keep `8648/tcp` and `8642/tcp` closed publicly throughout.

4. Decide sing-box fate.
   - If `foxjp` no longer serves sing-box, close `40000/tcp`, `40001/udp`, and `40002/udp`.
   - If sing-box stays on `foxjp`, keep only those sing-box ingress ports plus `22/tcp` and `80/tcp`.

## Verification Commands

Run on `foxjp`:

```bash
ss -ltnup
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
systemctl is-active nginx sing-box hermes-gateway hermes-webui
```

Expected application posture:

- AIClient-2-API ports bind to `127.0.0.1` only.
- Manifest binds to `127.0.0.1:2099` only.
- Hermes gateway binds to `127.0.0.1:8642`.
- Hermes Web UI may bind to `0.0.0.0:8648`; security group must block direct public access.
- Nginx is the only public HTTP entry on `80/tcp`.

## Notes

- Do not publish full sing-box subscription files or generated client configs in logs or chat. They contain credentials.
- Do not expose Postgres or OAuth callback ports publicly.
- Prefer Cloudflare/Nginx/domain-level controls for web applications and security group controls for direct port exposure.
