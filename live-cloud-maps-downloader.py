import requests
import os
from datetime import datetime

# The EXACT 8K maps available from Matteason's repository
MAPS = {
    "earth_day": "https://clouds.matteason.co.uk/images/8192x4096/earth.jpg",
    "clouds": "https://clouds.matteason.co.uk/images/8192x4096/clouds.jpg",
    "clouds_alpha": "https://clouds.matteason.co.uk/images/8192x4096/clouds-alpha.png",
    "earth_night": "https://clouds.matteason.co.uk/images/8192x4096/earth-night.jpg",
    "specular": "https://clouds.matteason.co.uk/images/8192x4096/specular.jpg"
}

BASE_FOLDER = "downloads"

def get_timestamp():
    # In CI the workflow pre-computes a rounded timestamp and injects it as an
    # env var so that filenames and the release tag are guaranteed to match.
    # When running locally we compute it here using the same rounding logic.
    env_ts = os.environ.get("ROUNDED_TIMESTAMP")
    if env_ts:
        return env_ts
    now = datetime.now()
    rounded_hour = (now.hour // 3) * 3
    return now.strftime("%Y%m%d") + f"_{rounded_hour:02d}00"

def download_maps():
    # Use a consistent timestamp for all maps in this run
    timestamp = get_timestamp()
    print(f"--- Starting Download Run: {timestamp} ---")

    for map_name, url in MAPS.items():
        # Create a dedicated folder for EACH map type (Great for 3D Image Sequences)
        map_folder = os.path.join(BASE_FOLDER, map_name)
        os.makedirs(map_folder, exist_ok=True)

        # Determine file extension and create the path
        ext = "png" if url.endswith(".png") else "jpg"
        filename = f"{map_name}_{timestamp}.{ext}"
        filepath = os.path.join(map_folder, filename)

        try:
            print(f"Downloading {map_name}...")
            response = requests.get(url, timeout=120, stream=True)

            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"DONE: Saved to {filepath}")
            else:
                print(f"FAILED: {map_name} (Status: {response.status_code})")
        except Exception as e:
            print(f"ERROR downloading {map_name}: {e}")

if __name__ == "__main__":
    download_maps()
