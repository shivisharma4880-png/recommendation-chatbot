"""Match a shopper message to one of the FAQ rows of the catalogue workbook."""

from __future__ import annotations

import re
from typing import Iterable, Optional

from src.catalogue import FAQ

_STOP = {
    "a", "an", "the", "i", "me", "my", "you", "your", "we", "us", "do", "does", "did", "can", "could", "would",
    "will", "should", "shall", "is", "are", "was", "be", "to", "of", "in", "on", "for", "and", "or", "with", "this",
    "that", "these", "those", "it", "its", "what", "which", "who", "how", "why", "when", "where", "if", "not", "at",
    "from", "there", "any", "have", "has", "get", "please", "tell", "about", "like", "want", "need", "am", "so",
    "also", "just", "kindly", "hi", "hello",
}
_QUESTION_START = re.compile(
    r"^(how|what|why|when|where|which|who|can|could|do|does|did|is|are|am|will|would|should|shall|kya|kaise|kab|kitna)\b", re.I
)


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokens(text: str) -> set:
    return {_stem(w) for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOP}


def is_question_like(message: str) -> bool:
    text = message.strip()
    return "?" in text or bool(_QUESTION_START.match(text))


# (message regex, FAQ question prefix, optional guard regex that must be absent)
_TOPIC_RULES = [
    (r"\b(deliver\w*|shipping|ship|arrive|arrival|dispatch|courier|reach me|pin ?code)\b", "how long will delivery"),
    (r"\b(returns?|exchange|refund)\b", "can i return"),
    (r"\bcancel\w*\b", "can i cancel"),
    (r"\b(real|pure|genuine|solid|actual)\s+(gold|silver)\b|\bprecious metal\b|\bhallmark", "is the jewellery in this catalogue real gold"),
    (r"\bsize chart\b|\bsize guide\b|\bwhich size\b|\bwhat size (should|do)\b|\bchoose (the )?(right )?size\b|\bmeasurements?\b", "how do i choose the right size"),
    (r"\bdifference between running and walking\b", "what is the difference between running and walking"),
]
_CARE_RULES = [
    (r"\bwatch(es)?\b", "how should i care for a watch"),
    (r"\bearrings?\b", "how should i care for earrings"),
    (r"\bsandals?\b", "how should i care for sandals"),
    (r"\b(jewell?ery|necklace|bracelet|bangles?|imitation)\b", "how should i care for imitation jewellery"),
    (r"\b(dress|kurta|saree|sari|lehenga|outfit|clothes|suit|top|shirt|fabric)\b", "how do i wash this dress"),
]
_CARE_WORDS = re.compile(r"\b(care|wash|laundry|clean|cleaning|dry ?clean)\b")


def _find(faqs: Iterable[FAQ], prefix: str) -> Optional[FAQ]:
    prefix = prefix.lower()
    for faq in faqs:
        if faq.question.lower().startswith(prefix):
            return faq
    return None


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def match_faq(message: str, faqs: list, hint: Optional[str] = None) -> Optional[FAQ]:
    """Best FAQ for ``message`` or None.

    Order: exact question text -> topic rules (delivery, returns, care...) -> token overlap.
    Only question-like messages (or very short ones) are matched by overlap so that shopping
    requests such as "I need an outfit for a festive occasion" are not hijacked by an FAQ.
    """
    lower = message.lower()
    norm = _norm(message)
    for faq in faqs:
        if _norm(faq.question) == norm:
            return faq

    question = is_question_like(message)
    questionish = question or len(norm.split()) <= 4
    shopping = re.search(r"\b(show|suggest|recommend|find|looking|give me)\b", lower)

    if questionish and not (shopping and not question):
        for pattern, prefix in _TOPIC_RULES:
            if re.search(pattern, lower):
                faq = _find(faqs, prefix)
                if faq:
                    return faq
        if _CARE_WORDS.search(lower):
            for pattern, prefix in _CARE_RULES:
                if re.search(pattern, lower):
                    faq = _find(faqs, prefix)
                    if faq:
                        return faq
        if re.search(r"\bin stock\b|\bavailability\b|\bstock status\b", lower):
            faq = _find(faqs, "are these products in stock")
            if faq:
                return faq

    if not question:
        return None
    msg_tokens = tokens(message + " " + (hint or ""))
    best, best_score = None, 0.0
    for faq in faqs:
        q_tokens = tokens(faq.question)
        if not q_tokens:
            continue
        inter = msg_tokens & q_tokens
        if len(inter) < 2:
            continue
        coverage = len(inter) / len(q_tokens)
        precision = len(inter) / max(1, len(tokens(message)))
        score = coverage * 0.7 + precision * 0.3
        if coverage >= 0.7 and precision >= 0.5 and score > best_score:
            best, best_score = faq, score
    return best
