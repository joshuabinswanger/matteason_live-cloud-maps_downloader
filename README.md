# Live Cloud Maps Downloader

[![8K Cloud Map Harvester](https://github.com/joshuabinswanger/matteason_live-cloud-maps_downloader/actions/workflows/daily-harvest.yml/badge.svg)](https://github.com/joshuabinswanger/matteason_live-cloud-maps_downloader/actions/workflows/daily-harvest.yml)

An automated harvester that downloads live 8K Earth texture maps from [matteason's Live Cloud Maps](https://github.com/matteason/live-cloud-maps) service and publishes them as timestamped GitHub Releases every 3 hours.

## Source

All map images are served by **Matt Eason's** live cloud maps project:

- **Website:** https://clouds.matteason.co.uk
- **Original repo:** https://github.com/matteason/live-cloud-maps

Matt's service provides real-time composite Earth textures updated regularly from satellite imagery.

> **Note for forks:** This workflow hits Matt's server every 3 hours. If you fork this repo, please consider whether that frequency is appropriate and be mindful of the load placed on a free community service.

## What Gets Downloaded

Five 8192×4096 (8K) map images are downloaded on each run:

| Map Name       | File               | Description                                               |
| -------------- | ------------------ | --------------------------------------------------------- |
| `earth_day`    | `earth.jpg`        | Full-colour dayside Earth surface with live cloud overlay |
| `clouds`       | `clouds.jpg`       | Cloud layer only (white clouds on black background)       |
| `clouds_alpha` | `clouds-alpha.png` | Cloud layer as a PNG with transparency (alpha channel)    |
| `earth_night`  | `earth-night.jpg`  | Nightside Earth showing city lights                       |
| `specular`     | `specular.jpg`     | Specular/water mask map for 3D shading                    |

## File Naming & Folder Structure

Each download run uses a single consistent timestamp (`YYYYMMDD_HHMM`) applied to all files in that batch, so every set of maps from the same moment shares the same timestamp.

Files are saved into per-map subfolders under `downloads/`:

```
downloads/
├── earth_day/
│   └── earth_day_20260310_1200.jpg
├── clouds/
│   └── clouds_20260310_1200.jpg
├── clouds_alpha/
│   └── clouds_alpha_20260310_1200.png
├── earth_night/
│   └── earth_night_20260310_1200.jpg
└── specular/
    └── specular_20260310_1200.jpg
```

The per-map subfolder structure makes these downloads ideal for use as **image sequences** in 3D software (Blender, Cinema 4D, etc.) — point your texture node at the folder and step through frames chronologically.

## Automation

A GitHub Actions workflow ([daily-harvest.yml](.github/workflows/daily-harvest.yml)) runs every 3 hours via cron and also supports manual triggering. After each download it creates a new **GitHub Release** tagged `maps-YYYYMMDD_HHMM` containing all five map files as release assets.

## Running Locally

```bash
pip install -r requirements.txt
python live-cloud-maps-downloader.py
```

Downloaded files will appear in a `downloads/` folder in the working directory. This folder is excluded from git via `.gitignore` — distribution is handled through GitHub Releases.

## License

See [LICENSE](LICENSE).

This repo was created with the help of AI.
