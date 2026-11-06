"""Draw the city grid maps: citymaps/<id>.svg, citymaps/<id>-sat.webp, citymaps/<id>-terrain.webp,
plus small versions for the grid layout: citymaps/<id>-thumb.svg, <id>-sat-thumb.webp and <id>-terrain-thumb.svg.

Usage:
    python3 -I tools/build_city_maps.py <cache dir> [map ids...] [--force] [--build=YYYYMMDD]
    python3 -I tools/build_city_maps.py --thumbs [map ids...]

--thumbs only remakes the small versions from the full-size files already in citymaps/ (no downloads).

Run from the project folder after tools/build_cities.py. With no ids it draws every city in
cities.js that doesn't have its files yet (add --force to redraw them all). Downloads are kept in
<cache dir>, so a run can be stopped and restarted, and redrawing doesn't download again.
Needs numpy and Pillow (pip install numpy pillow). Expect an hour or two and a few GB of downloads
for every city.

Each map is a square around the city (its size is in cities.js), in a local projection that is true
to scale, so streets keep their real angles. No names or labels are drawn. Sources, all free to
reuse with credit (the game shows it under the map):
- Streets, railways, water, parks, land: OpenStreetMap (ODbL), read from the Protomaps daily planet
  build (https://docs.protomaps.com/basemaps/downloads) with HTTP range requests, so only the
  tiles around each city are downloaded. --build picks a build; the default is the newest.
- Satellite: Sentinel-2 cloudless 2016 by EOX (CC BY 4.0, contains Copernicus Sentinel data); US
  cities use USGS aerial imagery instead (public domain, much sharper).
- Terrain: hill shading from the AWS Terrain Tiles (Mapzen; SRTM and other public sources).
"""
import base64
import bisect
import concurrent.futures
import gzip
import hashlib
import io
import json
import math
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.request

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "citymaps")
UA = "worldmapguesser-build/1.0 (static map builder)"
PROTOMAPS = "https://build.protomaps.com/{}.pmtiles"
PROTOMAPS_BUILDS = "https://build-metadata.protomaps.dev/builds.json"

SIZE = 2000              # viewBox width and height of every map
SIMPLIFY = 0.5           # Douglas-Peucker tolerance, viewBox units
SAT_PX_MAX = 2048        # satellite picture: up to this many pixels across...
SAT_PX_MIN = 900         # ...and at least this many (upscaled when the source is coarse)
TERRAIN_PX = 1024

SOURCES = {
    "eox": ("https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg", 14),
    "usgs": ("https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}", 16),
    "terrain": ("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png", 14),
}

# Streets: (class, OSM highway values, width in m), drawn in this order. Widths are exaggerated a
# little so streets show at the starting zoom.
ROADS = [
    ("foot", ["footway", "pedestrian", "steps", "living_street"], 4),
    ("minor", ["residential", "unclassified", "road"], 9),
    ("tertiary", ["tertiary", "tertiary_link"], 12),
    ("secondary", ["secondary", "secondary_link"], 15),
    ("primary", ["primary", "primary_link"], 18),
    ("major", ["motorway", "motorway_link", "trunk", "trunk_link"], 22),
]
# Protomaps' own road kinds, for roads whose OSM value isn't listed above.
ROAD_KIND = {"highway": "major", "major_road": "primary", "medium_road": "secondary", "minor_road": "minor"}
RAIL = {"rail", "light_rail", "tram", "narrow_gauge", "monorail", "funicular"}
RIVERS = {"river", "canal"}
GREEN = {"park", "garden", "forest", "wood", "grass", "grassland", "cemetery", "golf_course", "nature_reserve",
         "recreation_ground", "meadow", "scrub", "village_green", "playground", "pitch", "allotments", "orchard"}
PLAZA = {"pedestrian", "pier"}
RAIL_W, RIVER_W = 5, 14


# ---------------------------------------------------------------- downloads

