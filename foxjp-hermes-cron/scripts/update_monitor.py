#!/usr/bin/env python3
"""VPS monitoring report for Hermes cron.

This script only prints Markdown (or [SILENT]). Delivery is handled by Hermes Cron
Delivery, not by this script.
"""
import json
import os
import re
import subprocess
from datetime import datetime
from html import unescape
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

DISK_THRESHOLD = 60.0
US10Y_THRESHOLD = 4.55
DXY_THRESHOLD = 106.5

GITHUB_API = "https://api.github.com"
UA = "Mozilla/5.0 (compatible; HermesUpdateMonitor/1.0)"


def load_github_token():
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        return token

    env_path = os.path.expanduser("~/.hermes/.env")
    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key.startswith("export "):
                    key = key[len("export "):].strip()
                if key == "GITHUB_TOKEN":
                    return value.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


GITHUB_TOKEN = load_github_token()


def run_cmd(cmd, timeout=30):
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=timeout).strip()


def http_json(url, timeout=20):
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_json_or_default(url, default, timeout=20):
    try:
        return http_json(url, timeout=timeout)
    except Exception:
        return default


def http_text(url, timeout=20):
    headers = {"User-Agent": UA}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def is_stable_tag(tag):
    return bool(tag) and not re.search(r"(alpha|beta|rc|pre|preview|dev|nightly|canary)", tag, re.I)


def normalize_version(tag):
    if not tag:
        return ""
    s = tag.strip()
    s = re.sub(r"^refs/tags/", "", s)
    s = re.sub(r"\^\{\}$", "", s)
    s = s.lstrip("vV")
    # git describe: v2026.4.23-398-g4b5a88d7 -> 2026.4.23
    s = re.sub(r"-\d+-g[0-9a-f]+.*$", "", s)
    return s


def version_key(tag):
    """Return a sortable key for common numeric tags; fallback is string."""
    s = normalize_version(tag)
    nums = re.findall(r"\d+", s)
    if nums:
        return (1, tuple(int(n) for n in nums), s)
    return (0, tuple(), s)


def same_version(local, remote):
    return normalize_version(local) == normalize_version(remote)


def get_github_latest_release(repo):
    data = http_json(f"{GITHUB_API}/repos/{repo}/releases/latest")
    tag = data.get("tag_name", "")
    return tag if is_stable_tag(tag) else ""


def get_github_release_by_tag(repo, tag):
    if not tag:
        return {}
    data = http_json(f"{GITHUB_API}/repos/{repo}/releases/tags/{tag}")
    return data if isinstance(data, dict) else {}


def get_github_releases(repo, per_page=30):
    data = http_json_or_default(f"{GITHUB_API}/repos/{repo}/releases?per_page={per_page}", [])
    return data if isinstance(data, list) else []


def get_github_tags(repo, per_page=100):
    data = http_json(f"{GITHUB_API}/repos/{repo}/tags?per_page={per_page}")
    return data if isinstance(data, list) else []


def get_github_tags_or_default(repo, per_page=100, default=None):
    if default is None:
        default = []
    data = http_json_or_default(f"{GITHUB_API}/repos/{repo}/tags?per_page={per_page}", default)
    return data if isinstance(data, list) else default


def get_github_latest_stable_tag(repo):
    # GitHub tags API is the source for hermes-webui. Fetch first 100 and choose
    # highest stable numeric tag to avoid depending on release objects.
    tags = http_json(f"{GITHUB_API}/repos/{repo}/tags?per_page=100")
    names = [t.get("name", "") for t in tags if is_stable_tag(t.get("name", ""))]
    if not names:
        return ""
    return max(names, key=version_key)


def get_local_sing_box():
    out = run_cmd(["/etc/sing-box/sing-box", "version"])
    m = re.search(r"sing-box version\s+([^\s]+)", out)
    return m.group(1) if m else out.splitlines()[0]


def get_local_git_tag(path):
    return run_cmd(["/usr/bin/git", "-C", path, "describe", "--tags", "--always", "--dirty"])


def docker_manifest_digest(image):
    raw = run_cmd(["/usr/bin/docker", "manifest", "inspect", "--verbose", image], timeout=60)
    data = json.loads(raw)
    if isinstance(data, dict):
        desc = data.get("Descriptor") or data.get("descriptor") or {}
        digest = desc.get("digest") or data.get("Digest") or data.get("digest")
        if digest:
            return digest
        # Non-verbose fallback may contain config/layers only; no top-level digest.
        return ""
    if isinstance(data, list):
        # Prefer linux/amd64 entry for this VPS.
        for item in data:
            platform = item.get("Descriptor", {}).get("platform") or item.get("Platform") or item.get("platform") or {}
            os_name = platform.get("os") or platform.get("OS")
            arch = platform.get("architecture") or platform.get("Architecture")
            digest = (item.get("Descriptor") or {}).get("digest") or item.get("Digest") or item.get("digest")
            if os_name == "linux" and arch == "amd64" and digest:
                return digest
        for item in data:
            digest = (item.get("Descriptor") or {}).get("digest") or item.get("Digest") or item.get("digest")
            if digest:
                return digest
    return ""


