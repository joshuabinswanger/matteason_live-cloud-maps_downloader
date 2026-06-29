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

Two GitHub Actions workflows run the pipeline. Both are **triggered externally**
(e.g. from a Synology / Windows scheduled task) rather than by GitHub's built-in
`schedule:` cron, which is unreliable — it frequently runs late or silently skips
runs under load. Your own scheduler fires each workflow on its own clock:

```
your scheduler ─ every 6 h ─► dispatch  daily-harvest   ─► download 8K → per-run Release
               └ weekly    ─► dispatch  weekly-archive  ─► encode the week into one tiny archive
```

Dispatch with the GitHub CLI:

```bash
gh workflow run daily-harvest.yml  --repo joshuabinswanger/matteason_live-cloud-maps_downloader --ref main
gh workflow run weekly-archive.yml --repo joshuabinswanger/matteason_live-cloud-maps_downloader --ref main
```

…or with `curl` and a fine-grained PAT (no `gh` install needed on the NAS):

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/joshuabinswanger/matteason_live-cloud-maps_downloader/actions/workflows/weekly-archive.yml/dispatches \
  -d '{"ref":"main"}'
```

### Harvest — [daily-harvest.yml](.github/workflows/daily-harvest.yml)

Downloads the five 8K maps and publishes them as a **GitHub Release** tagged
`maps-YYYYMMDD_HHMM`, with all files as release assets. Run this on whatever
cadence you want frames at (every 6 h ≈ 28 frames/week).

### Weekly archive — [weekly-archive.yml](.github/workflows/weekly-archive.yml)

Consolidates a period's harvest releases into one compact archive. It pulls the
`maps-*` releases from the last `days` (default 7), then runs
[scripts/encode_archive.py](scripts/encode_archive.py) to produce, **per map type**:

| Output | Format | Purpose |
| ------ | ------ | ------- |
| `<map>_8K_<week>.mp4` | HEVC, `yuv444p`, CRF 20 (visually near-lossless) | Full-res 8K master archive |
| `clouds_alpha_8K_<week>_color.mp4` + `_mask.mp4` | Two grayscale HEVC streams (CRF 20 / CRF 14) | 8K cloud-colour layer + alpha mask, recombined on extraction |
| `<map>_2K_<week>.zip` | 2048×1024 JPEG q90 / PNG | Lightweight working textures |
| `manifest_<week>.csv` | CSV | Maps every video frame index → original timestamp |

These are published as a single Release tagged `archive-YYYY-WW`. Pass
`cleanup: true` to delete the per-run harvest releases once they've been folded
into the archive. The codec settings are overridable via env vars
(`X265_CRF`, `X265_PRESET`, `ALPHA_COLOR_CRF`, `ALPHA_MASK_CRF`).

**Why a video for the 8K master?** Two reasons: a video codec exploits the
temporal redundancy between near-identical consecutive frames, and it
consolidates a week of files into one. The size win depends heavily on the map —
on real harvested data, the busy full-colour maps land around **2×** smaller at
CRF 20, while simpler maps (night lights, cloud mask) go further. The bigger
practical benefit is having one tidy file per map plus the small 2K working
copies, instead of dozens of loose 8K stills. Extract any frame back out with
ffmpeg:

```bash
ffmpeg -i earth_day_8K_2026-W26.mp4 -vf "select=eq(n\,FRAME)" -vframes 1 earth_day.png
```

For `clouds_alpha`, recombine the colour and mask streams back into an RGBA PNG:

```bash
ffmpeg -i clouds_alpha_8K_2026-W26_color.mp4 -i clouds_alpha_8K_2026-W26_mask.mp4 \
  -filter_complex "[0:v]select=eq(n\,FRAME),format=gbrp[c];[1:v]select=eq(n\,FRAME)[m];[c][m]alphamerge,format=rgba" \
  -frames:v 1 clouds_alpha.png
```

## Running Locally

```bash
pip install -r requirements.txt
python live-cloud-maps-downloader.py
```

Downloaded files will appear in a `downloads/` folder in the working directory. This folder is excluded from git via `.gitignore` — distribution is handled through GitHub Releases.

### Archiving a local `downloads/` folder

`encode_archive.py` accepts the nested per-map `downloads/<map>/` tree directly
(not just the flat layout CI stages), so you can fold a local collection into
the same archive format without going through GitHub Releases:

```bash
# downloads/<map>/*  ->  out/<map>_8K_<label>.mp4 + _2K_<label>.zip + manifest
python scripts/encode_archive.py downloads archive_out my-label
```

Reverse it with `extract_archive.py` to get the 8K frames back (original
filenames restored from the manifest):

```bash
python scripts/extract_archive.py archive_out restored          # all maps
python scripts/extract_archive.py archive_out restored --maps earth_night
python scripts/extract_archive.py archive_out restored --frame 0
```

(`downloads_2k/` is already 2K, so it doesn't need video archiving — the
archive's `*_2K_*.zip` files are the equivalent working copies.)

## License

See [LICENSE](LICENSE).

This repo was created with the help of AI.
