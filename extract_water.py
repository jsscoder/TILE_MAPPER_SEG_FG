import osmium
import shapely.wkb as wkblib
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon

# --- CONFIGURATION ---
PBF_FILE = r"C:\Users\pc\Downloads\india-261118.osm.pbf"
BBOX = (77.28, 28.10, 77.72, 28.66)

OUT_WATER_AREAS = "noida_water_areas.shp"
OUT_WATER_LINES = "noida_water_lines.shp"
OUT_WATER_COMBINED = "noida_water.shp"
# ---------------------

wkbfab = osmium.geom.WKBFactory()

class WaterExtractor(osmium.SimpleHandler):
    def __init__(self, bbox):
        super().__init__()
        self.min_lon, self.min_lat, self.max_lon, self.max_lat = bbox
        self.water_areas = []
        self.water_lines = []

    def _in_bbox(self, geom):
        minx, miny, maxx, maxy = geom.bounds
        return not (maxx < self.min_lon or minx > self.max_lon or 
                    maxy < self.min_lat or miny > self.max_lat)

    def area(self, a):
        # Extract polygonal water features: natural=water, water=*, waterway=riverbank/dock, landuse=basin/reservoir
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
                    water_type = a.tags.get("water", a.tags.get("natural", a.tags.get("waterway", a.tags.get("landuse", "water"))))
                    self.water_areas.append({
                        "osm_id": a.id,
                        "type": str(water_type)[:20],
                        "geometry": geom
                    })
            except Exception:
                pass

    def way(self, w):
        # Extract linear water features: waterway=river, stream, canal, drain, ditch
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
    print(f"Scanning {PBF_FILE} for Noida water bodies...")
    handler = WaterExtractor(BBOX)
    handler.apply_file(PBF_FILE, locations=True)

    print(f"Found {len(handler.water_areas)} water area polygons and {len(handler.water_lines)} waterway lines.")

    # 1. Save water areas (polygons)
    gdf_areas = None
    if handler.water_areas:
        gdf_areas = gpd.GeoDataFrame(handler.water_areas, crs="EPSG:4326")
        gdf_areas.to_file(OUT_WATER_AREAS)
        print(f"Saved area polygons -> {OUT_WATER_AREAS}")

    # 2. Save waterway lines (linestrings)
    gdf_lines = None
    if handler.water_lines:
        gdf_lines = gpd.GeoDataFrame(handler.water_lines, crs="EPSG:4326")
        gdf_lines.to_file(OUT_WATER_LINES)
        print(f"Saved waterway lines -> {OUT_WATER_LINES}")

    # 3. Create a unified polygon layer (buffering lines appropriately so all water can be rasterized as polygons)
    print("Generating unified buffered water polygon layer...")
    polygons_list = []
    if gdf_areas is not None and not gdf_areas.empty:
        polygons_list.append(gdf_areas[["geometry", "type"]])

    if gdf_lines is not None and not gdf_lines.empty:
        # Reproject lines to EPSG:3857 to buffer in meters, then project back to EPSG:4326
        lines_3857 = gdf_lines.to_crs("EPSG:3857").copy()
        
        # Buffer based on waterway type: major rivers/canals ~10m, smaller streams/drains ~4m
        def get_buffer_width(ww_type):
            if ww_type in ("river", "canal"):
                return 10.0  # meters radius
            return 4.0      # meters radius
        
        lines_3857["geometry"] = [
            geom.buffer(get_buffer_width(t)) 
            for geom, t in zip(lines_3857.geometry, lines_3857["type"])
        ]
        buffered_lines = lines_3857.to_crs("EPSG:4326")
        polygons_list.append(buffered_lines[["geometry", "type"]])

    if polygons_list:
        unified_gdf = gpd.pd.concat(polygons_list, ignore_index=True)
        unified_gdf = gpd.GeoDataFrame(unified_gdf, crs="EPSG:4326")
        unified_gdf.to_file(OUT_WATER_COMBINED)
        print(f"Saved unified water polygon layer -> {OUT_WATER_COMBINED}")

    print("Water extraction complete!")
