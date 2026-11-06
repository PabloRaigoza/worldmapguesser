"""Build cities.js: the places for the city grid quizzes (guess a city from its streets).

Usage:
    python3 -I tools/build_cities.py ne_10m_populated_places.geojson cities.js

Download the input from
https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_populated_places.geojson

Three lists, each grouped like the other quizzes:
- popular cities (POPULAR below), by continent, coded by a slug of the name;
- country capitals, by continent, coded by the country's code in data.js (so its flag is flags/<code>.svg);
- US state capitals, by Census region, coded by the state's code in data.js.
Coordinates come from Natural Earth; the size of the area drawn from the city's population, so a big
city shows more ground than a small one. Display names and accepted alternatives are set here.
Each city also gets a map id: its picture is citymaps/<id>.svg (plus -sat.webp and -terrain.webp),
drawn by tools/build_city_maps.py. A city in more than one quiz (Tokyo, Boston) shares one map.
"""
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Popular cities: continent -> [(Natural Earth name, country code, display name or None, aliases...)]
# The country code picks the right Natural Earth place and the flag shown in results and stats.
POPULAR = {
    "Africa": [
        ("Cairo", "eg", None), ("Marrakesh", "ma", None, "Marrakech"), ("Casablanca", "ma", None),
        ("Fez", "ma", None, "Fes"), ("Tunis", "tn", None), ("Cape Town", "za", None),
        ("Johannesburg", "za", None, "Joburg"), ("Nairobi", "ke", None), ("Lagos", "ng", None),
        ("Accra", "gh", None), ("Dakar", "sn", None), ("Addis Ababa", "et", None),
        ("Zanzibar", "tz", "Zanzibar City", "Zanzibar", "Stone Town"),
    ],
    "Asia": [
        ("Tokyo", "jp", None), ("Kyoto", "jp", None), ("Osaka", "jp", None), ("Seoul", "kr", None),
        ("Busan", "kr", None, "Pusan"), ("Beijing", "cn", None, "Peking"), ("Shanghai", "cn", None),
        ("Hong Kong", "cn", None), ("Taipei", "tw", None), ("Singapore", "sg", None),
        ("Bangkok", "th", None), ("Hanoi", "vn", None), ("Ho Chi Minh City", "vn", None, "Saigon"),
        ("Kuala Lumpur", "my", None, "KL"), ("Jakarta", "id", None), ("Manila", "ph", None),
        ("Mumbai", "in", None, "Bombay"), ("Delhi", "in", None, "New Delhi"), ("Jaipur", "in", None),
        ("Dubai", "ae", None), ("Abu Dhabi", "ae", None), ("Doha", "qa", None),
        ("Jerusalem", "il", None), ("Tel Aviv", "il", None, "Tel Aviv-Yafo"), ("Kathmandu", "np", None),
        ("Istanbul", "tr", None, "Constantinople"),
    ],
    "Europe": [
        ("London", "gb", None), ("Paris", "fr", None), ("Rome", "it", None, "Roma"),
        ("Barcelona", "es", None), ("Madrid", "es", None), ("Seville", "es", None, "Sevilla"),
        ("Amsterdam", "nl", None), ("Berlin", "de", None), ("Munich", "de", None, "München", "Munchen"),
        ("Prague", "cz", None, "Praha"), ("Vienna", "at", None, "Wien"), ("Venice", "it", None, "Venezia"),
        ("Florence", "it", None, "Firenze"), ("Milan", "it", None, "Milano"), ("Naples", "it", None, "Napoli"),
        ("Lisbon", "pt", None, "Lisboa"), ("Porto", "pt", None, "Oporto"), ("Athens", "gr", None),
        ("Budapest", "hu", None), ("Dublin", "ie", None), ("Edinburgh", "gb", None),
        ("København", "dk", "Copenhagen", "København", "Kobenhavn"), ("Stockholm", "se", None),
        ("Oslo", "no", None), ("Brussels", "be", None, "Bruxelles", "Brussel"),
        ("Zürich", "ch", "Zurich", "Zürich"), ("Moscow", "ru", None),
        ("St. Petersburg", "ru", "Saint Petersburg", "St Petersburg", "Leningrad"),
        ("Kraków", "pl", "Kraków", "Krakow", "Cracow"), ("Dubrovnik", "hr", None),
    ],
    "North America": [
        ("New York", "us", "New York City", "New York", "NYC"), ("Los Angeles", "us", None, "LA"),
        ("Chicago", "us", None), ("San Francisco", "us", None, "SF"), ("Las Vegas", "us", None),
        ("Miami", "us", None), ("Washington, D.C.", "us", "Washington, D.C.", "Washington", "Washington DC", "DC"),
        ("Boston", "us", None), ("New Orleans", "us", None), ("Seattle", "us", None),
        ("Philadelphia", "us", None, "Philly"), ("Toronto", "ca", None), ("Vancouver", "ca", None),
        ("Montréal", "ca", "Montreal", "Montréal"), ("Québec", "ca", "Quebec City", "Quebec", "Québec"),
        ("Mexico City", "mx", None, "Ciudad de Mexico", "CDMX"), ("Cancún", "mx", "Cancún", "Cancun"),
        ("Havana", "cu", None, "La Habana"), ("Panama City", "pa", None, "Panama"),
    ],
    "South America": [
        ("Rio de Janeiro", "br", None, "Rio"), ("São Paulo", "br", None, "Sao Paulo"),
        ("Buenos Aires", "ar", None), ("Lima", "pe", None), ("Cusco", "pe", None, "Cuzco"),
        ("Bogota", "co", "Bogotá", "Bogota"), ("Medellín", "co", None, "Medellin"),
        ("Cartagena", "co", None), ("Santiago", "cl", None, "Santiago de Chile"),
        ("Montevideo", "uy", None), ("Quito", "ec", None), ("La Paz", "bo", None),
    ],
    "Oceania": [
        ("Sydney", "au", None), ("Melbourne", "au", None), ("Brisbane", "au", None), ("Perth", "au", None),
        ("Auckland", "nz", None), ("Wellington", "nz", None), ("Christchurch", "nz", None),
        ("Honolulu", "us", None),
    ],
}

