"""Copies the user's Google Health data into our own tables, where the coach's tools read it."""
import logging
from datetime import date, datetime, timedelta

from cryptography.fernet import InvalidToken

from app.db import get_conn
from app.google_health import (
    SCOPE_ACTIVITY,
    SCOPE_METRICS,
    SCOPE_PREFIX,
    SCOPE_SLEEP,
    AuthorizationExpired,
    GoogleHealthError,
    HealthClient,
    decrypt_token,
    encrypt_token,
    get_access_token,
)
from app.tools import TZ

logger = logging.getLogger("fitmecoach.sync")

BACKFILL_DAYS = 90        # first sync: enough history to work out the user's normal (baseline)
RESYNC_MINUTES = 15       # after that, look for new data at most this often
OVERLAP_DAYS = 2          # re-read the last few days each time: watches upload late and totals change

# Google has ~180 exercise types. The coach only needs a handful of broad groups.
WORKOUT_TYPES = {
    "run": {"RUNNING", "TRAIL_RUN", "TREADMILL", "INCLINE_RUN", "TRACK_AND_FIELD"},
    "walk": {"WALKING", "POWER_WALKING", "NORDIC_WALKING", "TREADMILL_WALK", "INCLINE_WALK", "STROLLER_WALK",
             "WALK_WITH_WEIGHTS", "HIKING", "BACKPACKING", "RUCKING"},
    "strength": {"STRENGTH_TRAINING", "FUNCTIONAL_STRENGTH_TRAINING", "WEIGHTLIFTING", "WEIGHTS", "FREE_WEIGHTS",
                 "WEIGHT_MACHINES", "POWERLIFTING", "BODY_WEIGHT", "CALISTHENICS", "RESISTANCE_BANDS", "TRX",
                 "CORE_TRAINING", "CROSSFIT"},
    "yoga": {"YOGA", "YOGA_BIKRAM", "YOGA_HATHA", "YOGA_POWER", "YOGA_VINYASA", "PILATES", "STRETCHING"},
    "ride": {"BIKING", "OUTDOOR_BIKE", "MOUNTAIN_BIKE", "STATIONARY_BIKE", "SPINNING", "ELECTRIC_BIKE",
             "ASSAULT_BIKE", "HAND_CYCLING"},
    "swim": {"SWIMMING", "SWIMMING_POOL", "SWIMMING_OPEN_WATER"},
    "hiit": {"HIIT", "INTERVAL_WORKOUT", "TABATA_WORKOUT", "CIRCUIT_TRAINING", "BOOTCAMP"},
}
# How much a minute in each heart rate zone counts towards the weekly cardio goal
ZONE_WEIGHT = {"MODERATE": 1, "VIGOROUS": 2, "PEAK": 2}

WORKOUT_TYPE = {google: ours for ours, names in WORKOUT_TYPES.items() for google in names}


# ---------- Reading Google's JSON (pure functions: no network, no database, easy to test) ----------

def _date(value):
    """{"year": 2026, "month": 10, "day": 9} -> date"""
    try:
        return date(value["year"], value["month"], value["day"])
    except (KeyError, TypeError, ValueError):
        return None


def _time(value):
    """"2026-10-09T17:40:00Z" -> datetime"""
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _int(value):
    # Google sends 64-bit numbers as strings: "8423"
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return None


def _seconds(value):
    """"3725s" -> 3725.0"""
    try:
        return float(value.rstrip("s"))
    except (AttributeError, ValueError):
        return None


