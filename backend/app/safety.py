EMERGENCY_MESSAGE = (
    "This could be a medical emergency. Please stop any activity and get medical help now: "
    "call 112 or go to the nearest hospital. As a fitness coach, I can't safely help with this."
)

MENTAL_HEALTH_MESSAGE = (
    "I'm really sorry you're going through this, and you don't have to face it alone. "
    "Please talk to someone now: call Tele-MANAS at 14416 (free, 24x7 in India), "
    "or call 112 if you're in immediate danger."
)

EMERGENCY_PHRASES = [
    "chest pain", "chest tightness", "pain in my chest", "fainted", "fainting", "passed out",
    "can't breathe", "cannot breathe", "trouble breathing", "coughing blood",
    "numb on one side", "worst headache",
]

MENTAL_HEALTH_PHRASES = [
    "kill myself", "suicide", "suicidal", "end my life", "want to die",
    "self harm", "self-harm", "hurt myself",
]


def check_red_flags(text):
    t = text.lower()
    if any(p in t for p in MENTAL_HEALTH_PHRASES):
        return MENTAL_HEALTH_MESSAGE
    if any(p in t for p in EMERGENCY_PHRASES):
        return EMERGENCY_MESSAGE
    return None