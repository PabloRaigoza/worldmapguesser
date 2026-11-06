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
- `shapes/`, `stateshapes/`, `maps/`, `neighbors.js`, `cities.js`: generated from Natural Earth (public domain)
  by `tools/build_shapes.py`, `tools/build_map.py`, `tools/build_neighbors.py` and `tools/build_cities.py`;
  each script's header says which file it needs. The city list, capital picks and accepted names are
  at the top of `tools/build_cities.py`.

## City grid maps

The city grid quizzes show pre-drawn maps from `citymaps/` (a street map SVG plus satellite and
terrain pictures per city), so nothing is loaded from map services while people play. To redraw them,
for example every year or two to pick up new streets:

    pip install numpy pillow
    python3 -I tools/build_city_maps.py ~/citymap-cache --force

It downloads OpenStreetMap data (from the Protomaps daily build), satellite imagery and elevation
for each city; the script's header lists the sources and their licences. Without `--force` it only
draws cities that don't have a map yet, which is what you want after adding cities to
`tools/build_cities.py` (rebuild `cities.js` first). Each map also gets small copies for the grid
layout (`-thumb.svg`, `-sat-thumb.webp`, `-terrain-thumb.svg`); `--thumbs` remakes just those from the files already there.
- `flags/`: [country-flags](https://github.com/hampusborgos/country-flags) by Hampus Borgos, from Wikimedia Commons
  (public domain). `stateflags/`: from Wikimedia Commons (public domain). Both were shrunk with SVGO.

## Testing locally

The site uses folder addresses (`/flag-quiz/`), so serve it rather than opening the files:

    python3 -m http.server

then open http://localhost:8000.
