import os
import io
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
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds

# --- CONFIGURATION ---
KMZ_PATH = r"C:\Users\pc\.gemini\antigravity\brain\821fc672-21f8-4d86-bfa1-e2d547feeb74\.user_uploaded\media_1795418267049_97ea6240.kmz"
ZOOM = 17
TILE_SIZE = 256
ROAD_BUFFER_METERS = 5.0  # Half-width (total 10m carriageway/roadway)
INCLUDE_NEIGHBORS = True  # Include 1-tile adjacent buffer around the road corridor

OUT_DIR = "dataset_corridor"
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

p2 = [p for p in root.findall(".//Placemark") if p.find("name") is not None and "AECC_ALIGNMENT" in p.find("name").text and ":2" in p.find("name").text][0]
lines = []
for ls in p2.findall(".//LineString"):
    raw = ls.find("coordinates").text.strip().split()
    coords = [tuple(map(float, pt.split(",")[:2])) for pt in raw]
    if len(coords) >= 2:
        lines.append(LineString([(round(x, 6), round(y, 6)) for x, y in coords]))

alignment_wgs84 = linemerge(unary_union(lines))
print(f"Alignment extracted! Length: {alignment_wgs84.length * 111.32:.2f} km")

# 2. Project to Web Mercator (EPSG:3857) for accurate metric buffer and rasterization
transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
alignment_3857 = shapely.transform(alignment_wgs84, lambda coords: np.column_stack(transformer.transform(coords[:, 0], coords[:, 1])))
road_poly_3857 = alignment_3857.buffer(ROAD_BUFFER_METERS)

# 3. Determine Corridor Tiles
bbox = alignment_wgs84.bounds
candidate_tiles = list(mercantile.tiles(*bbox, zooms=[ZOOM]))

corridor_tiles = set()
for t in candidate_tiles:
    b = mercantile.bounds(t)
    if alignment_wgs84.intersects(box(b.west, b.south, b.east, b.north)):
        corridor_tiles.add(t)
        if INCLUDE_NEIGHBORS:
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    corridor_tiles.add(mercantile.Tile(t.x + dx, t.y + dy, t.z))

corridor_tiles = sorted(list(corridor_tiles), key=lambda t: (t.x, t.y))
print(f"Total tiles to process at Zoom {ZOOM}: {len(corridor_tiles)}")

# 4. Process and Download Tiles
os.makedirs(OUT_IMAGES, exist_ok=True)
os.makedirs(OUT_MASKS, exist_ok=True)
os.makedirs(OUT_OVERLAYS, exist_ok=True)

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
palette = [0, 0, 0, 230, 25, 75] + [0, 0, 0] * 254  # 0: Black, 1: Red (Road)

saved_count = 0
for idx, t in enumerate(corridor_tiles):
    west, south, east, north = mercantile.xy_bounds(t)
    tr = from_bounds(west, south, east, north, TILE_SIZE, TILE_SIZE)

    # Rasterize road mask
    mask = rasterize(
        [(road_poly_3857, 1)],
        out_shape=(TILE_SIZE, TILE_SIZE),
        transform=tr,
        fill=0,
        all_touched=True,
        dtype=np.uint8
    )

    # Paths
    img_path = os.path.join(OUT_IMAGES, f"{t.z}_{t.x}_{t.y}.jpg")
    mask_path = os.path.join(OUT_MASKS, f"{t.z}_{t.x}_{t.y}.png")
    overlay_path = os.path.join(OUT_OVERLAYS, f"{t.z}_{t.x}_{t.y}.jpg")

    # Fetch Google Satellite imagery tile
    url = f"https://mt1.google.com/vt/lyrs=s&x={t.x}&y={t.y}&z={t.z}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            sat_bytes = resp.read()
            sat_img = Image.open(io.BytesIO(sat_bytes))
            sat_img.save(img_path)

        # Save mask as paletted PNG
        mask_img = Image.fromarray(mask, mode="L")
        mask_img.putpalette(palette)
        mask_img.save(mask_path)

        # Save visual overlay
        sat_arr = np.array(sat_img)
        overlay_arr = sat_arr.copy()
        overlay_arr[mask == 1] = [255, 0, 0]  # Red overlay on road
        Image.fromarray(overlay_arr).save(overlay_path)

        saved_count += 1
        if (idx + 1) % 25 == 0 or (idx + 1) == len(corridor_tiles):
            print(f"Progress: {idx + 1}/{len(corridor_tiles)} tiles saved...")
    except Exception as e:
        print(f"Error on tile {t}: {e}")

print(f"Done! Saved {saved_count} paired (Satellite, Mask, Overlay) tiles in '{OUT_DIR}/'.")
