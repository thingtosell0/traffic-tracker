# Thing To Sell — Traffic Tracker

Tiny pageview counter for thingtosell.com. Goal: track daily unique visitors
against the 500/day target.

## How it works

1. This app runs on Render (free tier).
2. A 3-line JS snippet on the storefront fires one `GET /hit` pixel per pageview.
3. `GET /stats?days=N&token=STATS_TOKEN` returns daily `{hits, uniques}` for reports.

No cookies, no fingerprinting. Uniques = distinct hashed IPs per day (America/Chicago).

## Deploy (Render)

1. Render Dashboard → New → Web Service → connect this repo.
2. Render reads `render.yaml`: Python, `pip install -r requirements.txt`,
   `gunicorn app:app`. `STATS_TOKEN` is auto-generated — copy its value from
   the Render dashboard (Environment tab); the daily report job needs it.
3. Note the public URL, e.g. `https://thing-to-sell-traffic-tracker.onrender.com`.

## Storefront snippet

Ecwid control panel → Settings → General → Custom code (head section), paste
`snippet.html` with `TRACKER_URL` replaced by the Render URL.

## Endpoints

- `GET /hit?p=<page>&r=<referrer>` → 1x1 gif, records the view
- `GET /stats?days=N&token=...` → `{"ok":true,"days":[{"date","hits","uniques"}]}`
- `GET /top-pages?day=YYYY-MM-DD&token=...` → hits per page path
- `GET /` → status page

## Notes

- Render free tier has ephemeral disk: a daily job snapshots `/stats` totals
  elsewhere so history survives restarts.
- Day boundaries use America/Chicago.
