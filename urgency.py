from nlp import normalize_text

LEVELS = ("low", "medium", "high", "critical")

CRITICAL_SIGNALS = [
    "emergency", "everyone", "everybody", "all users", "whole office",
    "entire office", "whole team", "entire team", "company wide",
    "production down", "data loss", "lost data", "lost all my data",
    "ransomware", "hacked", "breach", "virus", "malware", "phishing",
    "stolen", "on fire", "smoke",
]

HIGH_SIGNALS = [
    "urgent", "urgently", "asap", "immediately", "right now", "critical",
    "deadline", "client", "customer", "presentation", "board meeting",
    "interview", "blocked", "cant work", "cannot work", "unable to work",
    "not able to work", "cant do my work", "nothing works",
    "not working at all", "is down", "are down", "went down",
    "server down", "network down", "system down", "since morning",
    "since yesterday",
]

RELAXED_PHRASES = [
    "no rush", "not urgent", "not very urgent", "no hurry",
    "not in a hurry", "low priority", "when you get a chance",
    "when possible", "whenever you can", "at your convenience",
    "minor issue", "small issue", "cosmetic",
]


def _first_hit(padded, signals):
    for signal in signals:
        if f" {signal} " in padded:
            return signal
    return None


def detect_urgency(text, base="medium"):
    """
    Returns (urgency, reasons).
    base is the matched article's default urgency (or "medium").
    """
    padded = f" {normalize_text(text)} "
    base_index = LEVELS.index(base) if base in LEVELS else 1
    level = base_index
    reasons = [f"starting point: {LEVELS[base_index]}"]

    # Remove "not urgent" style phrases first so "urgent" inside them is ignored
    relaxed = []
    for phrase in RELAXED_PHRASES:
        key = f" {phrase} "
        if key in padded:
            relaxed.append(phrase)
            padded = padded.replace(key, " ")

    signal_found = False

    hit = _first_hit(padded, CRITICAL_SIGNALS)
    if hit:
        signal_found = True
        level = max(level, 3)
        reasons.append(f'message mentions "{hit}"')

    hit = _first_hit(padded, HIGH_SIGNALS)
    if hit:
        signal_found = True
        level = max(level, 2)
        reasons.append(f'message mentions "{hit}"')

    if relaxed and not signal_found:
        level = max(0, level - 1)
        reasons.append(f'user said "{relaxed[0]}"')

    return LEVELS[level], reasons