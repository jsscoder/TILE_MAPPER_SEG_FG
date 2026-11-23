import os
import io
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
import mercantile
import numpy as np
from PIL import Image
import pyproj
from shapely.geometry import LineString, box
from shapely.ops import unary_union, linemerge
import shapely
from rasterio.features import rasterize
from rasterio.transform import from_bounds

# --- CONFIGURATION ---
KMZ_PATH = r"C:\Users\omkar\Downloads\design_file.kmz"
ZOOM = 18                 # Zoom 18 (~0.6m/px) gives crisp 4K detail for 10m roads
BASE_TILE_SIZE = 256
GRID_N = 16               # 16 x 256 = 4096px (True 4K: 4096x4096)
SUPER_SIZE = BASE_TILE_SIZE * GRID_N
ROAD_BUFFER_METERS = 5.0  # Half-width (10m total carriageway)

OUT_DIR = "dataset_corridor_4k"
OUT_IMAGES = os.path.join(OUT_DIR, "images")
OUT_MASKS = os.path.join(OUT_DIR, "masks")
OUT_OVERLAYS = os.path.join(OUT_DIR, "overlays")
# ---------------------

# 1. Parse KML Alignment
print("Extracting road alignment from KMZ...")
with zipfile.ZipFile(KMZ_PATH, "r") as z:
    kml_name = [f for f in z.namelist() if f.endswith(".kml")][0]
    kml_data = z.read(kml_name)

root = ET.fromstring(kml_data)
for elem in root.iter():
    if "}" in elem.tag:
        elem.tag = elem.tag.split("}", 1)[1]

p2 = [
    p for p in root.findall(".//Placemark")
    if p.find("name") is not None and "AECC_ALIGNMENT" in p.find("name").text and ":2" in p.find("name").text
][0]

lines = []
for ls in p2.findall(".//LineString"):
    raw = ls.find("coordinates").text.strip().split()
    coords = [tuple(map(float, pt.split(",")[:2])) for pt in raw]
    if len(coords) >= 2:
        lines.append(LineString([(round(x, 6), round(y, 6)) for x, y in coords]))

alignment_wgs84 = linemerge(unary_union(lines))
print(f"Alignment extracted! Length: {alignment_wgs84.length * 111.32:.2f} km")

# 2. Project to Web Mercator (EPSG:3857)
transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
alignment_3857 = shapely.transform(
    alignment_wgs84,
    lambda coords: np.column_stack(transformer.transform(coords[:, 0], coords[:, 1]))
)
road_poly_3857 = alignment_3857.buffer(ROAD_BUFFER_METERS)

# 3. Group Corridor into Non-Overlapping 16x16 (4096x4096) Super-Tile Blocks
bbox = alignment_wgs84.bounds
candidate_tiles = list(mercantile.tiles(*bbox, zooms=[ZOOM]))

super_blocks = set()
for t in candidate_tiles:
    b = mercantile.bounds(t)
    if alignment_wgs84.intersects(box(b.west, b.south, b.east, b.north)):
        # Snap tile (x, y) to the top-left corner of its 16x16 super-tile grid
        bx = (t.x // GRID_N) * GRID_N
        by = (t.y // GRID_N) * GRID_N
        super_blocks.add((bx, by, t.z))

super_blocks = sorted(list(super_blocks))
print(f"Total 4K (4096x4096) super-tiles to generate at Zoom {ZOOM}: {len(super_blocks)}")

# 4. Stitch 4K Images & Rasterize 4K Masks
os.makedirs(OUT_IMAGES, exist_ok=True)
os.makedirs(OUT_MASKS, exist_ok=True)
os.makedirs(OUT_OVERLAYS, exist_ok=True)

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
palette = [0, 0, 0, 230, 25, 75] + [0, 0, 0] * 254  # 0: Background, 1: Road

for idx, (bx, by, z) in enumerate(super_blocks):
    # Top-left tile (bx, by) and bottom-right tile (bx + 15, by + 15) bounds
    west, _, _, north = mercantile.xy_bounds(mercantile.Tile(bx, by, z))
    _, south, east, _ = mercantile.xy_bounds(mercantile.Tile(bx + GRID_N - 1, by + GRID_N - 1, z))

    tr = from_bounds(west, south, east, north, SUPER_SIZE, SUPER_SIZE)

    # Rasterize the road polygon across the entire 4096x4096 block at once
    mask = rasterize(
        [(road_poly_3857, 1)],
        out_shape=(SUPER_SIZE, SUPER_SIZE),
        transform=tr,
        fill=0,
        all_touched=True,
        dtype=np.uint8
    )

    # Create blank 4096x4096 canvas and stitch the 16x16 grid
    canvas = Image.new("RGB", (SUPER_SIZE, SUPER_SIZE))
    failed_tiles = 0

    for dx in range(GRID_N):
        for dy in range(GRID_N):
            tx, ty = bx + dx, by + dy
            url = f"https://mt1.google.com/vt/lyrs=s&x={tx}&y={ty}&z={z}"
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    tile_img = Image.open(io.BytesIO(resp.read())).convert("RGB")
                    canvas.paste(tile_img, (dx * BASE_TILE_SIZE, dy * BASE_TILE_SIZE))
            except Exception:
                failed_tiles += 1
            time.sleep(0.02)  # Gentle throttle to avoid HTTP 429 rate limits

    base_name = f"{z}_{bx}_{by}_4k"
    img_path = os.path.join(OUT_IMAGES, f"{base_name}.jpg")
    mask_path = os.path.join(OUT_MASKS, f"{base_name}.png")
    overlay_path = os.path.join(OUT_OVERLAYS, f"{base_name}.jpg")

    canvas.save(img_path, quality=95)

    mask_img = Image.fromarray(mask, mode="P")
    mask_img.putpalette(palette)
    mask_img.save(mask_path)

    # Fast blended visual overlay
    sat_arr = np.array(canvas)
    sat_arr[mask == 1] = (sat_arr[mask == 1] * 0.5 + np.array([255, 0, 0]) * 0.5).astype(np.uint8)
    Image.fromarray(sat_arr).save(overlay_path, quality=85)

    print(f"[{idx + 1}/{len(super_blocks)}] Saved {base_name} (missed sub-tiles: {failed_tiles})")
