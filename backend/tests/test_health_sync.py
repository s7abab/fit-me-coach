from datetime import UTC, date, datetime

from app.google_health import decrypt_token, encrypt_token
from app.health_sync import metric_rows, sleep_rows, workout_rows

# Shaped like real Google Health API answers (https://developers.google.com/health/reference/rest)


def day(d):
    return {"year": 2026, "month": 10, "day": d}


def sleep_point(start, end, end_day, asleep, main=True, nap=False, stages=None):
    return {"sleep": {
        "interval": {"startTime": start, "endTime": end, "civilEndTime": {"date": day(end_day)}},
        "metadata": {"mainSleep": main, "nap": nap},
        "summary": {
            "minutesAsleep": str(asleep), "minutesAwake": "32",
            "stagesSummary": [{"type": t, "minutes": str(m)} for t, m in (stages or {}).items()],
        },
    }}


def test_sleep_night_is_read():
    rows = sleep_rows([sleep_point("2026-10-08T17:40:00Z", "2026-10-09T01:10:00Z", 9, 418,
                                   stages={"DEEP": 71, "REM": 96, "LIGHT": 251, "AWAKE": 32})])
    assert rows == [{
        "date": date(2026, 10, 9),
        "bedtime": datetime(2026, 10, 8, 17, 40, tzinfo=UTC),
        "wake_time": datetime(2026, 10, 9, 1, 10, tzinfo=UTC),
        "total_minutes": 418, "deep_minutes": 71, "rem_minutes": 96, "light_minutes": 251, "awake_minutes": 32,
    }]


def test_nap_does_not_replace_the_main_sleep():
    rows = sleep_rows([
        sleep_point("2026-10-09T09:00:00Z", "2026-10-09T09:40:00Z", 9, 35, main=False, nap=True),
        sleep_point("2026-10-08T17:40:00Z", "2026-10-09T01:10:00Z", 9, 418),
    ])
    assert [r["total_minutes"] for r in rows] == [418]


def test_broken_sleep_points_are_skipped():
    assert sleep_rows([{"sleep": {}}, {"sleep": {"interval": {"startTime": "nonsense", "endTime": None}}}, {}]) == []


def test_daily_metrics_are_merged_by_date():
    rows = metric_rows(
        steps=[{"civilStartTime": {"date": day(8)}, "steps": {"countSum": "9120"}},
               {"civilStartTime": {"date": day(9)}, "steps": {"countSum": "4310"}}],
        # 24 h mostly resting, 10 min moderate, 12 min vigorous (counts double) = 34 cardio minutes
        zone_minutes=[{"civilStartTime": {"date": day(9)}, "timeInHeartRateZone": {"timeInHeartRateZones": [
            {"heartRateZone": "LIGHT", "duration": "80000s"}, {"heartRateZone": "MODERATE", "duration": "600s"},
            {"heartRateZone": "VIGOROUS", "duration": "720s"}]}}],
        resting_hr=[{"dailyRestingHeartRate": {"date": day(9), "beatsPerMinute": "61"}}],
        hrv=[{"dailyHeartRateVariability": {"date": day(9), "averageHeartRateVariabilityMilliseconds": 48.26}}],
    )
    assert rows == [
        {"date": date(2026, 10, 8), "steps": 9120, "zone_minutes": None, "resting_hr": None, "hrv_ms": None},
        {"date": date(2026, 10, 9), "steps": 4310, "zone_minutes": 34, "resting_hr": 61, "hrv_ms": 48.3},
    ]


def test_impossible_heart_rates_are_dropped():
    assert metric_rows(resting_hr=[{"dailyRestingHeartRate": {"date": day(9), "beatsPerMinute": "0"}}]) == []


def test_workout_is_read():
    rows = workout_rows([{"exercise": {
        "interval": {"startTime": "2026-10-09T13:00:00Z", "endTime": "2026-10-09T13:45:00Z"},
        "exerciseType": "TRAIL_RUN", "displayName": "Trail Run", "activeDuration": "2460s",
        "metricsSummary": {"averageHeartRateBeatsPerMinute": "151", "caloriesKcal": 402.7},
    }}])
    assert rows == [{
        "started_at": datetime(2026, 10, 9, 13, 0, tzinfo=UTC),
        "type": "run", "name": "Trail Run", "duration_minutes": 41, "avg_hr": 151, "calories": 403,
    }]


def test_unknown_workout_type_keeps_googles_name():
    rows = workout_rows([{"exercise": {
        "interval": {"startTime": "2026-10-09T13:00:00Z", "endTime": "2026-10-09T13:30:00Z"},
        "exerciseType": "TABLE_TENNIS",
    }}])
    assert (rows[0]["type"], rows[0]["name"], rows[0]["duration_minutes"]) == ("table_tennis", "Table tennis", 30)


def test_refresh_token_is_not_stored_as_plain_text():
    encrypted = encrypt_token("1//refresh-token")
    assert "refresh-token" not in encrypted
    assert decrypt_token(encrypted) == "1//refresh-token"
