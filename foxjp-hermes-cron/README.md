# foxjp Hermes Cron Tasks

Pulled from `foxjp:/root/.hermes` on 2026-05-09.

This directory contains the non-secret code/config needed to reproduce the two Hermes cron tasks currently configured on `foxjp`.

## Included

- `cron/jobs.json`
  - Hermes cron job definitions.
  - `0628054925cb`: `daily-update-monitor`, schedule `0 14 * * *` UTC.
  - `fccf89573c04`: `X 财经日报邮件 | UTC+8 10:00`, schedule `0 2 * * *` UTC.
- `scripts/update_monitor.py`
  - VPS service/version monitor used by `daily-update-monitor`.
- `scripts/update_monitor.py.bak`
  - Existing backup copy found on `foxjp`.
- `x-daily-report/README.md`
  - Usage notes for the X/Twitter daily finance report.
- `x-daily-report/accounts.yaml`
  - Non-secret report configuration: recipient, timezone, lookback, account list.
- `x-daily-report/report.py`
  - X/Twitter daily finance report implementation.

## Excluded

The following remote files were intentionally not copied:

- `/root/.hermes/x-daily-report/.env`
- `/root/.hermes/google_token.json`
- `/root/.hermes/.env`
- `/root/.hermes/state.db*`
- `/root/.hermes/response_store.db*`
- `/root/.hermes/logs/`
- `/root/.hermes/cron/output/`
- `__pycache__/` and `*.pyc`

These excluded files contain credentials, runtime state, logs, generated reports, or compiled cache artifacts.

## Remote Paths

```text
/root/.hermes/cron/jobs.json
/root/.hermes/scripts/update_monitor.py
/root/.hermes/scripts/update_monitor.py.bak
/root/.hermes/x-daily-report/README.md
/root/.hermes/x-daily-report/accounts.yaml
/root/.hermes/x-daily-report/report.py
```

