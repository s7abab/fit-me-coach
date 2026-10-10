import pytest
from app.safety import check_red_flags, EMERGENCY_MESSAGE, MENTAL_HEALTH_MESSAGE


@pytest.mark.parametrize("text", [
    "I get chest pain when I run",
    "My chest feels tight when I climb stairs",
    "I fainted during my workout",
    "I have trouble breathing while jogging",
])
def test_emergencies_are_caught(text):
    assert check_red_flags(text) == EMERGENCY_MESSAGE


@pytest.mark.parametrize("text", [
    "I want to end my life",
    "I've been thinking about self-harm",
])
def test_mental_health_is_caught(text):
    assert check_red_flags(text) == MENTAL_HEALTH_MESSAGE


@pytest.mark.parametrize("text", [
    "Best exercises for chest day?",
    "How should I breathe during squats?",
    "I passed my fitness test",
    "Chest press vs push ups?",
])
def test_normal_gym_talk_is_not_flagged(text):
    assert check_red_flags(text) is None