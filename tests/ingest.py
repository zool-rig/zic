import pytest

from zic.ingestor.ingest import (
    clean_name,
    extract_year,
    fold_diacritics,
    genre_match_key,
    get_or_create_album,
    get_or_create_artist,
    get_or_create_genre,
    is_denylisted_genre,
    is_year_or_decade,
    make_sort_title,
    normalize_name,
    parse_number_pair,
    resolve_album_field,
    resolve_artist_field,
    split_artists,
    split_genres,
)

# --- clean_name -----------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        (". High tone        ", "High tone"),
        ("  multiple   spaces  ", "multiple spaces"),
        ("---", None),
        ("", None),
        (None, None),
        ("Normal Title", "Normal Title"),
    ],
)
def test_clean_name(raw, expected):
    assert clean_name(raw) == expected


# --- fold_diacritics / normalize_name --------------------------------------

def test_fold_diacritics_strips_accents():
    assert fold_diacritics("Taï Phong") == "Tai Phong"


def test_normalize_name_is_case_and_accent_insensitive():
    assert normalize_name("Taï Phong") == normalize_name("tai phong")
    assert normalize_name("  Café Del Mar  ") == "cafe del mar"


# --- placeholder resolution -------------------------------------------------

@pytest.mark.parametrize(
    "raw", ["Unknown", "unknown artist", "Various Artists", "Inconnu", "N/A", None, ""]
)
def test_resolve_artist_field_placeholders(raw):
    assert resolve_artist_field(raw) == "Unknown Artist"


def test_resolve_artist_field_keeps_real_names():
    assert resolve_artist_field("Air") == "Air"


@pytest.mark.parametrize("raw", ["Unknown Album", "inconnu", "album inconnu", None])
def test_resolve_album_field_placeholders(raw):
    assert resolve_album_field(raw) == "Unknown Album"


# --- years / genres ---------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [("1998-05-01", 1998), ("1998", 1998), (None, None), ("no year here", None)],
)
def test_extract_year(raw, expected):
    assert extract_year(raw) == expected


@pytest.mark.parametrize("token", ["2015", "90s", "2010s"])
def test_is_year_or_decade_true(token):
    assert is_year_or_decade(token) is True


@pytest.mark.parametrize("token", ["rock", "trip-hop", "20 something"])
def test_is_year_or_decade_false(token):
    assert is_year_or_decade(token) is False


def test_split_genres_splits_on_semicolon_and_comma():
    assert split_genres("Rock; Pop, Jazz") == {"rock", "pop", "jazz"}


def test_split_genres_empty_input():
    assert split_genres(None) == set()
    assert split_genres("") == set()


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Funk / Soul", {"funk", "soul"}),
        ("Folk, World, & Country", {"folk", "world", "country"}),
        ("Rap & Hip-Hop", {"rap", "hip-hop"}),
        ("Soul and R&B", {"soul", "r&b"}),
        ("Rock+Pop|Jazz", {"rock", "pop", "jazz"}),
        ("hip_hop_rap", {"hip hop", "rap"}),
        ("trip_hop", {"trip hop"}),
    ],
)
def test_split_genres_splits_compound_tags(raw, expected):
    assert split_genres(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("R&B", {"r&b"}),
        ("R & B", {"r & b"}),
        ("Rhythm and Blues", {"rhythm and blues"}),
        ("Rock & Roll; Blues", {"rock & roll", "blues"}),
        ("Drum and Bass / Jungle", {"drum and bass", "jungle"}),
        ("Stage & Screen", {"stage & screen"}),
        ("Pop, R&B & Soul", {"pop", "r&b", "soul"}),
    ],
)
def test_split_genres_keeps_protected_names_whole(raw, expected):
    assert split_genres(raw) == expected


def test_split_genres_does_not_split_inside_words():
    # "and" is a separator only as a whole word.
    assert split_genres("Grand Band, Andean") == {"grand band", "andean"}


@pytest.mark.parametrize(
    "token",
    ["wishlist", "Compilation", "Best of 2015", "50 albums you must hear before you die"],
)
def test_is_denylisted_genre(token):
    assert is_denylisted_genre(token) is True


def test_is_denylisted_genre_false_for_real_genre():
    assert is_denylisted_genre("trip-hop") is False


@pytest.mark.parametrize(
    "a, b", [("hip-hop", "hip hop"), ("Trip_Hop", "trip-hop"), ("R&B", "R&B")]
)
def test_genre_match_key_normalizes_separators(a, b):
    assert genre_match_key(a) == genre_match_key(b)


# --- titles / artists --------------------------------------------------------

@pytest.mark.parametrize(
    "title, expected",
    [("The Wall", "wall"), ("Les Misérables", "misérables"), ("Rumours", "rumours")],
)
def test_make_sort_title_strips_leading_article(title, expected):
    assert make_sort_title(title) == expected


def test_split_artists_handles_common_separators():
    assert split_artists("Daft Punk & Pharrell Williams") == ["Daft Punk", "Pharrell Williams"]
    assert split_artists("A feat. B") == ["A", "B"]
    assert split_artists("Solo Artist") == ["Solo Artist"]


def test_parse_number_pair():
    assert parse_number_pair("3/12") == (3, 12)
    assert parse_number_pair("3") == (3, None)
    assert parse_number_pair(None) == (None, None)
    assert parse_number_pair("bad/data") == (None, None)


# --- get_or_create_* (DB-backed) --------------------------------------------

def test_get_or_create_artist_dedupes_by_normalized_name(db):
    first_id = get_or_create_artist(db, "Air")
    second_id = get_or_create_artist(db, "AIR")
    assert first_id == second_id


def test_get_or_create_album_dedupes_by_normalized_name(db):
    artist_id = get_or_create_artist(db, "Air")
    first_id = get_or_create_album(db, "Moon Safari", artist_id, "1998", False)
    second_id = get_or_create_album(db, "moon safari", artist_id, "1998", False)
    assert first_id == second_id


def test_get_or_create_genre_dedupes_across_separators(db):
    genre_id_map = {}
    first_id = get_or_create_genre(db, "trip-hop", genre_id_map)
    second_id = get_or_create_genre(db, "Trip Hop", genre_id_map)
    assert first_id == second_id


def test_get_or_create_genre_creates_distinct_rows_for_distinct_genres(db):
    genre_id_map = {}
    rock_id = get_or_create_genre(db, "rock", genre_id_map)
    jazz_id = get_or_create_genre(db, "jazz", genre_id_map)
    assert rock_id != jazz_id
