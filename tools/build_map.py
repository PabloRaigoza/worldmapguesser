"""Build the clickable maps (maps/world.js, maps/us.js) from Natural Earth (public domain).

Usage:
    python3 -I tools/build_map.py world ne_10m_admin_0_countries.geojson maps/world.js <codes>
    python3 -I tools/build_map.py us ne_10m_admin_1_states_provinces_lakes.geojson maps/us.js <codes>

<codes> is the comma-separated list of quiz codes (lowercase); every other feature is drawn as
non-clickable background land. Inputs are the same files tools/build_shapes.py uses.

Each output is a script that sets window.MAPS[<name>] = {
    w, h,                     viewBox size
    places: {code: path},     one SVG path per quiz place
    bg: path,                 everything else (world map only)
    boxes: {code: [x0, y0, x1, y1]},  the place's main area, for zooming to a region
    dots: {code: [x, y]},     places too small to click get a dot here
}
It's a script rather than JSON so the page also works when opened straight from disk.
"""
import importlib.util
import json
import math
import os
import sys

# Reuse the polygon helpers from the shape builder (python -I leaves this folder off sys.path).
_spec = importlib.util.spec_from_file_location("build_shapes", os.path.join(os.path.dirname(__file__), "build_shapes.py"))
bs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bs)

SETTINGS = {
    # width of the viewBox, simplification tolerance and dot threshold, all in viewBox units
    "world": {"width": 2000, "tol": 0.3, "dot_below": 6},
    "us": {"width": 1000, "tol": 0.25, "dot_below": 8},
}
# Where a place's dot goes / what its region view frames, where its biggest island isn't the
# right spot (Kiribati's biggest atoll is in the Line Islands, far from the capital).
ANCHOR = {"KI": (173.0, 1.4)}


# ---- Projections (shared with the shape builder, so shapes look the way they do on the map) ----
equal_earth, albers = bs.equal_earth, bs.albers