def fetch(url, cache, byte_range=None, tries=8):
    """GET with a disk cache and retries (byte_range = (offset, length)). Returns bytes, or None for a 404."""
    key = hashlib.sha1(f"{url} {byte_range}".encode()).hexdigest()
    path = os.path.join(cache, key[:2], key)
    if os.path.exists(path):
        with open(path, "rb") as fh:
            body = fh.read()
        return None if body == b"404" else body
    headers = {"User-Agent": UA}
    if byte_range:
        headers["Range"] = f"bytes={byte_range[0]}-{byte_range[0] + byte_range[1] - 1}"
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as res:
                body = res.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                body = b"404"
                break
            if attempt == tries - 1:
                raise
            time.sleep(min(300, 5 * 2 ** attempt))  # busy server: back off
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == tries - 1:
                raise
            time.sleep(min(300, 5 * 2 ** attempt))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(body)
    return None if body == b"404" else body


def varint(b, i):
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, i


class PMTiles:
    """Just enough of the PMTiles v3 format (https://github.com/protomaps/PMTiles) to read tiles."""
    def __init__(self, url, cache):
        self.url, self.cache = url, cache
        h = fetch(url, cache, (0, 16384))
        if h[:7] != b"PMTiles" or h[7] != 3:
            sys.exit(f"{url} isn't a PMTiles v3 file")
        (self.root_off, self.root_len, _, _, self.leaf_off, _, self.data_off) = struct.unpack("<7Q", h[8:64])
        self.tile_gzip = h[98] == 2
        self.max_zoom = h[101]
        self.head = h
        self.dirs = {}

    def directory(self, off, length):
        if (off, length) not in self.dirs:
            raw = self.head[off:off + length] if off + length <= len(self.head) else fetch(self.url, self.cache, (off, length))
            b = gzip.decompress(raw)
            n, i = varint(b, 0)
            cols = []
            for _ in range(4):
                col = []
                for _ in range(n):
                    v, i = varint(b, i)
                    col.append(v)
                cols.append(col)
            ids, runs, lens, raw_offs = cols
            for k in range(1, n):
                ids[k] += ids[k - 1]
            offs = []
            for k in range(n):
                offs.append(offs[-1] + lens[k - 1] if raw_offs[k] == 0 and k > 0 else raw_offs[k] - 1)
            self.dirs[(off, length)] = (ids, offs, lens, runs)
        return self.dirs[(off, length)]

    @staticmethod
    def tile_id(z, x, y):
        acc = ((1 << (2 * z)) - 1) // 3  # tiles in all lower zooms
        n, d, s = 1 << z, 0, 1 << (z - 1)
        while s > 0:  # Hilbert curve index of (x, y)
            rx, ry = int(x & s > 0), int(y & s > 0)
            d += s * s * ((3 * rx) ^ ry)
            if ry == 0:
                if rx == 1:
                    x, y = n - 1 - x, n - 1 - y
                x, y = y, x
            s //= 2
        return acc + d

    def tile(self, z, x, y):
        t = self.tile_id(z, x, y)
        off, length = self.root_off, self.root_len
        for _ in range(4):
            ids, offs, lens, runs = self.directory(off, length)
            i = bisect.bisect_right(ids, t) - 1
            if i < 0:
                return None
            if runs[i] == 0:  # points to a leaf directory
                off, length = self.leaf_off + offs[i], lens[i]
                continue
            if t >= ids[i] + runs[i]:
                return None
            body = fetch(self.url, self.cache, (self.data_off + offs[i], lens[i]))
            return gzip.decompress(body) if self.tile_gzip else body
        return None


def pb_fields(b):
    """Protocol buffer fields: (field number, value) with varints decoded and the rest as bytes."""
    i, n = 0, len(b)
    while i < n:
        k, i = varint(b, i)
        f, w = k >> 3, k & 7
        if w == 0:
            v, i = varint(b, i)
        elif w == 2:
            ln, i = varint(b, i)
            v = b[i:i + ln]
            i += ln
        elif w == 5:
            v = b[i:i + 4]
            i += 4
        elif w == 1:
            v = b[i:i + 8]
            i += 8
        else:
            raise ValueError("bad protobuf")
        yield f, v


def packed(b):
    out, i = [], 0
    while i < len(b):
        v, i = varint(b, i)
        out.append(v)
    return out


