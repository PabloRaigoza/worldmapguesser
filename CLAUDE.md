# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Static geography-quiz site (https://www.worldmapguesser.com), hosted on GitHub Pages. Plain HTML/CSS/JS with no
build step, bundler, package manager or test suite for the app itself. Python scripts in `tools/` generate
pages and data. Always run them with `python3 -I` from the repo root.

## Commands

- Serve locally (needed because pages use folder addresses like `/flag-quiz/`): `python3 -m http.server`, then open http://localhost:8000
- Rebuild all HTML pages, `about/`, `404.html`, `sitemap.xml`, `robots.txt` and `CNAME`: `python3 -I tools/build_pages.py`
- Regenerate geo data from Natural Earth GeoJSON (download URLs and arguments are in each script's docstring):
  - `tools/build_shapes.py` → `shapes/*.svg`, `stateshapes/*.svg` (outlines in the clickable maps' projections: Equal Earth for countries, the US map's Albers ones for states; `--local` for the old per-shape projection). The projection functions live here and `build_map.py` imports them.
  - `tools/build_map.py` → `maps/world.js`, `maps/us.js` (clickable maps)
  - `tools/build_neighbors.py` → `neighbors.js` (land borders for the connect game)
  - `tools/build_cities.py` → `cities.js` (city grid quizzes; needs `ne_10m_populated_places.geojson`). The popular-city list, capital picks for multi-capital countries, downtown coordinate fixes and accepted names are hand-edited tables at the top of the script. Each city gets a map id; cities in several quizzes share one map.
  - `tools/build_city_maps.py <cache dir> [ids…] [--force]` → `citymaps/<id>.svg`, `<id>-sat.webp`, `<id>-terrain.webp`, plus grid thumbnails `<id>-thumb.svg`, `<id>-sat-thumb.webp` and `<id>-terrain-thumb.svg` (hill shading embedded as a data URI) (`--thumbs [ids…]` remakes only those, offline). Needs numpy and Pillow. It reads OpenStreetMap vector tiles from the Protomaps planet file over HTTP range requests (its own small PMTiles and vector-tile decoders), plus EOX Sentinel-2 or USGS imagery tiles and AWS terrain tiles. Downloads are cached, so reruns are fast.

## Generated files: don't hand-edit

- Every quiz `index.html` (root = world map quiz, `flag-quiz/`, `country-shape-quiz/`, `connect-countries/`, `us-state-*/`, `us-states-map-quiz/`, `connect-us-states/`, the three `*-grid-quiz/` city pages), plus `about/index.html`, `404.html`, `sitemap.xml`, `robots.txt`, `CNAME`. Edit `template.html` (shared layout, `{{…}}` placeholders) or the `PAGES` list / `ABOUT` text in `tools/build_pages.py`, then rebuild.
- `maps/*.js`, `neighbors.js`, `cities.js`, `citymaps/`, `shapes/`, `stateshapes/` come from the tools scripts.
- `flags/` and `stateflags/` are third-party public-domain SVGs, shrunk with SVGO.

## Architecture

- **One engine, many quizzes.** All quiz pages load `data.js`, `neighbors.js`, `cities.js` and `app.js`. Each page's `<body data-kind="…">` picks an entry in `KINDS` in `app.js` (`flags`, `shapes`, `map`, `connect`, plus `state-*` versions). A kind spreads `WORLD` or `US` (place list and wording) and sets flags such as `shape`, `map: "world"|"us"` and `connect`, an image path function, and a `prefix` for localStorage keys. Each quiz's stats and options are stored separately under `${prefix}.<name>`.
- **Adding a quiz** touches three places: a `KINDS` entry and the `PAGES` map (kind → URL path) in `app.js`, a `PAGES` tuple in `tools/build_pages.py`, and the nav tabs in `template.html`.
- **Place data**: `data.js` defines `REGIONS` (countries by continent) and `US_REGIONS` (states by Census region). Each entry is `[code, displayName, ...aliases]`. Answers are matched after `normalize()` (strips accents, "the/and/of", punctuation; saint→st). Dropdown search uses `searchKey()`, which keeps those words. Codes are lowercase ISO alpha-2 (state codes are the ISO 3166-2 suffix). They key every asset file name, map path and neighbour list.
- **Home screen**: region buttons toggle a selection (saved under `${prefix}.regions`); the Start button plays the picked regions together and a double click plays one at once. The session label is `K.all` or the region names joined with " + " (`sessionLabel()`); `isRanked()` accepts any such mix, so speed-run records are kept per mix.
- **Maps** are loaded lazily as `<script>` tags (`maps/<name>.js` sets `window.MAPS[name]`). They're scripts rather than JSON so pages also work from `file://`. Pan and zoom move the SVG with a CSS transform during a gesture and update the viewBox once it settles.
- **app.js** is a single IIFE split into `// ---- Section ----` blocks: options, weighted (softmax) question selection, sessions/rounds, map, connect (BFS over `NEIGHBORS`), multiple choice, grid mode, speed run, results, heatmap, stats, wiring. localStorage access goes through `load`/`save`, which fail quietly. The app has to keep working without storage.
- **City grid** (`cities`, `capitals`, `state-capitals` kinds; `K.city` names the list in `CITIES`): `showCity()` fetches `citymaps/<id>.svg` and puts it into the same `#map-svg` viewer the map quizzes use, registered in `MAPS` with `cover: true`, which keeps the view inside the map. The satellite and terrain pictures are `<image>` layers in that SVG, and the view is switched with `data-view` and CSS (`#map-svg.city` rules); a picture is only downloaded once its view is picked. The map files have no labels, and the colours come from style.css so they follow the theme. The grid layout shows the thumbnails as `<img>`s, so their colours are embedded in each file (with a `prefers-color-scheme` block that follows the page's `color-scheme`). Rotation (`canRotate()`) turns grid thumbnails with CSS and scales them up to cover their square; in single view the SVG goes in a `.map-rot` square as wide as the box's diagonal, turned with CSS, and `zoomAt`/drag turn screen moves back through `unrotate()`. Results and stats show the city's country or state flag.
- **Grid extras** (all grid quizzes): clicking a picture opens `#zoom-dialog` (`openZoom()`); for cities it borrows `#map-wrap` and draws the full map with `drawCity()`, copying the cell's rotation (`copyRotation()`), and puts `#map-wrap` back on close. Arrow keys in an empty box move between cells (`moveCell()`), handled before the dropdown's own keys.
- **Map mouse buttons**: any button (or a finger) drags; a left click or tap that moves under 6px picks; the right-click menu is off over maps.
- **Dropdown**: suggestions are ranked (display name starts with the query, then any alias does, then any match), so "washington" lists Washington before District of Columbia. Answers are never checked while typing, in any box: Enter (or picking from the list) submits, and a wrong submission is a miss. Tab / Shift+Tab move through the list like ↓ / ↑ (wrapping); with an empty box and no list, Tab moves focus as usual.
- **Paths**: generated pages set `<base href>` to the relative site root (the 404 page uses `/`), so asset URLs in `app.js` and the template are written relative to the root (`flags/xx.svg`, `maps/world.js`).
- **Quiz menu** (`nav.tabs` in `template.html`): a fixed left sidebar from 900px wide, which shrinks to an icon rail while a game, grid or connect screen is showing; below 900px a sideways-scrolling strip, scrolled to the current quiz. Icons are CSS masks picked by each link's `data-kind`, so a new quiz may need an icon rule in `style.css`. `markDone()` puts a green check (`.done`) on every quiz whose `K.all` category has a speed-run record in any variant, reading each quiz's `${prefix}.records`.
- **Theming**: CSS tokens in `style.css` cover the system dark mode and a `data-theme` override on `<html>`. `theme.js` runs the toggle button. The Inter font is self-hosted in `fonts/` (the About page promises nothing loads from other servers). A one-line inline script in each page's `<head>` (from `head()` in `build_pages.py`) applies the saved theme before first paint. The shape SVGs carry their own `prefers-color-scheme` style and follow the page through `color-scheme`.
