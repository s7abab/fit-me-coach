from datetime import date
from scripts.seed_sample_data import generate

TODAY = date(2026, 10, 10)


def test_same_seed_gives_same_data():
    assert generate(TODAY) == generate(TODAY)


def test_last_three_nights_are_short():
    sleeps, _, _ = generate(TODAY)
    assert all(s["total_minutes"] < 360 for s in sleeps[-3:])     # under 6h
    assert all(s["total_minutes"] > 360 for s in sleeps[:-3])     # normal nights over 6h


def test_resting_hr_is_raised_on_rough_days():
    _, metrics, _ = generate(TODAY)
    normal = sum(m["resting_hr"] for m in metrics[:-2]) / len(metrics[:-2])
    assert all(m["resting_hr"] >= normal + 3 for m in metrics[-2:])