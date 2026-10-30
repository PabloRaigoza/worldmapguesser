# World Map Guesser

https://www.worldmapguesser.com

Free geography quizzes: country and US state flags, shapes, click-on-the-map quizzes and a
border-hopping "connect" puzzle. Plain HTML/CSS/JS with no build step for the app itself.

## Editing the pages

Every quiz page (`index.html`, which is the world map quiz, `flag-quiz/index.html`, …) is generated. Edit `template.html`
(shared layout) or the page text in `tools/build_pages.py`, then run:

    python3 -I tools/build_pages.py

That also rebuilds `about/`, `404.html`, `sitemap.xml`, `robots.txt` and `CNAME`. Set `SITE_URL`
at the top of the script to your domain.

## Data

- `data.js`: the country and state lists, with accepted alternative names.
- `shapes/`, `stateshapes/`, `maps/`, `neighbors.js`: generated from Natural Earth (public domain)
  by `tools/build_shapes.py`, `tools/build_map.py` and `tools/build_neighbors.py`; each script's
  header says which file it needs.
- `flags/`: [country-flags](https://github.com/hampusborgos/country-flags) by Hampus Borgos, from Wikimedia Commons
  (public domain). `stateflags/`: from Wikimedia Commons (public domain). Both were shrunk with SVGO.

## Testing locally

The site uses folder addresses (`/flag-quiz/`), so serve it rather than opening the files:

    python3 -m http.server

then open http://localhost:8000.
