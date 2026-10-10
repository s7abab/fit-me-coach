import re

EMERGENCY_MESSAGE = (
    "This could be a medical emergency. Please stop any activity and get medical help now: "
    "call 112 or go to the nearest hospital. As a fitness coach, I can't safely help with this."
)

MENTAL_HEALTH_MESSAGE = (
    "I'm really sorry you're going through this, and you don't have to face it alone. "
    "Please talk to someone now: call Tele-MANAS at 14416 (free, 24x7 in India), "
    "or call 112 if you're in immediate danger."
)

# Patterns cover many ways of saying the same thing.
# Each one is written so normal gym talk ("chest day", "breathe during squats") does NOT match.
EMERGENCY_PATTERNS = [
    r"chest\s+(pain|tightness|pressure)",                         # chest pain, chest pressure
    r"(pain|tightness|pressure)\s+in\s+my\s+chest",               # pain in my chest
    r"chest\s+(feels|is|gets|felt)\s+(tight|heavy)",              # chest feels tight
    r"\bfaint(ed|ing)?\b",                                        # fainted, feel faint
    r"passed\s+out",
    r"(can[’']?t|cannot|trouble|hard\s+to|difficulty)\s+breath",  # can't breathe, trouble breathing
    r"coughing\s+(up\s+)?blood",
    r"numb(ness)?\s+on\s+one\s+side",
    r"worst\s+headache",
]

MENTAL_HEALTH_PATTERNS = [
    r"kill(ing)?\s+myself",
    r"suicid",                                                    # suicide, suicidal
    r"end\s+(my\s+life|it\s+all)",
    r"want\s+to\s+die",
    r"self[\s-]?harm",                                            # self harm, self-harm
    r"hurt(ing)?\s+myself",
]

# Compile once when the app starts (faster than compiling on every message)
_EMERGENCY = [re.compile(p, re.IGNORECASE) for p in EMERGENCY_PATTERNS]
_MENTAL_HEALTH = [re.compile(p, re.IGNORECASE) for p in MENTAL_HEALTH_PATTERNS]


def check_red_flags(text: str) -> str | None:
    """Return a safe fixed message if the text is a red flag, otherwise None."""
    if any(p.search(text) for p in _MENTAL_HEALTH):
        return MENTAL_HEALTH_MESSAGE
    if any(p.search(text) for p in _EMERGENCY):
        return EMERGENCY_MESSAGE
    return None
