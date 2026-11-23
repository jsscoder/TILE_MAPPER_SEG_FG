import os
import json
import csv
import glob
import shutil
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

import cactus

# --- CONFIGURATION ---
INPUT_IMAGES_DIR = "dataset_corridor_4k/images"
INPUT_MASKS_DIR = "dataset_corridor_4k/masks"
OUTPUT_BIFURCATED_DIR = "dataset_corridor_4k/bifurcated"
TEMP_PATCH_DIR = "dataset_corridor_4k/.tmp_vlm_patches"
MANIFEST_JSON = "dataset_corridor_4k/bifurcation_manifest.json"
MANIFEST_CSV = "dataset_corridor_4k/bifurcation_manifest.csv"

PATCH_SIZE = 512           # VLM native resolution so narrow canals/drains stay sharp
PRESENCE_THRESHOLD = 0.60  # Confidence threshold to flag multi-feature "mixed" corridors
FILE_ACTION = "copy"       # Use "move" instead of "copy" if you want to save disk space

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
        os.makedirs(os.path.join(OUTPUT_BIFURCATED_DIR, c, "images"), exist_ok=True)
        os.makedirs(os.path.join(OUTPUT_BIFURCATED_DIR, c, "masks"), exist_ok=True)
    os.makedirs(TEMP_PATCH_DIR, exist_ok=True)

def extract_patches_if_needed(img_path, tile_name):
    """Slices 4K (4096x4096) images into 512x512 patches for accurate VLM inspection."""
    with Image.open(img_path) as img:
        w, h = img.size
        if w <= PATCH_SIZE and h <= PATCH_SIZE:
            return [img_path], False

        patch_paths = []
        for y in range(0, h, PATCH_SIZE):
            for x in range(0, w, PATCH_SIZE):
                crop = img.crop((x, y, min(x + PATCH_SIZE, w), min(y + PATCH_SIZE, h)))
                p_path = os.path.join(TEMP_PATCH_DIR, f"{tile_name}_{x}_{y}.jpg")
                crop.save(p_path, quality=90)
                patch_paths.append(p_path)
        return patch_paths, True

def analyze_single_image(vision, image_path):
    """Runs Cactus Mirage extraction on a single patch/tile."""
    res = vision.extract(image_path, AERIAL_FORM)
    form_res = res.get("form", {})

    p_class_obj = form_res.get("primary_class", {})
    probs = p_class_obj.get("probabilities", {})

    best_cat = "background"
    best_prob = 0.0
    for cat, prob in probs.items():
        if cat != "-" and prob > best_prob:
            best_prob = prob
            best_cat = cat

    return {
        "primary": best_cat,
        "confidence": best_prob,
        "road": form_res.get("has_road", {}).get("probabilities", {}).get("yes", 0.0),
        "water": form_res.get("has_water", {}).get("probabilities", {}).get("yes", 0.0),
        "drain": form_res.get("has_drain", {}).get("probabilities", {}).get("yes", 0.0),
        "canal": form_res.get("has_canal", {}).get("probabilities", {}).get("yes", 0.0),
        "river": form_res.get("has_river", {}).get("probabilities", {}).get("yes", 0.0),
    }

def route_file(src_path, dst_path, action="copy"):
    if not os.path.exists(src_path):
        return
    if action == "move":
        shutil.move(src_path, dst_path)
    else:
        shutil.copy2(src_path, dst_path)

def bifurcate_tiles():
    setup_directories()

    print("Initializing Cactus Mirage VLM...")
    vision = cactus.Mirage()

    images = sorted(
        glob.glob(os.path.join(INPUT_IMAGES_DIR, "*.jpg")) +
        glob.glob(os.path.join(INPUT_IMAGES_DIR, "*.png"))
    )
    print(f"Found {len(images)} tiles in '{INPUT_IMAGES_DIR}'.")

    if not images:
        print(f"No images found in {INPUT_IMAGES_DIR}.")
        return

    manifest = []

    for idx, img_path in enumerate(images):
        tile_name = os.path.splitext(os.path.basename(img_path))[0]
        mask_path = os.path.join(INPUT_MASKS_DIR, f"{tile_name}.png")

        try:
            patches, is_tiled = extract_patches_if_needed(img_path, tile_name)
            patch_results = [analyze_single_image(vision, p) for p in patches]

            if is_tiled:
                for p in patches:
                    if os.path.exists(p):
                        os.remove(p)

            max_road = max(r["road"] for r in patch_results)
            max_water = max(r["water"] for r in patch_results)
            max_drain = max(r["drain"] for r in patch_results)
            max_canal = max(r["canal"] for r in patch_results)
            max_river = max(r["river"] for r in patch_results)

            best_patch = max(
                patch_results,
                key=lambda r: r["confidence"] if r["primary"] != "agricultural_land" else r["confidence"] * 0.8
            )
            best_cat = best_patch["primary"]
            best_prob = best_patch["confidence"]

            detected_features = [
                feat for feat, score in [
                    ("road", max_road),
                    ("drain", max_drain),
                    ("canal", max_canal),
                    ("river", max_river)
                ] if score >= PRESENCE_THRESHOLD
            ]

            if len(detected_features) >= 2:
                final_folder = "mixed"
            elif best_cat in ["road", "drain", "canal", "river", "buildings"]:
                final_folder = best_cat
            else:
                final_folder = "background"

            dest_img_path = os.path.join(OUTPUT_BIFURCATED_DIR, final_folder, "images", os.path.basename(img_path))
            dest_mask_path = os.path.join(OUTPUT_BIFURCATED_DIR, final_folder, "masks", os.path.basename(mask_path))

            # Save actual image and mask files into the bifurcated folder
            route_file(img_path, dest_img_path, action=FILE_ACTION)
            route_file(mask_path, dest_mask_path, action=FILE_ACTION)

            record = {
                "tile_id": tile_name,
                "assigned_folder": final_folder,
                "saved_image_path": dest_img_path,
                "saved_mask_path": dest_mask_path if os.path.exists(dest_mask_path) else "",
                "predicted_primary": best_cat,
                "detected_features": "|".join(detected_features) if detected_features else "none",
                "confidence": round(best_prob, 4),
                "prob_road": round(max_road, 4),
                "prob_water": round(max_water, 4),
                "prob_drain": round(max_drain, 4),
                "prob_canal": round(max_canal, 4),
                "prob_river": round(max_river, 4),
                "patches_evaluated": len(patches)
            }
            manifest.append(record)

            print(
                f"[{idx + 1}/{len(images)}] {tile_name} -> [{final_folder.upper()}] "
                f"(features: {record['detected_features']}, conf: {best_prob:.2%})"
            )

        except Exception as e:
            print(f"Error processing {tile_name}: {e}")

    if os.path.exists(TEMP_PATCH_DIR) and not os.listdir(TEMP_PATCH_DIR):
        os.rmdir(TEMP_PATCH_DIR)

    # Global summary manifests remain at root for easy tracking
    with open(MANIFEST_JSON, "w") as f:
        json.dump(manifest, f, indent=2)

    with open(MANIFEST_CSV, "w", newline="") as f:
        if manifest:
            writer = csv.DictWriter(f, fieldnames=manifest[0].keys())
            writer.writeheader()
            writer.writerows(manifest)

    print(f"\nBifurcation complete! Images & masks saved into '{OUTPUT_BIFURCATED_DIR}/<class>/'")

if __name__ == "__main__":
    bifurcate_tiles()
