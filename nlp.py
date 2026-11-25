import math
import re

# ---- Tuning knobs (safe to adjust) ----
MATCH_THRESHOLD = 0.30   # below this confidence, the bot says it is not sure
SATURATION = 6.0         # higher = confidence grows more slowly with score
PHRASE_BONUS = 2.0       # bonus per multi-word keyword phrase found
ALT_MIN_CONFIDENCE = 0.25
ALT_MIN_RATIO = 0.6      # an alternative must reach 60% of the best confidence

W_KEYWORD = 3.0
W_TITLE = 2.0
W_CATEGORY = 1.0
W_SOLUTION = 0.4

STOPWORDS = set(
    """a an the and or but if so to of in on at for from with by is are was were
    be been am do does did have has had i me my we our you your it its this that
    these those there here not no can cant cannot could would should will wont
    just very really please help need want get got getting im ive isnt dont
    doesnt didnt since when what why how which who whom as about into again
    also some any""".split()
)


def normalize_text(text):
    """Lowercase, unify common spellings, strip punctuation."""
    text = text.lower()
    text = text.replace("'", "").replace("\u2019", "")
    text = re.sub(r"wi[\s\-]?fi", "wifi", text)
    text = re.sub(r"e[\s\-]mail", "email", text)
    text = re.sub(r"(log|sign)[\s\-]?in\b", "login", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def stem(word):
    """Very small suffix stripper. Applied equally to messages and articles."""
    if len(word) <= 3:
        return word
    if word.endswith("ing") and len(word) > 5:
        word = word[:-3]
    elif word.endswith("ed") and len(word) > 4:
        word = word[:-2]
    elif word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "ls":
        word = word[:-1]
    return word


def tokenize(text):
    words = normalize_text(text).split()
    return [stem(w) for w in words if w not in STOPWORDS]


def _doc_weights(article):
    weights = {}

    def add(text, weight):
        for token in tokenize(text):
            if weights.get(token, 0) < weight:
                weights[token] = weight

    add(article["solution"], W_SOLUTION)
    add(article["category"], W_CATEGORY)
    add(article["title"], W_TITLE)
    add(article["keywords"], W_KEYWORD)
    return weights


def _keyword_phrases(article):
    phrases = []
    for part in article["keywords"].split(","):
        phrase = normalize_text(part)
        if len(phrase.split()) >= 2:
            phrases.append(phrase)
    return phrases


def find_matches(message, articles):
    """
    articles: list of dicts with id, title, category, keywords, solution.
    Returns a list of (article, score, confidence), best first.
    """
    if not articles:
        return []

    docs = [_doc_weights(a) for a in articles]
    total = len(articles)

    df = {}
    for weights in docs:
        for token in weights:
            df[token] = df.get(token, 0) + 1
    idf = {t: math.log((total + 1) / (count + 0.5)) + 1 for t, count in df.items()}

    query_tokens = set(tokenize(message))
    padded_message = f" {normalize_text(message)} "

    results = []
    for article, weights in zip(articles, docs):
        score = sum(idf[t] * weights[t] for t in query_tokens if t in weights)
        for phrase in _keyword_phrases(article):
            if f" {phrase} " in padded_message:
                score += PHRASE_BONUS
        confidence = score / (score + SATURATION) if score > 0 else 0.0
        results.append((article, score, confidence))

    results.sort(key=lambda r: r[2], reverse=True)
    return results


# ---- Small talk ----
GREETING_WORDS = {"hi", "hii", "hello", "hey", "hola", "namaste", "yo"}
GREETING_FILLER = {
    "there", "good", "morning", "afternoon", "evening", "everyone",
    "team", "auraflow", "bot", "how", "are", "you", "whats", "up",
}
THANKS_WORDS = {"thanks", "thank", "thx", "ty"}
THANKS_FILLER = {
    "you", "so", "much", "a", "lot", "very", "for", "the", "help",
    "that", "worked", "works", "great", "perfect", "awesome",
}
BYE_WORDS = {"bye", "goodbye", "cya"}


def detect_smalltalk(message):
    words = set(normalize_text(message).split())
    if not words or len(words) > 8:
        return None
    if words & GREETING_WORDS and words <= GREETING_WORDS | GREETING_FILLER:
        return "greeting"
    if words & THANKS_WORDS and words <= THANKS_WORDS | THANKS_FILLER:
        return "thanks"
    if words & BYE_WORDS and len(words) <= 3:
        return "bye"
    return None