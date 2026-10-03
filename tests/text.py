from zic.utils.text import (
    fold_diacritics,
    fuzzy_alternatives,
    match_rank,
    normalize_search_text,
)


def test_fold_diacritics():
    assert fold_diacritics("Taï Phong") == "Tai Phong"
    assert fold_diacritics("plain") == "plain"


def test_normalize_search_text_ignores_case_accents_and_punctuation():
    assert (
        normalize_search_text("  Beyoncé - Crazy in Love!") == "beyonce crazy in love"
    )
    assert normalize_search_text("La Femme d'Argent") == "la femme d argent"
    assert normalize_search_text("snake_case") == "snake case"


def test_match_rank_orders_exact_prefix_word_start_substring():
    tokens = ["moon"]
    exact = match_rank(tokens, "moon")
    prefix = match_rank(tokens, "moon safari")
    word_start = match_rank(tokens, "blue moon")
    substring = match_rank(tokens, "honeymoon")
    assert exact < prefix < word_start < substring


def test_match_rank_any_word_order():
    assert match_rank(["safari", "moon"], "moon safari") is not None


def test_match_rank_context_only_ranks_after_name_matches():
    in_name = match_rank(["air"], "air")
    in_context = match_rank(["air", "boy"], "sexy boy", "air")
    assert in_context is not None
    assert in_name < in_context


def test_match_rank_requires_every_token():
    assert match_rank(["moon", "rock"], "moon safari", "air") is None
    assert match_rank([], "moon safari") is None


def test_fuzzy_alternatives_fixes_typos_of_long_enough_tokens():
    vocabulary = {"daft", "punk", "air"}
    assert fuzzy_alternatives(["pnuk"], vocabulary) == {"pnuk": ["punk"]}
    # Too short to be corrected reliably.
    assert fuzzy_alternatives(["aie"], vocabulary) == {}


def test_fuzzy_alternatives_skips_known_words():
    assert fuzzy_alternatives(["punks"], {"punk"}, known_text="punks not dead") == {}


def test_match_rank_through_alternatives_ranks_last():
    alternatives = {"pnuk": ["punk"]}
    assert match_rank(["daft", "pnuk"], "daft punk", alternatives=alternatives) == (
        5,
        len("daft punk"),
    )
