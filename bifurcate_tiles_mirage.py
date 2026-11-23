import os
import json
import csv
import glob
from PIL import Image
import numpy as np

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import cactus

# --- CONFIGURATION ---
INPUT_IMAGES_DIR = "dataset_corridor/images"
OUTPUT_BIFURCATED_DIR = "dataset_corridor/bifurcated"
MANIFEST_JSON = "dataset_corridor/bifurcation_manifest.json"
MANIFEST_CSV = "dataset_corridor/bifurcation_manifest.csv"

# Classification Schema for Mirage VLM
AERIAL_FORM = {
    "primary_class": {
        "enum": ["road", "drain", "canal", "river", "buildings", "agricultural_land"]
    },
    "has_road": {"enum": ["yes", "no"]},
    "has_drain": {"enum": ["yes", "no"]},
    "has_canal": {"enum": ["yes", "no"]},
    "has_river": {"enum": ["yes", "no"]},
    "has_water": {"enum": ["yes", "no"]}
}
# ---------------------

def setup_directories():
    classes = ["road", "drain", "canal", "river", "buildings", "background", "mixed"]
    for c in classes:
        os.makedirs(os.path.join(OUTPUT_BIFURCATED_DIR, c), exist_ok=True)

def bifurcate_tiles():
    setup_directories()
    
    print("Initializing Cactus Mirage VLM...")
    vision = cactus.Mirage()
    
    # Locate all tile images
    images = glob.glob(os.path.join(INPUT_IMAGES_DIR, "*.jpg")) + glob.glob(os.path.join(INPUT_IMAGES_DIR, "*.png"))
    print(f"Found {len(images)} satellite tiles in '{INPUT_IMAGES_DIR}'.")
    
    if not images:
        print(f"No images found in {INPUT_IMAGES_DIR}. Please run export_corridor_tiles.py first!")
        return

    manifest = []
    
    for idx, img_path in enumerate(images):
        tile_name = os.path.splitext(os.path.basename(img_path))[0]
        
        try:
            # 1. Run Mirage extraction
            res = vision.extract(img_path, AERIAL_FORM)
            form_res = res.get("form", {})
            
            # Extract probabilities
            p_class_obj = form_res.get("primary_class", {})
            probs = p_class_obj.get("probabilities", {})
            
            # Find highest non-null category
            best_cat = "background"
            best_prob = 0.0
            for cat, prob in probs.items():
                if cat != "-" and prob > best_prob:
                    best_prob = prob
                    best_cat = cat

            has_road = form_res.get("has_road", {}).get("probabilities", {}).get("yes", 0.0)
            has_water = form_res.get("has_water", {}).get("probabilities", {}).get("yes", 0.0)
            has_drain = form_res.get("has_drain", {}).get("probabilities", {}).get("yes", 0.0)
            has_canal = form_res.get("has_canal", {}).get("probabilities", {}).get("yes", 0.0)
            has_river = form_res.get("has_river", {}).get("probabilities", {}).get("yes", 0.0)
            
            record = {
                "tile_id": tile_name,
                "image_path": img_path,
                "predicted_primary": best_cat,
                "confidence": round(best_prob, 4),
                "prob_road": round(has_road, 4),
                "prob_water": round(has_water, 4),
                "prob_drain": round(has_drain, 4),
                "prob_canal": round(has_canal, 4),
                "prob_river": round(has_river, 4)
            }
            manifest.append(record)
            
            # Destination category
            dest_dir = os.path.join(OUTPUT_BIFURCATED_DIR, best_cat if best_cat in ["road", "drain", "canal", "river", "buildings"] else "background")
            
            # Copy / symlink or note path
            with open(os.path.join(dest_dir, f"{tile_name}.txt"), "w") as f:
                json.dump(record, f, indent=2)

            if (idx + 1) % 10 == 0 or (idx + 1) == len(images):
                print(f"[{idx + 1}/{len(images)}] Processed {tile_name} -> {best_cat} ({best_prob:.2%})")

        except Exception as e:
            print(f"Error processing {tile_name}: {e}")

    # Save manifest
    with open(MANIFEST_JSON, "w") as f:
        json.dump(manifest, f, indent=2)

    with open(MANIFEST_CSV, "w", newline="") as f:
        if manifest:
            writer = csv.DictWriter(f, fieldnames=manifest[0].keys())
            writer.writeheader()
            writer.writerows(manifest)

    print(f"\nBifurcation complete! Manifests saved to:")
    print(f"  JSON: {MANIFEST_JSON}")
    print(f"  CSV:  {MANIFEST_CSV}")

if __name__ == "__main__":
    bifurcate_tiles()
