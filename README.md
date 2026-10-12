# musicgalaxy

I'm trying to create a music player that displays composer, singer or genre names as tags and pulls in music from archive .org. There is supposed to be separate autoplay logics, like a random walk, staying within a genre, spiral through time, etc. I also want to have some measure of relatedness between different tags, like if a certain kind of music is close to another, or if two composers are similar. I'm using "temp" musical temperature variable for this but there must be something better. Please review the code and suggest improvements. I'm using electron and running it on my local machine

## Running it

Requires [Node.js](https://nodejs.org/) (which includes npm).

```sh
npm install   # first time only: downloads Electron
npm start     # opens the MusicGalaxy window
```

Opening `index_fixed_working_v9.html` directly in a browser (double-clicking it) does **not** work:
browsers block a `file://` page from reading `knowledge_base.json`, so you get
"Failed to load knowledge_base.json" and an empty map. If you want to use a browser instead of
Electron, serve the folder over HTTP and open the page from there:

```sh
python3 -m http.server 8000
# then open http://localhost:8000/index_fixed_working_v9.html
```

## Files

- `main.js`, `package.json` – Electron wrapper
- `index_fixed_working_v9.html` – the app (D3 tag cloud, search, autoplay modes, archive.org streaming)
- `knowledge_base.json` – composers, singers and conductors with tags, era, `temp`, archive.org collections and related entries
- `tools/merge_aliases.py` – merges duplicate entries for the same person (e.g. "Mozart" / "Wolfgang Amadeus Mozart") into one entry with `aliases`
