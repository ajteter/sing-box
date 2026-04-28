# foxjp Sing-box 维护说明

本文档记录 foxjp 上 `sing-box` 的实际部署方式、稳定版锁定策略，以及给 Hermes 监控/更新脚本使用的检查流程。

## 当前部署状态

- VPS: `foxjp`
- 服务: `sing-box.service`
- 服务文件: `/etc/systemd/system/sing-box.service`
- 核心二进制: `/etc/sing-box/sing-box`
- 配置目录: `/etc/sing-box/conf`
- fscarmen 管理脚本: `/etc/sing-box/sb.sh`
- 客户端订阅: `/var/www/sub/mihomo.yaml`
- CN 规则文件:
  - `/var/www/sub/rules/cn-domain.mrs`
  - `/var/www/sub/rules/cn-ip.mrs`
- CN 规则同步 timer: `mihomo-cn-rules-update.timer`

当前协议端口：

```text
40000/tcp  VLESS Reality
40001/udp  Hysteria2
40002/udp  TUIC
```

当前要求：

```text
sing-box 核心必须使用 SagerNet/sing-box 官方 stable release。
不要追 alpha / beta / rc / prerelease。
```

## fscarmen 脚本使用原则

foxjp 的 `sing-box` 是通过 `fscarmen/sing-box` 安装和生成配置的，但核心二进制已经手动锁定为官方稳定版。

重要规则：

- 不要直接用 fscarmen 脚本执行核心更新。
- 不要无人值守运行 `/etc/sing-box/sb.sh` 或 `sb` 来升级，因为脚本可能拉到 alpha/rc。
- fscarmen 只作为配置/服务生成工具。
- 版本监控和核心更新必须以 `SagerNet/sing-box` 的 stable release 为准。
- 如果以后手动用 `sb` 改协议或重装配置，完成后必须再次检查 `/etc/sing-box/sing-box version`，必要时重新锁回 stable。

## 日常监控命令

```bash
systemctl is-enabled sing-box
systemctl is-active sing-box
/etc/sing-box/sing-box version | head -n 1
ss -ltnup | grep -E '40000|40001|40002|sing-box'
systemctl is-enabled mihomo-cn-rules-update.timer
systemctl is-active mihomo-cn-rules-update.timer
systemctl --failed --no-pager
```

当前版本获取：

```bash
current=$(/etc/sing-box/sing-box version | awk '/^sing-box version/{print $3}')
echo "$current"
```

## 获取上游 stable 版本

foxjp 默认没有 `jq`，建议用 Python 查询 GitHub API，并跳过 draft/prerelease：

```bash
python3 - <<'PY'
import json
import urllib.request

url = "https://api.github.com/repos/SagerNet/sing-box/releases?per_page=30"
data = json.load(urllib.request.urlopen(url, timeout=20))

for release in data:
    if release.get("draft") or release.get("prerelease"):
        continue

    tag = release["tag_name"]
    version = tag.lstrip("v")
    wanted = f"sing-box-{version}-linux-amd64.tar.gz"

    for asset in release["assets"]:
        if asset["name"] == wanted:
            print(version, asset["browser_download_url"])
            raise SystemExit(0)

raise SystemExit("no stable linux-amd64 asset found")
PY
```

监控脚本应只提醒有新的 stable 版本。默认不建议自动升级，因为 `sing-box` 偶尔会有配置兼容性变化。

## 安全更新流程

如果要执行核心更新，必须按以下流程：

1. 下载官方 stable tar.gz。
2. 解压出新的 `sing-box`。
3. 先执行配置检查。
4. 检查通过后备份旧二进制。
5. 替换 `/etc/sing-box/sing-box`。
6. 重启 `sing-box`。
7. 验证服务状态和监听端口。
8. 如果失败，恢复旧二进制并重启。

示例流程：

```bash
set -euo pipefail

version="1.13.8"
url="https://github.com/SagerNet/sing-box/releases/download/v${version}/sing-box-${version}-linux-amd64.tar.gz"
workdir="/tmp/sing-box-update-${version}"

rm -rf "$workdir"
mkdir -p "$workdir"
cd "$workdir"

curl -fL -o "sing-box-${version}-linux-amd64.tar.gz" "$url"
tar -xzf "sing-box-${version}-linux-amd64.tar.gz"

new_bin="$workdir/sing-box-${version}-linux-amd64/sing-box"
"$new_bin" version
"$new_bin" check -C /etc/sing-box/conf

backup="/etc/sing-box/sing-box.bak.$(date +%Y%m%d%H%M%S)"
cp /etc/sing-box/sing-box "$backup"
install -m 0755 "$new_bin" /etc/sing-box/sing-box

systemctl restart sing-box
systemctl is-active sing-box
/etc/sing-box/sing-box version | head -n 1
ss -ltnup | grep -E '40000|40001|40002|sing-box'
```

回滚流程：

```bash
install -m 0755 /etc/sing-box/sing-box.bak.YYYYMMDDHHMMSS /etc/sing-box/sing-box
systemctl restart sing-box
systemctl is-active sing-box
```

## 订阅和规则说明

订阅文件：

```text
https://sub.222046.xyz/mihomo.yaml
```

`mihomo.yaml` 使用 `rule-providers`，不依赖客户端本地 `geosite.dat` / `geoip.dat` 自动更新。

规则同步服务：

```text
mihomo-cn-rules-update.service
mihomo-cn-rules-update.timer
```

同步频率：

```ini
OnBootSec=5min
OnUnitActiveSec=1d
Persistent=true
```

上游规则源：

```text
https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/geosite/cn.mrs
https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/geoip/cn.mrs
```

## 日志安全

不要把以下文件的完整内容写进日志或聊天记录：

```text
/var/www/sub/mihomo.yaml
/etc/sing-box/subscribe/proxies
/etc/sing-box/subscribe/clash2
```

这些文件里包含 UUID、password、Reality public key 等节点信息。

