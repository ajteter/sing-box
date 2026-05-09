# FOXJP AIClient-2-API 部署方案

最后更新：2026-04-30

## 目标

在 foxjp 上部署 [justlovemaki/AIClient-2-API](https://github.com/justlovemaki/AIClient-2-API)，用于把 Gemini CLI、Antigravity、Codex、Kiro、Grok 等客户端侧能力转换成 OpenAI 兼容 API。

本方案只覆盖初始部署，不包含自动更新脚本、监控告警、定时健康检查。

## 结论

推荐使用 Docker Compose 部署到 `/opt/aiclient2api`，数据持久化到 `/opt/aiclient2api/configs`，所有容器端口只绑定 `127.0.0.1`，再用 Nginx 给 Web UI 暴露一个子域名。

建议子域名：

```text
a2a.222046.xyz
```

建议本机监听：

```text
127.0.0.1:3000
```

## 当前 foxjp 端口状态

2026-04-30 复查时，foxjp 监听端口如下：

```text
0.0.0.0:80             nginx
0.0.0.0:22             sshd
127.0.0.1:2099         Manifest Docker
127.0.0.1:8642         Hermes gateway
127.0.0.1:8648         Hermes Web UI
*:40000                sing-box
```

当前 Docker 容器：

```text
mnfst-manifest-1       manifestdotbuild/manifest:latest   127.0.0.1:2099->2099/tcp
mnfst-postgres-1       postgres:16-alpine                 5432/tcp
```

AIClient-2-API 官方默认端口与现有服务没有冲突。

## 官方端口说明

AIClient-2-API 官方 README 的 Docker 示例使用以下端口：

```text
3000           Web UI
8085           Gemini OAuth callback
8086           Antigravity OAuth callback
1455           Codex OAuth callback
19876-19880    Kiro OAuth callback
```

部署时不要把这些 OAuth callback 端口直接暴露到公网。Web UI 可以通过 Nginx 子域名访问，OAuth 授权端口建议只绑定本机，必要时从本地电脑用 SSH tunnel 转发。

## 部署目录

建议目录：

```text
/opt/aiclient2api
/opt/aiclient2api/configs
```

`configs` 是持久化目录。以后重建容器、升级镜像时，应保留这个目录。

## Docker Compose 配置

在 `/opt/aiclient2api/compose.yaml` 写入：

```yaml
services:
  aiclient2api:
    image: justlikemaki/aiclient-2-api:latest
    container_name: aiclient2api
    restart: unless-stopped
    ports:
      - "127.0.0.1:3000:3000"
      - "127.0.0.1:8085:8085"
      - "127.0.0.1:8086:8086"
      - "127.0.0.1:1455:1455"
      - "127.0.0.1:19876-19880:19876-19880"
    volumes:
      - ./configs:/app/configs
    environment:
      - ARGS=
```

说明：

- 官方示例使用 `--restart=always`；这里建议 `unless-stopped`，便于手动停用后不被 Docker 自动拉起。
- `latest` 适合跟随项目快速更新；如果后续追求稳定，应在部署后记录 image digest，再另写更新策略。
- 所有端口都绑定 `127.0.0.1`，避免绕过 Nginx 直接公网访问。

## 部署命令

执行前先确认 Docker Compose 可用：

```bash
docker compose version
```

创建目录并启动：

```bash
mkdir -p /opt/aiclient2api/configs
cd /opt/aiclient2api
docker compose up -d
```

查看容器：

```bash
docker ps --filter name=aiclient2api
docker logs --tail=100 aiclient2api
```

本机验证：

```bash
curl -fsS http://127.0.0.1:3000/
ss -ltnp | grep -E '3000|8085|8086|1455|1987[6-9]|19880'
```

## Nginx 反代方案

建议新增 Nginx server block：

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name a2a.222046.xyz;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

检查并重载：

```bash
nginx -t
systemctl reload nginx
```

Cloudflare 侧需要给 `a2a.222046.xyz` 配置到 foxjp。是否开启 Cloudflare 代理都可以；如果只暴露 Web UI，开启代理更合适。OAuth callback 端口不走公网 DNS。

## 首次登录和安全设置

官方默认 Web UI 密码是：

```text
admin123
```

首次登录后应立即修改密码，并生成或调整 API Key。不要把管理 UI 直接裸露在公网端口上。

如果需要进一步限制访问，可以二选一：

- 用 Nginx Basic Auth 保护 `a2a.222046.xyz`。
- 只允许特定 IP 访问该 server block。

如果 AIClient-2-API 自身登录机制足够使用，可以先不加 Basic Auth，避免和应用内登录重复。

## OAuth 授权方式

因为 OAuth callback 端口只绑定在 foxjp 的 `127.0.0.1`，本地浏览器授权时需要 SSH tunnel。

建议命令：

```bash
ssh \
  -L 3000:127.0.0.1:3000 \
  -L 8085:127.0.0.1:8085 \
  -L 8086:127.0.0.1:8086 \
  -L 1455:127.0.0.1:1455 \
  -L 19876:127.0.0.1:19876 \
  -L 19877:127.0.0.1:19877 \
  -L 19878:127.0.0.1:19878 \
  -L 19879:127.0.0.1:19879 \
  -L 19880:127.0.0.1:19880 \
  foxjp
```

然后本地访问：

```text
http://127.0.0.1:3000
```

授权完成后，相关凭据应落到 `/opt/aiclient2api/configs` 或应用配置指定的位置。

## 验收标准

部署完成后应满足：

- `docker ps` 中存在 `aiclient2api`，状态为 running。
- `curl http://127.0.0.1:3000/` 有正常响应。
- `ss -ltnp` 显示 AIClient-2-API 端口全部绑定在 `127.0.0.1`。
- `nginx -t` 通过。
- `http://a2a.222046.xyz` 能访问 Web UI。
- 默认密码已修改。
- `/opt/aiclient2api/configs` 中有配置或凭据文件，重建容器后不会丢失。

## 后续待办

当前不实施，但后续可以补：

- 更新流程：拉取新镜像、备份 configs、重建容器、失败回滚。
- 监控脚本：检查容器运行状态、Web UI HTTP 状态、关键 provider 健康状态。
- 备份策略：定期备份 `/opt/aiclient2api/configs`。
- Nginx 访问控制：按需增加 Basic Auth、IP allowlist 或 Cloudflare Access。