def get_local_manifest_info(container="mnfst-manifest-1"):
    container_raw = run_cmd(["/usr/bin/docker", "inspect", container], timeout=30)
    container_data = json.loads(container_raw)[0]
    image_ref = container_data.get("Config", {}).get("Image", "")
    image_id = container_data.get("Image", "")

    repo_digests = []
    labels = {}
    try:
        image_raw = run_cmd(["/usr/bin/docker", "image", "inspect", image_id], timeout=30)
        image_data = json.loads(image_raw)[0]
        repo_digests = image_data.get("RepoDigests") or []
        labels = image_data.get("Config", {}).get("Labels") or {}
    except Exception:
        pass

    return {
        "image_ref": image_ref,
        "image_id": image_id,
        "repo_digests": repo_digests,
        "revision": labels.get("org.opencontainers.image.revision") or labels.get("revision") or "",
        "version": labels.get("org.opencontainers.image.version") or labels.get("version") or "",
    }


def short_sha(revision, length=7):
    if not revision:
        return ""
    return revision[:length]


def is_generic_manifest_version(version):
    if not version:
        return True
    return version.strip().lower() in {"main", "master", "latest", "edge", "nightly", "dev"}


def format_manifest_local_build(local):
    version = (local.get("version") or "").strip()
    revision = (local.get("revision") or "").strip()
    image_ref = local.get("image_ref") or ""
    image_id = local.get("image_id") or ""
    short_revision = short_sha(revision)

    if version and not is_generic_manifest_version(version):
        return version
    if version and short_revision:
        return f"{version}@{short_revision}"
    if short_revision:
        return short_revision
    if version:
        return version
    return image_ref or image_id[:19]