def mvt_layers(data, wanted):
    """Decode a Mapbox Vector Tile: {layer: (extent, [(tags, geometry type, [rings or lines])])}."""
    out = {}
    for f, layer in pb_fields(data):
        if f != 3:
            continue
        name, keys, vals, feats, extent = None, [], [], [], 4096
        for ff, v in pb_fields(layer):
            if ff == 1:
                name = v.decode()
                if name not in wanted:
                    break
            elif ff == 2:
                feats.append(v)
            elif ff == 3:
                keys.append(v.decode())
            elif ff == 4:
                val = None
                for vf, vv in pb_fields(v):
                    val = vv.decode() if vf == 1 else (vv == 1 if vf == 7 else vv)
                vals.append(val)
            elif ff == 5:
                extent = v
        if name not in wanted:
            continue
        decoded = []
        for ft in feats:
            tags, gtype, geom = [], 0, []
            for ff, v in pb_fields(ft):
                if ff == 2:
                    tags = packed(v)
                elif ff == 3:
                    gtype = v
                elif ff == 4:
                    geom = packed(v)
            props = {keys[tags[j]]: vals[tags[j + 1]] for j in range(0, len(tags) - 1, 2)}
            parts, cur, x, y, i = [], [], 0, 0, 0
            while i < len(geom):
                cmd, count = geom[i] & 7, geom[i] >> 3
                i += 1
                if cmd == 7:  # close path
                    if cur:
                        cur.append(cur[0])
                    continue
                for _ in range(count):
                    dx, dy = geom[i], geom[i + 1]
                    i += 2
                    x += (dx >> 1) ^ -(dx & 1)
                    y += (dy >> 1) ^ -(dy & 1)
                    if cmd == 1:  # move to: a new line or ring
                        if cur:
                            parts.append(cur)
                        cur = [(x, y)]
                    else:
                        cur.append((x, y))
            if cur:
                parts.append(cur)
            decoded.append((props, gtype, parts))
        out[name] = (extent, decoded)
    return out


def tile_mosaic(source, lat0, lon0, half_m, px_target, cache):
    """Fetch the Web Mercator tiles covering the square and resample them onto it: an RGB array."""
    url, zmax = SOURCES[source]
    side = 2 * half_m
    # Lowest zoom whose ground resolution is at least as fine as the output needs.
    z = next((zz for zz in range(10, zmax + 1)
              if 156543.03 * math.cos(math.radians(lat0)) / 2 ** zz <= side / px_target), zmax)
    n = 2 ** z
    x0, y0, x1, y1 = merc_box(lat0, lon0, half_m, z)
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    tiles = [(tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]
    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        bodies = list(pool.map(lambda t: fetch(url.format(z=z, x=t[0] % n, y=t[1]), cache), tiles))
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256, 3), np.float32)
    bad = 0
    for (tx, ty), body in zip(tiles, bodies):
        if body is None:
            bad += 1
            continue
        img = np.asarray(Image.open(io.BytesIO(body)).convert("RGB").resize((256, 256)), np.float32)
        if source != "terrain" and img.std() < 2:
            bad += 1  # the USGS service answers outside its coverage with a plain tile
        mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = img
    if bad > len(tiles) * 0.05:
        return None
    # Sentinel-2 cloudless marks places it has no picture of (some Pacific atolls) in plain white.
    if source == "eox" and (mosaic.min(axis=2) > 250).mean() > 0.05:  # more than a few clouds
        return None
    # Output pixel centres -> lat/lon (local projection) -> mosaic pixel, bilinear.
    k = (np.arange(px_target) + 0.5) / px_target * 2 - 1
    lon = lon0 + k * half_m / (111320 * math.cos(math.radians(lat0)))
    lat = lat0 - k * half_m / 110574
    mx = (lon + 180) / 360 * n * 256 - tx0 * 256 - 0.5
    my = (1 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2 * n * 256 - ty0 * 256 - 0.5
    MX, MY = np.meshgrid(mx, my)
    return bilinear(mosaic, MX, MY)


def merc_box(lat0, lon0, half_m, z):
    """The square's corners in Web Mercator pixels at zoom z (256-pixel tiles)."""
    n = 2 ** z
    def merc(lat, lon):
        return ((lon + 180) / 360 * n * 256, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * 256)
    dlat, dlon = half_m / 110574, half_m / (111320 * math.cos(math.radians(lat0)))
    x0, y0 = merc(lat0 + dlat, lon0 - dlon)
    x1, y1 = merc(lat0 - dlat, lon0 + dlon)
    return x0, y0, x1, y1


def bilinear(img, x, y):
    h, w = img.shape[:2]
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = x.astype(int), y.astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy)
            + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)


