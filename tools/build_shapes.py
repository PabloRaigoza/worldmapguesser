"""Build shapes/<iso2>.svg country outlines from Natural Earth (public domain).

Usage:
    python3 -I tools/build_shapes.py ne_10m_admin_0_countries.geojson shapes/ <codes>
    python3 -I tools/build_shapes.py ne_10m_admin_1_states_provinces_lakes.geojson stateshapes/ <codes> --admin1 US

<codes> is a comma-separated list of ISO alpha-2 codes (lowercase) to build, or with --admin1 <country>,
that country's subdivision codes (the part after the dash in ISO 3166-2, e.g. "ca" for US-CA).
Download the input from
https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_admin_0_countries.geojson
https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_admin_1_states_provinces_lakes.geojson

Each outline gets its own Lambert azimuthal equal-area projection centred on the country,
so shapes aren't stretched (and countries crossing the antimeridian stay in one piece).
"""
import json
import math
import os
import sys

SIZE = 1000          # longest side of each SVG, in viewBox units
SIMPLIFY = 0.7       # Douglas-Peucker tolerance, viewBox units
DOT_BELOW = 6        # islands smaller than this (viewBox units) are drawn as dots...
DOT_R = 9            # ...of this radius, so atoll nations stay visible
EARTH_R = 6371.0

# Extra Natural Earth features to fold into a country, and the only features to use where
# Natural Earth has several with the same ISO code.
MERGE = {
    "SO": ["Somaliland"],
    "CY": ["N. Cyprus", "Cyprus U.N. Buffer Zone", "Akrotiri", "Dhekelia"],
    "CU": ["USNB Guantanamo Bay"],
    "KZ": ["Baikonur"],
}
ONLY = {"FR": "France", "BR": "Brazil", "AU": "Australia", "KZ": "Kazakhstan"}
# Max distance (km) from the core landmass for outlying islands, where the default keeps too much.
FAR_LIMIT_KM = {"NO": 300}  # leave out Svalbard and Jan Mayen
# Countries whose core is just the largest polygon (overseas parts are big enough to count otherwise).
CORE_IS_LARGEST = {"FR"}  # French Guiana is ~13% of France's land area


def iso2(props):
    code = props.get("ISO_A2_EH")
    return code if code not in (None, "-99") else props.get("ISO_A2")


