import os
import mercantile
import geopandas as gpd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from PIL import Image
import numpy as np
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, desc=""):
        total = len(iterable) if hasattr(iterable, "__len__") else None
        for idx, item in enumerate(iterable):
            if idx > 0 and idx % 2000 == 0 and total:
                print(f"[{desc}] Processed {idx}/{total} tiles ({idx/total*100:.1f}%)...")
            yield item

# --- CONFIGURATION ---
BBOX = (77.28, 28.10, 77.72, 28.66)
ZOOM = 17
TILE_SIZE = 256
OUT_MASK_DIR = "dataset/masks"

SHP_BUILDINGS = "noida_buildings.shp"
SHP_ROADS = "noida_roads.shp"
SHP_WATER = "noida_water.shp"

# Set to True to save as Paletted PNG (color visible in viewers, while retaining raw integer class IDs)
SAVE_PALETTED = True

# Class IDs & Colors:
# 0: Background -> Black (0, 0, 0)
# 1: Building   -> Red (230, 25, 75)
# 2: Road       -> Green (60, 180, 75)
# 3: Water      -> Blue (0, 130, 200)
PALETTE = [
    0, 0, 0,        # 0: Background
    230, 25, 75,    # 1: Building
    60, 180, 75,    # 2: Road
    0, 130, 200,    # 3: Water
] + [0, 0, 0] * 252
# ---------------------

print("Loading shapefiles and projecting to EPSG:3857...")
gdf_b = gpd.read_file(SHP_BUILDINGS).to_crs("EPSG:3857") if os.path.exists(SHP_BUILDINGS) else None
gdf_r = gpd.read_file(SHP_ROADS).to_crs("EPSG:3857") if os.path.exists(SHP_ROADS) else None
gdf_w = gpd.read_file(SHP_WATER).to_crs("EPSG:3857") if os.path.exists(SHP_WATER) else None

# Clean empty/null geometries
if gdf_b is not None:
    gdf_b = gdf_b[gdf_b.geometry.notnull() & (~gdf_b.geometry.is_empty)]
if gdf_r is not None:
    gdf_r = gdf_r[gdf_r.geometry.notnull() & (~gdf_r.geometry.is_empty)]
    # Buffer roads (~3m ground radius, ~3.41 EPSG:3857 units at 28.5 deg latitude)
    gdf_r["geometry"] = gdf_r.geometry.buffer(3.41)
if gdf_w is not None:
    gdf_w = gdf_w[gdf_w.geometry.notnull() & (~gdf_w.geometry.is_empty)]

# Build spatial indexes for instant bounding box lookups
print("Building R-tree spatial indexes...")
sindex_b = gdf_b.sindex if gdf_b is not None else None
sindex_r = gdf_r.sindex if gdf_r is not None else None
sindex_w = gdf_w.sindex if gdf_w is not None else None

tiles = list(mercantile.tiles(*BBOX, zooms=[ZOOM]))
print(f"Generating mask tiles for {len(tiles)} XYZ coordinates at Zoom {ZOOM}...")

saved = 0
for t in tqdm(tiles, desc="Tiling masks"):
    west, south, east, north = mercantile.xy_bounds(t)
    tile_box = (west, south, east, north)

    # 1. Query spatial index candidates for this tile
    b_cands = list(sindex_b.intersection(tile_box)) if sindex_b else []
    r_cands = list(sindex_r.intersection(tile_box)) if sindex_r else []
    w_cands = list(sindex_w.intersection(tile_box)) if sindex_w else []

    # Fast skip: if no features touch this tile, skip rasterization entirely
    if not b_cands and not r_cands and not w_cands:
        continue

    # 2. Burn order: Water (3) -> Roads (2) -> Buildings (1)
    # This ensures roads/bridges cross water, and buildings remain crisp on top
    tile_shapes = []
    if w_cands:
        tile_shapes.extend([(gdf_w.geometry.iloc[i], 3) for i in w_cands])
    if r_cands:
        tile_shapes.extend([(gdf_r.geometry.iloc[i], 2) for i in r_cands])
    if b_cands:
        tile_shapes.extend([(gdf_b.geometry.iloc[i], 1) for i in b_cands])

    transform = from_bounds(west, south, east, north, TILE_SIZE, TILE_SIZE)

    # 3. Burn shapes onto 256x256 array (all_touched=True ensures connected roads/rivers)
    mask = rasterize(
        shapes=tile_shapes,
        out_shape=(TILE_SIZE, TILE_SIZE),
        transform=transform,
        fill=0,
        all_touched=True,
        dtype=np.uint8
    )

    if np.max(mask) == 0:
        continue

    out_path = os.path.join(OUT_MASK_DIR, str(t.z), str(t.x), f"{t.y}.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    img = Image.fromarray(mask, mode="L")
    if SAVE_PALETTED:
        img.putpalette(PALETTE)
    img.save(out_path)
    saved += 1

print(f"Done! Generated {saved} non-empty mask tiles in {OUT_MASK_DIR}/")
