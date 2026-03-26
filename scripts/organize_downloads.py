import os
import shutil

DOWNLOADS_FOLDER = "downloads"

MAP_TYPES = [
    "earth_day",
    "clouds_alpha",  # check clouds_alpha before clouds to avoid prefix clash
    "clouds",
    "earth_night",
    "specular",
]

def organize():
    files = [f for f in os.listdir(DOWNLOADS_FOLDER)
             if os.path.isfile(os.path.join(DOWNLOADS_FOLDER, f))]

    for filename in files:
        for map_type in MAP_TYPES:
            if filename.startswith(map_type + "_"):
                dest_folder = os.path.join(DOWNLOADS_FOLDER, map_type)
                os.makedirs(dest_folder, exist_ok=True)
                src = os.path.join(DOWNLOADS_FOLDER, filename)
                dst = os.path.join(dest_folder, filename)
                shutil.move(src, dst)
                print(f"Moved: {filename} -> {map_type}/")
                break
        else:
            print(f"Skipped (no matching map type): {filename}")

def add_frame_numbers():
    for map_type in MAP_TYPES:
        folder = os.path.join(DOWNLOADS_FOLDER, map_type)
        if not os.path.isdir(folder):
            continue

        files = sorted([f for f in os.listdir(folder)
                        if os.path.isfile(os.path.join(folder, f))])

        for i, filename in enumerate(files, start=1):
            name, ext = os.path.splitext(filename)
            new_filename = f"{name}_{i:04d}{ext}"
            src = os.path.join(folder, filename)
            dst = os.path.join(folder, new_filename)
            os.rename(src, dst)
            print(f"Renamed: {filename} -> {new_filename}")

if __name__ == "__main__":
    organize()
    add_frame_numbers()
    print("Done.")