# Country capitals where Natural Earth lists several or none: country code -> Natural Earth name.
# Where a country splits its capital, the official/constitutional one is used.
CAPITAL_PICK = {
    "bj": "Porto-Novo", "ci": "Yamoussoukro", "sz": "Mbabane", "ma": "Rabat", "ng": "Abuja",
    "za": "Pretoria", "tz": "Dodoma", "il": "Jerusalem", "jp": "Tokyo", "my": "Kuala Lumpur",
    "mm": "Naypyidaw", "ph": "Manila", "lk": "Sri Jayawardenepura Kotte", "nl": "Amsterdam",
    "bo": "Sucre", "cl": "Santiago",
    # Not listed as country capitals: Palestine's administrative seat, Kosovo (no ISO code in the data).
    "ps": "Ramallah", "xk": "Pristina",
}
# Not in Natural Earth at all: code -> (name, lat, lon, population)
CAPITAL_MANUAL = {"nr": ("Yaren", -0.5466, 166.9211, 1000)}

# Display name and accepted alternatives, keyed by the Natural Earth name (both capital lists).
NAMES = {
    "Nur-Sultan": ["Astana", "Nur-Sultan"],
    "København": ["Copenhagen", "København", "Kobenhavn"],
    "Washington,  D.C.": ["Washington, D.C.", "Washington", "Washington DC", "DC"],
    "Bogota": ["Bogotá", "Bogota"],
    "Andorra": ["Andorra la Vella"],
    "Tarawa": ["South Tarawa", "Tarawa"],
    "Luxembourg": ["Luxembourg City", "Luxembourg"],
    "Djibouti": ["Djibouti City", "Djibouti"],
    "Melekeok": ["Ngerulmud", "Melekeok"],
    "Sri Jayawardenepura Kotte": ["Sri Jayawardenepura Kotte", "Kotte", "Sri Jayewardenepura Kotte"],
    "Naypyidaw": ["Naypyidaw", "Nay Pyi Taw", "Naypyitaw"],
    "Ulaanbaatar": ["Ulaanbaatar", "Ulan Bator"],
    "Sanaa": ["Sanaa", "Sana'a"],
    "Beijing": ["Beijing", "Peking"],
    "Kyiv": ["Kyiv", "Kiev"],
    "Ashgabat": ["Ashgabat", "Ashkhabad"],
    "Bern": ["Bern", "Berne"],
    "Tehran": ["Tehran", "Teheran"],
    "Havana": ["Havana", "La Habana"],
    "Mexico City": ["Mexico City", "Ciudad de Mexico", "CDMX"],
    "New Delhi": ["New Delhi", "Delhi"],
    "Dhaka": ["Dhaka", "Dacca"],
    "Rome": ["Rome", "Roma"],
    "Lisbon": ["Lisbon", "Lisboa"],
    "Prague": ["Prague", "Praha"],
    "Vienna": ["Vienna", "Wien"],
    "Warsaw": ["Warsaw", "Warszawa"],
    "Brussels": ["Brussels", "Bruxelles", "Brussel"],
    "Bucharest": ["Bucharest", "Bucuresti"],
    "Belgrade": ["Belgrade", "Beograd"],
    "Kuala Lumpur": ["Kuala Lumpur", "KL"],
    "Saint John's": ["St. John's", "Saint John's"],
    "Saint George's": ["St. George's", "Saint George's"],
    "St.  Paul": ["Saint Paul", "St. Paul"],
    "Ramallah": ["Ramallah"],
    "Pristina": ["Pristina", "Prishtina", "Priština"],
}

