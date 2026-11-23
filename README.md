# TILE_MAPPER_SEG_FG

An end-to-end Geospatial AI pipeline for extracting, tiling, triaging, and semantically segmenting linear civil infrastructure (roads, canals, drains, rivers, and buildings) from satellite imagery and CAD/GIS vector data.

---

## 📌 Project Overview & Scope

High-resolution aerial satellite imagery ($256 \times 256$, Zoom 17, $\sim 1.11\text{ m/px}$) presents a unique computer vision challenge: **thin linear infrastructure (roads, canals, roadside ditches) typically covers only $2\%$ to $4\%$ of a tile's area**, while $96\%+$ is occupied by surrounding rural landscape (farmland, waterlogged paddy fields, tree canopies).

**TILE_MAPPER_SEG_FG** bridges the gap between raw civil engineering design data (AutoCAD Civil 3D alignments / KML / Shapefiles), global OpenStreetMap extracts, and deep learning segmentation models. It implements an active 2-stage AI pipeline:
1. **Stage 1 (VLM Triage & Curation):** Sub-50MB edge Vision-Language Model (**Mirage VLM** by Cactus Compute) performs zero-shot multi-label scene understanding to index, filter, and bifurcate tiles.
2. **Stage 2 (Dense Semantic Segmentation):** Prepares paired, sub-pixel accurate ground truth masks for fine-grained semantic segmentation models (**SegFormer / UNet++**).

---

## 🏗️ Architecture & Pipeline Workflow

```
[AutoCAD Civil 3D / KML / OSM PBF]
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 1. Vector Extraction & Reprojection                     │
│    - WGS84 (EPSG:4326) -> Web Mercator (EPSG:3857)       │
│    - Dynamic metric buffering (roads, canals, drains)   │
└─────────────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 2. Spatial Indexing & XYZ Tile Harvesting               │
│    - GEOS R-Tree (sindex) for O(1) candidate query       │
│    - Google Maps Satellite XYZ harvesting at Zoom 17    │
│    - 1-tile adjacent contextual corridor buffer         │
└─────────────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 3. Multi-Class Mask Rasterization                       │
│    - Layer burning hierarchy: Water -> Roads -> Bldgs   │
│    - Mode 'P' (8-bit paletted PNG) preserving class IDs │
│    - all_touched=True for unbroken line connectivity    │
└─────────────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 4. Mirage VLM Multi-Label Bifurcation                   │
│    - Zero-shot classification into class buckets        │
│    - Generates bifurcation_manifest.csv & .json         │
└─────────────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ 5. Dense Semantic Segmentation (Phase 2)                │
│    - SegFormer (nvidia/mit-b2, mit-b3) / UNet++         │
│    - Sub-pixel boundary classification on GPU           │
└─────────────────────────────────────────────────────────┘
```

---

## ⚡ Quick Start: One-Click Environment Setup (with `uv`)

