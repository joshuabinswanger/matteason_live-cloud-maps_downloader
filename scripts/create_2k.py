from PIL import Image
import os

DOWNLOADS_FOLDER = "downloads"
OUTPUT_FOLDER = "downloads_2k"
TARGET_SIZE = (2048, 1024)  # width x height, matches 8K source aspect ratio (2:1)

MAP_TYPES = [
    "earth_day",
    "clouds_alpha",
    "clouds",
    "earth_night",
    "specular",
]

def create_2k():
    for map_type in MAP_TYPES:
        src_folder = os.path.join(DOWNLOADS_FOLDER, map_type)
        dst_folder = os.path.join(OUTPUT_FOLDER, map_type)

        if not os.path.isdir(src_folder):
            print(f"Skipping {map_type} (folder not found)")
            continue

        os.makedirs(dst_folder, exist_ok=True)

        files = sorted([f for f in os.listdir(src_folder)
                        if os.path.isfile(os.path.join(src_folder, f))])

        for filename in files:
            src_path = os.path.join(src_folder, filename)
            dst_path = os.path.join(dst_folder, filename)

            with Image.open(src_path) as img:
                resized = img.resize(TARGET_SIZE, Image.LANCZOS)
                ext = os.path.splitext(filename)[1].lower()
                if ext in (".jpg", ".jpeg"):
                    resized.save(dst_path, "JPEG", quality=85, optimize=True)
                elif ext == ".png":
                    resized.save(dst_path, "PNG", optimize=True, compress_level=6)

            print(f"Resized: {map_type}/{filename}")

if __name__ == "__main__":
    create_2k()
    print("Done.")
