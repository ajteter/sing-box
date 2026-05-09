#!/usr/bin/env python3
"""Generate and email a daily X/Twitter finance report.

Uses public-clis/twitter-cli for X retrieval and Hermes Google Workspace Gmail API wrapper
for email delivery. All report text is generated from real fetched data only; failures are
reported explicitly in the email body.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "accounts.yaml"
DOTENV_PATH = BASE_DIR / ".env"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
GAPI = HERMES_HOME / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

CRYPTO = {
    "BTC": ["BTC", "比特币", "Bitcoin", "$BTC"],
    "ETH": ["ETH", "以太坊", "Ethereum", "$ETH"],
    "SOL": ["SOL", "Solana", "$SOL"],
    "BNB": ["BNB", "$BNB"],
    "XRP": ["XRP", "$XRP"],
    "DOGE": ["DOGE", "狗狗币", "$DOGE"],
}

MACRO = {
    "GOLD": ["黄金", "Gold", "XAU", "GLD"],
    "OIL": ["原油", "石油", "Oil", "WTI", "Brent", "布伦特"],
    "USD": ["美元", "DXY", "美元指数"],
    "UST": ["美债", "国债", "Treasury", "10Y", "收益率"],
    "VIX": ["VIX", "恐慌指数"],
}

INDEX_ETF = {
    "SPY": ["SPY", "标普", "S&P", "S&P 500", "SP500"],
    "QQQ": ["QQQ", "纳指", "纳斯达克", "Nasdaq", "NDX"],
    "DIA": ["DIA", "道指", "Dow"],
    "IWM": ["IWM", "罗素", "Russell"],
    "TLT": ["TLT", "长债"],
}

US_STOCK_ALIASES = {
    "NVDA": ["NVDA", "英伟达", "Nvidia"],
    "TSLA": ["TSLA", "特斯拉", "Tesla"],
    "AAPL": ["AAPL", "苹果", "Apple"],
    "MSFT": ["MSFT", "微软", "Microsoft"],
    "GOOGL": ["GOOGL", "GOOG", "谷歌", "Google", "Alphabet"],
    "META": ["META", "Meta", "Facebook"],
    "AMZN": ["AMZN", "亚马逊", "Amazon"],
    "AMD": ["AMD", "超微"],
    "MSTR": ["MSTR", "MicroStrategy"],
    "COIN": ["COIN", "Coinbase"],
    "SMCI": ["SMCI", "超微电脑"],
    "PLTR": ["PLTR", "Palantir"],
}

FINANCE_KEYWORDS = [
    "股票", "美股", "港股", "A股", "币", "加密", "链", "ETF", "指数", "期货", "期权", "利率", "降息", "加息",
    "美联储", "CPI", "PPI", "GDP", "非农", "收益率", "债", "美元", "黄金", "原油", "财报", "营收", "利润",
    "估值", "市值", "买入", "卖出", "做多", "做空", "看多", "看空", "仓位", "交易", "价格", "涨", "跌",
    "market", "stock", "crypto", "bitcoin", "ethereum", "fed", "rate", "inflation", "earnings", "revenue", "profit",
]

BULLISH = ["看多", "做多", "买入", "上涨", "突破", "反弹", "利好", "牛", "long", "bull", "buy", "rally", "breakout"]
BEARISH = ["看空", "做空", "卖出", "下跌", "破位", "利空", "风险", "崩", "short", "bear", "sell", "dump", "crash"]

URL_RE = re.compile(r"https?://\S+")
TICKER_RE = re.compile(r"(?<![A-Za-z0-9])\$?([A-Z]{1,5})(?![A-Za-z0-9])")


def run(cmd: list[str], timeout: int = 120, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=check)


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def date_window(tz_name: str, date_str: str | None) -> tuple[dt.date, dt.datetime, dt.datetime]:
    tz = ZoneInfo(tz_name)
    if date_str:
        day = dt.date.fromisoformat(date_str)
    else:
        day = dt.datetime.now(tz).date() - dt.timedelta(days=1)
    start = dt.datetime.combine(day, dt.time.min, tzinfo=tz)
    end = start + dt.timedelta(days=1)
    return day, start, end


def parse_twitter_json(raw: str) -> list[dict[str, Any]]:
    if not raw.strip():
        return []
    data = json.loads(raw)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("tweets", "items", "results", "data"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
        return [data]
    return []


def get_field(obj: dict[str, Any], names: list[str], default: Any = None) -> Any:
    for name in names:
        if name in obj and obj[name] not in (None, ""):
            return obj[name]
    return default


def normalize_tweet(obj: dict[str, Any], handle: str) -> dict[str, Any]:
    tid = str(get_field(obj, ["id", "tweet_id", "rest_id", "conversation_id"], ""))
    text = str(get_field(obj, ["text", "full_text", "content", "body"], ""))
    created = get_field(obj, ["created_at", "date", "time", "timestamp"], "")
    url = str(get_field(obj, ["url", "tweet_url", "link"], ""))
    if not url and tid:
        url = f"https://x.com/{handle}/status/{tid}"
    return {"id": tid or url or text[:80], "handle": handle, "text": text, "created_at": created, "url": url, "raw": obj}


def parse_time(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            value /= 1000
        return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    # Try ISO-like first.
    try:
        fixed = s.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(fixed)
    except Exception:
        pass
    for fmt in ["%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S"]:
        try:
            parsed = dt.datetime.strptime(s, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed
        except Exception:
            continue
    return None


def fetch_account(handle: str, since: str, until: str, max_items: int) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    collected: dict[str, dict[str, Any]] = {}
    commands = [
        ["twitter", "user-posts", handle, "--max", str(max_items), "--json"],
        ["twitter", "search", "", "--from", handle, "--since", since, "--until", until, "--type", "latest", "--max", str(max_items), "--json"],
    ]
    for cmd in commands:
        proc = run(cmd, timeout=180)
        if proc.returncode != 0:
            errors.append(f"Command failed: {' '.join(cmd)}\nSTDERR: {proc.stderr.strip()}\nSTDOUT: {proc.stdout.strip()}")
            continue
        try:
            items = parse_twitter_json(proc.stdout)
        except Exception as exc:
            errors.append(f"JSON parse failed for {' '.join(cmd)}: {exc}\nRaw output: {proc.stdout[:1000]}")
            continue
        for obj in items:
            tw = normalize_tweet(obj, handle)
            collected[tw["id"]] = tw
    return list(collected.values()), errors


def twitter_auth_check() -> str | None:
    proc = run(["twitter", "status", "--yaml"], timeout=60)
    if proc.returncode != 0:
        return f"twitter status failed\nSTDERR: {proc.stderr.strip()}\nSTDOUT: {proc.stdout.strip()}"
    if "ok: true" in proc.stdout:
        return None
    return f"twitter status not authenticated\nSTDERR: {proc.stderr.strip()}\nSTDOUT: {proc.stdout.strip()}"


def classify_type(tw: dict[str, Any]) -> str:
    raw = tw.get("raw", {})
    text = tw.get("text", "") or ""
    if any(k in raw for k in ["retweeted_status", "retweet"]):
        return "转推"
    if any(k in raw for k in ["quoted_status", "quote", "quoted_tweet"]):
        return "引用"
    if any(k in raw for k in ["in_reply_to_status_id", "reply_to", "in_reply_to_screen_name"]):
        return "回复"
    if text.startswith("RT @"):
        return "转推"
    return "原帖/未识别"


def clean_text(text: str) -> str:
    text = URL_RE.sub("", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_assets(text: str) -> list[tuple[str, str]]:
    found: dict[str, str] = {}
    groups = [("加密", CRYPTO), ("大类资产", MACRO), ("指数/ETF", INDEX_ETF), ("美股", US_STOCK_ALIASES)]
    low = text.lower()
    for category, mapping in groups:
        for asset, aliases in mapping.items():
            for alias in aliases:
                if alias.startswith("$"):
                    pattern = re.escape(alias)
                    if re.search(pattern + r"\b", text, re.I):
                        found[asset] = category
                elif alias.isascii() and alias.isalnum():
                    if re.search(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", text, re.I):
                        found[asset] = category
                elif alias.lower() in low:
                    found[asset] = category
    # Explicit $TICKER for US equities / ETFs, filtered for common false positives.
    false = {"USD", "CEO", "AI", "API", "GDP", "CPI", "PPI", "ATH", "TV", "ETF", "X"}
    for m in re.finditer(r"\$([A-Z]{1,5})(?![A-Za-z0-9])", text):
        ticker = m.group(1)
        if ticker not in false and ticker not in found:
            found[ticker] = "美股/ETF/加密待确认"
    return sorted(found.items())


def is_finance(text: str, assets: list[tuple[str, str]]) -> bool:
    if assets:
        return True
    low = text.lower()
    return any(k.lower() in low for k in FINANCE_KEYWORDS)


def sentiment(text: str) -> str:
    low = text.lower()
    bull = sum(1 for k in BULLISH if k.lower() in low)
    bear = sum(1 for k in BEARISH if k.lower() in low)
    if bull > bear:
        return "偏多"
    if bear > bull:
        return "偏空/风险"
    return "中性/观察"


def summarize_item(text: str, max_len: int = 180) -> str:
    txt = clean_text(text)
    if len(txt) <= max_len:
        return txt or "（无文本内容）"
    return txt[: max_len - 1] + "…"


def build_report(day: dt.date, tweets: list[dict[str, Any]], errors: list[str], start: dt.datetime, end: dt.datetime, tz_name: str) -> tuple[str, str]:
    tz = ZoneInfo(tz_name)
    rows = []
    non_finance = []
    asset_counts: Counter[str] = Counter()
    asset_categories: dict[str, str] = {}
    asset_examples: dict[str, list[str]] = defaultdict(list)
    type_counts: Counter[str] = Counter()

    for tw in tweets:
        parsed = parse_time(tw.get("created_at"))
        if parsed and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        local_time = parsed.astimezone(tz) if parsed else None
        if local_time and not (start <= local_time < end):
            continue
        text = tw.get("text", "")
        assets = extract_assets(text)
        fin = is_finance(text, assets)
        row_type = classify_type(tw)
        row = {
            **tw,
            "local_time": local_time,
            "type": row_type,
            "assets": assets,
            "finance": fin,
            "sentiment": sentiment(text),
            "summary": summarize_item(text, max_len=120),
            "text_len": len(clean_text(text)),
        }
        type_counts[row_type] += 1
        if fin:
            rows.append(row)
            for asset, cat in assets:
                asset_counts[asset] += 1
                asset_categories[asset] = cat
                if len(asset_examples[asset]) < 2:
                    asset_examples[asset].append(row["summary"])
        else:
            non_finance.append(row)

    rows.sort(key=lambda r: r.get("local_time") or dt.datetime.min.replace(tzinfo=tz))
    total = len(rows) + len(non_finance)

    def score_row(row: dict[str, Any]) -> tuple[int, int, int]:
        asset_score = min(len(row["assets"]), 3)
        type_bonus = {"引用": 3, "原帖/未识别": 2, "回复": 1, "转推": 0}.get(row["type"], 0)
        sentiment_bonus = 1 if row["sentiment"] != "中性/观察" else 0
        return (asset_score * 10 + type_bonus * 3 + sentiment_bonus * 2 + min(row["text_len"], 280) // 40, row["text_len"], len(row["assets"]))

    top_rows = sorted(rows, key=score_row, reverse=True)[:8]
    high_conf_assets = [(asset, count) for asset, count in asset_counts.most_common() if asset_categories.get(asset) != "美股/ETF/加密待确认"][:10]
    dominant_assets = "、".join([a for a, _ in high_conf_assets[:6]]) or "未发现高置信度标的"
    core = "无可用内容。" if total == 0 else f"共抓到 {total} 条内容，其中财经相关 {len(rows)} 条；主线集中在 {dominant_assets}。"
    if errors:
        core += " 抓取存在失败，见文末错误。"

    subject = f"X 财经日报 | {day.isoformat()} | {len(set(t['handle'] for t in tweets)) or 1} accounts"

    md: list[str] = []
    md.append("# X 财经日报\n")
    md.append(f"日期：{day.isoformat()}（{tz_name}）\n")
    md.append("## 1. 总览\n")
    md.append(f"- 抓取内容数：{total}\n")
    md.append(f"- 财经相关：{len(rows)}；非财经：{len(non_finance)}\n")
    if type_counts:
        md.append("- 内容类型：" + "、".join(f"{k} {v}" for k, v in type_counts.items()) + "\n")
    md.append(f"- 高置信度标的数：{len(high_conf_assets)}\n")
    md.append(f"- 一句话主线：{core}\n")

    md.append("\n## 2. 高度概括\n")
    if rows:
        by_handle = Counter(r["handle"] for r in rows)
        sent = Counter(r["sentiment"] for r in rows)
        md.append("- 账号活跃度：" + "；".join(f"@{h} 财经相关 {c} 条" for h, c in by_handle.items()) + "\n")
        if high_conf_assets:
            md.append("- 高频标的：" + "、".join(f"{a}({c})" for a, c in high_conf_assets[:8]) + "\n")
        md.append("- 情绪分布：" + "、".join(f"{k} {v}" for k, v in sent.items()) + "\n")
        if top_rows:
            md.append("- 重点方向：" + "；".join(r["summary"] for r in top_rows[:3]) + "\n")
    else:
        md.append("- 未抓到可判断为财经相关的内容。\n")

    md.append("\n## 3. 标的汇总（仅高置信度）\n")
    if high_conf_assets:
        md.append("| 标的 | 类别 | 提及次数 | 代表性内容 |\n|---|---|---:|---|\n")
        for asset, count in high_conf_assets:
            examples = " / ".join(asset_examples[asset][:2])
            md.append(f"| {asset} | {asset_categories.get(asset, '')} | {count} | {examples} |\n")
    else:
        md.append("未提取到高置信度标的。\n")

    md.append("\n## 4. 重点内容（Top 8）\n")
    if top_rows:
        for r in top_rows:
            tstr = r["local_time"].strftime("%H:%M") if r.get("local_time") else "时间未知"
            assets = "、".join(a for a, cat in r["assets"] if cat != "美股/ETF/加密待确认") or "无明确高置信度标的"
            md.append(f"- **{tstr} @{r['handle']} [{r['type']}] [{r['sentiment']}]** {r['summary']}\n")
            md.append(f"  - 标的：{assets}\n")
            if r.get("url"):
                md.append(f"  - 链接：{r['url']}\n")
    else:
        md.append("无财经重点内容。\n")

    md.append("\n## 5. 非财经内容一句话\n")
    if non_finance:
        md.append(f"共 {len(non_finance)} 条，已忽略展开，仅保留财经相关主线。\n")
    else:
        md.append("无或未抓到。\n")

    if errors:
        md.append("\n## 6. 抓取/处理错误（原始错误）\n")
        for err in errors:
            md.append("```text\n" + err[:3000] + "\n```\n")

    text_body = "".join(md)
    html_body = markdownish_to_html(text_body)
    return subject, html_body


def markdownish_to_html(text_body: str) -> str:
    lines = text_body.splitlines()
    out = ["<html><body style='font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; line-height:1.5;'>"]
    in_code = False
    in_table = False
    for line in lines:
        esc = html.escape(line)
        if line.startswith("```"):
            if not in_code:
                out.append("<pre style='background:#f6f8fa;padding:12px;white-space:pre-wrap;'>")
                in_code = True
            else:
                out.append("</pre>")
                in_code = False
            continue
        if in_code:
            out.append(esc + "\n")
            continue
        if line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            out.append(f"<p>• {esc[2:]}</p>")
        elif line.startswith("|---"):
            continue
        elif line.startswith("|") and line.endswith("|"):
            cells = [html.escape(c.strip()) for c in line.strip("|").split("|")]
            tag = "th" if not in_table else "td"
            if not in_table:
                out.append("<table border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse;'>")
                in_table = True
            out.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
        else:
            if in_table:
                out.append("</table>")
                in_table = False
            if line.strip():
                out.append(f"<p>{esc}</p>")
    if in_table:
        out.append("</table>")
    if in_code:
        out.append("</pre>")
    out.append("</body></html>")
    return "\n".join(out)


def get_authenticated_email() -> str | None:
    proc = run([sys.executable, str(GAPI), "gmail", "labels"], timeout=120)
    if proc.returncode != 0:
        return None
    token_path = HERMES_HOME / "google_token.json"
    # Gmail send to "me" is accepted by API wrapper? Use authenticated profile if available via whoami is not supported.
    # Leave auto recipient as "me"; Gmail API resolves it for sending to self in this wrapper.
    return "me"


def send_email(to: str, subject: str, body_html: str, dry_run: bool = False) -> None:
    if dry_run:
        print(subject)
        print(body_html)
        return
    cmd = [sys.executable, str(GAPI), "gmail", "send", "--to", to, "--subject", subject, "--body", body_html, "--html"]
    proc = run(cmd, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"Gmail send failed\nSTDERR: {proc.stderr}\nSTDOUT: {proc.stdout}")
    print(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--date", help="Report date in Asia/Shanghai calendar, YYYY-MM-DD. Defaults to yesterday.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-send", action="store_true")
    args = parser.parse_args()

    load_dotenv(DOTENV_PATH)
    cfg = load_config(Path(args.config))
    tz_name = cfg.get("timezone", "Asia/Shanghai")
    day, start, end = date_window(tz_name, args.date)
    max_items = int(cfg.get("max_items_per_account", 100))
    since, until = day.isoformat(), (day + dt.timedelta(days=1)).isoformat()

    all_tweets: list[dict[str, Any]] = []
    errors: list[str] = []
    auth_error = twitter_auth_check()
    if auth_error:
        errors.append(auth_error)
    else:
        for account in cfg.get("accounts", []):
            handle = str(account["handle"]).lstrip("@")
            tweets, errs = fetch_account(handle, since, until, max_items)
            all_tweets.extend(tweets)
            errors.extend(errs)

    subject, body = build_report(day, all_tweets, errors, start, end, tz_name)
    if args.no_send:
        print(subject)
        print(body)
        return 0

    recipient = str(cfg.get("recipient_email", "auto"))
    if recipient == "auto":
        recipient = get_authenticated_email() or "me"
    send_email(recipient, subject, body, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
