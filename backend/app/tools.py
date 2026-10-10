import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

from app.retrieval import search

TZ = ZoneInfo("Asia/Kolkata")
MAX_DAYS = 30


# ---------- Small helpers ----------

def _today():
    return datetime.now(TZ).date()


def _fetch(conn, sql, params):
    # Returns rows as dictionaries: row["total_minutes"] instead of row[3]
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _avg(values, digits=1):
    values = [float(v) for v in values if v is not None]
    return round(sum(values) / len(values), digits) if values else None


def _clock_minutes(ts):
    """Bedtime as minutes after noon, so 23:30 and 00:30 average correctly."""
    local = ts.astimezone(TZ)
    minutes = local.hour * 60 + local.minute
    return minutes + 24 * 60 if local.hour < 12 else minutes


def _format_clock(minutes_after_midnight):
    m = round(minutes_after_midnight) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def _days(args, default):
    days = int(args.get("days", default))
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_DAYS}")
    return days


# ---------- Tools ----------

def get_user_profile(conn, user_id, args):
    rows = _fetch(conn, "SELECT name, age, sex, height_cm, weight_kg, goal FROM users WHERE id = %s", (user_id,))
    if not rows:
        return {"error": "user not found"}
    p = rows[0]
    return {
        "name": p["name"], "age": p["age"], "sex": p["sex"],
        "height_cm": float(p["height_cm"]) if p["height_cm"] else None,
        "weight_kg": float(p["weight_kg"]) if p["weight_kg"] else None,
        "goal": p["goal"],
    }


def get_sleep(conn, user_id, args):
    days = _days(args, 7)
    since = _today() - timedelta(days=days)
    rows = _fetch(conn, """
        SELECT date, bedtime, wake_time, total_minutes, deep_minutes, rem_minutes
        FROM sleep_logs WHERE user_id = %s AND date > %s ORDER BY date
    """, (user_id, since))
    if not rows:
        return {"error": "no sleep data for this period"}

    # The user's normal sleep BEFORE this period, for comparison
    baseline = _fetch(conn, """
        SELECT avg(total_minutes) AS avg_minutes FROM sleep_logs WHERE user_id = %s AND date <= %s
    """, (user_id, since))[0]["avg_minutes"]

    nights = [{
        "date": r["date"].isoformat(),
        "hours": round(r["total_minutes"] / 60, 1),
        "bedtime": r["bedtime"].astimezone(TZ).strftime("%H:%M"),
        "wake_time": r["wake_time"].astimezone(TZ).strftime("%H:%M"),
        "deep_minutes": r["deep_minutes"],
        "rem_minutes": r["rem_minutes"],
    } for r in rows]

    return {
        "period_nights": len(rows),
        "avg_hours": _avg([r["total_minutes"] / 60 for r in rows]),
        "avg_bedtime": _format_clock(sum(_clock_minutes(r["bedtime"]) for r in rows) / len(rows)),
        "nights_under_6h": sum(1 for r in rows if r["total_minutes"] < 360),
        "baseline_avg_hours_before_period": round(float(baseline) / 60, 1) if baseline else None,
        "nights": nights,
    }


def get_daily_metrics(conn, user_id, args):
    days = _days(args, 7)
    since = _today() - timedelta(days=days)
    rows = _fetch(conn, """
        SELECT date, steps, active_minutes, resting_hr, hrv_ms
        FROM daily_metrics WHERE user_id = %s AND date >= %s ORDER BY date
    """, (user_id, since))
    if not rows:
        return {"error": "no daily data for this period"}

    base = _fetch(conn, """
        SELECT avg(resting_hr) AS rhr, avg(hrv_ms) AS hrv, avg(steps) AS steps
        FROM daily_metrics WHERE user_id = %s AND date < %s
    """, (user_id, since))[0]

    return {
        "period_days": len(rows),
        "avg_steps": _avg([r["steps"] for r in rows], 0),
        "avg_resting_hr": _avg([r["resting_hr"] for r in rows]),
        "avg_hrv_ms": _avg([r["hrv_ms"] for r in rows]),
        "baseline_before_period": {
            "avg_resting_hr": round(float(base["rhr"]), 1) if base["rhr"] else None,
            "avg_hrv_ms": round(float(base["hrv"]), 1) if base["hrv"] else None,
            "avg_steps": round(float(base["steps"])) if base["steps"] else None,
        },
        "days": [{
            "date": r["date"].isoformat(),
            "steps": r["steps"],
            "active_minutes": r["active_minutes"],
            "resting_hr": r["resting_hr"],
            "hrv_ms": float(r["hrv_ms"]) if r["hrv_ms"] is not None else None,
        } for r in rows],
    }


