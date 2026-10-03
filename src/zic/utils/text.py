import re
import unicodedata
from collections.abc import Iterable
from difflib import get_close_matches

NON_WORD_RE = re.compile(r"[\W_]+")

FUZZY_MIN_TOKEN_LENGTH = 4
FUZZY_CUTOFF = 0.75
FUZZY_MAX_ALTERNATIVES = 3


def fold_diacritics(s: str) -> str:
    """ "Taï Phong" -> "Tai Phong": strips accents for matching purposes."""
    if s.isascii():  # most names: skip the costly per-character pass
        return s
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def normalize_search_text(text: str) -> str:
    """ "Beyoncé - Crazy in Love!" -> "beyonce crazy in love": case-,
    accent- and punctuation-insensitive search key."""
    return " ".join(NON_WORD_RE.sub(" ", fold_diacritics(text).lower()).split())


def fuzzy_alternatives(
    tokens: list[str], vocabulary: Iterable[str], known_text: str = ""
) -> dict[str, list[str]]:
    """Close spellings of each query token found in the vocabulary, to
    tolerate typos ("daft pnuk" -> "punk"). Tokens found as-is in
    `known_text` aren't typos and are skipped, as are short tokens: they'd
    match too many unrelated words."""
    vocabulary = list(vocabulary)
    alternatives: dict[str, list[str]] = {}
    for token in tokens:
        if len(token) < FUZZY_MIN_TOKEN_LENGTH or token in known_text:
            continue
        close = get_close_matches(
            token, vocabulary, n=FUZZY_MAX_ALTERNATIVES, cutoff=FUZZY_CUTOFF
        )
        close = [word for word in close if word != token]
        if close:
            alternatives[token] = close
    return alternatives


def match_rank(
    tokens: list[str],
    primary: str,
    secondary: str = "",
    alternatives: dict[str, list[str]] | None = None,
) -> tuple[int, int] | None:
    """Ranks a normalized text against normalized query tokens (lower is
    better), or returns None if it doesn't match. Every token must be found
    in `primary` (the name) or `secondary` (context, e.g. the artist).

    Ranks: 0 exact name, 1 name prefix, 2 every token starts a word of the
    name, 3 every token in the name, 4 some tokens in the context only,
    5 only matched through a typo-tolerant alternative. Ties go to the
    shortest name."""
    if not tokens:
        return None

    if all(token in primary for token in tokens):
        query = " ".join(tokens)
        padded = f" {primary}"
        if primary == query:
            rank = 0
        elif primary.startswith(query):
            rank = 1
        elif all(f" {token}" in padded for token in tokens):
            rank = 2
        else:
            rank = 3
        return rank, len(primary)

    haystack = f"{primary} {secondary}"
    if all(token in haystack for token in tokens):
        return 4, len(primary)

    if alternatives and all(
        token in haystack
        or any(alt in haystack for alt in alternatives.get(token, ()))
        for token in tokens
    ):
        return 5, len(primary)

    return None