def terrain_image(lat0, lon0, half_m, cache):
    rgb = tile_mosaic("terrain", lat0, lon0, half_m, TERRAIN_PX, cache)
    if rgb is None:
        return None
    elev = rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768
    elev = np.maximum(elev, -10)  # don't shade the sea floor
    gy, gx = np.gradient(elev, 2 * half_m / TERRAIN_PX)
    # Hill shading, light from the north-west. Flat cities get some exaggeration so they aren't blank.
    relief = float(np.percentile(elev, 98) - np.percentile(elev, 2))
    zf = 1 + 2 * max(0.0, 1 - relief / 150)
    slope = np.arctan(zf * np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(315), math.radians(45)
    shade = np.clip(np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect), 0, 1)
    # Colour by height within the map (at least a 60 m span, so small bumps stay pale).
    lo = float(np.percentile(elev, 1))
    t = np.clip((elev - lo) / max(60.0, relief), 0, 1)[..., None]
    low, mid, high = np.array([206, 222, 186]), np.array([226, 208, 160]), np.array([176, 140, 104])
    tint = np.where(t < 0.5, low + (mid - low) * (t * 2), mid + (high - mid) * ((t - 0.5) * 2))
    return np.clip(tint * (0.45 + 0.65 * shade[..., None]), 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- geometry

LO, HI = -2.0, SIZE + 2.0  # clip a hair outside the view so edges don't show


def clip_line(pts, lo=LO, hi=HI):
    """Split a polyline into the pieces inside the square lo..hi (Liang-Barsky per segment)."""
    out, cur = [], []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        t0, t1, dx, dy = 0.0, 1.0, x1 - x0, y1 - y0
        ok = True
        for p, q in ((-dx, x0 - lo), (dx, hi - x0), (-dy, y0 - lo), (dy, hi - y0)):
            if p == 0:
                if q < 0:
                    ok = False
                    break
            elif p < 0:
                t0 = max(t0, q / p)
            else:
                t1 = min(t1, q / p)
        if not ok or t0 > t1:
            if cur:
                out.append(cur)
                cur = []
            continue
        a, b = (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)
        if not cur:
            cur = [a]
        cur.append(b)
        if t1 < 1:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [c for c in out if len(c) > 1]


def clip_ring(pts, lo=LO, hi=HI):
    """Sutherland-Hodgman against the square lo..hi: a ring stays a ring, with the same winding."""
    def edge(points, inside, cross):
        res = []
        for i, cur in enumerate(points):
            prev = points[i - 1]
            if inside(cur):
                if not inside(prev):
                    res.append(cross(prev, cur))
                res.append(cur)
            elif inside(prev):
                res.append(cross(prev, cur))
        return res
    def at_x(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))
    def at_y(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    for inside, cross in ((lambda p: p[0] >= lo, at_x(lo)), (lambda p: p[0] <= hi, at_x(hi)),
                          (lambda p: p[1] >= lo, at_y(lo)), (lambda p: p[1] <= hi, at_y(hi))):
        pts = edge(pts, inside, cross)
        if not pts:
            return []
    return pts if len(pts) > 2 else []


def simplify(pts, tol=SIMPLIFY):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        d2 = dx * dx + dy * dy or 1e-12
        best, idx = 0.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / d2))
            dist = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if dist > best:
                best, idx = dist, i
        if best > tol * tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def path_d(parts, closed=False):
    """Compact SVG path data: one decimal, relative line-tos."""
    out = []
    for pts in parts:
        if closed:
            pts = pts + [pts[0]]
        q = [(round(x * 10), round(y * 10)) for x, y in simplify(pts)]
        q = [p for i, p in enumerate(q) if i == 0 or p != q[i - 1]]
        if len(q) < (4 if closed else 2):
            continue
        if closed:
            q = q[:-1]
        rel = " ".join(f"{(x1 - x0) / 10:g} {(y1 - y0) / 10:g}" for (x0, y0), (x1, y1) in zip(q, q[1:]))
        out.append(f"M{q[0][0] / 10:g} {q[0][1] / 10:g}l{rel}{'z' if closed else ''}")
    return re.sub(r" -", "-", "".join(out))


