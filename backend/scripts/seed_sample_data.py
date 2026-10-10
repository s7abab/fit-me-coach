import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.db import get_conn

TZ = ZoneInfo("Asia/Kolkata")
DAYS = 30          # how many days of history
ROUGH_DAYS = 3     # the hidden story: last 3 days are rough

DEMO_USER = {
    "name": "Demo User",
    "email": "demo@fitmecoach.local",
    "age": 28,
    "sex": "male",
    "height_cm": 175,
    "weight_kg": 74,
    "goal": "Build muscle and improve sleep",
}

# Weekly workout plan (0 = Monday ... 6 = Sunday)
WEEKLY_PLAN = {
    0: ("strength", "Push day", 60),
    1: ("run", "Easy run", 35),
    2: ("strength", "Pull day", 60),
    3: None,                                  # rest day
    4: ("strength", "Leg day", 65),
    5: ("run", "Long run", 55),
    6: None,                                  # rest day
}


# ---------- Data generators (pure functions: no database, easy to test) ----------

def make_sleep(wake_day, rough):
    weekend_night = (wake_day - timedelta(days=1)).weekday() in (4, 5)   # Fri/Sat night
    if rough:
        total = round(random.gauss(320, 15))     # ~5.3 hours
        deep_pct = random.uniform(0.10, 0.13)
    else:
        total = round(random.gauss(430, 25))     # ~7.2 hours
        deep_pct = random.uniform(0.15, 0.20)

    deep = round(total * deep_pct)
    rem = round(total * random.uniform(0.20, 0.25))
    light = total - deep - rem
    awake = random.randint(15, 40)

    # Bed around 11 PM; later on weekends; much later on rough nights
    bed_offset = random.gauss(0, 20) + (60 if weekend_night else 0) + (90 if rough else 0)
    bedtime = datetime.combine(wake_day - timedelta(days=1), time(23, 0), TZ) + timedelta(minutes=bed_offset)
    bedtime = bedtime.replace(second=0, microsecond=0)
    wake_time = bedtime + timedelta(minutes=total + awake)

    return {
        "date": wake_day, "bedtime": bedtime, "wake_time": wake_time,
        "total_minutes": total, "deep_minutes": deep, "rem_minutes": rem,
        "light_minutes": light, "awake_minutes": awake,
    }


def make_workout(day, rough):
    plan = WEEKLY_PLAN[day.weekday()]
    if plan is None:
        return None
    wtype, name, minutes = plan
    duration = round(minutes * (0.7 if rough else 1.0) + random.gauss(0, 4))   # shorter when tired
    avg_hr = round(random.gauss(148, 5) if wtype == "run" else random.gauss(125, 6))
    started_at = datetime.combine(day, time(18, 30), TZ) + timedelta(minutes=random.gauss(0, 20))
    return {
        "started_at": started_at.replace(second=0, microsecond=0),
        "type": wtype, "name": name, "duration_minutes": duration,
        "avg_hr": avg_hr, "calories": round(duration * (10 if wtype == "run" else 6)),
    }


def make_metrics(day, rough, workout):
    steps = random.gauss(8500, 1500)
    if workout and workout["type"] == "run":
        steps += 4500
    if rough:
        steps *= 0.75
    workout_minutes = workout["duration_minutes"] if workout else 0
    workout_calories = workout["calories"] if workout else 0
    return {
        "date": day,
        "steps": max(1500, round(steps)),
        "active_minutes": round(workout_minutes + random.gauss(25, 8)),
        "calories_out": round(1900 + steps * 0.04 + workout_calories),
        "resting_hr": round(random.gauss(60, 1.5) + (6 if rough else 0)),     # higher when stressed
        "hrv_ms": round(random.gauss(55, 4) - (15 if rough else 0), 1),         # lower when stressed
    }


def generate(today, days=DAYS, seed=42):
    """Create `days` of history ending yesterday (sleep includes last night)."""
    random.seed(seed)   # same seed = same data every time
    rough_from = today - timedelta(days=ROUGH_DAYS - 1)
    start = today - timedelta(days=days)
    sleeps, metrics, workouts = [], [], []

    for i in range(days):
        day = start + timedelta(days=i)          # a full past day
        wake_day = day + timedelta(days=1)       # the night after it ends on this morning
        sleeps.append(make_sleep(wake_day, rough=wake_day >= rough_from))
        rough = day >= rough_from
        workout = make_workout(day, rough)
        if workout:
            workouts.append(workout)
        metrics.append(make_metrics(day, rough, workout))

    return sleeps, metrics, workouts


# ---------- Database ----------

def upsert_demo_user(conn):
    return conn.execute(
        """
        INSERT INTO users (name, email, age, sex, height_cm, weight_kg, goal)
        VALUES (%(name)s, %(email)s, %(age)s, %(sex)s, %(height_cm)s, %(weight_kg)s, %(goal)s)
        ON CONFLICT (email) DO UPDATE SET
            name = EXCLUDED.name, age = EXCLUDED.age, sex = EXCLUDED.sex,
            height_cm = EXCLUDED.height_cm, weight_kg = EXCLUDED.weight_kg, goal = EXCLUDED.goal
        RETURNING id
        """,
        DEMO_USER,
    ).fetchone()[0]


def main():
    today = datetime.now(TZ).date()
    sleeps, metrics, workouts = generate(today)

    with get_conn() as conn, conn.transaction():
        user_id = upsert_demo_user(conn)

        # Replace the demo user's old data, so re-running gives a clean, fresh 30 days
        for table in ("sleep_logs", "daily_metrics", "workouts"):
            conn.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))

        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO sleep_logs (user_id, date, bedtime, wake_time, total_minutes,
                       deep_minutes, rem_minutes, light_minutes, awake_minutes)
                   VALUES (%(user_id)s, %(date)s, %(bedtime)s, %(wake_time)s, %(total_minutes)s,
                       %(deep_minutes)s, %(rem_minutes)s, %(light_minutes)s, %(awake_minutes)s)""",
                [{**s, "user_id": user_id} for s in sleeps],
            )
            cur.executemany(
                """INSERT INTO daily_metrics (user_id, date, steps, active_minutes, calories_out, resting_hr, hrv_ms)
                   VALUES (%(user_id)s, %(date)s, %(steps)s, %(active_minutes)s, %(calories_out)s,
                       %(resting_hr)s, %(hrv_ms)s)""",
                [{**m, "user_id": user_id} for m in metrics],
            )
            cur.executemany(
                """INSERT INTO workouts (user_id, started_at, type, name, duration_minutes, avg_hr, calories)
                   VALUES (%(user_id)s, %(started_at)s, %(type)s, %(name)s, %(duration_minutes)s,
                       %(avg_hr)s, %(calories)s)""",
                [{**w, "user_id": user_id} for w in workouts],
            )

    print(f"Demo user id={user_id}: {len(sleeps)} nights, {len(metrics)} days, {len(workouts)} workouts")


if __name__ == "__main__":
    main()