# Where Natural Earth's point is well away from the centre people know (metro-area centroids):
# Natural Earth name -> (lat, lon) of downtown / the old town.
CENTRE = {
    "Los Angeles": (34.0522, -118.2437), "Chicago": (41.8781, -87.6298), "Seattle": (47.6062, -122.3321),
    "Boston": (42.3601, -71.0589), "Philadelphia": (39.9526, -75.1652), "Toronto": (43.6532, -79.3832),
    "Las Vegas": (36.1147, -115.1728), "New Orleans": (29.9511, -90.0715), "Phoenix": (33.4484, -112.0740),
    "Atlanta": (33.7490, -84.3880), "Miami": (25.7617, -80.1918), "Salt Lake City": (40.7608, -111.8910),
    "Sydney": (-33.8688, 151.2093), "Istanbul": (41.0082, 28.9784), "Rio de Janeiro": (-22.935, -43.195),
    "Osaka": (34.6937, 135.5023), "Kyoto": (35.0116, 135.7681), "Busan": (35.1796, 129.0756),
    "Amsterdam": (52.3676, 4.9041), "Prague": (50.0755, 14.4378), "Madrid": (40.4168, -3.7038),
    "Stockholm": (59.3293, 18.0686), "Funafuti": (-8.5211, 179.1983),
    "Malé": (4.1755, 73.5093),
}

# Half the width of the square drawn around each city, in km, by population.
def half_km_for(pop):
    return 5 if pop >= 3_000_000 else 3.5 if pop >= 300_000 else 2


