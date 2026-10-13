"""Compatibility entrypoint; language dispatch, never German fallback."""
from .languages import LANGUAGES
from .languages.de.matcher import normalize


def is_candidate(text: str, language: str) -> bool:
    provider = LANGUAGES.resolve(language)
    return provider is not None and provider.is_candidate(text)
