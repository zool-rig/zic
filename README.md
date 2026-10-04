<div align=center>
    <img src="https://raw.githubusercontent.com/zool-rig/zic/main/images/zic.png" width=128 alt=logo>
    <h1>ZIC</h1>
    <p>A local-library desktop music player with album/genre browsing and genre-aware smart playlists.</p>

![Python](https://img.shields.io/badge/python-3.13%2B-blue?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/UI-PySide6-41cd52?logo=qt&logoColor=white)
![SQLite](https://img.shields.io/badge/database-SQLite-07405e?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![PyPI](https://img.shields.io/pypi/v/zic)
![Downloads](https://img.shields.io/pypi/dm/zic)

![overview](https://raw.githubusercontent.com/zool-rig/zic/main/images/overview.png)
</div>


## Features

- **Smart playlists that never run dry** : an album flows into the rest of the artist's discography, then into albums of *near* genres, then into a random selection (see [Smart playlists](#smart-playlists))
- **Mood-following shuffle** : the random playlist learns from what you listen to the end, and resets as soon as you skip (see [Mood](#mood))
- **Genre intelligence** : genre proximity is computed from your own library's co-occurrence patterns, not a fixed taxonomy (see [Genre Intelligence](#genre-intelligence))
- **Global search** : find artists, albums, genres and songs as you type, forgiving accents, word order and small typos
- **Metadata editing** : fix song and album info from the app, optionally written back to your files' tags
- Play local MP3/M4A music files, browse your albums, artists and genres
- Automatic metadata enrichment and covers with the Discogs API
- Library scans with live progress, in the terminal and in the app, that follow moved files and drop deleted ones
- Likes and plays history

## Prerequisites

- Python 3.13+
- **Audio codecs** : ZIC relies on Qt Multimedia to play MP3/M4A files, which in turn relies on system-level codecs (via FFmpeg on most platforms). If you get no sound with no error, install FFmpeg for your OS:

  | OS | Command |
  | - | - |
  | Linux (Debian/Ubuntu) | `sudo apt install ffmpeg` |
  | Linux (Arch) | `sudo pacman -S ffmpeg` |
  | macOS (Homebrew) | `brew install ffmpeg` (maybe no action needed) |
  | Windows | Usually bundled with Qt Multimedia, no action needed |

## Installation

### With `uv` (Recommended)

[uv](https://docs.astral.sh/uv/getting-started/installation/) is a faster and more convenient package manager than `pip`

```bash
# cd where you want to create the virtual env
uv venv zic-venv

source zic-venv/bin/activate # Linux/macOS
# zic-venv\Scripts\activate  # Windows

uv pip install zic
```

### Quick install

```bash
pip install zic
```

## Getting started

### Import your library

```bash
zic ingest /path/to/your/library
```

### First launch

```bash
zic
```

The first time you launch ZIC, a welcome dialog will ask you to register where your MP3/M4A library and your database are located.

![first-launch](https://raw.githubusercontent.com/zool-rig/zic/main/images/first-launch.png)

### Keep your library up to date

Use **Database > Check for new songs** in the app (or run `zic ingest` again). Only new and modified files are read, and a progress dialog shows the files left, the elapsed time and an estimate of the remaining time. Music keeps playing meanwhile, and the library can't be edited until the scan is over.

A scan also keeps the library in sync with your folders:

- **moved or renamed files** are recognized by their content and keep their plays and likes (as long as the file itself wasn't modified on the way)
- **deleted files** are removed from the library, along with the albums they leave empty
- if no audio file is found at all (e.g. an external drive that isn't mounted), nothing is removed

**Database > Full rescan** re-reads every file, e.g. after re-tagging files with another tool.

From the terminal, `zic ingest` shows the same progress in a live text interface, then a summary.

## Smart playlists

Whatever you start, ZIC keeps the music going with songs that make sense, instead of stopping at the end of an album or jumping to anything:

1. **The album** you started, in order (or shuffled, or from the song you picked)
2. **The rest of the artist's discography**
3. **Albums of near genres** : the album's genres and their closest neighbors in your [genre space](#genre-intelligence)
4. **A random selection**, which follows your current [mood](#mood)

Each step only kicks in when the previous one is exhausted, and songs already played in the playlist aren't picked again.

### Mood

The shuffle button starts a fully random playlist. Then, ZIC listens to how you listen:

- **Listening to a song to the end** sets the mood : the song's genres, extended to their near genres. The next songs are picked within that mood.
- **Skipping a song** resets the mood : the next pick is fully random again, until a song catches you.

The playlist drifts along with you: let a song play and you get more of its kind; skip and you're off somewhere else. The mood also drives the random step of the other playlists. When no song matches the mood anymore, ZIC falls back to a fully random pick.

> [!TIP]
> The mood relies on genre proximity: [compute genre positions](#computing-positions) once your library is imported.

## Search

The search bar of the album explorer finds **artists, albums, genres and songs** as you type, grouped by kind. It ignores case, accents and punctuation (`beyonce` finds *Beyoncé*), word order, and tolerates small typos in artist, album and genre names (`daft pnuk` finds *Daft Punk*).

- **An artist or a genre** filters the explorer
- **An album** opens it
- **A song** opens its album with the song highlighted

Use the arrow keys and Enter to pick a result. Pressing Enter without picking one filters the album explorer by the typed text.

## Editing metadata

The info buttons of the album view open a dialog for the album or for a song, showing its details (file, format, bitrate, plays, likes, dates...) and letting you edit:

- **Songs** : title, artist, track and disc numbers. A song can also be **hidden** from the library; hidden songs are listed in their album's info, where they can be shown again.
- **Albums** : name, album artist, year and genres. Giving an album the name and artist of another one merges them.

> [!IMPORTANT]
> By default, edits are also **written to the tags of your audio files**: they're kept on rescans and seen by other music players. You can turn this off in the dialog (the choice is remembered): your files are then left untouched, but a full rescan, or any change to a file, brings back the file's own tags.

## Genre Intelligence

Most music apps treat genres as a flat, external taxonomy. ZIC does something different: it computes how *your* genres relate to each other based on how they actually co-occur across your own albums.

### How it works

1. **Co-occurrence analysis** — ZIC looks at which genre tags appear together on the same albums in your library.
2. **Positive PMI (Pointwise Mutual Information)** — rather than raw counts (which would let generic tags like "rock" dominate purely through volume), ZIC measures how much more often two genres co-occur than pure chance would predict, with discounting to avoid overweighting rare pairs.
3. **Classical MDS (Multidimensional Scaling)** — the resulting similarity scores are projected into a compact set of coordinates per genre, positioning genres close together when they tend to appear side by side in your collection, and far apart when they don't.

These positions power the **genre-aware [smart playlists](#smart-playlists)** (finding "near genres" when an album and its artist's discography are exhausted) and the **[mood](#mood)**, and can be visualized directly.

### Computing positions

Run this after importing your library, and again whenever you've ingested enough new albums that genre relationships might have shifted:

```bash
zic genres compute ~/Music/.db
```

### Visualizing genre space

See how your own genres cluster together, in an interactive 2D plot opened in your browser:

```bash
zic genres vis ~/Music/.db
```

![genres-visualization](https://raw.githubusercontent.com/zool-rig/zic/main/images/genres-vis.png)

>[!NOTE]
>These visualizations are in 2D, so they are partial representations of the real space which is in 8 dimensions

## Configuration

### App config

A toml file containing the library directory and database locations

| OS | Location |
| - | - |
| Linux | ~/.config/Zic/app_config.toml |
| Windows | %LOCALAPPDATA%\Zic\app_config.toml |
| Mac Os | ~/Library/Application Support/Zic/app_config.toml |

### User Config

When closed, ZIC saves your preferences (volume, sorting, hotkeys, whether edits are written to your files...) in a json file

| OS | Location |
| - | - |
| Linux | ~/.local/share/Zic/user_config.json |
| Windows | %LOCALAPPDATA%\Zic\user_config.json |
| Mac Os | ~/Library/Application Support/Zic/user_config.json |

### Ingestor environment variables

While running the ingestor, you can specify your Discogs API credentials with the following environment variables : `ZIC_INGESTOR_DISCOGS_KEY` and `ZIC_INGESTOR_DISCOGS_TOKEN`

### Hotkeys

| Key | Action |
| - | - |
| Space | Toggle play/pause |
| m | Mute |
| n | Next song |
| p | Previous song |
| F5 | Reload library |
| s | Shuffle playlist |
| Right arrow | Advance playback (5s) |
| Left arrow | Rewind playback (5s) |
| + | Volume up |
| - | Volume down |
| l | Like current song |
| d | Dislike current song |

## CLI Reference

```bash
❯ zic --help
Usage: zic [OPTIONS] [COMMAND] [ARGS]...

  A local-library desktop music player with album/genre browsing and genre-
  aware smart playlists.

Options:
  -V      Show the current version of ZIC
  --help  Show this message and exit.

Commands:
  genres  Manage genre proximity positions used to build genre-aware...
  ingest  Ingests an audio library (mp3/m4a) into a SQLite database.

  Run the GUI : zic
```

```bash
❯ zic ingest --help
Usage: zic ingest [OPTIONS] FOLDER

  Ingests an audio library (mp3/m4a) into a SQLite database.

Positional arguments:
  FOLDER  Root folder of the library to scan

Options:
  --db PATH                 Path to the SQLite database, default to
                            '$FOLDER/.db'
  --rescan                  Force re-parsing of every file, even unchanged
                            ones
  -k, --discogs-key TEXT    A Discogs Auth key
  -t, --discogs-token TEXT  A Discogs Auth token
  --help                    Show this message and exit.
```

```bash
❯ zic genres --help
Commands:
  compute  Computes proximity positions for every genre in the library.
  vis      Opens an interactive 2D plot of the computed genre positions.
```

## Contributing

Contributions are welcome !

### Installation

1. Clone this repository
2. cd into `zic`
3. Create a venv

```bash
uv venv
source .venv/bin/activate # Linux/macOS
# .venv\Scripts\activate  # Windows
```

4. Install zic as editable package

```bash
uv pip install -e .
```

### Debug

You can set the `ZIC_DEVEL=1` env var to activate the debug level of logging.

### Run tests and checks

`uv sync` installs the development tools (pytest, ruff) along with ZIC. The same checks run on every push and pull request to `main` (see [.github/workflows/ci.yml](https://github.com/zool-rig/zic/blob/main/.github/workflows/ci.yml)):

```bash
uv run ruff check src tests          # lint
uv run ruff format --check src tests # formatting (`ruff format src tests` to fix it)
uv run pytest                        # tests
```

### Database schema

The database is a cache of your library, rebuilt from your files: after a change to `schema.sql`, delete the database and run `zic ingest` again. Plays, likes, hidden songs and library-only edits live in the database only and are lost when it's deleted.

## License

See [LICENSE](https://github.com/zool-rig/zic/blob/main/LICENSE).
