import osmium
import shapely.wkb as wkblib
import geopandas as gpd

# --- CONFIGURATION ---
PBF_FILE = r"C:\Users\pc\Downloads\india-261118.osm.pbf"

# Bounding box: (min_lon, min_lat, max_lon, max_lat)
# Default: Noida / Gautam Buddha Nagar (Change to (76.83, 28.40, 77.35, 28.89) for Delhi)
BBOX = (77.28, 28.10, 77.72, 28.66)

OUT_BUILDINGS = "noida_buildings.shp"
OUT_ROADS = "noida_roads.shp"
OUT_WATER_AREAS = "noida_water_areas.shp"
OUT_WATER_LINES = "noida_water_lines.shp"
OUT_WATER_COMBINED = "noida_water.shp"
# ---------------------

wkbfab = osmium.geom.WKBFactory()

class AssetExtractor(osmium.SimpleHandler):
    def __init__(self, bbox):
        super().__init__()
        self.min_lon, self.min_lat, self.max_lon, self.max_lat = bbox
        self.buildings = []
        self.roads = []
        self.water_areas = []
        self.water_lines = []

    def _in_bbox(self, geom):
        minx, miny, maxx, maxy = geom.bounds
        return not (maxx < self.min_lon or minx > self.max_lon or 
                    maxy < self.min_lat or miny > self.max_lat)

    def area(self, a):
        # 1. Extract building polygons
        if "building" in a.tags:
            try:
                wkb = wkbfab.create_multipolygon(a)
                geom = wkblib.loads(wkb, hex=True)
                if self._in_bbox(geom):
                    self.buildings.append({
                        "osm_id": a.id,
                        "building": a.tags.get("building", "yes"),
                        "geometry": geom
                    })
            except Exception:
                pass

        # 2. Extract polygonal water features (lakes, ponds, reservoirs, basins, riverbanks)
        is_water = (
            ("natural" in a.tags and a.tags["natural"] == "water") or
            ("water" in a.tags) or
            ("waterway" in a.tags and a.tags["waterway"] in ("riverbank", "dock", "basin", "canal")) or
            ("landuse" in a.tags and a.tags["landuse"] in ("reservoir", "basin"))
        )
        if is_water:
            try:
                wkb = wkbfab.create_multipolygon(a)
                geom = wkblib.loads(wkb, hex=True)
                if self._in_bbox(geom):
                    wtype = a.tags.get("water", a.tags.get("natural", a.tags.get("waterway", a.tags.get("landuse", "water"))))
                    self.water_areas.append({
                        "osm_id": a.id,
                        "type": str(wtype)[:20],
                        "geometry": geom
                    })
            except Exception:
                pass

    def way(self, w):
        # 1. Extract road polylines
        if "highway" in w.tags:
            try:
                wkb = wkbfab.create_linestring(w)
                geom = wkblib.loads(wkb, hex=True)
                if self._in_bbox(geom):
                    self.roads.append({
                        "osm_id": w.id,
                        "highway": w.tags.get("highway", "road"),
                        "geometry": geom
                    })
            except Exception:
                pass

        # 2. Extract linear waterway polylines (rivers, canals, streams, drains)
        if "waterway" in w.tags:
            ww_type = w.tags["waterway"]
            if ww_type not in ("riverbank", "dock"):  # Areas handled in area()
                try:
                    wkb = wkbfab.create_linestring(w)
                    geom = wkblib.loads(wkb, hex=True)
                    if self._in_bbox(geom):
                        self.water_lines.append({
                            "osm_id": w.id,
                            "type": str(ww_type)[:20],
                            "geometry": geom
                        })
                except Exception:
                    pass

if __name__ == "__main__":
    print(f"Scanning {PBF_FILE} for Noida assets (buildings, roads, water)...")
    handler = AssetExtractor(BBOX)
    # locations=True resolves node coordinates for ways and areas automatically
    handler.apply_file(PBF_FILE, locations=True)

    print(f"Found {len(handler.buildings)} buildings, {len(handler.roads)} roads, "
          f"{len(handler.water_areas)} water areas, and {len(handler.water_lines)} waterways.")

    # Save Buildings
    if handler.buildings:
        gdf_b = gpd.GeoDataFrame(handler.buildings, crs="EPSG:4326")
        gdf_b.to_file(OUT_BUILDINGS)
        print(f"Saved -> {OUT_BUILDINGS}")

    # Save Roads
    if handler.roads:
        gdf_r = gpd.GeoDataFrame(handler.roads, crs="EPSG:4326")
        gdf_r.to_file(OUT_ROADS)
        print(f"Saved -> {OUT_ROADS}")

    # Save Water Areas
    gdf_wa = None
    if handler.water_areas:
        gdf_wa = gpd.GeoDataFrame(handler.water_areas, crs="EPSG:4326")
        gdf_wa.to_file(OUT_WATER_AREAS)
        print(f"Saved -> {OUT_WATER_AREAS}")

    # Save Water Lines
    gdf_wl = None
    if handler.water_lines:
        gdf_wl = gpd.GeoDataFrame(handler.water_lines, crs="EPSG:4326")
        gdf_wl.to_file(OUT_WATER_LINES)
        print(f"Saved -> {OUT_WATER_LINES}")

    # Save Unified Buffered Water Polygon Layer
    polygons_list = []
    if gdf_wa is not None and not gdf_wa.empty:
        polygons_list.append(gdf_wa[["geometry", "type"]])

    if gdf_wl is not None and not gdf_wl.empty:
        wl_3857 = gdf_wl.to_crs("EPSG:3857").copy()
        def get_buf(ww):
            return 10.0 if ww in ("river", "canal") else 4.0
        wl_3857["geometry"] = [geom.buffer(get_buf(t)) for geom, t in zip(wl_3857.geometry, wl_3857["type"])]
        polygons_list.append(wl_3857.to_crs("EPSG:4326")[["geometry", "type"]])

    if polygons_list:
        unified_gdf = gpd.pd.concat(polygons_list, ignore_index=True)
        unified_gdf = gpd.GeoDataFrame(unified_gdf, crs="EPSG:4326")
        unified_gdf.to_file(OUT_WATER_COMBINED)
        print(f"Saved -> {OUT_WATER_COMBINED}")