This project uses [`uv`](https://docs.astral.sh/uv/) for ultra-fast dependency resolution and isolated virtual environments.

### 🪟 Windows (One-Click)
Double-click **`setup.bat`**, or run in PowerShell:
```powershell
.\setup.ps1
```
*(If `uv` is not present on your system, the script automatically installs it, creates an isolated `.venv`, and installs all dependencies from `req.txt`)*.

### 🐧 Linux / macOS
```bash
chmod +x setup.sh && ./setup.sh
```

### 📦 Manual Installation
```bash
# Using uv (fastest)
uv venv .venv
uv pip install -r req.txt

# Or using standard pip
python -m venv .venv
# Windows: .venv\Scripts\activate | Linux/macOS: source .venv/bin/activate
pip install -r req.txt
```

---

## 📂 Repository Structure & Core Modules

| Script | Purpose & Functionality |
| :--- | :--- |
| [**`tiler.py`**](tiler.py) | High-throughput `osmium` handler that scans `.osm.pbf` dumps to extract Buildings, Roads, Water Areas, and Waterways within an arbitrary bounding box into clean shapefiles. |
| [**`extract_water.py`**](extract_water.py) | Dedicated waterbody extractor; categorizes polygonal water (lakes, ponds, reservoirs, riverbeds) and linear waterways (rivers, canals, streams, drains) and synthesizes a unified buffered polygon layer. |
| [**`mask_tiles.py`**](mask_tiles.py) | High-speed XYZ rasterizer. Uses GeoPandas R-tree spatial indexing (`sindex`) to eliminate the $O(N \times M)$ bottleneck, generating 37,000+ tiles in under 2 minutes. Burns layers in proper GIS occlusion order. |
| [**`export_corridor_tiles.py`**](export_corridor_tiles.py) | Extracts the design alignment from AutoCAD Civil 3D KML/KMZ corridors, queries intersecting XYZ tiles at Zoom 17, downloads Google Satellite imagery, and generates paired masks and verification overlays. |
| [**`bifurcate_tiles_mirage.py`**](bifurcate_tiles_mirage.py) | Integrates **Cactus Compute Mirage VLM** to run structured multi-label extraction on aerial tiles, sorting them into class directories and exporting dataset manifests. |

---

## 🗺️ Geospatial & Coordinate Reference Systems (CRS)

* **Tile Scheme:** Standard Slippy Map XYZ (`{z}/{x}/{y}`)
* **Tile Dimensions:** $256 \times 256$ pixels
* **Zoom Level:** **Zoom 17**
  * **Ground Resolution:** $\sim 1.11\text{ meters per pixel}$ at latitude $21.8^\circ\text{N}$.
  * **Physical Tile Coverage:** $284\text{ m} \times 284\text{ m}$ ($0.08\text{ km}^2$).
* **Projection Alignment:**
  * Vector geometries stored in **EPSG:4326** (WGS84).
  * Reprojected on the fly to **EPSG:3857** (Web Mercator) for exact metric buffering and sub-pixel alignment with Google Maps raster tiles.

---

## 🎨 Semantic Class Definitions & Palette

Masks are encoded in **Mode `P` (8-bit Paletted PNG)**. In standard image viewers, classes display in distinct colors, while programmatically (`numpy.array`), pixels retain exact integer class IDs:

| Class ID | Class Name | RGB Color | Hex | Layer Precedence |
| :---: | :--- | :---: | :---: | :---: |
| **0** | **Background** | `[0, 0, 0]` | `#000000` | Base canvas (unclassified landscape) |
| **3** | **Water / River** | `[0, 130, 200]` | `#0082C8` | Burned 1st (underneath bridges) |
| **2** | **Road / Alignment** | `[60, 180, 75]` | `#3CB44B` | Burned 2nd (crosses over water) |
| **1** | **Building** | `[230, 25, 75]` | `#E6194B` | Burned 3rd (crisp footprint, no road overlap) |

---

## 🧪 Key Findings & Lessons Learned

During the validation of the $26.14\text{ km}$ State Highway 5 (SH5) corridor in Purba Medinipur, West Bengal:

1. **Why VLMs Report 0% Primary Road on Road Tiles:**
   * In a $256 \times 256$ aerial tile at Zoom 17, a 2-lane road occupies only $\approx 2.8\%$ of the pixels. The remaining $97.2\%$ is agricultural land or waterlogged terrain.
   * Whole-image classification models categorize the macro-scene (e.g. `agricultural_land` or `water`), rather than the thin road stroke.
2. **Deltaic Landscape Reflectance:**
   * In coastal West Bengal, flooded paddy fields and aquaculture ponds (*bheris*) visually reflect light similarly to rivers. Compact general-domain VLMs frequently tag these as `river` ($89\%$ probability).
3. **The Necessity of SegFormer / UNet++:**
   * Dense semantic segmentation solves this by classifying **every individual pixel** ($65,536$ predictions per tile), cleanly isolating the thin road ribbon and ditch boundaries from the surrounding $97\%$ farmland.

---

## 🚀 Quickstart Guide

### 1. Installation

Using `uv` (recommended) or standard `pip`:

```bash
# Clone the repository
git clone https://github.com/jsscoder/TILE_MAPPER_SEG_FG.git
cd TILE_MAPPER_SEG_FG

# Create virtual environment
uv venv my_env
source my_env/bin/activate  # On Windows: .\my_env\Scripts\activate

# Install geospatial & ML dependencies
uv pip install geopandas rasterio mercantile shapely pillow numpy tqdm pyproj python-dotenv cactus-compute
```

### 2. Configure Environment

Copy `.env.example` to `.env` and set your Cactus Compute API key:

```bash
cp .env.example .env
```

### 3. Running the Pipeline

```bash
# Step 1: Extract assets from OSM PBF
python tiler.py

# Step 2: Harvest corridor satellite tiles and rasterize ground truth masks
python export_corridor_tiles.py

# Step 3: Run Mirage VLM multi-label bifurcation
python bifurcate_tiles_mirage.py
```

---

## 📜 License

This project is licensed under the Apache 2.0 License.
