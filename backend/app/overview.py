"""Today at a glance, in the style of Google Health: readiness, weekly cardio, steps and sleep."""
from datetime import datetime, timedelta

from psycopg.rows import dict_row

from app.tools import TZ

BASELINE_DAYS = 30          # "your normal" = your average over the month before
MIN_BASELINE_DAYS = 5       # with less history than this, there is no normal to compare with
WEEKLY_ZONE_MINUTES = 150   # WHO: at least 150 minutes of moderate activity a week

# How much each signal counts towards readiness
WEIGHTS = {"hrv": 0.4, "resting_hr": 0.3, "sleep": 0.3}


def _clamp(value):
    return max(0, min(100, value))


def readiness_score(hrv=None, hrv_normal=None, resting_hr=None, resting_hr_normal=None,
                    sleep_hours=None, sleep_normal=None):
    """Our own 0-100 estimate of how recovered the user is. NOT Google's readiness score (their API
    does not share it). Each signal scores 75 when it matches the user's normal, more when it is
    better and less when it is worse. Returns None unless at least two signals are available.
    `signals` lists what the score was built from, so the app can show why it is high or low."""
    signals = []
    if sleep_hours is not None and sleep_normal:
        signals.append({"key": "sleep", "value": round(sleep_hours, 1), "normal": round(sleep_normal, 1),
                        "score": _clamp(75 + (sleep_hours - sleep_normal) * 25)})        # 3 hours short = 0
    if resting_hr and resting_hr_normal:
        signals.append({"key": "resting_hr", "value": round(resting_hr), "normal": round(resting_hr_normal),
                        "score": _clamp(75 - (resting_hr - resting_hr_normal) * 7.5)})   # 10 bpm above normal = 0
    if hrv and hrv_normal:
        signals.append({"key": "hrv", "value": round(hrv), "normal": round(hrv_normal),
                        "score": _clamp(75 + (hrv / hrv_normal - 1) * 250)})             # 30% below normal = 0
    if len(signals) < 2:
        return None

    score = round(sum(s["score"] * WEIGHTS[s["key"]] for s in signals) / sum(WEIGHTS[s["key"]] for s in signals))
    for s in signals:
        s["score"] = round(s["score"])
    return {
        "score": score,
        "level": "high" if score >= 70 else "moderate" if score >= 40 else "low",
        "signals": signals,
    }


def _latest_and_normal(rows, key, today):
    """The newest reading (it must be from today or yesterday) and the average of the readings before it."""
    values = [(r["date"], float(r[key])) for r in rows if r[key] is not None]
    if not values or values[-1][0] < today - timedelta(days=1):
        return None, None
    earlier = [v for _, v in values[:-1]]
    normal = sum(earlier) / len(earlier) if len(earlier) >= MIN_BASELINE_DAYS else None
    return values[-1][1], normal


def get_overview(conn, user_id):
    today = datetime.now(TZ).date()
    since = today - timedelta(days=BASELINE_DAYS + 1)
    with conn.cursor(row_factory=dict_row) as cur:
        days = cur.execute(
            "SELECT date, steps, zone_minutes, resting_hr, hrv_ms FROM daily_metrics "
            "WHERE user_id = %s AND date >= %s ORDER BY date", (user_id, since)).fetchall()
        nights = cur.execute(
            "SELECT date, bedtime, wake_time, total_minutes, deep_minutes, rem_minutes, light_minutes, awake_minutes "
            "FROM sleep_logs WHERE user_id = %s AND date >= %s ORDER BY date", (user_id, since)).fetchall()
    by_date = {d["date"]: d for d in days}

    # ----- Steps: today so far, and the last 7 days -----
    last_7 = [today - timedelta(days=i) for i in range(6, -1, -1)]
    step_days = [{"date": d.isoformat(), "steps": by_date.get(d, {}).get("steps")} for d in last_7]
    counted = [d["steps"] for d in step_days if d["steps"] is not None]

    # ----- Weekly cardio: zone minutes since Monday -----
    monday = today - timedelta(days=today.weekday())
    week = [monday + timedelta(days=i) for i in range(7)]
    cardio_days = [{"date": d.isoformat(), "minutes": by_date.get(d, {}).get("zone_minutes")} for d in week]
    has_cardio = any(d["zone_minutes"] is not None for d in days)

    # ----- Sleep: the most recent night -----
    night = nights[-1] if nights else None
    earlier_nights = [n["total_minutes"] for n in nights[:-1]]
    sleep_normal = sum(earlier_nights) / len(earlier_nights) / 60 if len(earlier_nights) >= MIN_BASELINE_DAYS else None

    # ----- Readiness: last night's sleep and the newest heart readings, against the user's normal -----
    hrv, hrv_normal = _latest_and_normal(days, "hrv_ms", today)
    resting_hr, resting_hr_normal = _latest_and_normal(days, "resting_hr", today)
    recent_night = night if night and night["date"] >= today - timedelta(days=1) else None

    return {
        "readiness": readiness_score(
            hrv, hrv_normal, resting_hr, resting_hr_normal,
            recent_night["total_minutes"] / 60 if recent_night else None, sleep_normal),
        "cardio": {
            "week_minutes": sum(d["minutes"] or 0 for d in cardio_days),
            "target_minutes": WEEKLY_ZONE_MINUTES,
            "days": cardio_days,
        } if has_cardio else None,
        "steps": {
            "today": step_days[-1]["steps"],
            "avg_7d": round(sum(counted) / len(counted)) if counted else None,
            "days": step_days,
        } if counted else None,
        "sleep": {
            "date": night["date"].isoformat(),
            "minutes": night["total_minutes"],
            "normal_hours": round(sleep_normal, 1) if sleep_normal else None,
            "bedtime": night["bedtime"].astimezone(TZ).strftime("%H:%M"),
            "wake_time": night["wake_time"].astimezone(TZ).strftime("%H:%M"),
            "deep_minutes": night["deep_minutes"], "rem_minutes": night["rem_minutes"],
            "light_minutes": night["light_minutes"], "awake_minutes": night["awake_minutes"],
        } if night else None,
    }
