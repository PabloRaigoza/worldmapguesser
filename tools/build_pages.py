"""Build the site's HTML pages from template.html, plus about/, 404.html, sitemap.xml, robots.txt, CNAME.

Usage:
    python3 -I tools/build_pages.py

Run it from the project folder after editing template.html or the text below. Each quiz gets its own
page (its own address, title and description) so search engines can list them separately; all of
them run the same app.js. Set SITE_URL to your domain before publishing.
"""
import html
import json
import os
import sys
from datetime import date

SITE_URL = "https://www.worldmapguesser.com"  # no trailing slash
SITE_NAME = "World Map Guesser"
# Visitor counting snippet added to every page's <head> (empty = none). See README.
ANALYTICS = ""
# Counts quoted in the page text (data.js has the lists).
N_COUNTRIES = 197

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# kind (app.js KINDS key), path, <title>, meta description, h1, intro under the h1, page text
PAGES = [
    ("flags", "flag-quiz/", "Flag Quiz – Guess All 197 World Flags",
     "Free flag quiz: name every country's flag, by continent or the whole world. Type, multiple choice or grid mode, speed runs and stats on your slowest flags.",
     "Flag Quiz", "Pick a continent and type the country for each flag.",
     f"""<h2>How to play</h2>
<p>A flag appears; type the country it belongs to. The list suggests names as you type, or switch to multiple choice, or put a whole continent on screen at once with the grid layout. Missed flags come back at the end of the round, and <em>My stats</em> shows which flags you're slowest on.</p>
<h2>Which flags are included?</h2>
<p>All {N_COUNTRIES} countries: the 193 UN members plus Vatican City, Palestine, Kosovo and Taiwan, grouped by continent. Turn on speed run to race the clock and set a record for each continent.</p>"""),
    ("shapes", "country-shape-quiz/", "Country Shape Quiz – Guess Countries by Outline",
     "Can you recognise a country from its outline? Free country shape quiz for every continent, with optional rotation, multiple choice and speed runs.",
     "Country Shape Quiz", "Pick a continent and name each country from its outline.",
     """<h2>How to play</h2>
<p>Each round shows a country's silhouette with no map around it. Name it by typing, from a list, or from four choices. For a harder game, turn the shapes 90°, to any angle, or set them spinning.</p>
<p>Outlines are drawn to scale for each country individually, so small and large countries fill the screen the same way; tiny island nations are shown as dots.</p>"""),
    ("map", "", "World Map Guesser – Free World Map Quiz",
     "Free world map quiz: find and click every country on a zoomable map, one continent or the whole world, with or without borders. Plus flag, shape and US state quizzes.",
     "World Map Guesser", "Pick a continent and click each country on the map.",
     """<h2>How to play</h2>
<p>A country's name appears above the map; click it. Scroll or pinch to zoom and drag to move. Small countries and islands have a dot you can click. After three wrong clicks the answer is shown.</p>
<p>Hide the borders for a real challenge: the land is drawn in one colour, so you have to know where each country sits.</p>"""),
    ("connect", "connect-countries/", "Connect Countries – Border Geography Puzzle",
     "Join two countries by naming the neighbours in between. A free geography puzzle about land borders, with thousands of puzzles across every continent.",
     "Connect Countries", "Join two countries with a chain of neighbours that share land borders.",
     """<h2>How to play</h2>
<p>Two countries are highlighted on the map. Type countries that link them through shared land borders. Each guess is coloured: green if it's on a shortest route, amber if it's a step or two off, red if it's off track. Connect them before you run out of guesses.</p>"""),
    ("state-flags", "us-state-flags-quiz/", "US State Flags Quiz – All 50 State Flags",
     "Free US state flags quiz: name all 50 state flags plus DC, by region or all at once. Typing, multiple choice, grid mode and speed runs.",
     "State Flag Quiz", "Pick a region and type the US state for each flag.",
     """<h2>How to play</h2>
<p>A state flag appears; type the state. Play all 50 states plus Washington, D.C., or one Census region at a time: Northeast, Midwest, South or West. Includes the newest flags, such as Minnesota's and Utah's from 2024.</p>"""),
    ("state-shapes", "us-state-shapes-quiz/", "US State Shapes Quiz – Guess States by Outline",
     "Recognise all 50 US states from their outlines. Free state shape quiz with rotation, multiple choice and speed runs.",
     "State Shape Quiz", "Pick a region and name each US state from its outline.",
     """<h2>How to play</h2>
<p>Each round shows one state's outline on its own. Name it by typing, from a list, or from four choices. Rotate or spin the shapes for an extra challenge.</p>"""),
    ("state-map", "us-states-map-quiz/", "US States Map Quiz – Find All 50 States",
     "Free US map quiz: find all 50 states and DC on a zoomable map, with an optional borderless mode.",
     "State Map Quiz", "Pick a region and click each state on the map.",
     """<h2>How to play</h2>
<p>A state's name appears above the map; click it. Alaska and Hawaii are in the corner as usual, and DC has a dot. Hide the borders to test whether you really know where each state is.</p>"""),
    ("state-connect", "connect-us-states/", "Connect US States – State Border Puzzle",
     "Join two US states by naming the states in between. A free puzzle about state borders.",
     "Connect States", "Join two states with a chain of neighbours that share borders.",
     """<h2>How to play</h2>
<p>Two states are highlighted. Type states that link them through shared borders (states that only touch at a corner, like the Four Corners, don't count). Green guesses are on a shortest route, amber are close, red are off track.</p>"""),
]