def get_release_commit_sha(repo, tag):
    release = get_github_release_by_tag(repo, tag)
    target_commitish = (release.get("target_commitish") or "").strip()
    if re.fullmatch(r"[0-9a-f]{7,40}", target_commitish, re.I):
        return target_commitish
    body = release.get("body") or ""
    patterns = [
        r"[Cc]ommit:\s*`?([0-9a-f]{7,40})`?",
        r"\(([0-9a-f]{7,40})\)",
        r"\b([0-9a-f]{40})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, body)
        if match:
            return match.group(1)
    return ""


def resolve_github_tag_commit_sha(tag_item):
    commit = (tag_item.get("commit") or {}) if isinstance(tag_item, dict) else {}
    commit_sha = (commit.get("sha") or "").strip()
    commit_url = (commit.get("url") or "").strip()
    if not commit_sha:
        return ""
    if not commit_url:
        return commit_sha
    try:
        data = http_json(commit_url)
    except Exception:
        return commit_sha
    if isinstance(data, dict):
        tag_object = (data.get("object") or {})
        if (tag_object.get("type") or "").strip().lower() == "commit":
            object_sha = (tag_object.get("sha") or "").strip()
            if object_sha:
                return object_sha
    return commit_sha


def find_manifest_release_for_revision(repo, revision, per_page=30):
    revision = (revision or "").strip().lower()
    if not revision:
        return ""

    releases = get_github_releases(repo, per_page=per_page)
    for release in releases:
        tag_name = (release.get("tag_name") or "").strip()
        if not is_stable_tag(tag_name):
            continue
        target_commitish = (release.get("target_commitish") or "").strip().lower()
        if target_commitish and revision == target_commitish:
            return tag_name
        release_sha = get_release_commit_sha(repo, tag_name).strip().lower()
        if release_sha and revision == release_sha:
            return tag_name

    tags = get_github_tags_or_default(repo, per_page=per_page)
    for item in tags:
        tag_name = item.get("name", "")
        if not is_stable_tag(tag_name):
            continue
        commit_sha = resolve_github_tag_commit_sha(item).strip().lower()
        if commit_sha and revision == commit_sha:
            return tag_name
    return ""



def get_tradingview_price(symbol):
    html = http_text(f"https://www.tradingview.com/symbols/TVC-{symbol}/", timeout=20)

    patterns = [
        r'data-last-price=["\']([^"\']+)["\']',
        r'"last_price"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
        r'"price"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return float(unescape(m.group(1)).replace(",", ""))

    # JSON-LD / meta fallback: choose a nearby numeric value after symbol mention.
    idx = html.find(f"TVC:{symbol}")
    if idx != -1:
        chunk = html[idx:idx + 5000]
        m = re.search(r'([0-9]+(?:\.[0-9]+)?)', chunk)
        if m:
            return float(m.group(1))
    raise RuntimeError(f"Unable to parse TradingView price for {symbol}")


def check_disk(alerts, diagnostics):
    stat = os.statvfs("/")
    usage = (stat.f_blocks - stat.f_bfree) * 100 / stat.f_blocks
    diagnostics.append(f"disk / = {usage:.1f}%")
    if usage > DISK_THRESHOLD:
        alerts.append(f"- ⚠️ 磁盘告警: `/` 使用率 {usage:.1f}% > {DISK_THRESHOLD:.0f}%")


def check_versions(alerts, diagnostics):
    diagnostics.append(f"github token configured={'yes' if GITHUB_TOKEN else 'no'}")
    # sing-box: GitHub releases/latest
    try:
        local = get_local_sing_box()
        remote = get_github_latest_release("SagerNet/sing-box")
        diagnostics.append(f"sing-box local={local} remote={remote}")
        if remote and not same_version(local, remote):
            alerts.append(f"- 🔄 服务更新: sing-box `{local}` → `{remote}`")
    except Exception as e:
        diagnostics.append(f"sing-box check failed: {e}")

    # hermes-agent: GitHub releases/latest. Local may be ahead of latest release;
    # compare against the base tag from git describe.
    try:
        local = get_local_git_tag("/root/.hermes/hermes-agent")
        remote = get_github_latest_release("nousresearch/hermes-agent")
        diagnostics.append(f"hermes-agent local={local} remote={remote}")
        if remote and not same_version(local, remote):
            alerts.append(f"- 🔄 服务更新: hermes-agent `{local}` → `{remote}`")
    except Exception as e:
        diagnostics.append(f"hermes-agent check failed: {e}")

    # hermes-webui: GitHub tags, not releases.
    try:
        local = get_local_git_tag("/root/hermes-webui")
        remote = get_github_latest_stable_tag("EKKOLearnAI/hermes-web-ui")
        diagnostics.append(f"hermes-webui local={local} remote={remote}")
        if remote and version_key(remote) > version_key(local):
            alerts.append(f"- 🔄 服务更新: hermes-webui `{local}` → `{remote}`")
    except Exception as e:
        diagnostics.append(f"hermes-webui check failed: {e}")

    # manifest: Docker image digest + GitHub release mapping for display.
    try:
        local = get_local_manifest_info("mnfst-manifest-1")
        local_build = format_manifest_local_build(local)
        local_release = ""
        if local.get("revision"):
            try:
                local_release = find_manifest_release_for_revision("mnfst/manifest", local.get("revision"), per_page=100)
            except Exception as mapping_error:
                diagnostics.append(f"manifest local release mapping failed: {mapping_error}")
        remote_release = ""
        try:
            remote_release = get_github_latest_release("mnfst/manifest")
        except Exception as release_error:
            diagnostics.append(f"manifest latest release lookup failed: {release_error}")
        remote_digest = docker_manifest_digest("manifestdotbuild/manifest:latest")
        local_digests = local.get("repo_digests") or []
        diagnostics.append(
            "manifest local_image=" + local.get("image_ref", "") +
            " local_build=" + local_build +
            " local_release=" + local_release +
            " local_digests=" + ",".join(local_digests) +
            " remote_release=" + remote_release +
            " remote=" + remote_digest
        )
        digest_match = bool(remote_digest and any(remote_digest in d for d in local_digests))
        if remote_digest and not digest_match:
            local_label = local_release or local_build
            remote_label = remote_release or remote_digest
            alerts.append(f"- 🔄 服务更新: manifest Docker 镜像 `{local_label}` → `{remote_label}`")
    except Exception as e:
        diagnostics.append(f"manifest check failed: {e}")


def check_market(alerts, diagnostics):
    try:
        us10y = get_tradingview_price("US10Y")
        diagnostics.append(f"US10Y={us10y}")
        if us10y > US10Y_THRESHOLD:
            alerts.append(f"- 📉 市场预警: US10Y `{us10y:.3f}%` > `{US10Y_THRESHOLD}%`，杀估值信号，提示减仓科技股")
    except Exception as e:
        diagnostics.append(f"US10Y check failed: {e}")

    try:
        dxy = get_tradingview_price("DXY")
        diagnostics.append(f"DXY={dxy}")
        if dxy > DXY_THRESHOLD:
            alerts.append(f"- 📉 市场预警: DXY `{dxy:.3f}` > `{DXY_THRESHOLD}`，美元流动性紧缩信号")
    except Exception as e:
        diagnostics.append(f"DXY check failed: {e}")


def main():
    alerts = []
    diagnostics = []

    check_disk(alerts, diagnostics)
    check_versions(alerts, diagnostics)
    check_market(alerts, diagnostics)

    if not alerts:
        print("[SILENT]")
        return

    now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    print(f"### 系统监控报告 ({now})\n")
    print("\n".join(alerts))
    print("\n---")


if __name__ == "__main__":
    main()
