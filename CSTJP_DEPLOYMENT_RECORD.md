# CSTJP Deployment Record

Last updated: 2026-05-09

This document records the deployment information reconstructed from the conversation history. The old host was temporarily named `csthk` / SSH alias `cst`, but the updated VPS name is `cstjp` and the updated public IP is:

```text
154.36.154.227
```

The old host is no longer reachable, so the status below is historical deployment information, not a fresh verification result.

## Host

```text
Name: cstjp
Public IP: 154.36.154.227
Old SSH alias used during deployment: cst
OS observed during deployment: Ubuntu 24.04.1 LTS
Architecture observed during deployment: x86_64
User observed during deployment: root
```

## Architecture

The deployment used Nginx as the public HTTP entrypoint, Docker Compose for web applications, and a direct systemd service for sing-box.

```text
Internet
  |
  |-- 80/tcp -> Nginx
  |      |-- manifest.222046.xyz -> 127.0.0.1:2099
  |      |-- a2a.222046.xyz      -> 127.0.0.1:3000
  |      `-- sub.222046.xyz      -> /var/www/sub
  |
  |-- 40000/tcp -> sing-box VLESS Reality
  |-- 40001/udp -> sing-box Hysteria2
  `-- 40002/udp -> sing-box TUIC
```

Application ports were intentionally bound to `127.0.0.1` where possible. Only Nginx and sing-box protocol ports were intended to be publicly reachable.

## Base Packages

The following packages were installed:

```text
nginx
docker.io
docker-compose-v2
```

Observed versions during deployment:

```text
Docker: 29.1.3
Docker Compose: 2.40.3
Nginx: 1.24.0
```

Services enabled or expected to be active:

```text
docker
nginx
sing-box
mihomo-cn-rules-update.timer
```

## Manifest

Manifest was installed using the official Docker Compose self-host deployment from:

```text
https://github.com/mnfst/manifest
```

Deployment directory:

```text
/root/manifest
```

Expected containers:

```text
mnfst-manifest-1
mnfst-postgres-1
```

Expected local port binding:

```text
127.0.0.1:2099 -> manifest container port 2099
```

Important environment variables in `/root/manifest/.env`:

```text
BETTER_AUTH_SECRET=<generated secret>
BETTER_AUTH_URL=https://manifest.222046.xyz
```

`BETTER_AUTH_URL` was changed from HTTP to HTTPS because login returned `Invalid origin`.

Nginx route:

```text
manifest.222046.xyz -> http://127.0.0.1:2099
```

Historical verification:

```text
/api/v1/health returned {"status":"healthy", ...}
mnfst-manifest-1 was healthy
mnfst-postgres-1 was healthy
```

## AIClient-2-API

Deployment directory:

```text
/opt/aiclient2api
```

Persistent configuration directory:

```text
/opt/aiclient2api/configs
```

Compose file:

```text
/opt/aiclient2api/compose.yaml
```

Image:

```text
justlikemaki/aiclient-2-api:latest
```

Container name:

```text
aiclient2api
```

Expected port bindings:

```text
127.0.0.1:3000        -> Web UI
127.0.0.1:8085        -> Gemini OAuth callback
127.0.0.1:8086        -> Antigravity OAuth callback
127.0.0.1:1455        -> Codex OAuth callback
127.0.0.1:19876-19880 -> Kiro OAuth callback
```

Nginx route:

```text
a2a.222046.xyz -> http://127.0.0.1:3000
```

Security note:

```text
OAuth callback ports should stay bound to 127.0.0.1 and should not be opened publicly.
```

Historical verification:

```text
aiclient2api container was healthy
GET / through Nginx host routing returned 200 OK
```

## sing-box

sing-box was installed directly on the host, not through Docker.

Source policy:

```text
Use official SagerNet/sing-box stable releases only.
Do not use alpha, beta, rc, prerelease, or unattended fscarmen updates.
```

Installed version:

```text
sing-box 1.13.11
```

Binary:

```text
/etc/sing-box/sing-box
```

Config directory:

```text
/etc/sing-box/conf
```

Systemd unit:

```text
/etc/systemd/system/sing-box.service
```

Expected service command:

```text
/etc/sing-box/sing-box run -C /etc/sing-box/conf
```

Migrated config files:

```text
/etc/sing-box/conf/00_log.json
/etc/sing-box/conf/01_outbounds.json
/etc/sing-box/conf/02_endpoints.json
/etc/sing-box/conf/03_route.json
/etc/sing-box/conf/04_experimental.json
/etc/sing-box/conf/05_dns.json
/etc/sing-box/conf/06_ntp.json
/etc/sing-box/conf/11_xtls-reality_inbounds.json
/etc/sing-box/conf/12_hysteria2_inbounds.json
/etc/sing-box/conf/13_tuic_inbounds.json
```

Protocol ports:

```text
40000/tcp VLESS Reality
40001/udp Hysteria2
40002/udp TUIC
```

The server-side sing-box config listened on wildcard addresses such as `::` and did not directly depend on the public IP. The subscription files did contain the old IP and were updated.