def get_workouts(conn, user_id, args):
    days = _days(args, 14)
    since = datetime.combine(_today() - timedelta(days=days), datetime.min.time(), TZ)
    rows = _fetch(conn, """
        SELECT started_at, type, name, duration_minutes, avg_hr, calories
        FROM workouts WHERE user_id = %s AND started_at >= %s ORDER BY started_at
    """, (user_id, since))

    by_type = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1

    return {
        "period_days": days,
        "workout_count": len(rows),
        "total_minutes": sum(r["duration_minutes"] for r in rows),
        "count_by_type": by_type,
        "workouts": [{
            "date": r["started_at"].astimezone(TZ).date().isoformat(),
            "weekday": r["started_at"].astimezone(TZ).strftime("%A"),
            "name": r["name"],
            "type": r["type"],
            "duration_minutes": r["duration_minutes"],
            "avg_hr": r["avg_hr"],
        } for r in rows],
    }


def search_guides(conn, user_id, args):
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query is required"}
    chunks = search(conn, query, k=4)
    return {"results": [{
        "title": c["title"], "page": c["page"], "url": c["url"], "text": c["content"][:900],
    } for c in chunks]}


# ---------- Registry: name -> function + the description the AI reads ----------

TOOLS = {
    "get_user_profile": {
        "fn": get_user_profile,
        "description": "Get the user's profile: age, sex, height, weight and fitness goal.",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_sleep": {
        "fn": get_sleep,
        "description": ("Get the user's sleep for the last N nights: hours, bedtime, wake time, deep and REM sleep, "
                        "plus averages and the user's normal (baseline) sleep before this period."),
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer", "minimum": 1, "maximum": 30, "description": "Number of nights (default 7)."}}},
    },
    "get_daily_metrics": {
        "fn": get_daily_metrics,
        "description": ("Get the user's daily steps, active minutes, resting heart rate and HRV for the last N days, "
                        "plus their normal (baseline) values before this period. Higher resting HR or lower HRV than "
                        "baseline can mean poor recovery."),
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer", "minimum": 1, "maximum": 30, "description": "Number of days (default 7)."}}},
    },
    "get_workouts": {
        "fn": get_workouts,
        "description": "Get the user's workouts for the last N days: name, type, duration and average heart rate.",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer", "minimum": 1, "maximum": 30, "description": "Number of days (default 14)."}}},
    },
    "search_guides": {
        "fn": search_guides,
        "description": ("Search trusted health guidelines (WHO, US Physical Activity Guidelines, ICMR-NIN diet, "
                        "NHLBI sleep) for general facts and recommendations. Use for any general health question."),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "What to search for, as a clear question."}},
            "required": ["query"]},
    },
}


def tool_schemas():
    """Tool definitions in the format the OpenAI-style API expects"""
    return [{"type": "function", "function": {"name": name, "description": t["description"],
                                              "parameters": t["parameters"]}}
            for name, t in TOOLS.items()]


def run_tool(conn, user_id, name, args):
    """Run a tool by name. Never raises: errors are returned so the AI can see them and recover."""
    tool = TOOLS.get(name)
    if tool is None:
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        return json.dumps(tool["fn"](conn, user_id, args or {}))
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"})