def bbox(points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def ring_path(ring, tol):
    pts = bs.simplify(ring, tol)
    if len(pts) < 3:
        return ""
    return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"


def polygons_path(polys, tol):
    """polys: projected [[outer, hole, ...], ...] in output units."""
    out = []
    for p in polys:
        for i, ring in enumerate(p):
            dims = bbox(ring)
            if i > 0 and max(dims[2] - dims[0], dims[3] - dims[1]) < 2 * tol:
                continue  # hole too small to see
            out.append(ring_path(ring, tol))
    return "".join(out)


# ---- World ----
def load_world(src, codes):
    fc = json.load(open(src, encoding="utf-8"))
    by_name = {f["properties"]["NAME"]: f for f in fc["features"]}
    owner = {}  # feature index -> quiz code
    for i, f in enumerate(fc["features"]):
        code = bs.iso2(f["properties"])
        if code in codes and (code not in bs.ONLY or f["properties"]["NAME"] == bs.ONLY[code]):
            owner[i] = code
    for code, names in bs.MERGE.items():
        for n in names:
            if code in codes and n in by_name:
                owner[fc["features"].index(by_name[n])] = code
    places, bg = {}, []
    for i, f in enumerate(fc["features"]):
        if f["properties"]["NAME"] == "Antarctica":
            continue
        polys = bs.polygons(f["geometry"])
        if i in owner:
            places.setdefault(owner[i], []).extend(polys)
        else:
            bg.extend(polys)
    return places, bg


def world_projector():
    # Centred on 12°E with the seam at 168°W, so Chukotka, Fiji, Tonga and Samoa aren't cut in two.
    lon0 = bs.WORLD_LON0

    def shift(poly):
        lons = [x for x, _ in poly[0]]
        if sum(lons) / len(lons) < -168:
            return [[(x + 360, y) for x, y in ring] for ring in poly]
        return poly

    def proj_poly(poly):
        return [[equal_earth(x - lon0, y) for x, y in ring] for ring in shift(poly)]

    def proj_point(lon, lat):
        if lon < -168:
            lon += 360
        return equal_earth(lon - lon0, lat)
    return proj_poly, proj_point


def build_world(src, codes):
    places, bg = load_world(src, codes)
    proj_poly, proj_point = world_projector()
    proj_places = {c: [proj_poly(p) for p in polys] for c, polys in places.items()}
    proj_bg = [proj_poly(p) for p in bg]
    allpts = [pt for polys in list(proj_places.values()) + [proj_bg] for p in polys for pt in p[0]]
    return finish("world", proj_places, proj_bg, allpts, places, lambda lon, lat: proj_point(lon, lat))


# ---- US ----
def build_us(src, codes):
    fc = json.load(open(src, encoding="utf-8"))
    places = {}
    for f in fc["features"]:
        p = f["properties"]
        if p.get("iso_a2") == "US":
            code = p["iso_3166_2"].split("-", 1)[1]
            if code in codes:
                places.setdefault(code, []).extend(bs.polygons(f["geometry"]))
    lower, ak, hi = bs.US_LOWER, bs.US_AK, bs.US_HI
    ak_lon = lambda x: x - 360 if x > 0 else x  # western Aleutians sit past the antimeridian

    def proj(code, poly):
        if code == "AK":
            return [[ak(ak_lon(x), y) for x, y in ring] for ring in poly]
        if code == "HI":
            return [[hi(x, y) for x, y in ring] for ring in poly]
        return [[lower(x, y) for x, y in ring] for ring in poly]

    raw = {}
    for code, polys in places.items():
        if code in ("AK", "HI"):
            polys = bs.keep_polygons(code, polys)  # drop far Aleutians / NW Hawaiian Islands
            places[code] = polys
        raw[code] = [proj(code, p) for p in polys]

    # Alaska and Hawaii go in insets below the south-west corner of the lower 48.
    l48 = union([bbox(r[0]) for c, polys in raw.items() if c not in ("AK", "HI") for r in polys])
    w, h = l48[2] - l48[0], l48[3] - l48[1]
    insets = {"AK": (0.35, l48[0], 0.0), "HI": (1.0, l48[0] + 0.25 * w, 0.0)}
    transforms = {}
    for code, (k, left, _) in insets.items():
        b = union([bbox(r[0]) for r in raw[code]])
        bottom = l48[3] + 0.02 * h
        dx = left - b[0] * k
        dy = bottom - b[3] * k
        transforms[code] = (k, dx, dy)
        raw[code] = [[[(x * k + dx, y * k + dy) for x, y in ring] for ring in p] for p in raw[code]]

    def point(code, lon, lat):
        if code in transforms:
            k, dx, dy = transforms[code]
            x, y = (ak(ak_lon(lon), lat) if code == "AK" else hi(lon, lat))
            return x * k + dx, y * k + dy
        return lower(lon, lat)

    allpts = [pt for polys in raw.values() for p in polys for pt in p[0]]
    return finish("us", raw, [], allpts, places, point, per_code_point=True)


# ---- Shared output ----
def finish(name, proj_places, proj_bg, allpts, lonlat_places, point, per_code_point=False):
    cfg = SETTINGS[name]
    x0, y0, x1, y1 = bbox(allpts)
    pad = 0.01 * (x1 - x0)
    scale = cfg["width"] / (x1 - x0 + 2 * pad)
    to = lambda x, y: ((x - x0 + pad) * scale, (y - y0 + pad) * scale)
    W, H = round((x1 - x0 + 2 * pad) * scale), round((y1 - y0 + 2 * pad) * scale)
    out = {"w": W, "h": H, "places": {}, "bg": "", "boxes": {}, "dots": {}}

    for code, polys in proj_places.items():
        view = [[[to(x, y) for x, y in ring] for ring in p] for p in polys]
        out["places"][code.lower()] = polygons_path(view, cfg["tol"])
        # The region view frames the place's main area, not far-flung islands or territories.
        kept = bs.keep_polygons(code, lonlat_places[code])
        idx = [i for i, p in enumerate(lonlat_places[code]) if any(p is k for k in kept)]
        main = [view[i] for i in idx] or view
        # ...and not islands that ended up across the map (the western Aleutians, at 172°E).
        size_of = lambda p: (bbox(p[0])[2] - bbox(p[0])[0]) * (bbox(p[0])[3] - bbox(p[0])[1])
        biggest = max(main, key=size_of)
        cx = (bbox(biggest[0])[0] + bbox(biggest[0])[2]) / 2
        main = [p for p in main if abs((bbox(p[0])[0] + bbox(p[0])[2]) / 2 - cx) < W / 4]
        box = union([bbox(p[0]) for p in main])
        if code in ANCHOR:
            lon, lat = ANCHOR[code]
            ax, ay = to(*(point(code, lon, lat) if per_code_point else point(lon, lat)))
            box = [ax - 3, ay - 3, ax + 3, ay + 3]
        out["boxes"][code.lower()] = [round(v, 1) for v in box]
        # A dot where even the biggest piece of land is too small to click (microstates, atolls).
        bb = bbox(biggest[0])
        if max(bb[2] - bb[0], bb[3] - bb[1]) < cfg["dot_below"] or code in ANCHOR:
            b = bb if code not in ANCHOR else box
            out["dots"][code.lower()] = [round((b[0] + b[2]) / 2, 1), round((b[1] + b[3]) / 2, 1)]

    if proj_bg:
        view = [[[to(x, y) for x, y in ring] for ring in p] for p in proj_bg]
        out["bg"] = polygons_path(view, cfg["tol"])
    return out


def main():
    name, src, dst, codes = sys.argv[1], sys.argv[2], sys.argv[3], set(sys.argv[4].upper().split(","))
    data = build_world(src, codes) if name == "world" else build_us(src, codes)
    missing = codes - {c.upper() for c in data["places"]}
    if missing:
        print("missing", sorted(missing))
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write("// Generated by tools/build_map.py from Natural Earth data. Do not edit.\n")
        fh.write(f"(window.MAPS ||= {{}})[{json.dumps(name)}] = {json.dumps(data, separators=(',', ':'))};\n")
    print(f"{name}: {len(data['places'])} places, {len(data['dots'])} dots, {os.path.getsize(dst) // 1024} KB")


if __name__ == "__main__":
    main()