def slug(s):
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def quiz_lists(data_js):
    """REGIONS and US_REGIONS from data.js as {group: [(code, name)]}."""
    src = open(data_js, encoding="utf-8").read()
    world_src, us_src = src.split("const US_REGIONS")
    def groups(text):
        out = {}
        for m in re.finditer(r'"([^"]+)":\s*\[(.*?)\n  \]', text, re.S):
            out[m.group(1)] = re.findall(r'\["([a-z]{2})", "([^"]+)"', m.group(2))
        return out
    return groups(world_src), groups(us_src)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    places = [f["properties"] for f in json.load(open(sys.argv[1], encoding="utf-8"))["features"]]
    world, us = quiz_lists(os.path.join(ROOT, "data.js"))

    def iso(p):
        return "xk" if p["ADM0NAME"] == "Kosovo" else p["ISO_A2"].lower()

    def find(name, cc, cls=None):
        hits = [p for p in places if iso(p) == cc and name in (p["NAME"], p["NAMEASCII"], p["NAME_EN"])
                and (cls is None or p["FEATURECLA"] == cls)]
        if not hits:
            sys.exit(f"not found in Natural Earth: {name} ({cc})")
        return max(hits, key=lambda p: p["POP_MAX"])

    map_ids = {}  # map id -> (lat, lon), so a city in several quizzes shares one map

    def entry(p, code, names, flag=None):
        names = names or NAMES.get(p["NAME"]) or [p["NAME"]]
        lat, lon = CENTRE.get(p["NAME"], (p["LATITUDE"], p["LONGITUDE"]))
        lat, lon = round(lat, 4), round(lon, 4)
        map_id = slug(names[0])
        if map_ids.get(map_id, (lat, lon)) != (lat, lon):
            map_id = f"{map_id}-{code if len(code) == 2 else flag}"  # same name, different place
        map_ids[map_id] = (lat, lon)
        info = [map_id, lat, lon, half_km_for(p["POP_MAX"])]
        return [code, *dict.fromkeys(names)], info + ([flag] if flag else [])

    out = {"cities": ({}, {}), "capitals": ({}, {}), "state-capitals": ({}, {})}

    regions, info = out["cities"]
    for continent, cities in POPULAR.items():
        regions[continent] = []
        for ne_name, cc, display, *aliases in cities:
            # Hong Kong is its own entry in Natural Earth; its flag here is China's.
            p = find(ne_name, "hk" if ne_name == "Hong Kong" else cc)
            code = slug(display or ne_name)
            e, i = entry(p, code, [display or ne_name, *aliases], cc)
            regions[continent].append(e)
            info[code] = i

    regions, info = out["capitals"]
    for continent, countries in world.items():
        regions[continent] = []
        for code, _ in countries:
            if code in CAPITAL_MANUAL:
                name, lat, lon, pop = CAPITAL_MANUAL[code]
                p = {"NAME": name, "LATITUDE": lat, "LONGITUDE": lon, "POP_MAX": pop}
            elif code in CAPITAL_PICK:
                p = find(CAPITAL_PICK[code], code)
            else:
                caps = [x for x in places if iso(x) == code and x["FEATURECLA"] == "Admin-0 capital"]
                if len(caps) != 1:
                    sys.exit(f"{code}: {len(caps)} capitals in Natural Earth; add it to CAPITAL_PICK")
                p = caps[0]
            e, i = entry(p, code, None)
            regions[continent].append(e)
            info[code] = i

    regions, info = out["state-capitals"]
    for region, states in us.items():
        regions[region] = []
        for code, state in states:
            if code == "dc":
                continue  # not a state, and Washington is the whole district
            caps = [x for x in places if x["ISO_A2"] == "US" and x["FEATURECLA"] == "Admin-1 capital"
                    and x["ADM1NAME"] == state]
            if len(caps) != 1:
                sys.exit(f"{state}: {len(caps)} capitals in Natural Earth")
            e, i = entry(caps[0], code, None)
            regions[region].append(e)
            info[code] = i

    for kind, (regions, _) in out.items():
        codes = [e[0] for es in regions.values() for e in es]
        assert len(codes) == len(set(codes)), f"duplicate codes in {kind}"

    def js(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        fh.write("// Generated by tools/build_cities.py from Natural Earth data. Do not edit.\n"
                 "// CITIES[kind] = { regions: {group: [[code, name, ...aliases]]},\n"
                 "//                  info: {code: [map id, lat, lng, half width in km, flag code (popular cities only)]} }\n"
                 "const CITIES = {\n")
        for kind, (regions, info) in out.items():
            fh.write(f'  "{kind}": {{\n    regions: {js(regions)},\n    info: {js(info)},\n  }},\n')
        fh.write("};\n")
    print(", ".join(f"{k}: {len(i)}" for k, (_, i) in out.items()))


if __name__ == "__main__":
    main()
