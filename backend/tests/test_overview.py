from app.overview import readiness_score

NORMAL = {"hrv_normal": 55, "resting_hr_normal": 60, "sleep_normal": 7.2}


def test_a_normal_day_is_high_readiness():
    result = readiness_score(hrv=55, resting_hr=60, sleep_hours=7.2, **NORMAL)
    assert (result["score"], result["level"]) == (75, "high")
    assert [s["key"] for s in result["signals"]] == ["sleep", "resting_hr", "hrv"]
    assert result["signals"][0] == {"key": "sleep", "value": 7.2, "normal": 7.2, "score": 75}


def test_a_rough_night_is_low_readiness():
    # Low HRV, raised resting heart rate and a short night: all three point the same way
    result = readiness_score(hrv=40, resting_hr=66, sleep_hours=5.3, **NORMAL)
    assert result["level"] == "low"


def test_better_than_normal_never_goes_above_100():
    assert readiness_score(hrv=90, resting_hr=50, sleep_hours=9.5, **NORMAL)["score"] == 100


def test_missing_signal_is_left_out_not_counted_as_zero():
    result = readiness_score(hrv=55, sleep_hours=7.2, hrv_normal=55, sleep_normal=7.2)
    assert result["score"] == 75
    assert [s["key"] for s in result["signals"]] == ["sleep", "hrv"]


def test_one_signal_is_not_enough():
    assert readiness_score(hrv=55, hrv_normal=55) is None
    assert readiness_score(hrv=55, resting_hr=60, sleep_hours=7) is None     # no normal to compare with yet

