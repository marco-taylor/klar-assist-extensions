"""Language selection shared by modules, without changing ConversationInput."""
import re
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
_TAG = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{2,8})*")


@dataclass(frozen=True)
class LanguageTag:
    canonical: str
    language: str


def normalize_language(value: object) -> LanguageTag | None:
    """Conservative language/script/region/variant tags; no guessed language."""
    if not isinstance(value, str):
        return None
    value = value.strip().replace('_', '-')
    if len(value) > 63 or not _TAG.fullmatch(value):
        return None
    parts = value.split('-')
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 4 and part.isalpha():
            normalized.append(part.title())
        elif (len(part) == 2 and part.isalpha()) or (len(part) == 3 and part.isdigit()):
            normalized.append(part.upper())
        else:
            normalized.append(part.lower())
    return LanguageTag('-'.join(normalized), normalized[0])


class LanguageRegistry(Generic[T]):
    """Explicit providers; None declares a planned, inactive language."""
    def __init__(self):
        self._providers: dict[str, T | None] = {}

    def register(self, code: str, provider: T | None):
        tag = normalize_language(code)
        if tag is None:
            raise ValueError("Invalid language code")
        if tag.canonical in self._providers:
            raise ValueError("Language already registered")
        self._providers[tag.canonical] = provider

    def resolve(self, code: object) -> T | None:
        tag = normalize_language(code)
        if tag is None:
            return None
        if tag.canonical in self._providers:
            return self._providers[tag.canonical]
        return self._providers.get(tag.language)

    @property
    def declared_languages(self) -> tuple[str, ...]:
        return tuple(self._providers)

    @property
    def supported_languages(self) -> tuple[str, ...]:
        return tuple(code for code, provider in self._providers.items() if provider is not None)
