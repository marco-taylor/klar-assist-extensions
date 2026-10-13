"""Cheap, bounded candidate gate; no intent/entity/number interpretation."""
import re
import unicodedata


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split()).strip('?.!"“”„ ')

# A full utterance must be a weather question, never an imperative/mixed plan.
_CANDIDATE = re.compile(
    r"(?:wetter(?:\s+[^.!?;]+)?|"
    r"wie (?:ist|wird) (?:das wetter(?:\s+[^.!?;]+)?|[^.!?;]+ das wetter)|"
    r"wie sieht (?:das wetter(?:\s+[^.!?;]+)?|[^.!?;]+ das wetter) aus|"
    r"(?:regnet es|wird es(?:\s+[^.!?;]+)? regnen)(?:\s+[^.!?;]+)?|"
    r"wie wird es (?:am )?(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag))"
)
_FORBIDDEN = re.compile(r"\b(?:und|aber|schalte|stelle|öffne|oeffne|starte|stoppe|kalender|termine?|licht|heizung|rollläden|rolllaeden|timer)\b")


def is_candidate(text: str) -> bool:
    if not isinstance(text, str) or not 0 < len(text) <= 320:
        return False
    normalized = normalize(text)
    return not _FORBIDDEN.search(normalized) and _CANDIDATE.fullmatch(normalized) is not None