def sleep_rows(points):
    """One row per night: the main sleep that ended on each morning. Naps are left out."""
    best = {}
    for point in points:
        sleep = point.get("sleep") or {}
        interval = sleep.get("interval") or {}
        bedtime, wake_time = _time(interval.get("startTime")), _time(interval.get("endTime"))
        if not bedtime or not wake_time or wake_time <= bedtime:
            continue

        summary = sleep.get("summary") or {}
        stages = {s.get("type"): _int(s.get("minutes")) for s in summary.get("stagesSummary") or []}
        awake = _int(summary.get("minutesAwake"))
        if awake is None:
            awake = stages.get("AWAKE")
        total = _int(summary.get("minutesAsleep"))
        if total is None:
            total = round((wake_time - bedtime).total_seconds() / 60) - (awake or 0)
        if not 0 < total <= 1440:
            continue

        meta = sleep.get("metadata") or {}
        rank = (bool(meta.get("mainSleep")), not meta.get("nap"), total)
        day = _date((interval.get("civilEndTime") or {}).get("date")) or wake_time.astimezone(TZ).date()
        if day in best and best[day][0] >= rank:
            continue
        best[day] = (rank, {
            "date": day, "bedtime": bedtime, "wake_time": wake_time, "total_minutes": total,
            "deep_minutes": stages.get("DEEP"), "rem_minutes": stages.get("REM"),
            "light_minutes": stages.get("LIGHT"), "awake_minutes": awake,
        })
    return [row for _, row in sorted(best.values(), key=lambda item: item[1]["date"])]


def metric_rows(steps=(), zone_minutes=(), resting_hr=(), hrv=()):
    """Merge four separate Google answers into one row per day."""
    days = {}

    def put(day, key, value):
        if day and value is not None:
            days.setdefault(day, {"date": day, "steps": None, "zone_minutes": None, "resting_hr": None,
                                  "hrv_ms": None})[key] = value

    def rollup_day(rollup):
        return _date((rollup.get("civilStartTime") or {}).get("date"))

    for r in steps:
        count = _int((r.get("steps") or {}).get("countSum"))
        put(rollup_day(r), "steps", count if count is not None and count >= 0 else None)

    for r in zone_minutes:
        zones = (r.get("timeInHeartRateZone") or {}).get("timeInHeartRateZones")
        if zones is not None:
            # Cardio minutes, counted the way the Google Health app's weekly cardio does:
            # a minute in the moderate zone counts once, a minute in a harder zone counts double
            seconds = sum((_seconds(z.get("duration")) or 0) * ZONE_WEIGHT.get(z.get("heartRateZone"), 0) for z in zones)
            put(rollup_day(r), "zone_minutes", round(seconds / 60))

    for p in resting_hr:
        data = p.get("dailyRestingHeartRate") or {}
        bpm = _int(data.get("beatsPerMinute"))
        put(_date(data.get("date")), "resting_hr", bpm if bpm is not None and 25 <= bpm <= 220 else None)

    for p in hrv:
        data = p.get("dailyHeartRateVariability") or {}
        ms = data.get("averageHeartRateVariabilityMilliseconds")
        put(_date(data.get("date")), "hrv_ms", round(ms, 1) if isinstance(ms, (int, float)) and 0 < ms < 1000 else None)

    return [days[day] for day in sorted(days)]


def workout_rows(points):
    rows = {}
    for point in points:
        exercise = point.get("exercise") or {}
        interval = exercise.get("interval") or {}
        started_at, ended_at = _time(interval.get("startTime")), _time(interval.get("endTime"))
        if not started_at:
            continue
        seconds = _seconds(exercise.get("activeDuration"))          # time moving, without pauses
        if seconds is None and ended_at:
            seconds = (ended_at - started_at).total_seconds()
        if not seconds or seconds <= 0:
            continue

        google_type = exercise.get("exerciseType") or "OTHER"
        summary = exercise.get("metricsSummary") or {}
        rows[started_at] = {
            "started_at": started_at,
            "type": WORKOUT_TYPE.get(google_type, google_type.lower()),
            "name": exercise.get("displayName") or google_type.replace("_", " ").capitalize(),
            "duration_minutes": max(1, round(seconds / 60)),
            "avg_hr": _int(summary.get("averageHeartRateBeatsPerMinute")),
            "calories": _int(summary.get("caloriesKcal")),
        }
    return [rows[key] for key in sorted(rows)]


# ---------- Saving ----------