def head(title, description, path, root, app_name=None):
    url = f"{SITE_URL}/{path}"
    if SITE_NAME not in title:
        title = f"{title} | {SITE_NAME}"
    t, d = html.escape(title), html.escape(description)
    # Structured data: the site's name (Google shows it above results) and, on quiz pages, the quiz itself.
    data = [{"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "url": f"{SITE_URL}/"}] if path == "" else []
    if app_name:
        data.append({"@context": "https://schema.org", "@type": "WebApplication", "name": app_name, "url": url,
                     "description": description, "applicationCategory": "GameApplication", "operatingSystem": "Any",
                     "isAccessibleForFree": True, "inLanguage": "en",
                     "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}})
    ld = "".join(f'\n  <script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in data)
    return f"""  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <base href="{root}">
  <script>try {{ const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; }} catch {{}}</script>
  <title>{t}</title>
  <meta name="description" content="{d}">
  <link rel="canonical" href="{url}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="{html.escape(SITE_NAME)}">
  <meta property="og:title" content="{t}">
  <meta property="og:description" content="{d}">
  <meta property="og:url" content="{url}">
  <meta property="og:image" content="{SITE_URL}/assets/og-image.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{html.escape(SITE_NAME)}: flags, shapes, maps and border puzzles">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
  <link rel="icon" href="assets/favicon-32.png" sizes="32x32" type="image/png">
  <link rel="apple-touch-icon" href="assets/apple-touch-icon.png">
  <meta name="theme-color" content="#2563eb">
  <link rel="stylesheet" href="style.css">
  <script src="theme.js" defer></script>{ld}{ANALYTICS}"""


def more_links(skip):
    names = {"flags": "Flag quiz", "shapes": "Country shapes", "map": "World map quiz", "connect": "Connect countries",
             "state-flags": "US state flags", "state-shapes": "US state shapes", "state-map": "US states map",
             "state-connect": "Connect US states"}
    items = "".join(f'<li><a href="{p or "./"}">{names[k]}</a></li>' for k, p, *_ in PAGES if k != skip)
    return f"<h2>More quizzes</h2>\n<ul class=\"more-quizzes\">{items}</ul>"


def write(path, text):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(text)


def static_page(path, title, description, body):
    root = "../" * path.count("/") or "./"
    return f"""<!doctype html>
<!-- Generated by tools/build_pages.py. Do not edit. -->
<html lang="en">
<head>
{head(title, description, path, root)}
</head>
<body class="static-page">
  <main>
{body}
    <footer class="site-footer"><a href="./">Play the quizzes</a><button type="button" class="theme-toggle"></button></footer>
  </main>
</body>
</html>
"""


ABOUT = """    <h1>About &amp; credits</h1>
    <p class="sub">World Map Guesser is a set of free geography quizzes: maps, flags, shapes and border puzzles.</p>
    <h2>Credits</h2>
    <ul>
      <li><strong>Maps, country and state outlines, and borders</strong>:
        <a href="https://www.naturalearthdata.com/">Natural Earth</a> (public domain).</li>
      <li><strong>US state flags</strong>: drawings from
        <a href="https://commons.wikimedia.org/wiki/Category:SVG_flags_of_the_United_States_states">Wikimedia Commons</a>,
        public domain (Mississippi's is marked “copyrighted free use”, which allows any use).</li>
      <li><strong>Country flags</strong>: <a href="https://github.com/hampusborgos/country-flags">country-flags</a>
        by Hampus Borgos, drawn from Wikimedia Commons (public domain).</li>
    </ul>
    <h2>Borders and names</h2>
    <p>Borders follow Natural Earth's default view and aren't a statement on any dispute. Most countries accept
      their common alternative names (Czechia or Czech Republic, Ivory Coast or Côte d'Ivoire, and so on).</p>
    <h2>Privacy</h2>
    <p>No accounts, no cookies and no tracking. Your scores, stats and records are saved only in your own browser
      (local storage), so clearing your browser data resets them.</p>"""


def main():
    template = open(os.path.join(ROOT, "template.html"), encoding="utf-8").read()
    for kind, path, title, description, h1, intro, about in PAGES:
        root = "../" * path.count("/") or "./"
        page = (template
                .replace("{{head}}", head(title, description, path, root, h1))
                .replace("{{kind}}", kind)
                .replace("{{h1}}", html.escape(h1))
                .replace("{{intro}}", html.escape(intro))
                .replace("{{about}}", about + "\n" + more_links(kind)))
        page = page.replace("<!-- Template for every quiz page", "<!-- Generated by tools/build_pages.py from template.html. Do not edit.\n     Template for every quiz page", 1)
        write(os.path.join(path, "index.html"), page)

    write("about/index.html", static_page("about/", "About & credits",
                                          "Credits, data sources and privacy for these free geography quizzes.", ABOUT))
    write("404.html", static_page("404", "Page not found", "This page doesn't exist.",
                                  "    <h1>Page not found</h1>\n    <p class=\"sub\">That page doesn't exist. Try one of the quizzes below.</p>\n"
                                  + "    " + more_links(None))
          # GitHub Pages serves this at whatever address was missing, so links must start from the site root.
          .replace('<base href="./">', '<base href="/">')
          .replace('  <link rel="canonical"', '  <meta name="robots" content="noindex">\n  <link rel="canonical"'))

    today = date.today().isoformat()
    urls = sorted(p for _, p, *_ in PAGES) + ["about/"]
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + "".join(f"  <url><loc>{SITE_URL}/{u}</loc><lastmod>{today}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")
    domain = SITE_URL.split("://", 1)[1]
    if domain != "example.com":
        write("CNAME", domain + "\n")  # tells GitHub Pages which custom domain this site uses
    else:
        print("SITE_URL is still example.com: set your domain at the top of this script.", file=sys.stderr)
    print(f"built {len(PAGES)} quiz pages, about/, 404.html, sitemap.xml, robots.txt")


if __name__ == "__main__":
    main()
