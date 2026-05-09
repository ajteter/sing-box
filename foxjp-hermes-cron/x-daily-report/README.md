# X Daily Finance Report

Daily X/Twitter finance digest for Steam.

## Files

- `accounts.yaml`: account list and delivery config.
- `report.py`: fetches with `twitter-cli`, summarizes finance/asset mentions, sends through Hermes Gmail API.

## Auth

`twitter-cli` needs X cookies or env vars:

```bash
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
twitter status --yaml
```

Gmail uses Hermes Google Workspace OAuth at `~/.hermes/google_token.json`.

## Manual run

```bash
cd ~/.hermes/x-daily-report
python report.py --no-send
python report.py
```

## Add account

Edit `accounts.yaml`:

```yaml
accounts:
  - handle: some_handle
    url: https://x.com/some_handle
    label: some_label
```