def save_sleep(conn, user_id, rows):
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO sleep_logs (user_id, date, bedtime, wake_time, total_minutes,
                   deep_minutes, rem_minutes, light_minutes, awake_minutes)
               VALUES (%(user_id)s, %(date)s, %(bedtime)s, %(wake_time)s, %(total_minutes)s,
                   %(deep_minutes)s, %(rem_minutes)s, %(light_minutes)s, %(awake_minutes)s)
               ON CONFLICT (user_id, date) DO UPDATE SET
                   bedtime = EXCLUDED.bedtime, wake_time = EXCLUDED.wake_time,
                   total_minutes = EXCLUDED.total_minutes, deep_minutes = EXCLUDED.deep_minutes,
                   rem_minutes = EXCLUDED.rem_minutes, light_minutes = EXCLUDED.light_minutes,
                   awake_minutes = EXCLUDED.awake_minutes""",
            [{**row, "user_id": user_id} for row in rows],
        )


def save_metrics(conn, user_id, rows):
    # COALESCE: if one of the four requests failed this time, keep the value we already had
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO daily_metrics (user_id, date, steps, zone_minutes, resting_hr, hrv_ms)
               VALUES (%(user_id)s, %(date)s, %(steps)s, %(zone_minutes)s, %(resting_hr)s, %(hrv_ms)s)
               ON CONFLICT (user_id, date) DO UPDATE SET
                   steps = COALESCE(EXCLUDED.steps, daily_metrics.steps),
                   zone_minutes = COALESCE(EXCLUDED.zone_minutes, daily_metrics.zone_minutes),
                   resting_hr = COALESCE(EXCLUDED.resting_hr, daily_metrics.resting_hr),
                   hrv_ms = COALESCE(EXCLUDED.hrv_ms, daily_metrics.hrv_ms)""",
            [{**row, "user_id": user_id} for row in rows],
        )


def save_workouts(conn, user_id, rows):
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO workouts (user_id, started_at, type, name, duration_minutes, avg_hr, calories)
               VALUES (%(user_id)s, %(started_at)s, %(type)s, %(name)s, %(duration_minutes)s,
                   %(avg_hr)s, %(calories)s)
               ON CONFLICT (user_id, started_at) DO UPDATE SET
                   type = EXCLUDED.type, name = EXCLUDED.name, duration_minutes = EXCLUDED.duration_minutes,
                   avg_hr = EXCLUDED.avg_hr, calories = EXCLUDED.calories""",
            [{**row, "user_id": user_id} for row in rows],
        )


# ---------- The connection: one row per user who linked Google Health ----------

def save_connection(conn, user_id, refresh_token, scopes):
    """Store the user's Google refresh token (encrypted). Returns False if they shared no health data."""
    scopes = sorted(s for s in scopes if s.startswith(SCOPE_PREFIX))
    if not scopes:
        return False
    conn.execute(
        """
        INSERT INTO google_health_connections AS c (user_id, refresh_token_encrypted, scopes)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            refresh_token_encrypted = EXCLUDED.refresh_token_encrypted, scopes = EXCLUDED.scopes,
            status = 'active', last_error = NULL, sync_started_at = NULL,
            -- Newly shared data (or a reconnect after a gap) needs the full history again
            last_synced_at = CASE WHEN c.status = 'active' AND c.scopes @> EXCLUDED.scopes THEN c.last_synced_at END
        """,
        (user_id, encrypt_token(refresh_token), scopes),
    )
    return True


def connection_state(conn, user_id):
    """What the app should show: none | syncing | ready | error | expired."""
    row = conn.execute(
        "SELECT status, last_synced_at, last_error FROM google_health_connections WHERE user_id = %s", (user_id,)
    ).fetchone()
    if not row:
        return {"status": "none", "last_synced_at": None}
    status, last_synced_at, last_error = row
    if status == "active":
        status = "ready" if last_synced_at else "error" if last_error else "syncing"
    return {"status": status, "last_synced_at": last_synced_at.isoformat() if last_synced_at else None}


