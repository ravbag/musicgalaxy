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
- **Bottom to top is `temp`**, the hand-assigned "musical temperature" (1 = cool/austere, 10 = hot/intense).
  Positions are jittered, and names related to each other are pulled together.
- **Colour is the type of artist**: gold = composer, pink = singer, blue = conductor.
- **Large bold names** are "masters", the 100 core figures; smaller names are secondary.
- **Drag** to pan and **scroll** to zoom. The name that's playing pulses.

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
- *Wikimedia Commons*: picks a random matching audio file, skipping MIDI files, spoken-word articles,
  pronunciation clips and anything under 45 seconds.
- The track line shows the source in blue, then the artist and the track title. For Commons it also
  shows the performer or uploader and the licence, since many files require attribution.

If no source has anything playable, it shows "No recordings found" and, when autoplay is on, skips to
the next pick. After 5 failures in a row it stops and asks you to check your connection.

### Autoplay modes

The mode decides what plays next when a track ends (with Autoplay ON). Clicking a mode button
while something is playing jumps to the next track straight away.

| Mode | What it does |
|---|---|
| **Pure Random** | Any artist, chosen uniformly at random. Ignores similarity and play history. |
| **Random Walk** (default) | A small step to something nearby. Candidates are the current artist's related artists plus 40 random ones; artists that are more similar (see below) are much more likely. |
| **Within Tag** | Stays inside the active tag (or, if none is set, the current artist's first tag), e.g. only *Opera*. If fewer than 10 artists have that tag, related artists are added to the pool. Clicking a tag chip in this mode jumps straight to that tag. |
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

#### How "similar" and "likely" are worked out

Random Walk, Within Tag, Spiral Time and Teleport all score candidate artists and pick one at
random, with higher scores much more likely:

- **Similarity** (0–1) between two artists combines shared tags (55%), closeness in era (30%),
  and bonuses for the same type of artist, a shared school (e.g. First Viennese School) and a shared region.
- **Play history**: artists you've played recently (within roughly the last hour) are strongly avoided,
  and artists played many times become gradually less likely.
- **Masters** get a boost over secondary artists.

`temp` currently only affects position on the map, not what plays next.

### Buttons

| Button | Action |
|---|---|
| **Autoplay: ON/OFF** | Whether a new track starts automatically when one ends. |
| **Resume Last** | Picks up the last track you were listening to, at the position you left it. |
| **Clear Tag** | Removes the active tag (Within Tag then falls back to the current artist's first tag). |
| **Center View** | Zooms back to the current artist, or resets the view if nothing is playing. |

### What's remembered between sessions

Your mode, active tag, autoplay setting, the last artist and the last track (with playback position)
are saved locally. On start-up the map centres on the last artist without playing anything;
press **Resume Last** to carry on.

## Data: `knowledge_base.json`

A list of 430 artists. Each entry looks like:

| Field | Meaning |
|---|---|
| `id` | Display name, e.g. `"Wolfgang Amadeus Mozart"` (unique) |
| `key` | Stable lowercase identifier, e.g. `"wolfgang_amadeus_mozart"` |
| `aliases` | Other names for the same person, e.g. `["Mozart"]` (optional) |
| `type` | `Composer`, `Singer` or `Conductor` |
| `is_master` | `true` for the core figures (drawn larger, preferred by autoplay) |
| `era` | Year the person was roughly active |
| `temp` | Hand-assigned "musical temperature", 1–10 |
| `tags` | Styles, forms, nationalities, e.g. `["Classical", "Austrian", "Opera"]` |
| `collections` | archive.org collections to search for recordings (78 rpm collections are searched separately, see *Where the music comes from*) |
| `meta` | `schools`, `regions`, `forms`, `styles` used for similarity |
| `related` | Precomputed neighbours: `{ "id", "w" (weight 0–1), "why" (reasons) }` |

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
