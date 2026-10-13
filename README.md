# MusicGalaxy

A desktop music explorer. Composers, singers and conductors are laid out as a cloud of names;
click one and MusicGalaxy finds a recording of them on [archive.org](https://archive.org) and plays it.
When a track ends, an autoplay mode picks the next name: a random walk to a related artist,
staying within a genre, moving through time, and so on.

Longer-term goals: a better measure of how related two artists or styles are than the current
hand-assigned `temp` ("musical temperature") value, and more autoplay strategies.

## Requirements

- [Node.js](https://nodejs.org/) (LTS version; includes `npm`)
- [git](https://git-scm.com/)
- An internet connection (recordings stream from archive.org and Wikimedia Commons, radio from stations listed on Radio Browser, and D3 loads from d3js.org)

Check they're installed:

```sh
node --version
git --version
```

## Getting the code

First time:

```sh
git clone https://github.com/ravbag/musicgalaxy.git
cd musicgalaxy
```

Already cloned:

```sh
cd path/to/musicgalaxy
git pull
```

## Running it

### As a desktop app (Electron) — recommended

```sh
npm install   # first time only: downloads Electron (takes a minute)
npm start     # opens the MusicGalaxy window
```

After the first time, `npm start` is all you need.

### In a web browser

Double-clicking `index_fixed_working_v9.html` does **not** work. Browsers block a page opened from
disk (`file://`) from reading `knowledge_base.json`, so you'd see "Failed to load knowledge_base.json"
and an empty map. Serve the folder over HTTP instead:

```sh
python3 -m http.server 8000      # on Windows: python -m http.server 8000
```

Then open <http://localhost:8000/index_fixed_working_v9.html>. Press Ctrl+C in the terminal to stop the server.

## Using the app

### The map

- **Left to right is time**: each name sits at its `era` (roughly when the person was active),
  from the 1100s on the left to the present on the right.
- **Bottom to top is relatedness**: artists that are related in style (ignoring time, which is
  already left to right) sit at similar heights. The order is worked out from the relatedness
  measure below, so it improves when you build `relations.json`. Each name is also pulled towards
  its most related artists.
- **Colour is the type of artist**: gold = composer, pink = singer, blue = conductor, green = instrumentalist.
- **Large bold names** are "masters", the 100 core figures; smaller names are secondary.
- **Drag** to pan and **scroll** to zoom. The name that's playing pulses.
- **Zoom in to see more names.** Zoomed out you see only the masters; at normal zoom the most
  notable other artists too; from about 3× zoom all of them. The counter in the bottom-right corner
  shows how many are visible ("173 of 896 names · zoom in for more"). Notability is how many
  Wikipedia languages cover an artist, with a head start for the hand-curated artists over the ones
  the build script added. The artist that's playing, its closest related artists and any search
  matches are always shown, whatever the zoom.

### Playing music

- **Click any name** to play a recording by or of them.
- **Search box**: type to filter by name, alternative name (e.g. "Chopin" finds Frédéric Chopin)
  or tag (e.g. "Baroque"). Names that don't match are dimmed. Click a result, or press
  **Enter** to play the best match. **Esc** closes the results list.
- **Tag chips**: the tags of the current artist appear under the track title. Clicking one makes it
  the *active tag*, which the Within Tag mode uses.
- The player bar has the usual play/pause, seek and volume controls.

### Where the music comes from

There are three sources. The **Sources** chips under the buttons switch each one on or off
(at least one stays on), and your choice is remembered.

| Source | What it is | Sound |
|---|---|---|
| **archive.org** | The artist's archive.org collections (from `collections` in the data), plus any archive.org item mentioning Musopen. 78 rpm transfers are excluded here. | Varies; often good |
| **Wikimedia Commons** | Free and public-domain audio files on [Wikimedia Commons](https://commons.wikimedia.org) that mention the artist, many from Musopen and other free recording projects | Mixed, often good |
| **78 rpm (historic)** | archive.org's 78 rpm transfers (the Great 78 Project and similar), roughly 1900–1950 | Mono, with surface noise and short sides |

**Order.** For each artist, archive.org and Wikimedia Commons are tried first, in random order for
variety, and 78s last. The exception is singers and conductors active before 1950, whose recordings
mostly exist only on 78s; for them the 78s are tried first.

**Choosing a recording.**
- *archive.org*: takes up to 50 of the most-downloaded matching items and looks at up to 3 of them at
  random. It plays a random full-length track, in the best encoding available (FLAC first, then
  high-bitrate MP3/Ogg, then low-bitrate MP3), and prefers an item with a good encoding.
- *Wikimedia Commons*: picks a random matching audio file, preferring files categorised as music.
  It skips MIDI files, pronunciation clips, anything under 45 seconds and spoken content: talks,
  concert introductions, interviews, lectures and podcasts, recognised by words such as *interview*,
  *lecture*, *concert introduction*, *pre-concert talk*, *inleiding*, *(Konzert)einführung* or
  *conférence* in the title, description or categories. Plain "introduction" is allowed, since it's
  common in music titles (*Introduction and Allegro*).
- The track line shows the source in blue, then the artist and the track title. For Commons it also
  shows the performer or uploader and the licence, since many files require attribution.

If no source has anything playable, it shows "No recordings found" and, when autoplay is on, skips to
the next pick. After 5 failures in a row it stops and asks you to check your connection.

### Autoplay modes

The mode decides what plays next when a track ends (with Autoplay ON). Choosing a new mode while a
track is playing lets that track finish; the status line says "New mode starts after this track";
press **Skip** to start it straight away. If
nothing is playing, the new mode starts straight away. Teleport and Radio always act immediately, and so
does leaving Radio (a live stream never ends).

| Mode | What it does |
|---|---|
| **Pure Random** | Any artist, chosen uniformly at random. Ignores similarity and play history. |
| **Random Walk** (default) | A small step to something nearby. Candidates are the current artist's 12 most similar artists plus 40 random ones; artists that are more similar (see below) are much more likely. |
| **Within Tag** | Stays inside the active tag (or, if none is set, the current artist's first tag), e.g. only *Opera*. If fewer than 10 artists have that tag, the most similar artists are added to the pool. Clicking a tag chip in this mode jumps straight to that tag. |
| **Spiral Time** | Moves through history about 25 years per track, choosing artists close to the target era who are also similar to the current one. It turns around at either end of the timeline and heads back. |
| **Teleport** | A one-off jump to something deliberately *dissimilar*, for a change of scene. After the jump it returns to the mode you were in before. |
| **Radio** | Live internet radio instead of individual recordings. See *Radio mode* below. |

### Radio mode

**Radio** plays live internet radio stations from [Radio Browser](https://www.radio-browser.info),
a free, community-maintained directory of stations around the world. Unlike the other modes it
doesn't play a particular artist's recordings; it tunes to a station playing that *kind* of music.

- **Press Radio** to tune in. It uses the active tag if one is set, otherwise the current artist's
  styles, otherwise general classical radio.
- **Press Radio again** for a different station. It avoids stations you've heard recently, moving on
  to related genres before repeating one.
- **Click an artist** to tune to a station in their styles (Hildegard von Bingen → early music or
  medieval radio, Wagner → opera radio).
- **Click a tag chip** to tune to that tag's radio (e.g. *Baroque*, *Opera*, *Sacred* → choral radio).
- The track line shows `Radio · <genre>` in blue, then the station name, country and stream quality.

Only style tags are used to find stations. Nationality and role tags such as *French* or *Conductor*
are ignored, since on radio those mean French-language or talk stations. If no station is found for a
style, it falls back to the next style and finally to `classical`.

Some stations can't be played and are skipped: plain `http` streams (the app only allows secure
`https` audio), HLS (`.m3u8`) streams, and stations that failed Radio Browser's last check. A station
that goes silent or errors is replaced by another automatically. Choose any other mode button to leave
Radio and go back to individual recordings.

#### How "related" and "likely" are worked out

Relatedness (0–1) between two artists is the brain of the app: every mode, the map's vertical axis,
the links between names and the "why" line all use it. It combines three kinds of evidence:

- **Documented links** from `relations.json` (see *Building the relatedness database*): teacher and
  student, "influenced by", family, one artist performing another's works, collaborations, artists
  that the same people listen to (ListenBrainz), and artists named together on archive.org recordings.
- **Shared style**: shared school, movement, ensemble or opera house, voice type, instrument, genre and
  country, and shared tags. Things that few artists share count for more than things many share
  (*Notre-Dame school* says more than *German*). Bookkeeping tags (*Secondary*, *Archive*, *Conductor*)
  don't count.
- **Time**: shared style counts fully between contemporaries and less between artists centuries apart.
  Documented links don't depend on time: a teacher can be 40 years older than a student.

The weights are in the `RELATEDNESS` block near the top of the relatedness code in
`index_fixed_working_v9.html`, so you can tune them (more weight on teachers, less on country...)
without rebuilding anything. Without `relations.json` the app still works, using shared style and time
only.

Choosing the next artist:

- Each mode scores candidates by relatedness (Spiral Time also by closeness to its target year,
  Teleport by *distance*), and higher scores are much more likely.
- **Play history**: an artist you've just played is 500× less likely; that penalty halves every hour.
  Artists played many times also become gradually less likely.
- **Masters** are 1.6× as likely as an otherwise equal secondary artist.

#### The "why" line

Under the track title, a line explains how the new artist connects to the previous one and which mode
chose it, for example:

- *Random walk from Léonin: Pérotin studied with Léonin · both Notre-Dame school*
- *Within Opera · from Maria Callas: both Verismo · both known for Opera*
- *Spiral Time, towards ~1725 · from Henry Purcell: both Baroque · contemporaries*
- *Teleport: a deliberate jump away from Hildegard von Bingen*

When you click a name yourself, it shows the link from the previous artist (*Link from ...*).

### Buttons

| Button | Action |
|---|---|
| **Skip ⏭** | Moves on now: the next pick in the current mode (or the next station in Radio mode). The keyboard's "next track" media key does the same. |
| **Autoplay: ON/OFF** | Whether a new track starts automatically when one ends. |
| **Resume Last** | Picks up the last track you were listening to, at the position you left it. |
| **Clear Tag** | Removes the active tag (Within Tag then falls back to the current artist's first tag). |
| **Center View** | Zooms back to the current artist, or resets the view if nothing is playing. |

### What's remembered between sessions

Your mode, active tag, autoplay setting, the last artist and the last track (with playback position)
are saved locally. On start-up the map centres on the last artist without playing anything;
press **Resume Last** to carry on.

## Data: `knowledge_base.json`

A list of artists (430 hand-curated ones, plus those added by `tools/build_relations.py`). Each entry
looks like:

| Field | Meaning |
|---|---|
| `id` | Display name, e.g. `"Wolfgang Amadeus Mozart"` (unique) |
| `key` | Stable lowercase identifier, e.g. `"wolfgang_amadeus_mozart"` |
| `aliases` | Other names for the same person, e.g. `["Mozart"]` (optional) |
| `type` | `Composer`, `Singer`, `Conductor` or `Instrumentalist` |
| `is_master` | `true` for the core figures (drawn larger, preferred by autoplay) |
| `era` | Year the person was roughly active |
| `temp` | Hand-assigned "musical temperature", 1–10. No longer used by the app; kept for reference |
| `tags` | Styles, forms, nationalities, e.g. `["Classical", "Austrian", "Opera"]` |
| `collections` | archive.org collections to search for recordings (78 rpm collections are searched separately, see *Where the music comes from*) |
| `meta` | `schools`, `regions`, `forms`, `styles`; schools and regions (nationalities) count as shared style |
| `related` | Old precomputed neighbours. No longer used; replaced by `relations.json` |
| `qid`, `mbid` | Wikidata and MusicBrainz identifiers (added by the build script) |
| `born`, `died`, `sitelinks` | From Wikidata; `sitelinks` is the number of Wikipedia language editions |
| `attrs` | From Wikidata: `movement`, `genre`, `instrument`, `voice`, `member` (ensembles, opera houses, employers), `country` |
| `source` | `"wikidata"` for artists added by the build script |

## Building the relatedness database

`tools/build_relations.py` gathers how artists are related from open sources, and adds more artists.
Run it on your computer (it needs internet access) from the repository folder:

```sh
python3 tools/build_relations.py
```

The first run takes roughly half an hour, mostly because MusicBrainz allows one request per second.
Every download is cached in `tools/.cache`, so if it's interrupted, run it again and it carries on;
later runs are quick. It only needs Python 3 (no packages to install).

What it does:

1. **Matches each artist to Wikidata** using name, type and dates. The person is chosen over, say, a
   crater or a band with the same name.
2. **Adds more artists**: classical composers, conductors, opera singers, pianists, violinists,
   organists and cellists with articles in at least 40 Wikipedia languages (up to 500), plus the
   teachers, students, influences and family of artists already in the database. Only people whose
   Wikidata description starts with a musical role ("German composer", "Italian soprano",
   "orchestral and operatic conductor") are added, and not jazz, pop or rock musicians, so writers
   or rulers who also composed (Goethe, Henry VIII) stay out. Composers and instrumentalists born
   after 1850 also need a genre or movement whose name sounds classical (classical, opera,
   minimalism, postminimalism, neoclassical, serial, film score, ...), unless they are a teacher,
   student or influence of an artist already in the database. New artists get tags (period, style,
   voice, instrument, nationality) from Wikidata.
   Each run rebuilds the added artists from scratch; your curated entries are never removed.
   Curated stub entries with a made-up era (1850, tagged *Romantic, Secondary*) are matched by name
   and corrected with their real era and style.
3. **Collects relations**: Wikidata (teacher/student, influence, family, works one artist performed
   by another, and shared movement, genre, ensembles, voice, instrument, country), MusicBrainz
   (teacher, family, collaborations), ListenBrainz (listened to by the same people) and archive.org
   (named together on recordings).
4. **Writes** `knowledge_base.json` (a backup of the previous one is kept as `knowledge_base.json.bak`),
   `relations.json`, and `tools/relations_report.md`.

**Read the report afterwards.** It lists artists it couldn't match, matches it wasn't sure about, the
artists it added, the candidates it skipped (with the reason) and any source that failed.

`tools/wikidata_overrides.json` holds your corrections and additions:

```json
{
  "Arcangelo Corelli": "Q1234567",
  "Some Artist": null,
  "include": ["Max Richter", "Q714325"]
}
```

- `"Name": "Q…"` fixes a wrong match (`Q1234567` stands for the id shown at the top of the artist's
  Wikidata page); `null` means never match.
- `"include"` lists artists to add whatever the rules say, e.g. a favourite who is under the
  40-language notability cut-off or has no classical genre on Wikidata. Use a name (the best-known
  musician of exactly that name) or a Wikidata id. The report warns if a name isn't found.

Then run the script again.

Useful options (`--help` lists them all):

| Option | Effect |
|---|---|
| `--max-new 200` | Add at most 200 new artists (default 500) |
| `--min-sitelinks 60` | Only add artists with articles in at least 60 Wikipedia languages (default 40) |
| `--no-expand` | Don't add artists; only relate the existing ones |
| `--no-musicbrainz`, `--no-listenbrainz`, `--no-cooccurrence` | Skip a source |
| `--dry-run` | Only write the report |

When you're happy with the result, commit `knowledge_base.json`, `relations.json` and (if you made
one) `tools/wikidata_overrides.json`, so the database is shared through the repository.

The script's tests run without internet: `python3 -m unittest tools/test_build_relations.py`.

### `tools/merge_aliases.py`

Merges entries that refer to the same person (e.g. "Mozart" and "Wolfgang Amadeus Mozart") into
one entry with an `aliases` list, and rewrites all `related` references to match. The mapping is the
`ALIASES` table at the top of the script. Run it after adding data:

```sh
python3 tools/merge_aliases.py            # rewrites knowledge_base.json in place
```

Running it again on an already-merged file changes nothing.

## Files

| File | Purpose |
|---|---|
| `index_fixed_working_v9.html` | The app: map, search, player and autoplay logic |
| `knowledge_base.json` | Artist data (see above) |
| `main.js`, `package.json` | Electron wrapper (`npm start`) |
| `relations.json` | Documented relations between artists, with evidence (built by `tools/build_relations.py`) |
| `tools/build_relations.py` | Builds the relatedness database from Wikidata, MusicBrainz, ListenBrainz and archive.org |
| `tools/test_build_relations.py` | Offline tests for the build script |
| `tools/wikidata_overrides.json` | Optional: your corrections to Wikidata matches |
| `tools/relations_report.md` | Written by the build script: what was matched, added or skipped |
| `tools/merge_aliases.py` | Duplicate-merging script for the data |

## Troubleshooting

- **"Failed to load knowledge_base.json"**: you probably opened the HTML file directly. Use `npm start`
  or the local server above. If it still fails, the status line now says why (for example, invalid
  JSON or leftover git merge-conflict markers in the file).
- **Blank map, no status message**: D3 couldn't load from d3js.org. Check your internet connection.
- **"No recordings found" for an artist**: none of the enabled sources had playable audio for them;
  autoplay moves on. Check that the sources you want are switched on, or add archive.org collections
  to the artist's entry in `knowledge_base.json`.
- **Too many scratchy old recordings**: switch off the **78 rpm (historic)** source.
- **Radio says "No radio station found"**: Radio Browser had no working `https` station for that
  style, or couldn't be reached. Try another tag, or press Radio with no tag selected for general
  classical radio.
- **Nothing plays after clicking**: open DevTools (View → Toggle Developer Tools in Electron, or
  F12 in a browser) and check the Console for `[search]`, `[radio]`, `[play]` or `[audio]` messages.
