"""Thing To Sell traffic tracker.

Tiny pageview counter for thingtosell.com.
- GET /hit?p=<page>&r=<referrer>  -> records one pageview, returns a 1x1 gif
- GET /stats?days=N&token=TOKEN    -> JSON daily totals [{date, hits, uniques}]
- GET /                            -> status page

Day boundaries use America/Chicago. Uniques are counted per hashed IP per day.
No cookies, no fingerprinting. Render free tier has ephemeral disk, so a daily
job snapshots totals elsewhere; this app is the collector, not the archive.
"""
import hashlib
import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, g, jsonify, request, Response

TZ = ZoneInfo("America/Chicago")
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "hits.db"))
STATS_TOKEN = os.environ.get("STATS_TOKEN", "")

GIF_1PX = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
    b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)

app = Flask(__name__)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.execute(
            "CREATE TABLE IF NOT EXISTS hits ("
            "day TEXT NOT NULL, "
            "page TEXT NOT NULL DEFAULT '', "
            "ref_host TEXT NOT NULL DEFAULT '', "
            "ip_hash TEXT NOT NULL DEFAULT '', "
            "ts TEXT NOT NULL)"
        )
        g.db.execute("CREATE INDEX IF NOT EXISTS idx_hits_day ON hits(day)")
        g.db.commit()
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _today():
    return datetime.now(TZ).strftime("%Y-%m-%d")


@app.route("/hit", methods=["GET", "POST"])
def hit():
    page = (request.values.get("p") or "")[:200]
    ref = (request.values.get("r") or "")[:300]
    ref_host = ""
    if ref:
        try:
            from urllib.parse import urlparse

            ref_host = urlparse(ref).netloc[:120]
        except Exception:
            ref_host = ""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    ip_hash = hashlib.sha256((ip + _today()).encode()).hexdigest()[:32]
    db = get_db()
    db.execute(
        "INSERT INTO hits (day, page, ref_host, ip_hash, ts) VALUES (?,?,?,?,?)",
        (_today(), page, ref_host, ip_hash, datetime.now(TZ).isoformat(timespec="seconds")),
    )
    db.commit()
    return Response(GIF_1PX, mimetype="image/gif", headers={"Cache-Control": "no-store"})


@app.route("/stats")
def stats():
    token = request.args.get("token", "")
    if not STATS_TOKEN or token != STATS_TOKEN:
        return jsonify({"ok": False, "error": "unauthorized"}), 403
    try:
        days = max(1, min(90, int(request.args.get("days", "7"))))
    except ValueError:
        days = 7
    db = get_db()
    rows = db.execute(
        "SELECT day, COUNT(*) AS hits, COUNT(DISTINCT ip_hash) AS uniques "
        "FROM hits GROUP BY day ORDER BY day DESC LIMIT ?",
        (days,),
    ).fetchall()
    data = [{"date": r[0], "hits": r[1], "uniques": r[2]} for r in rows]
    # Fill missing days with zeros so the report always covers `days` days
    have = {d["date"] for d in data}
    today = datetime.now(TZ).date()
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        if d not in have:
            data.append({"date": d, "hits": 0, "uniques": 0})
    data.sort(key=lambda x: x["date"], reverse=True)
    return jsonify({"ok": True, "timezone": "America/Chicago", "days": data})


@app.route("/top-pages")
def top_pages():
    token = request.args.get("token", "")
    if not STATS_TOKEN or token != STATS_TOKEN:
        return jsonify({"ok": False, "error": "unauthorized"}), 403
    day = request.args.get("day") or _today()
    db = get_db()
    rows = db.execute(
        "SELECT page, COUNT(*) AS hits FROM hits WHERE day = ? "
        "GROUP BY page ORDER BY hits DESC LIMIT 20",
        (day,),
    ).fetchall()
    return jsonify({"ok": True, "day": day, "pages": [{"page": r[0], "hits": r[1]} for r in rows]})


@app.route("/")
def index():
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM hits").fetchone()[0]
    today_row = db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT ip_hash) FROM hits WHERE day = ?", (_today(),)
    ).fetchone()
    return (
        "<h1>Thing To Sell traffic tracker</h1>"
        f"<p>Total hits recorded: {total}</p>"
        f"<p>Today ({_today()}): {today_row[0]} hits / {today_row[1]} uniques</p>"
        "<p>Endpoints: /hit (pixel), /stats?days=N&amp;token=..., /top-pages?day=YYYY-MM-DD&amp;token=...</p>"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