def polygons(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def haversine(a, b):
    (lon1, lat1), (lon2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(min(1, h)))


def unwrap(lon, ref):
    return ref + ((lon - ref + 540) % 360 - 180)


def ring_area_km2(ring):
    """Approximate area of a lon/lat ring (shoelace on a local equirectangular plane)."""
    lat0 = sum(p[1] for p in ring) / len(ring)
    lon_ref = ring[0][0]
    kx = math.cos(math.radians(lat0)) * EARTH_R * math.pi / 180
    ky = EARTH_R * math.pi / 180
    pts = [(unwrap(x, lon_ref) * kx, y * ky) for x, y in ring]
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def centroid(ring):
    ref = ring[0][0]
    lon = sum(unwrap(p[0], ref) for p in ring) / len(ring)
    lat = sum(p[1] for p in ring) / len(ring)
    return ((lon + 180) % 360 - 180, lat)


def keep_polygons(code, polys):
    """Drop far-flung territories (French Guiana, Galapagos, Canaries…).

    The "core" is the biggest polygons making up 90% of the land area. Any other polygon further
    from the core's bounding box than max(300 km, half the core's diagonal) is left out. For island
    nations the core itself is spread out, so every island stays.
    """
    info = sorted(((p, ring_area_km2(p[0]), centroid(p[0])) for p in polys), key=lambda t: -t[1])
    total = sum(a for _, a, _ in info) or 1
    core, acc = [], 0.0
    for t in info:
        core.append(t)
        acc += t[1]
        if acc >= 0.9 * total or code in CORE_IS_LARGEST:
            break
    ref = core[0][2][0]
    lons = [unwrap(x, ref) for p, _, _ in core for x, _ in p[0]]
    lats = [y for p, _, _ in core for _, y in p[0]]
    w, e, s_, n = min(lons), max(lons), min(lats), max(lats)
    diag = haversine((w, s_), (e, n))
    limit = FAR_LIMIT_KM.get(code, max(300, diag / 2))
    kept = []
    for p, _, (lon, lat) in info:
        lon = unwrap(lon, ref)
        nearest = (min(max(lon, w), e), min(max(lat, s_), n))
        if haversine((lon, lat), nearest) <= limit:
            kept.append(p)
    return kept


def project(lon, lat, lon0, lat0):
    l, p = math.radians(lon - lon0), math.radians(lat)
    p0 = math.radians(lat0)
    k = math.sqrt(2 / max(1e-12, 1 + math.sin(p0) * math.sin(p) + math.cos(p0) * math.cos(p) * math.cos(l)))
    x = k * math.cos(p) * math.sin(l)
    y = k * (math.cos(p0) * math.sin(p) - math.sin(p0) * math.cos(p) * math.cos(l))
    return x, -y


def simplify(pts, tol):
    if len(pts) < 4:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-12
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            x, y = pts[i]
            d = abs(dy * (x - x1) - dx * (y - y1)) / norm if (dx or dy) else math.hypot(x - x1, y - y1)
            if d > best:
                best, idx = d, i
        if best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def build(code, polys):
    polys = keep_polygons(code, polys)
    main = max(polys, key=lambda p: ring_area_km2(p[0]))
    ref = centroid(main[0])[0]
    lons = [unwrap(x, ref) for p in polys for x, _ in p[0]]
    lats = [y for p in polys for _, y in p[0]]
    lon0 = ((min(lons) + max(lons)) / 2 + 180) % 360 - 180
    lat0 = (min(lats) + max(lats)) / 2

    rings = [[[project(x, y, lon0, lat0) for x, y in ring] for ring in p] for p in polys]
    xs = [x for p in rings for x, _ in p[0]]
    ys = [y for p in rings for _, y in p[0]]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    pad = 0.04 * max(w, h)
    scale = SIZE / (max(w, h) + 2 * pad)
    ox, oy = min(xs) - pad, min(ys) - pad
    vw, vh = round((w + 2 * pad) * scale), round((h + 2 * pad) * scale)

    def to_view(ring):
        return [((x - ox) * scale, (y - oy) * scale) for x, y in ring]

    def dim(ring):
        rx = [x for x, _ in ring]
        ry = [y for _, y in ring]
        return max(max(rx) - min(rx), max(ry) - min(ry))

    view = [[to_view(r) for r in p] for p in rings]
    largest = max(dim(p[0]) for p in view)
    paths, dots = [], []
    for p in view:
        outer = p[0]
        d = dim(outer)
        if d < DOT_BELOW:
            if largest >= 60:
                continue  # a speck next to a real landmass: leave it out
            cx = sum(x for x, _ in outer) / len(outer)
            cy = sum(y for _, y in outer) / len(outer)
            dots.append(f'<circle class="s" cx="{cx:.1f}" cy="{cy:.1f}" r="{DOT_R}"/>')
            continue
        for i, ring in enumerate(p):
            if i > 0 and dim(ring) < 3:
                continue  # tiny lake/hole
            pts = simplify(ring, SIMPLIFY)
            if len(pts) < 3:
                continue
            paths.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw} {vh}" width="{vw}" height="{vh}">'
        "<style>.s{fill:#475569;stroke:#475569}"
        "@media (prefers-color-scheme:dark){.s{fill:#cbd5e1;stroke:#cbd5e1}}</style>"
        f'<path class="s" fill-rule="evenodd" stroke-width="2" stroke-linejoin="round" d="{"".join(paths)}"/>'
        + "".join(dots)
        + "</svg>"
    )


def main():
    src, out_dir, codes = sys.argv[1], sys.argv[2], sys.argv[3].upper().split(",")
    admin1 = sys.argv[5].upper() if len(sys.argv) > 5 and sys.argv[4] == "--admin1" else None
    fc = json.load(open(src, encoding="utf-8"))
    by_code, by_name = {}, {}
    for f in fc["features"]:
        props = f["properties"]
        if admin1:
            if props.get("iso_a2") == admin1:
                by_code.setdefault(props["iso_3166_2"].split("-", 1)[1], []).append(f)
            continue
        by_name[props["NAME"]] = f
        by_code.setdefault(iso2(props), []).append(f)
    os.makedirs(out_dir, exist_ok=True)
    for code in codes:
        feats = by_code.get(code, [])
        if code in ONLY:
            feats = [f for f in feats if f["properties"]["NAME"] == ONLY[code]]
        feats += [by_name[n] for n in MERGE.get(code, []) if n in by_name and by_name[n] not in feats]
        polys = [p for f in feats for p in polygons(f["geometry"])]
        if not polys:
            print("missing", code)
            continue
        with open(os.path.join(out_dir, f"{code.lower()}.svg"), "w", encoding="utf-8") as fh:
            fh.write(build(code, polys))
    print("built", len(codes))


if __name__ == "__main__":
    main()