# ---------------------------------------------------------------- drawing

def draw_svg(pm, lat0, lon0, half_m, sat_src):
    z = 14 if half_m >= 5000 else pm.max_zoom  # the biggest cities: one zoom out is plenty and 4x fewer tiles
    x0, y0, x1, y1 = merc_box(lat0, lon0, half_m, z)
    tiles = [(tx, ty) for ty in range(int(y0 // 256), int(y1 // 256) + 1) for tx in range(int(x0 // 256), int(x1 // 256) + 1)]
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        datas = list(pool.map(lambda t: pm.tile(z, *t), tiles))

    # Mercator pixel -> viewBox. Over a few km Mercator is the local projection scaled by
    # 1/cos(lat) in both directions, so this is just a scale and a shift.
    kx, ky = SIZE / (x1 - x0), SIZE / (y1 - y0)
    u = SIZE / (2 * half_m)  # viewBox units per metre
    roads = {cls: [] for cls, _, _ in ROADS}
    road_of = {v: cls for cls, vals, _ in ROADS for v in vals}
    rail, rivers, water, green, plaza, earth = [], [], [], [], [], []
    for (tx, ty), data in zip(tiles, datas):
        if data is None:
            continue
        layers = mvt_layers(data, {"earth", "water", "landuse", "roads", "transit"})
        for name, (extent, feats) in layers.items():
            # Clip each tile to its own square (tiles overlap by a buffer), then move it into place.
            to = lambda pts: [((tx * 256 + px * 256 / extent - x0) * kx, (ty * 256 + py * 256 / extent - y0) * ky) for px, py in pts]
            for props, gtype, parts in feats:
                kind, detail = props.get("kind"), props.get("kind_detail")
                if gtype == 3:
                    target = (earth if name == "earth" else water if name == "water"
                              else green if kind in GREEN else plaza if kind in PLAZA else None)
                    if target is not None:
                        target += [to(r) for r in (clip_ring(p, 0, extent) for p in parts) if r]
                elif gtype == 2:
                    if props.get("is_tunnel"):
                        continue
                    if name == "roads" and kind not in ("rail", "ferry"):
                        cls = road_of.get(detail) or (ROAD_KIND.get(kind) if kind != "path" else None)
                        target = roads[cls] if cls else None
                    elif kind == "rail" or detail in RAIL:
                        target = rail if detail != "subway" else None
                    elif name == "water" and (kind in RIVERS or detail in RIVERS):
                        target = rivers
                    else:
                        target = None
                    if target is not None:
                        target += [to(l) for p in parts for l in clip_line(p, 0, extent)]

    rings = lambda rs: [r for r in (clip_ring(r) for r in rs) if r]
    lines = lambda ls: [p for l in ls for p in clip_line(l)]
    sw = lambda m: f"{max(0.4, m * u):.2f}"
    # The sea is the square minus the land: the square drawn anticlockwise plus the land shapes,
    # which vector tiles draw clockwise, so with the nonzero rule the land cuts out of the sea.
    # (A separate sea shape lets the terrain view show the sea but hide the land colour.)
    sea = f"M{LO:g} {LO:g}V{HI:g}H{HI:g}V{LO:g}z" + path_d(rings(earth), True)
    out = [f'<rect class="c-land" width="{SIZE}" height="{SIZE}"/>',
           f'<path class="c-sea" d="{sea}"/>',
           f'<path class="c-green" d="{path_d(rings(green), True)}"/>',
           f'<path class="c-water" d="{path_d(rings(water), True)}"/>',
           f'<path class="c-river" stroke-width="{sw(RIVER_W)}" d="{path_d(lines(rivers))}"/>',
           f'<path class="c-plaza" d="{path_d(rings(plaza), True)}"/>',
           f'<path class="c-rail" stroke-width="{sw(RAIL_W)}" d="{path_d(lines(rail))}"/>']
    for cls, _, width in ROADS:
        out.append(f'<path class="c-road c-{cls}" stroke-width="{sw(width)}" d="{path_d(lines(roads[cls]))}"/>')
    out = [o for o in out if ' d=""' not in o]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" data-km="{2 * half_m / 1000:g}" data-sat="{sat_src}">'
            # Colours for viewing the file on its own; the game uses its own (style.css).
            '<style>.c-land{fill:#f2efe9}.c-sea,.c-water{fill:#aad3df}.c-river{fill:none;stroke:#aad3df}'
            '.c-green{fill:#cdebb0}.c-plaza{fill:#fbfaf7}.c-rail{fill:none;stroke:#999;stroke-dasharray:6 4}'
            '.c-road{fill:none;stroke:#fff;stroke-linecap:round;stroke-linejoin:round}.c-major{stroke:#f6c66b}'
            '.c-primary{stroke:#fcd6a4}.c-foot{stroke:#e5e0d6}</style>'
            + "".join(out) + "</svg>\n")


# ---------------------------------------------------------------- grid thumbnails
# The grid shows dozens of maps at once, so it gets a lighter copy of each: no footpaths or plazas,
# coarser lines, and roads drawn at least a set width so they still show at a few hundred pixels.
THUMB_TOL = 2.5          # simplification tolerance, viewBox units
THUMB_MIN_W = {"c-river": 6, "c-rail": 3, "c-minor": 3.5, "c-tertiary": 5, "c-secondary": 6, "c-primary": 8, "c-major": 10}
THUMB_DROP = ("c-foot", "c-plaza")
THUMB_SAT_PX = 640
# The terrain view: hill shading with the water and faint streets on top, as in the game's terrain view.
# The shading is embedded in the file (an image used as an <img> can't load anything else).
TERRAIN_DROP = ("c-land", "c-green", "c-plaza", "c-foot")
TERRAIN_STYLE = (
    "<style>.c-sea,.c-water{fill:#aad3df}.c-river{fill:none;stroke:#aad3df}.c-rail{fill:none;stroke:rgba(70,60,50,.28);"
    "stroke-dasharray:6 4}.c-road{fill:none;stroke:rgba(70,60,50,.28);stroke-linecap:round;stroke-linejoin:round}"
    "@media (prefers-color-scheme:dark){.c-sea,.c-water{fill:#1d3a52}.c-river{stroke:#1d3a52}}</style>")
# Same colours as #map-svg.city in style.css. The grid shows these files as images, which the page's
# CSS can't reach; they follow the page's theme through its color-scheme.
THUMB_STYLE = (
    "<style>.c-land{fill:#f2efe9}.c-sea,.c-water{fill:#aad3df}.c-river{fill:none;stroke:#aad3df}.c-green{fill:#cdebb0}"
    ".c-rail{fill:none;stroke:#9a9a9a;stroke-dasharray:6 4}.c-road{fill:none;stroke:#fff;stroke-linecap:round;"
    "stroke-linejoin:round}.c-primary{stroke:#fcd6a4}.c-major{stroke:#f6c66b}"
    "@media (prefers-color-scheme:dark){.c-land{fill:#262b35}.c-sea,.c-water{fill:#1d3a52}.c-river{stroke:#1d3a52}"
    ".c-green{fill:#24372a}.c-rail{stroke:#6b7280}.c-road{stroke:#59606e}.c-primary{stroke:#8a7350}"
    ".c-major{stroke:#b38c46}}</style>")


def parse_d(d):
    """Path data written by path_d() -> ([[(x, y), ...], ...], closed)."""
    parts = []
    for m in re.finditer(r"M([^l]+)l([^Mz]*)(z?)", d):
        nums = [float(v) for v in re.findall(r"-?[\d.]+(?:e-?\d+)?", m.group(1) + " " + m.group(2))]
        x, y = nums[0], nums[1]
        pts = [(x, y)]
        for i in range(2, len(nums) - 1, 2):
            x += nums[i]
            y += nums[i + 1]
            pts.append((x, y))
        parts.append(pts)
    return parts, d.rstrip().endswith("z")


def make_thumbs(map_id):
    src = os.path.join(OUT, f"{map_id}.svg")
    svg = open(src, encoding="utf-8").read()
    head = re.match(r"<svg[^>]*>", svg).group(0)
    out = []  # (classes, element)
    for el in re.findall(r"<(?:rect|path)[^>]*/>", svg):
        cls = re.search(r'class="([^"]*)"', el).group(1)
        if el.startswith("<rect"):
            out.append((cls, el))
            continue
        d = re.search(r' d="([^"]*)"', el).group(1)
        attrs = ""
        sw = re.search(r'stroke-width="([^"]*)"', el)
        if sw:
            w = max([float(sw.group(1))] + [v for c, v in THUMB_MIN_W.items() if c in cls.split()])
            attrs = f' stroke-width="{w:g}"'
        if cls == "c-sea":
            # The square plus the land rings; the square keeps its exact corners.
            square, rest = d.split("z", 1)
            parts, _ = parse_d(rest)
            body = square + "z" + thumb_d(parts, True)
        else:
            parts, closed = parse_d(d)
            body = thumb_d(parts, closed)
        if body:
            out.append((cls, f'<path class="{cls}"{attrs} d="{body}"/>'))
    keep = lambda drop: "".join(el for cls, el in out if not set(cls.split()) & set(drop))
    with open(os.path.join(OUT, f"{map_id}-thumb.svg"), "w", encoding="utf-8") as fh:
        fh.write(head + THUMB_STYLE + keep(THUMB_DROP) + "</svg>\n")
    terrain = os.path.join(OUT, f"{map_id}-terrain.webp")
    if os.path.exists(terrain):
        buf = io.BytesIO()
        Image.open(terrain).convert("RGB").resize((THUMB_SAT_PX, THUMB_SAT_PX), Image.LANCZOS).save(buf, "WEBP", quality=70, method=6)
        shade = f'<image width="{SIZE}" height="{SIZE}" preserveAspectRatio="none" href="data:image/webp;base64,{base64.b64encode(buf.getvalue()).decode()}"/>'
        with open(os.path.join(OUT, f"{map_id}-terrain-thumb.svg"), "w", encoding="utf-8") as fh:
            fh.write(head + TERRAIN_STYLE + shade + keep(THUMB_DROP + TERRAIN_DROP) + "</svg>\n")
    sat = os.path.join(OUT, f"{map_id}-sat.webp")
    if os.path.exists(sat):
        img = Image.open(sat).convert("RGB")
        img.resize((THUMB_SAT_PX, THUMB_SAT_PX), Image.LANCZOS).save(
            os.path.join(OUT, f"{map_id}-sat-thumb.webp"), quality=70, method=6)


def thumb_d(parts, closed):
    """Whole-number path data, simplified harder, with specks left out."""
    out = []
    for pts in parts:
        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        if max(xs) - min(xs) < (14 if closed else 4) and max(ys) - min(ys) < (14 if closed else 4):
            continue
        if closed:
            pts = pts + [pts[0]]
        q = [(round(x), round(y)) for x, y in simplify(pts, THUMB_TOL * (1.6 if closed else 1))]
        q = [p for i, p in enumerate(q) if i == 0 or p != q[i - 1]]
        if len(q) < (4 if closed else 2):
            continue
        if closed:
            q = q[:-1]
        rel = " ".join(f"{x1 - x0} {y1 - y0}" for (x0, y0), (x1, y1) in zip(q, q[1:]))
        out.append(f"M{q[0][0]} {q[0][1]}l{rel}{'z' if closed else ''}")
    return re.sub(r" -", "-", "".join(out))


def cities():
    """{map id: (lat, lon, half width km, is in the US)} from cities.js."""
    src = open(os.path.join(ROOT, "cities.js"), encoding="utf-8").read()
    maps = {}
    for kind, body in re.findall(r'"([a-z-]+)": \{\n    regions: .*?\n    info: (\{.*?\}),\n', src):
        for code, info in json.loads(body).items():
            map_id, lat, lon, half_km, *flag = info
            us = kind == "state-capitals" or flag == ["us"] or (kind == "capitals" and code == "us")
            maps[map_id] = (lat, lon, half_km, us or maps.get(map_id, (0, 0, 0, False))[3])
    return maps


def build(pm, map_id, lat, lon, half_km, us, cache):
    half_m = half_km * 1000
    t0 = time.time()
    sat, sat_src = None, None
    for src in (["usgs"] if us else []) + ["eox"]:
        native = 156543.03 * math.cos(math.radians(lat)) / 2 ** SOURCES[src][1]
        px = int(min(SAT_PX_MAX, max(SAT_PX_MIN, 2 * half_m / native)))
        sat = tile_mosaic(src, lat, lon, half_m, px, cache)
        if sat is not None:
            sat_src = src
            break
    svg = draw_svg(pm, lat, lon, half_m, sat_src or "")
    terr = terrain_image(lat, lon, half_m, cache)
    os.makedirs(OUT, exist_ok=True)
    files = {f"{map_id}.svg": None, f"{map_id}-sat.webp": sat, f"{map_id}-terrain.webp": terr}
    with open(os.path.join(OUT, f"{map_id}.svg"), "w", encoding="utf-8") as fh:
        fh.write(svg)
    for name, img in files.items():
        if name.endswith(".webp") and img is not None:
            Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(os.path.join(OUT, name), quality=72, method=6)
    size = sum(os.path.getsize(os.path.join(OUT, n)) for n in files if os.path.exists(os.path.join(OUT, n)))
    make_thumbs(map_id)
    print(f"{map_id}: satellite {sat_src or 'none'}, {size / 1e6:.2f} MB, {time.time() - t0:.0f}s", flush=True)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--thumbs" in sys.argv:
        todo = args or sorted(m for m in cities() if os.path.exists(os.path.join(OUT, f"{m}.svg")))
        for map_id in todo:
            make_thumbs(map_id)
        print(f"made thumbnails for {len(todo)} maps")
        return
    if not args:
        sys.exit(__doc__)
    cache, wanted = args[0], args[1:]
    force = "--force" in sys.argv
    build_date = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--build=")), None)
    if not build_date:
        builds = json.loads(urllib.request.urlopen(urllib.request.Request(PROTOMAPS_BUILDS, headers={"User-Agent": UA}), timeout=60).read())
        build_date = builds[-1]["key"].removesuffix(".pmtiles")
    print(f"OpenStreetMap data: Protomaps build {build_date}", flush=True)
    pm = PMTiles(PROTOMAPS.format(build_date), cache)
    maps = cities()
    unknown = [w for w in wanted if w not in maps]
    if unknown:
        sys.exit(f"not in cities.js: {', '.join(unknown)}")
    todo = wanted or [m for m in maps if force or not os.path.exists(os.path.join(OUT, f"{m}.svg"))]
    print(f"{len(todo)} maps to draw", flush=True)
    failed = []
    for i, map_id in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] ", end="", flush=True)
        try:
            build(pm, map_id, *maps[map_id], cache)
        except Exception as e:  # keep going; run again later to retry
            print(f"{map_id}: FAILED ({e!r})", flush=True)
            failed.append(map_id)
    if failed:
        print("failed (run again to retry):", " ".join(failed))
    stale = sorted({re.sub(r"(-sat|-terrain)?(-thumb)?\.(svg|webp)$", "", n) for n in os.listdir(OUT)} - set(maps)) if os.path.isdir(OUT) else []
    if stale:
        print("in citymaps/ but not in cities.js (delete if unwanted):", " ".join(stale))


if __name__ == "__main__":
    main()