def claim_sync(conn, user_id):
    """If this user's data is due for a refresh, mark the sync as started and return how many days to fetch.
    Returns None when the data is fresh or another request is already syncing."""
    row = conn.execute(
        """
        UPDATE google_health_connections SET sync_started_at = now(), last_error = NULL
        WHERE user_id = %s AND status = 'active'
          AND (sync_started_at IS NULL OR sync_started_at < now() - make_interval(mins => %s))
        RETURNING last_synced_at
        """,
        (user_id, RESYNC_MINUTES),
    ).fetchone()
    if not row:
        return None
    if row[0] is None:
        return BACKFILL_DAYS
    days_since = (datetime.now(TZ).date() - row[0].astimezone(TZ).date()).days
    return min(BACKFILL_DAYS, days_since + OVERLAP_DAYS)


# ---------- Sync ----------

def _pull(conn, client, user_id, scopes, days):
    """Fetch each kind of data the user agreed to share. Returns (how many worked, what failed)."""
    today = datetime.now(TZ).date()
    start = today - timedelta(days=days)
    since = start.isoformat()
    # Daily totals come one per calendar day; the range excludes its end day, so end tomorrow to include today
    first_day, end = start + timedelta(days=1), today + timedelta(days=1)
    metrics = {}

    steps = []
    if SCOPE_ACTIVITY in scopes:
        steps += [
            ("steps", lambda: metrics.update(steps=client.daily_rollup("steps", first_day, end))),
            ("zone minutes", lambda: metrics.update(
                zone_minutes=client.daily_rollup("time-in-heart-rate-zone", first_day, end))),
            ("workouts", lambda: save_workouts(conn, user_id, workout_rows(client.list_points(
                "exercise", f'exercise.interval.civil_start_time >= "{since}"', page_size=25)))),
        ]
    if SCOPE_METRICS in scopes:
        steps += [
            ("resting heart rate", lambda: metrics.update(resting_hr=client.list_points(
                "daily-resting-heart-rate", f'daily_resting_heart_rate.date >= "{since}"'))),
            ("HRV", lambda: metrics.update(hrv=client.list_points(
                "daily-heart-rate-variability", f'daily_heart_rate_variability.date >= "{since}"'))),
        ]
    if SCOPE_SLEEP in scopes:
        steps.append(("sleep", lambda: save_sleep(conn, user_id, sleep_rows(client.list_points(
            "sleep", f'sleep.interval.civil_end_time >= "{since}"', page_size=25)))))

    failed = []
    for label, step in steps:
        try:
            step()
        except AuthorizationExpired:
            raise
        except GoogleHealthError as e:
            # The message names the request that failed. It never contains health data.
            logger.warning("Google Health sync: %s failed for user %s: %s", label, user_id, e)
            failed.append(label)

    save_metrics(conn, user_id, metric_rows(**metrics))
    return len(steps) - len(failed), failed


def sync_user(user_id, days=BACKFILL_DAYS):
    """Bring one user's last `days` days up to date. Never raises: the outcome is saved on their connection."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT refresh_token_encrypted, scopes FROM google_health_connections WHERE user_id = %s AND status = 'active'",
            (user_id,),
        ).fetchone()
        if not row:
            return

        try:
            access_token = get_access_token(decrypt_token(row[0]))
            with HealthClient(access_token) as client:
                worked, failed = _pull(conn, client, user_id, set(row[1]), days)
        except (AuthorizationExpired, InvalidToken):
            conn.execute(
                "UPDATE google_health_connections SET status = 'expired', last_error = 'Sign in again to reconnect' "
                "WHERE user_id = %s", (user_id,))
            return
        except Exception as e:
            logger.exception("Google Health sync failed for user %s", user_id)
            conn.execute("UPDATE google_health_connections SET last_error = %s WHERE user_id = %s",
                         (type(e).__name__, user_id))
            return

        if worked:
            conn.execute(
                "UPDATE google_health_connections SET last_synced_at = now(), last_error = %s WHERE user_id = %s",
                ("Could not read: " + ", ".join(failed) if failed else None, user_id))
        else:
            conn.execute("UPDATE google_health_connections SET last_error = %s WHERE user_id = %s",
                         ("Could not read: " + ", ".join(failed) if failed else "No health data was shared", user_id))
        logger.info("Google Health sync user=%s days=%d ok=%d failed=%d", user_id, days, worked, len(failed))