For the updated `cstjp` host, subscription entries should use:

```text
server: 154.36.154.227
```

Node naming was changed from `foxjp` to `csthk` during the old deployment. For the updated host, the intended final node name should be:

```text
cstjp
```

Files that contain node names and server addresses:

```text
/etc/sing-box/conf/11_xtls-reality_inbounds.json
/etc/sing-box/conf/12_hysteria2_inbounds.json
/etc/sing-box/conf/13_tuic_inbounds.json
/var/www/sub/mihomo.yaml
/var/www/sub/proxies.generated.yaml
```

Recommended correction for the updated host:

```text
Replace node name: csthk -> cstjp
Replace old server IP: 154.64.247.161 -> 154.36.154.227
```

Historical verification:

```text
sing-box check -C /etc/sing-box/conf passed
sing-box.service was active
40000/tcp, 40001/udp, and 40002/udp were listening
```

## Subscription Static Site

Static directory:

```text
/var/www/sub
```

Nginx route:

```text
sub.222046.xyz -> /var/www/sub
```

Important files:

```text
/var/www/sub/mihomo.yaml
/var/www/sub/proxies.generated.yaml
/var/www/sub/rules/cn-domain.mrs
/var/www/sub/rules/cn-ip.mrs
```

For the updated `cstjp` host, `mihomo.yaml` and `proxies.generated.yaml` should use:

```text
Node prefix/name: cstjp
Server IP: 154.36.154.227
```

Do not paste full subscription files into tickets, chat, or logs. They contain credentials.

## CN Rule Updates

Update script:

```text
/usr/local/sbin/update-mihomo-cn-rules.sh
```

Systemd service:

```text
/etc/systemd/system/mihomo-cn-rules-update.service
```

Systemd timer:

```text
/etc/systemd/system/mihomo-cn-rules-update.timer
```

Timer policy:

```ini
OnBootSec=5min
OnUnitActiveSec=1d
Persistent=true
```

Rule sources:

```text
https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/geosite/cn.mrs
https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/geoip/cn.mrs
```

Deployment note:

The first hand-written copy of the update script had shell variables expanded too early. It was fixed by copying the working script from `foxjp`, then running the service successfully.

## Nginx

Expected config files:

```text
/etc/nginx/conf.d/manifest.conf
/etc/nginx/conf.d/aiclient.conf
/etc/nginx/conf.d/sub.conf
```

Expected host mappings:

```text
manifest.222046.xyz -> http://127.0.0.1:2099
a2a.222046.xyz      -> http://127.0.0.1:3000
sub.222046.xyz      -> /var/www/sub
```

Expected public listener:

```text
80/tcp
```

HTTPS was not terminated directly on the VPS during the recorded deployment. `BETTER_AUTH_URL` was set to HTTPS for the external access URL, so HTTPS is expected to be provided by the upstream DNS/proxy/tunnel layer if no local TLS certificate is installed.

## Firewall And Security Group

Expected public ingress:

```text
22/tcp    SSH
80/tcp    Nginx HTTP
40000/tcp sing-box VLESS Reality
40001/udp sing-box Hysteria2
40002/udp sing-box TUIC
```

Ports that should not be publicly opened:

```text
2099
3000
8085
8086
1455
19876-19880
5432
```

## Operational Checks

Useful commands:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
systemctl is-active nginx docker sing-box mihomo-cn-rules-update.timer
systemctl --failed --no-pager
nginx -t
/etc/sing-box/sing-box check -C /etc/sing-box/conf
ss -ltnup | grep -E '(:80|:22|:2099|:3000|:8085|:8086|:1455|:1987[6-9]|:19880|:40000|:40001|:40002)'
curl -fsS -H 'Host: manifest.222046.xyz' http://127.0.0.1/api/v1/health
curl -I -sS -H 'Host: a2a.222046.xyz' http://127.0.0.1/
curl -I -sS -H 'Host: sub.222046.xyz' http://127.0.0.1/mihomo.yaml
```

For `cstjp`, also check that old host labels and old IPs are gone:

```bash
grep -RIn -- 'foxjp\|csthk\|154.64.247.161\|64.83.43.146' /etc/sing-box /var/www/sub 2>/dev/null
```

Expected result after correction:

```text
No foxjp labels
No csthk labels
No old IPs
Only cstjp labels and 154.36.154.227 as the subscription server IP
```

## Sensitive Information Policy

Do not store the following directly in this document:

```text
UUIDs
passwords
Reality private keys
full subscription files
full AIClient credential files
Manifest secrets
```

This document intentionally records paths, ports, services, domains, and recovery notes only.

## Follow-up Items

```text
1. Update SSH alias from cst to cstjp if needed.
2. Recreate or migrate files to the new cstjp host.
3. Replace subscription server IP with 154.36.154.227.
4. Replace node labels with cstjp.
5. Confirm DNS records point to the new IP or proxy target.
6. Confirm VPS security group allows 80/tcp, 40000/tcp, 40001/udp, and 40002/udp.
7. Decide whether a2a.222046.xyz should remain enabled.
8. Re-run all operational checks after the new host is reachable.
```
